#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = REPO_ROOT / "services" / "mlx-worker-python"
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.runtime.structured_output_constraints import (
    _compile_json_schema,
    _schema_value_satisfies_node,
    build_structured_output_logits_processors,
)


def load(*args: Any, **kwargs: Any) -> Any:
    from mlx_lm import load as mlx_lm_load

    return mlx_lm_load(*args, **kwargs)


def stream_generate(*args: Any, **kwargs: Any) -> Any:
    from mlx_lm import stream_generate as mlx_lm_stream_generate

    return mlx_lm_stream_generate(*args, **kwargs)


def make_sampler(*args: Any, **kwargs: Any) -> Any:
    from mlx_lm.sample_utils import make_sampler as mlx_lm_make_sampler

    return mlx_lm_make_sampler(*args, **kwargs)


_CONFORMANCE_FIXTURES: tuple[dict[str, object], ...] = (
    {
        "name": "const_object",
        "schema": {
            "type": "object",
            "required": ["a"],
            "additionalProperties": False,
            "properties": {"a": {"const": "x"}},
        },
        "prompt": 'Return exactly this JSON object with no surrounding text: {"a":"x"}',
    },
    {
        "name": "enum_required_optional",
        "schema": {
            "type": "object",
            "required": ["status"],
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["ok", "error"]},
                "note": {"type": "string"},
            },
        },
        "prompt": 'Return exactly this JSON object with no surrounding text: {"status":"ok"}',
    },
    {
        "name": "free_text",
        "schema": {
            "type": "object",
            "required": ["text"],
            "additionalProperties": False,
            "properties": {"text": {"type": "string"}},
        },
        "prompt": 'Return exactly this JSON object with no surrounding text: {"text":"ok"}',
    },
    {
        "name": "nested_object_array",
        "schema": {
            "type": "object",
            "required": ["a"],
            "additionalProperties": False,
            "properties": {
                "a": {
                    "type": "object",
                    "required": ["b"],
                    "additionalProperties": False,
                    "properties": {
                        "b": {
                            "type": "array",
                            "maxItems": 1,
                            "items": {"type": "integer"},
                        }
                    },
                },
            },
        },
        "prompt": (
            "Return exactly this JSON object with no surrounding text: "
            '{"a":{"b":[]}}'
        ),
    },
)
_BENCHMARK_FIXTURE = _CONFORMANCE_FIXTURES[0]


