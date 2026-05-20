#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline


DEFAULT_FIXTURE_ID = "agentic-lora-sft-smoke.dev.v1"


def run_smoke(
    repo_root: Path,
    *,
    output_dir: Path | None = None,
    fixture_id: str = DEFAULT_FIXTURE_ID,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    fixture_dir = repo_root / "services" / "mlx-worker-python" / "fixtures" / "training" / fixture_id
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"Agentic LoRA SFT smoke fixture does not exist: {fixture_dir}")

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="melix-agentic-lora-sft-smoke-"))
    else:
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    base_model_dir = output_dir / "base-model"
    base_model_dir.mkdir(parents=True, exist_ok=True)

    source_model = common_pb2.ModelSpec(
        model_id="agentic-lora-sft-smoke-model",
        model_path=str(base_model_dir),
        revision="fixture-v1",
        model_kind="text",
        max_context=2048,
        ext={
            "text_family_id": "llama",
            "text_layer_count": "1",
        },
    )

    train_output_dir = output_dir / "train"
    jobs_root = output_dir / "jobs"
    started = time.perf_counter()
    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="agentic-lora-sft-smoke",
        request_ext={
            "operation": "train_lora",
            "training_mode": "lora",
            "training_objective": "agentic_sft",
            "adapter_name": "agentic-lora-sft-smoke",
            "dataset_uri": str(fixture_dir),
            "batch_size": "1",
            "epochs": "1",
            "max_steps": "1",
            "num_layers": "1",
            "target_modules": "q_proj",
            "response_only": "true",
            "mask_prompt": "true",
        },
        source_model=source_model,
        output_dir=train_output_dir,
        jobs_root=jobs_root,
    )
    duration_ms = (time.perf_counter() - started) * 1000.0

    adapter_manifest = result.manifest
    normalized_manifest_path = Path(adapter_manifest["normalized_dataset_manifest_path"])
    normalized_manifest = json.loads(normalized_manifest_path.read_text(encoding="utf-8"))
    normalized_dir = normalized_manifest_path.parent
    train_rows = _read_jsonl(normalized_dir / "train.jsonl")
    valid_rows = _read_jsonl(normalized_dir / "valid.jsonl")
    source_train_rows = _read_jsonl(normalized_dir / "agentic-traces.train.jsonl")
    source_valid_rows = _read_jsonl(normalized_dir / "agentic-traces.valid.jsonl")

    projection_metrics = dict(normalized_manifest.get("agentic_sft_projection_metrics", {}))
    token_metrics = dict(normalized_manifest.get("agentic_sft_token_metrics", {}))
    quality_metrics = dict(normalized_manifest.get("trajectory_quality_metrics", {}))

    checks = {
        "adapter_manifest_exists": result.manifest_path.is_file(),
        "normalized_manifest_exists": normalized_manifest_path.is_file(),
        "train_jsonl_exists": (normalized_dir / "train.jsonl").is_file(),
        "valid_jsonl_exists": (normalized_dir / "valid.jsonl").is_file(),
        "agentic_traces_train_exists": (normalized_dir / "agentic-traces.train.jsonl").is_file(),
        "agentic_traces_valid_exists": (normalized_dir / "agentic-traces.valid.jsonl").is_file(),
        "agentic_training_objective": adapter_manifest.get("training_objective") == "agentic_sft",
        "agentic_dataset_contract": adapter_manifest.get("dataset_contract") == "agentic_tool_trace",
        "trainer_chat_messages": adapter_manifest.get("trainer_dataset_format") == "chat_messages",
        "response_only_enabled": adapter_manifest.get("response_only") is True,
        "mask_prompt_enabled": adapter_manifest.get("mask_prompt") is True,
        "projection_boundaries_match_rows": int(
            projection_metrics.get("response_only_boundary_count", 0) or 0
        )
        == len(train_rows) + len(valid_rows),
        "source_traces_preserved": len(source_train_rows) == 1 and len(source_valid_rows) == 1,
        "token_metrics_present": all(
            int(token_metrics.get(key, 0) or 0) > 0
            for key in (
                "source_trace_count",
                "trace_tokens",
                "tool_call_tokens",
                "observation_tokens",
                "final_answer_tokens",
            )
        ),
        "quality_metrics_clean": (
            int(quality_metrics.get("agentic_trace_count", 0) or 0) == 2
            and int(quality_metrics.get("dirty_count", 0) or 0) == 0
            and int(quality_metrics.get("leakage_count", 0) or 0) == 0
        ),
    }
    passed = all(checks.values())

    return {
        "passed": passed,
        "fixture_id": fixture_id,
        "output_dir": str(output_dir),
        "adapter_manifest_path": str(result.manifest_path),
        "normalized_dataset_manifest_path": str(normalized_manifest_path),
        "training_backend": adapter_manifest.get("training_backend"),
        "duration_ms": duration_ms,
        "checks": checks,
        "metrics": {
            "agentic_lora_sft_smoke.source_trace_count": float(
                normalized_manifest.get("source_trace_sample_count", 0)
            ),
            "agentic_lora_sft_smoke.source_trace_validation_sample_count": float(
                normalized_manifest.get("source_trace_validation_sample_count", 0)
            ),
            "agentic_lora_sft_smoke.trainer_row_count": float(len(train_rows)),
            "agentic_lora_sft_smoke.trainer_validation_row_count": float(len(valid_rows)),
            "agentic_lora_sft_smoke.tool_call_count": float(
                projection_metrics.get("tool_call_count", 0)
            ),
            "agentic_lora_sft_smoke.observation_count": float(
                projection_metrics.get("tool_observation_count", 0)
            ),
            "agentic_lora_sft_smoke.response_only_boundary_count": float(
                projection_metrics.get("response_only_boundary_count", 0)
            ),
            "agentic_lora_sft_smoke.trace_tokens": float(token_metrics.get("trace_tokens", 0)),
            "agentic_lora_sft_smoke.tool_call_tokens": float(
                token_metrics.get("tool_call_tokens", 0)
            ),
            "agentic_lora_sft_smoke.observation_tokens": float(
                token_metrics.get("observation_tokens", 0)
            ),
            "agentic_lora_sft_smoke.final_answer_tokens": float(
                token_metrics.get("final_answer_tokens", 0)
            ),
            "agentic_lora_sft_smoke.duration_ms": duration_ms,
        },
        "manifest": {
            "dataset_id": adapter_manifest.get("dataset_id"),
            "dataset_format": adapter_manifest.get("dataset_format"),
            "trainer_dataset_format": adapter_manifest.get("trainer_dataset_format"),
            "training_objective": adapter_manifest.get("training_objective"),
            "dataset_contract": adapter_manifest.get("dataset_contract"),
            "trajectory_dataset_id": adapter_manifest.get("trajectory_dataset_id"),
            "trajectory_trace_digest": adapter_manifest.get("trajectory_trace_digest"),
            "trajectory_provenance_field_count": adapter_manifest.get(
                "trajectory_provenance_field_count"
            ),
        },
        "projection_metrics": projection_metrics,
        "token_metrics": token_metrics,
        "quality_metrics": quality_metrics,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic agentic LoRA SFT smoke training."
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable payload.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the script parent repository.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for persisted smoke artifacts. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--fixture-id",
        default=DEFAULT_FIXTURE_ID,
        help="Training fixture id under services/mlx-worker-python/fixtures/training.",
    )
    args = parser.parse_args()

    payload = run_smoke(
        args.repo_root,
        output_dir=args.output_dir,
        fixture_id=args.fixture_id,
    )
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print("Agentic LoRA SFT smoke passed." if payload["passed"] else "Agentic LoRA SFT smoke failed.")
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
