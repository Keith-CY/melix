#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACT = Path("docs/metrics/issue-2601-paired-contiguous-paged-memory.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and emit numeric metrics from the Paged KV paired-memory probe."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", type=Path)
    return parser.parse_args()


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def analyze_artifact(payload: dict[str, Any]) -> dict[str, float]:
    contiguous = _mapping(payload.get("contiguous"), "contiguous")
    paged = _mapping(payload.get("paged"), "paged")
    comparison = _mapping(payload.get("comparison"), "comparison")
    failures: list[str] = []

    if payload.get("status") != "passed":
        failures.append("status")
    if _number(payload.get("session_count"), "session_count") < 4:
        failures.append("session_count")
    if _number(paged.get("model_eval_batch_size"), "paged.model_eval_batch_size") < 2:
        failures.append("model_eval_batch_size")
    if _number(paged.get("sample_count"), "paged.sample_count") <= 1:
        failures.append("paged_sample_count")
    if _number(contiguous.get("sample_count"), "contiguous.sample_count") <= 1:
        failures.append("contiguous_sample_count")
    if _number(paged.get("output_token_count"), "paged.output_token_count") != _number(
        contiguous.get("output_token_count"), "contiguous.output_token_count"
    ):
        failures.append("output_token_parity")
    logical_bytes = _number(comparison.get("logical_session_bytes"), "logical_session_bytes")
    resident_bytes = _number(comparison.get("resident_block_bytes"), "resident_block_bytes")
    if logical_bytes <= resident_bytes:
        failures.append("logical_vs_resident")

    active_reduction = _number(
        comparison.get("mlx_active_peak_delta_reduction_bytes"),
        "mlx_active_peak_delta_reduction_bytes",
    )
    reported_reduction = _number(
        comparison.get("mlx_reported_peak_delta_reduction_bytes"),
        "mlx_reported_peak_delta_reduction_bytes",
    )
    if active_reduction <= 0:
        failures.append("mlx_active_peak_reduction")
    if reported_reduction <= 0:
        failures.append("mlx_reported_peak_reduction")

    failure_count = float(len(failures))
    return {
        "status_passed": 1.0 if not failures else 0.0,
        "status_warning": 0.0,
        "status_failed": 1.0 if failures else 0.0,
        "failure_count": failure_count,
        "session_count": _number(payload.get("session_count"), "session_count"),
        "model_eval_batch_size": _number(
            paged.get("model_eval_batch_size"), "paged.model_eval_batch_size"
        ),
        "sample_count_min": min(
            _number(paged.get("sample_count"), "paged.sample_count"),
            _number(contiguous.get("sample_count"), "contiguous.sample_count"),
        ),
        "logical_session_bytes": logical_bytes,
        "resident_block_bytes": resident_bytes,
        "mlx_active_peak_delta_reduction_bytes": active_reduction,
        "mlx_reported_peak_delta_reduction_bytes": reported_reduction,
        "process_resident_peak_delta_reduction_bytes": _number(
            comparison.get("process_resident_peak_delta_reduction_bytes"),
            "process_resident_peak_delta_reduction_bytes",
        ),
        "paged_mlx_active_peak_delta_bytes": _number(
            paged.get("mlx_active_peak_delta_bytes"), "paged.mlx_active_peak_delta_bytes"
        ),
        "paged_tokens_per_second": _number(
            paged.get("tokens_per_second"), "paged.tokens_per_second"
        ),
    }


def main() -> int:
    args = parse_args()
    root = args.repo_root.resolve()
    artifact = args.artifact or (root / DEFAULT_ARTIFACT)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    metrics = analyze_artifact(_mapping(payload, "artifact"))
    print(json.dumps(metrics, sort_keys=True))
    return 1 if metrics["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
