#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path


def _seed_registry(job_count: int):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))
    from worker.model_ops.job_registry import ModelOpsJobRegistry

    registry = ModelOpsJobRegistry()
    removed_count = 0
    for index in range(job_count):
        model_id = f"melix-dev-derived-{index:04d}"
        adapter_manifest_path = f"/runtime/train/{model_id}/train_lora.adapter.json"

        train_job = registry.start("train_lora", "melix-dev-text", f"/runtime/train/{model_id}")
        registry.attach_manifest(
            train_job.job_id,
            json.dumps(_train_manifest(index, adapter_manifest_path)),
        )
        registry.complete(train_job.job_id, adapter_manifest_path)

        activation_job = registry.start("activate_adapter", "melix-dev-text", f"/runtime/activate/{model_id}")
        activation_manifest_path = f"/runtime/activate/{model_id}/manifest.json"
        registry.attach_manifest(
            activation_job.job_id,
            json.dumps(_activation_manifest(index, adapter_manifest_path)),
        )
        registry.complete(activation_job.job_id, activation_manifest_path)

        if index % 5 == 0:
            removal_job = registry.start("remove_derived_model", "melix-dev-text", f"/runtime/remove/{model_id}")
            registry.attach_manifest(
                removal_job.job_id,
                json.dumps(_removal_manifest(index, activation_job.job_id, activation_manifest_path, adapter_manifest_path)),
            )
            registry.complete(removal_job.job_id, f"/runtime/remove/{model_id}/remove_derived_model.lifecycle.json")
            removed_count += 1
    return registry, job_count - removed_count


def _train_manifest(index: int, adapter_manifest_path: str) -> dict[str, str]:
    return {
        "job_id": f"model-ops-train-{index:04d}",
        "operation": "train_lora",
        "source_model": "melix-dev-text",
        "adapter_name": f"adapter-{index:04d}",
        "adapter_set_hash": f"hash-{index:04d}",
        "output_path": adapter_manifest_path,
    }


def _activation_manifest(index: int, adapter_manifest_path: str) -> dict[str, str]:
    model_id = f"melix-dev-derived-{index:04d}"
    return {
        "job_id": f"model-ops-activate-{index:04d}",
        "operation": "activate_adapter",
        "adapter_manifest_path": adapter_manifest_path,
        "adapter_weights_path": f"/runtime/train/{model_id}/adapters.safetensors",
        "adapter_set_hash": f"hash-{index:04d}",
        "derived_model_id": model_id,
        "derived_model_path": f"/runtime/activate/{model_id}",
        "derived_model_alias": f"alias-{index:04d}",
        "source_model": "melix-dev-text",
        "activation_mode": "fused_derived_model",
    }


def _removal_manifest(
    index: int,
    activation_job_id: str,
    activation_manifest_path: str,
    adapter_manifest_path: str,
) -> dict[str, str]:
    model_id = f"melix-dev-derived-{index:04d}"
    return {
        "job_id": f"model-ops-remove-{index:04d}",
        "operation": "remove_derived_model",
        "source_model": "melix-dev-text",
        "derived_model_id": model_id,
        "activation_job_id": activation_job_id,
        "activation_manifest_path": activation_manifest_path,
        "adapter_manifest_path": adapter_manifest_path,
    }


def _write_restore_jobs_root(root: Path, job_count: int) -> int:
    removed_count = 0
    for index in range(job_count):
        model_id = f"melix-dev-derived-{index:04d}"
        adapter_manifest_path = f"/runtime/train/{model_id}/train_lora.adapter.json"
        train_path = root / "train_lora" / f"model-ops-train-{index:04d}" / "train_lora.adapter.json"
        train_path.parent.mkdir(parents=True, exist_ok=True)
        train_path.write_bytes(json.dumps(_train_manifest(index, adapter_manifest_path), sort_keys=True).encode("utf-8"))

        activation_job_id = f"model-ops-activate-{index:04d}"
        activation_path = root / "activate_adapter" / activation_job_id / model_id / "manifest.json"
        activation_path.parent.mkdir(parents=True, exist_ok=True)
        activation_path.write_bytes(json.dumps(_activation_manifest(index, adapter_manifest_path), sort_keys=True).encode("utf-8"))

        if index % 5 == 0:
            removal_path = root / "remove_derived_model" / f"model-ops-remove-{index:04d}" / "remove_derived_model.lifecycle.json"
            removal_path.parent.mkdir(parents=True, exist_ok=True)
            removal_path.write_bytes(
                json.dumps(
                    _removal_manifest(index, activation_job_id, f"/runtime/activate/{model_id}/manifest.json", adapter_manifest_path),
                    sort_keys=True,
                ).encode("utf-8")
            )
            removed_count += 1
    return job_count * 2 + removed_count


