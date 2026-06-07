#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2  # noqa: E402
from worker.runtime.mlx_vlm_runtime import MLXVLMRuntime  # noqa: E402


SCHEMA_VERSION = "melix.gemma4_qat_runtime_evidence.v1"
DEFAULT_PROMPT = "Explain in two short sentences why local Apple Silicon inference benefits from quantized model assets."
DEFAULT_TARGETS: tuple[tuple[str, str], ...] = (
    (
        "mlx-community/gemma-4-E2B-it-qat-4bit",
        "mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
    ),
    (
        "mlx-community/gemma-4-E4B-it-qat-4bit",
        "mlx-community/gemma-4-E4B-it-qat-assistant-bf16",
    ),
)


@dataclass(frozen=True)
class GenerationObservation:
    status: str
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_latency_ms: float
    ttft_ms: float
    decode_tokens_per_second: float
    peak_memory_gb: float
    fallback_count: int | None = None
    num_draft_tokens: int | None = None
    draft_model_configured: bool | None = None
    acceptance_rate: float | None = None
    rollback_rate: float | None = None
    accepted_tokens: int | None = None
    rejected_tokens: int | None = None
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect real-model Gemma 4 QAT MLX baseline and MTP speculative-decode evidence."
    )
    parser.add_argument("--target-model-id", action="append", help="Target QAT MLX repo id. Repeatable.")
    parser.add_argument("--draft-model-id", action="append", help="Draft companion repo id. Repeatable and index-matched.")
    parser.add_argument("--target-model-path", action="append", type=Path, help="Existing local target snapshot path.")
    parser.add_argument("--draft-model-path", action="append", type=Path, help="Existing local draft companion snapshot path.")
    parser.add_argument("--output", type=Path, help="Write JSON evidence to this path.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--num-draft-tokens", type=int, default=6)
    parser.add_argument("--download", action="store_true", help="Download missing target and draft snapshots from Hugging Face.")
    parser.add_argument("--dry-run", action="store_true", help="Emit schema-shaped evidence without loading model weights.")
    parser.add_argument("--metrics", action="store_true", help="Emit flat numeric metrics for PR-scoped performance.")
    return parser.parse_args()


def run_runtime_evidence(
    *,
    target_model_id: str,
    target_model_path: str | Path | None,
    draft_model_id: str,
    draft_model_path: str | Path | None,
    prompt: str,
    max_tokens: int,
    num_draft_tokens: int,
    runtime_factory: Callable[[], Any] = MLXVLMRuntime,
    download: bool = False,
) -> dict[str, Any]:
    target_path = Path(target_model_path).expanduser() if target_model_path is not None else None
    draft_path = Path(draft_model_path).expanduser() if draft_model_path is not None else None
    download_performed = False
    if target_path is None or not target_path.exists():
        if not download:
            raise FileNotFoundError(f"target model path does not exist: {target_path}")
        target_path = download_snapshot(target_model_id)
        download_performed = True
    if draft_path is None or not draft_path.exists():
        if not download:
            raise FileNotFoundError(f"draft model path does not exist: {draft_path}")
        draft_path = download_snapshot(draft_model_id)
        download_performed = True

    runtime = runtime_factory()
    loaded_model = runtime.load_model(
        model_spec_for_qat_target(
            model_id=target_model_id,
            model_path=target_path,
        )
    )
    try:
        messages = [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text=prompt)])]
        prepared = runtime.render_prompt(messages, loaded_model=loaded_model)
        sampling = common_pb2.SamplingConfig(
            temperature=0.0,
            top_p=1.0,
            top_k=0,
            max_output_tokens=max(1, max_tokens),
        )
        baseline = observe_generation(
            lambda: runtime.generate_tokens(
                loaded_model,
                prepared,
                sampling,
                Event(),
            )
        )
        speculative = observe_generation(
            lambda: runtime.generate_tokens(
                loaded_model,
                prepared,
                sampling,
                Event(),
                acceleration_policy=common_pb2.AccelerationPolicy(
                    mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
                    draft_model_id=str(draft_path),
                    allow_baseline_fallback=True,
                    num_draft_tokens=max(1, num_draft_tokens),
                ),
            )
        )
    finally:
        close_loaded_model = getattr(runtime, "close_loaded_model", None)
        if callable(close_loaded_model):
            close_loaded_model(loaded_model)

    status = "passed" if baseline.status == "passed" and speculative.status == "passed" else "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target": {
            "model_id": target_model_id,
            "model_path": str(target_path),
            "asset_format": "mlx",
            "qat": True,
        },
        "draft_companion": {
            "model_id": draft_model_id,
            "model_path": str(draft_path),
            "role": "mtp",
            "downloaded_implicitly": False,
        },
        "runtime": {
            "download_requested": bool(download),
            "download_performed": download_performed,
            "prompt_only": True,
            "max_tokens": max(1, max_tokens),
            "num_draft_tokens": max(1, num_draft_tokens),
        },
        "baseline": asdict(baseline),
        "speculative_decode": asdict(speculative),
        "metrics": evidence_metrics(baseline, speculative),
    }


