#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
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
            json.dumps({"adapter_name": f"adapter-{index:04d}", "adapter_set_hash": f"hash-{index:04d}"}),
        )
        registry.complete(train_job.job_id, adapter_manifest_path)

        activation_job = registry.start("activate_adapter", "melix-dev-text", f"/runtime/activate/{model_id}")
        activation_manifest_path = f"/runtime/activate/{model_id}/manifest.json"
        registry.attach_manifest(
            activation_job.job_id,
            json.dumps(
                {
                    "adapter_manifest_path": adapter_manifest_path,
                    "adapter_weights_path": f"/runtime/train/{model_id}/adapters.safetensors",
                    "adapter_set_hash": f"hash-{index:04d}",
                    "derived_model_id": model_id,
                    "derived_model_path": f"/runtime/activate/{model_id}",
                    "derived_model_alias": f"alias-{index:04d}",
                    "source_model": "melix-dev-text",
                    "activation_mode": "fused_derived_model",
                }
            ),
        )
        registry.complete(activation_job.job_id, activation_manifest_path)

        if index % 5 == 0:
            removal_job = registry.start("remove_derived_model", "melix-dev-text", f"/runtime/remove/{model_id}")
            registry.attach_manifest(
                removal_job.job_id,
                json.dumps(
                    {
                        "derived_model_id": model_id,
                        "activation_job_id": activation_job.job_id,
                        "activation_manifest_path": activation_manifest_path,
                        "adapter_manifest_path": adapter_manifest_path,
                    }
                ),
            )
            registry.complete(removal_job.job_id, f"/runtime/remove/{model_id}/remove_derived_model.lifecycle.json")
            removed_count += 1
    return registry, job_count - removed_count


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

    payload = {
        "active_manifest_count": float(active_count),
        "active_manifest_elapsed_ms_mean": round(statistics.fmean(active_elapsed_ms), 6),
        "elapsed_ms_mean": round(
            statistics.fmean(active_elapsed_ms)
            + statistics.fmean(resolve_elapsed_ms)
            + statistics.fmean(manifest_path_elapsed_ms),
            6,
        ),
        "job_count": float(job_count),
        "manifest_path_elapsed_ms_mean": round(statistics.fmean(manifest_path_elapsed_ms), 6),
        "removed_count": float(job_count - active_count),
        "resolve_target_elapsed_ms_mean": round(statistics.fmean(resolve_elapsed_ms), 6),
        "sample_count": float(sample_count),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