def _measure_restore(job_count: int, sample_count: int) -> tuple[list[float], int]:
    from worker.model_ops.job_registry import ModelOpsJobRegistry

    elapsed_samples: list[float] = []
    restored_count = 0
    with tempfile.TemporaryDirectory(prefix="melix-job-registry-restore-probe-") as temp_dir:
        jobs_root = Path(temp_dir) / "jobs"
        expected_count = _write_restore_jobs_root(jobs_root, job_count)
        for _ in range(sample_count):
            started = time.perf_counter()
            registry = ModelOpsJobRegistry(jobs_root=jobs_root)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            restored_count = len(registry._jobs)
            if restored_count != expected_count:  # pragma: no cover - defensive probe guard
                raise RuntimeError(f"expected {expected_count} restored jobs, got {restored_count}")
    return elapsed_samples, restored_count


def main() -> int:
    job_count = 1200
    sample_count = 6
    registry, active_count = _seed_registry(job_count)
    target_model_id = "melix-dev-derived-0001"
    warmup_target = registry.resolve_derived_model_target(derived_model_id=target_model_id)
    if not warmup_target or warmup_target.get("derived_model_id") != target_model_id:
        raise RuntimeError("derived-model warmup lookup returned the wrong target")
    target_manifest_path = str(warmup_target.get("activation_manifest_path", ""))
    warmup_manifest_path_target = registry.resolve_derived_model_target(manifest_path=target_manifest_path)
    if not warmup_manifest_path_target or warmup_manifest_path_target.get("derived_model_id") != target_model_id:
        raise RuntimeError("manifest-path warmup lookup returned the wrong target")  # pragma: no cover

    active_elapsed_ms: list[float] = []
    resolve_elapsed_ms: list[float] = []
    manifest_path_elapsed_ms: list[float] = []
    for _ in range(sample_count):
        started = time.perf_counter()
        manifests = registry.active_derived_model_manifests()
        active_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        if len(manifests) != active_count:
            raise RuntimeError(f"expected {active_count} active manifests, got {len(manifests)}")

        started = time.perf_counter()
        target = registry.resolve_derived_model_target(derived_model_id=target_model_id)
        resolve_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        if not target or target.get("derived_model_id") != target_model_id:
            raise RuntimeError("derived-model lookup returned the wrong target")

        started = time.perf_counter()
        manifest_path_target = registry.resolve_derived_model_target(manifest_path=target_manifest_path)
        manifest_path_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        if not manifest_path_target or manifest_path_target.get("derived_model_id") != target_model_id:
            raise RuntimeError("manifest-path lookup returned the wrong target")  # pragma: no cover

    restore_elapsed_ms, restored_job_count = _measure_restore(job_count=400, sample_count=3)

    payload = {
        "active_manifest_count": float(active_count),
        "active_manifest_elapsed_ms_mean": round(statistics.fmean(active_elapsed_ms), 6),
        "elapsed_ms_mean": round(
            statistics.fmean(active_elapsed_ms)
            + statistics.fmean(resolve_elapsed_ms)
            + statistics.fmean(manifest_path_elapsed_ms)
            + statistics.fmean(restore_elapsed_ms),
            6,
        ),
        "job_count": float(job_count),
        "manifest_path_elapsed_ms_mean": round(statistics.fmean(manifest_path_elapsed_ms), 6),
        "removed_count": float(job_count - active_count),
        "resolve_target_elapsed_ms_mean": round(statistics.fmean(resolve_elapsed_ms), 6),
        "restore_elapsed_ms_mean": round(statistics.fmean(restore_elapsed_ms), 6),
        "restore_elapsed_ms_min": round(min(restore_elapsed_ms), 6),
        "restored_job_count": float(restored_job_count),
        "sample_count": float(sample_count),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