def model_spec_for_qat_target(*, model_id: str, model_path: Path) -> common_pb2.ModelSpec:
    quant_profile = "qat-4bit" if "4bit" in model_id.lower() else "qat"
    return common_pb2.ModelSpec(
        model_id=model_id,
        model_path=str(model_path),
        model_kind="vlm",
        revision="main",
        tokenizer_hash=f"hf.{model_id}",
        quant_profile_id=quant_profile,
        parser_mode="text",
        reasoning_mode="off",
        max_context=4096,
        ext={
            "melix.hf_repo_id": model_id,
            "melix.hf_revision": "main",
            "melix.model_path": str(model_path),
            "melix.qat.enabled": "true",
            "melix.qat.family": "gemma4",
            "melix.qat.source": "google_gemma4_qat",
            "melix.qat.asset_format": "mlx",
            "melix.qat.quantization_family": "4bit" if "4bit" in model_id.lower() else "",
            "melix.vlm.backend_id": "mlx_vlm",
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "vision_tokenization_mode": "interleaved",
            "vision_max_images_per_prompt": "8",
            "melix.multimodal_adapter_hash": "vision-family-gemma4-v1",
        },
    )


def observe_generation(generate: Callable[[], Any]) -> GenerationObservation:
    started_at = time.perf_counter()
    first_event_ms: float | None = None
    text_parts: list[str] = []
    last_event: Any | None = None
    try:
        for event in generate():
            if first_event_ms is None:
                first_event_ms = (time.perf_counter() - started_at) * 1000.0
            last_event = event
            text = str(getattr(event, "text", "") or "")
            if text:
                text_parts.append(text)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        return GenerationObservation(
            status="failed",
            text="".join(text_parts),
            prompt_tokens=0,
            completion_tokens=0,
            total_latency_ms=round(elapsed_ms, 3),
            ttft_ms=round(first_event_ms or elapsed_ms, 3),
            decode_tokens_per_second=0.0,
            peak_memory_gb=0.0,
            error=str(exc),
        )

    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if last_event is None:
        return GenerationObservation(
            status="failed",
            text="",
            prompt_tokens=0,
            completion_tokens=0,
            total_latency_ms=round(elapsed_ms, 3),
            ttft_ms=round(first_event_ms or elapsed_ms, 3),
            decode_tokens_per_second=0.0,
            peak_memory_gb=0.0,
            error="runtime produced no token events",
        )

    completion_tokens = int(getattr(last_event, "completion_tokens", 0) or len(text_parts))
    event_tps = float(getattr(last_event, "generation_tps", 0.0) or 0.0)
    measured_decode_tps = completion_tokens / max(0.001, elapsed_ms / 1000.0)
    return GenerationObservation(
        status="passed",
        text="".join(text_parts),
        prompt_tokens=int(getattr(last_event, "prompt_tokens", 0) or 0),
        completion_tokens=completion_tokens,
        total_latency_ms=round(elapsed_ms, 3),
        ttft_ms=round(first_event_ms or elapsed_ms, 3),
        decode_tokens_per_second=round(event_tps or measured_decode_tps, 4),
        peak_memory_gb=round(float(getattr(last_event, "peak_memory", 0.0) or 0.0), 4),
        fallback_count=optional_int(last_event, "speculative_fallback_count"),
        num_draft_tokens=optional_int(last_event, "speculative_num_draft_tokens"),
        draft_model_configured=optional_bool(last_event, "speculative_draft_model_configured"),
        acceptance_rate=optional_float(last_event, "speculative_acceptance_rate"),
        rollback_rate=optional_float(last_event, "speculative_rollback_rate"),
        accepted_tokens=optional_int(last_event, "speculative_accepted_tokens"),
        rejected_tokens=optional_int(last_event, "speculative_rejected_tokens"),
    )


