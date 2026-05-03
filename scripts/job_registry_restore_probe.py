#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path


TRAIN_MANIFEST_COUNT = 5000
ACTIVATE_MANIFEST_COUNT = 5000
REMOVE_MANIFEST_COUNT = 5000
SAMPLE_COUNT = 8
SOURCE_MODEL_ID = "melix-dev-text"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _train_manifest_paths() -> list[Path]:
    return [
        Path(f"/tmp/melix-restore/train_lora/model-ops-{index:05d}/train_lora.adapter.json")
        for index in range(TRAIN_MANIFEST_COUNT)
    ]


def _activate_manifest_paths() -> list[Path]:
    return [
        Path(f"/tmp/melix-restore/activate_adapter/model-ops-{TRAIN_MANIFEST_COUNT + index:05d}/one/manifest.json")
        for index in range(ACTIVATE_MANIFEST_COUNT)
    ]


def _remove_manifest_paths() -> list[Path]:
    base = TRAIN_MANIFEST_COUNT + ACTIVATE_MANIFEST_COUNT
    return [
        Path(f"/tmp/melix-restore/remove_derived_model/model-ops-{base + index:05d}/remove_derived_model.lifecycle.json")
        for index in range(REMOVE_MANIFEST_COUNT)
    ]


def _expected_job_id(path: Path) -> str:
    if path.name == "manifest.json":
        return path.parent.parent.name
    return path.parent.name


def _payload_for(operation: str, path: Path) -> dict[str, object]:
    job_id = _expected_job_id(path)
    return {
        "job_id": job_id,
        "operation": operation,
        "source_model": SOURCE_MODEL_ID,
        "derived_model_id": job_id,
        "activation_job_id": job_id,
        "activation_manifest_path": str(path),
        "adapter_manifest_path": str(path),
    }


def _measure_restore() -> dict[str, float]:
    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))
    from worker.model_ops.job_registry import ModelOpsJobRegistry

    train_manifest_paths = _train_manifest_paths()
    activate_manifest_paths = _activate_manifest_paths()
    remove_manifest_paths = _remove_manifest_paths()
    expected_job_count = float(
        len(train_manifest_paths) + len(activate_manifest_paths) + len(remove_manifest_paths)
    )

    original_read_manifest_dict = ModelOpsJobRegistry.__dict__["_read_manifest_dict"]
    elapsed_samples: list[float] = []
    try:
        for _ in range(SAMPLE_COUNT):
            registry = ModelOpsJobRegistry()

            def fake_read_manifest_dict(path: Path) -> dict[str, object]:
                if path.name == "train_lora.adapter.json":
                    return _payload_for("train_lora", path)
                if path.name == "manifest.json":
                    return _payload_for("activate_adapter", path)
                return _payload_for("remove_derived_model", path)

            ModelOpsJobRegistry._read_manifest_dict = staticmethod(fake_read_manifest_dict)
            started = time.perf_counter()
            registry._restore_manifest_jobs(
                operation="train_lora",
                manifest_paths=train_manifest_paths,
                pct=0.97,
            )
            registry._restore_manifest_jobs(
                operation="activate_adapter",
                manifest_paths=activate_manifest_paths,
                pct=0.95,
            )
            registry._restore_manifest_jobs(
                operation="remove_derived_model",
                manifest_paths=remove_manifest_paths,
                pct=0.95,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if float(len(registry._jobs)) != expected_job_count:
                raise RuntimeError(
                    f"expected {expected_job_count:.0f} restored jobs, got {len(registry._jobs)}"
                )
            elapsed_samples.append(elapsed_ms)
    finally:
        ModelOpsJobRegistry._read_manifest_dict = original_read_manifest_dict

    restore_elapsed_ms_mean = statistics.fmean(elapsed_samples)
    return {
        "job_count": expected_job_count,
        "per_manifest_ms_mean": round(restore_elapsed_ms_mean / expected_job_count, 9),
        "restore_elapsed_ms_mean": round(restore_elapsed_ms_mean, 6),
        "sample_count": float(SAMPLE_COUNT),
        "train_manifest_count": float(len(train_manifest_paths)),
        "activate_manifest_count": float(len(activate_manifest_paths)),
        "remove_manifest_count": float(len(remove_manifest_paths)),
    }


def main() -> int:
    print(json.dumps(_measure_restore(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