def _run_once(
    model: Any,
    tokenizer: Any,
    *,
    max_tokens: int,
    constrained: bool,
    fixture: dict[str, object] = _BENCHMARK_FIXTURE,
) -> dict[str, object]:
    schema = fixture["schema"]
    prompt = fixture["prompt"]
    if not isinstance(schema, dict) or not isinstance(prompt, str):
        raise ValueError("real-model fixture must provide an object schema and string prompt")
    execution_ext = {
        "melix.structured_output.mode": "json_schema",
        "melix.structured_output.schema_json": json.dumps(schema, separators=(",", ":")),
    }
    processors = (
        build_structured_output_logits_processors(execution_ext, tokenizer)
        if constrained
        else None
    )
    responses = list(
        stream_generate(
            model,
            tokenizer,
            prompt,
            max_tokens=max_tokens,
            sampler=make_sampler(temp=0),
            logits_processors=processors,
        )
    )
    if not responses:
        raise RuntimeError("real-model probe generated no tokens")
    final = responses[-1]
    text = "".join(response.text for response in responses)
    valid = False
    if constrained:
        try:
            parsed = json.loads(text)
            valid = _schema_value_satisfies_node(
                parsed,
                _compile_json_schema(execution_ext["melix.structured_output.schema_json"]),
            )
        except (json.JSONDecodeError, ValueError):
            valid = False
    return {
        "text": text,
        "valid": valid,
        "generation_tokens": final.generation_tokens,
        "generation_tps": final.generation_tps,
        "peak_memory_gb": final.peak_memory,
        "finish_reason": final.finish_reason or "",
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded local-model structured-output A/B probe")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3, choices=range(1, 4))
    parser.add_argument("--max-tokens", type=int, default=16, choices=range(1, 17))
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _write_report(report: dict[str, object], output: Path | None) -> None:
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")


def _model_evidence(model_path: Path) -> dict[str, object]:
    config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
    text_config = config.get("text_config")
    if not isinstance(text_config, dict):
        text_config = {}
    quantization = config.get("quantization")
    if not isinstance(quantization, dict):
        quantization = {}
    return {
        "model_type": str(config.get("model_type") or ""),
        "architectures": list(config.get("architectures") or []),
        "quantization_bits": quantization.get("bits"),
        "quantization_group_size": quantization.get("group_size"),
        "num_hidden_layers": text_config.get(
            "num_hidden_layers",
            config.get("num_hidden_layers"),
        ),
        "num_kv_shared_layers": text_config.get(
            "num_kv_shared_layers",
            config.get("num_kv_shared_layers"),
        ),
    }


def main() -> int:
    args = _parse_args()
    config_path = args.model_path / "config.json"
    if not config_path.is_file():
        raise SystemExit(f"model config not found: {config_path}")

    evidence = _model_evidence(args.model_path)
    try:
        model, tokenizer = load(str(args.model_path))
    except (OSError, RuntimeError, ValueError) as exc:
        unexpected = re.search(r"Received (\d+) parameters not in model", str(exc))
        report = {
            "schema_version": "melix.structured_output.real_model_probe.v2",
            "status": "blocked_external_runtime",
            "model_path": str(args.model_path.resolve()),
            "model_evidence": evidence,
            "error_type": type(exc).__name__,
            "error_summary": str(exc).splitlines()[0],
            "unexpected_parameter_count": int(unexpected.group(1)) if unexpected else None,
        }
        _write_report(report, args.output)
        return 2
    baseline_warmup = _run_once(model, tokenizer, max_tokens=2, constrained=False)
    constrained_warmup = _run_once(
        model,
        tokenizer,
        max_tokens=args.max_tokens,
        constrained=True,
    )

    baseline = [
        _run_once(model, tokenizer, max_tokens=args.max_tokens, constrained=False)
        for _ in range(args.iterations)
    ]
    constrained = [
        _run_once(model, tokenizer, max_tokens=args.max_tokens, constrained=True)
        for _ in range(args.iterations)
    ]
    conformance_runs = [
        {
            "fixture": str(fixture["name"]),
            **_run_once(
                model,
                tokenizer,
                max_tokens=args.max_tokens,
                constrained=True,
                fixture=fixture,
            ),
        }
        for fixture in _CONFORMANCE_FIXTURES
    ]
    baseline_tps = statistics.median(float(item["generation_tps"]) for item in baseline)
    constrained_tps = statistics.median(
        float(item["generation_tps"]) for item in constrained
    )
    report = {
        "schema_version": "melix.structured_output.real_model_probe.v2",
        "status": "measured",
        "model_path": str(args.model_path.resolve()),
        "model_evidence": evidence,
        "iterations": args.iterations,
        "max_tokens": args.max_tokens,
        "baseline_warmup": baseline_warmup,
        "constrained_warmup": constrained_warmup,
        "baseline_median_generation_tps": baseline_tps,
        "constrained_median_generation_tps": constrained_tps,
        "throughput_ratio": constrained_tps / baseline_tps if baseline_tps else 0.0,
        "constrained_invalid_output_count": sum(not bool(item["valid"]) for item in constrained),
        "conformance_fixture_count": len(conformance_runs),
        "conformance_invalid_output_count": sum(
            not bool(item["valid"]) for item in conformance_runs
        ),
        "peak_memory_gb": max(
            float(item["peak_memory_gb"])
            for item in (
                baseline_warmup,
                constrained_warmup,
                *baseline,
                *constrained,
                *conformance_runs,
            )
        ),
        "baseline_runs": baseline,
        "constrained_runs": constrained,
        "conformance_runs": conformance_runs,
    }
    _write_report(report, args.output)
    return 0 if (
        report["throughput_ratio"] >= 0.8
        and report["constrained_invalid_output_count"] == 0
        and report["conformance_invalid_output_count"] == 0
        and constrained_warmup["valid"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