def evidence_metrics(
    baseline: GenerationObservation,
    speculative: GenerationObservation,
) -> dict[str, float]:
    baseline_tps = baseline.decode_tokens_per_second
    speculative_tps = speculative.decode_tokens_per_second
    return {
        "baseline_passed": 1.0 if baseline.status == "passed" else 0.0,
        "speculative_passed": 1.0 if speculative.status == "passed" else 0.0,
        "baseline_ttft_ms": baseline.ttft_ms,
        "speculative_ttft_ms": speculative.ttft_ms,
        "baseline_decode_tokens_per_second": baseline_tps,
        "speculative_decode_tokens_per_second": speculative_tps,
        "decode_tokens_per_second_delta_pct": (
            round(((speculative_tps - baseline_tps) / baseline_tps) * 100.0, 4)
            if baseline_tps > 0
            else 0.0
        ),
        "baseline_peak_memory_gb": baseline.peak_memory_gb,
        "speculative_peak_memory_gb": speculative.peak_memory_gb,
        "speculative_acceptance_rate": float(speculative.acceptance_rate or 0.0),
        "speculative_fallback_count": float(speculative.fallback_count or 0),
    }


def optional_float(event: Any, name: str) -> float | None:
    value = getattr(event, name, None)
    if value is None:
        return None
    return float(value)


def optional_int(event: Any, name: str) -> int | None:
    value = getattr(event, name, None)
    if value is None:
        return None
    return int(value)


def optional_bool(event: Any, name: str) -> bool | None:
    value = getattr(event, name, None)
    if value is None:
        return None
    return bool(value)


def download_snapshot(model_id: str) -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo_id=model_id, revision="main")).resolve()


def resolve_target_paths(
    target_model_ids: list[str],
    target_model_paths: list[Path],
    *,
    download: bool,
) -> list[Path | None]:
    if target_model_paths:
        if len(target_model_paths) != len(target_model_ids):
            raise ValueError("--target-model-path count must match --target-model-id count")
        return [path.expanduser().resolve() for path in target_model_paths]
    if not download:
        raise ValueError("--target-model-path is required unless --download or --dry-run is used")
    return [None for _model_id in target_model_ids]


def resolve_draft_paths(
    draft_model_ids: list[str],
    draft_model_paths: list[Path],
    *,
    download: bool,
) -> list[Path | None]:
    if draft_model_paths:
        if len(draft_model_paths) != len(draft_model_ids):
            raise ValueError("--draft-model-path count must match --draft-model-id count")
        return [path.expanduser().resolve() for path in draft_model_paths]
    if not download:
        raise ValueError("--draft-model-path is required unless --download or --dry-run is used")
    return [None for _model_id in draft_model_ids]


def dry_run_report() -> dict[str, Any]:
    baseline = GenerationObservation(
        status="passed",
        text="dry-run baseline",
        prompt_tokens=1,
        completion_tokens=1,
        total_latency_ms=0.0,
        ttft_ms=0.0,
        decode_tokens_per_second=1.0,
        peak_memory_gb=0.0,
    )
    speculative = GenerationObservation(
        status="passed",
        text="dry-run speculative",
        prompt_tokens=1,
        completion_tokens=1,
        total_latency_ms=0.0,
        ttft_ms=0.0,
        decode_tokens_per_second=1.0,
        peak_memory_gb=0.0,
        fallback_count=0,
        num_draft_tokens=6,
        draft_model_configured=True,
        acceptance_rate=1.0,
        rollback_rate=0.0,
        accepted_tokens=1,
        rejected_tokens=0,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "target": {"model_id": DEFAULT_TARGETS[0][0], "model_path": "", "asset_format": "mlx", "qat": True},
        "draft_companion": {"model_id": DEFAULT_TARGETS[0][1], "role": "mtp", "downloaded_implicitly": False},
        "runtime": {
            "download_requested": False,
            "download_performed": False,
            "prompt_only": True,
            "max_tokens": 0,
            "num_draft_tokens": 6,
        },
        "baseline": asdict(baseline),
        "speculative_decode": asdict(speculative),
        "metrics": evidence_metrics(baseline, speculative),
    }


def metrics_payload(*, dry_run: bool) -> dict[str, float]:
    iterations = int_env("MELIX_GEMMA4_QAT_RUNTIME_EVIDENCE_METRIC_ITERATIONS", default=1000)
    elapsed_samples: list[float] = []
    report: dict[str, Any] | None = None
    for _ in range(3):
        started_at = time.perf_counter()
        for _ in range(iterations):
            report = dry_run_report()
        elapsed_samples.append((time.perf_counter() - started_at) * 1000.0)
    assert report is not None
    return {
        "schema_ok": 1.0 if report["schema_version"] == SCHEMA_VERSION else 0.0,
        "status_passed": 1.0 if report["status"] == "passed" else 0.0,
        "dry_run": 1.0 if dry_run else 0.0,
        "download_performed": 0.0,
        "target_count": float(len(DEFAULT_TARGETS)),
        "iteration_count": float(iterations),
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
    }


def int_env(name: str, *, default: int) -> int:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _model_ids(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    target_ids = args.target_model_id or [target for target, _draft in DEFAULT_TARGETS]
    draft_ids = args.draft_model_id or [draft for _target, draft in DEFAULT_TARGETS]
    if len(target_ids) != len(draft_ids):
        raise ValueError("--target-model-id count must match --draft-model-id count")
    return target_ids, draft_ids


def main() -> int:
    args = parse_args()
    if args.metrics:
        print(json.dumps(metrics_payload(dry_run=args.dry_run), sort_keys=True))
        return 0
    if args.dry_run:
        report: dict[str, Any] = dry_run_report()
    else:
        target_ids, draft_ids = _model_ids(args)
        target_paths = resolve_target_paths(
            target_ids,
            args.target_model_path or [],
            download=args.download,
        )
        draft_paths = resolve_draft_paths(
            draft_ids,
            args.draft_model_path or [],
            download=args.download,
        )
        reports = [
            run_runtime_evidence(
                target_model_id=target_id,
                target_model_path=target_path,
                draft_model_id=draft_id,
                draft_model_path=draft_path,
                prompt=args.prompt,
                max_tokens=args.max_tokens,
                num_draft_tokens=args.num_draft_tokens,
                download=args.download,
            )
            for target_id, draft_id, target_path, draft_path in zip(
                target_ids,
                draft_ids,
                target_paths,
                draft_paths,
                strict=True,
            )
        ]
        report = {
            "schema_version": SCHEMA_VERSION,
            "status": "passed" if all(item["status"] == "passed" for item in reports) else "failed",
            "targets": reports,
        }
    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
