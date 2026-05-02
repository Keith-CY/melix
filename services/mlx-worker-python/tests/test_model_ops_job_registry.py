from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from worker.model_ops.job_registry import ModelOpsJob, ModelOpsJobRegistry


def test_collect_restore_manifest_paths_scans_expected_operations_once(tmp_path: Path) -> None:
    jobs_root = tmp_path / "jobs"
    (jobs_root / "train_lora" / "model-ops-0002").mkdir(parents=True)
    (jobs_root / "train_lora" / "model-ops-abc").mkdir(parents=True)
    (jobs_root / "activate_adapter" / "model-ops-0001" / "one").mkdir(parents=True)
    (jobs_root / "activate_adapter" / "model-ops-0001" / "two").mkdir(parents=True)
    (jobs_root / "remove_derived_model" / "model-ops-0003").mkdir(parents=True)
    (jobs_root / "other" / "ignored").mkdir(parents=True)

    train_manifest = jobs_root / "train_lora" / "model-ops-0002" / "train_lora.adapter.json"
    activate_manifest = (
        jobs_root / "activate_adapter" / "model-ops-0001" / "one" / "manifest.json"
    )
    remove_manifest = jobs_root / "remove_derived_model" / "model-ops-0003" / "remove_derived_model.lifecycle.json"

    train_manifest.write_text(json.dumps({"operation": "train_lora"}), encoding="utf-8")
    activate_manifest.write_text(json.dumps({"operation": "activate_adapter"}), encoding="utf-8")
    remove_manifest.write_text(json.dumps({"operation": "remove_derived_model"}), encoding="utf-8")

    paths = ModelOpsJobRegistry._collect_restore_manifest_paths(jobs_root)

    assert paths["train_lora"] == [train_manifest]
    assert paths["activate_adapter"] == [activate_manifest]
    assert paths["remove_derived_model"] == [remove_manifest]


def test_job_registry_restore_scans_manifest_directories_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    jobs_root = tmp_path / "jobs"
    (jobs_root / "train_lora" / "model-ops-0001").mkdir(parents=True)
    (jobs_root / "activate_adapter" / "model-ops-0002" / "one").mkdir(parents=True)
    (jobs_root / "remove_derived_model" / "model-ops-0003").mkdir(parents=True)

    (jobs_root / "train_lora" / "model-ops-0001" / "train_lora.adapter.json").write_text(
        json.dumps(
            {
                "job_id": "model-ops-0001",
                "operation": "train_lora",
                "source_model": "src-1",
            }
        ),
        encoding="utf-8",
    )
    (jobs_root / "activate_adapter" / "model-ops-0002" / "one" / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": "model-ops-0002",
                "operation": "activate_adapter",
                "source_model": "src-2",
                "derived_model_id": "derived-2",
            }
        ),
        encoding="utf-8",
    )
    (jobs_root / "remove_derived_model" / "model-ops-0003" / "remove_derived_model.lifecycle.json").write_text(
        json.dumps(
            {
                "job_id": "model-ops-0003",
                "operation": "remove_derived_model",
                "source_model": "src-3",
            }
        ),
        encoding="utf-8",
    )

    scan_calls: list[str] = []
    original_scandir = __import__("os").scandir

    def tracked_scandir(path: str | bytes | Path) -> Any:
        scan_calls.append(str(path))
        return original_scandir(path)

    monkeypatch.setattr(__import__("os"), "scandir", tracked_scandir)

    registry = ModelOpsJobRegistry(jobs_root=jobs_root)

    assert set(registry._jobs) == {"model-ops-0003", "model-ops-0002", "model-ops-0001"}
    assert any(str(jobs_root / "train_lora") == call for call in scan_calls)
    assert any(str(jobs_root / "activate_adapter") == call for call in scan_calls)
    assert any(str(jobs_root / "remove_derived_model") == call for call in scan_calls)
    assert len(scan_calls) <= 9


def test_json_safe_reuses_clean_containers_and_copies_only_changed_branch() -> None:
    clean = {"rows": [{"pct": 1.0, "label": "ready"}]}

    assert ModelOpsJobRegistry._json_safe(clean) is clean

    unsafe = {"rows": [{"pct": math.nan, "label": "bad"}], "other": {"pct": 1.0}}
    safe = ModelOpsJobRegistry._json_safe(unsafe)

    assert safe == {"rows": [{"pct": None, "label": "bad"}], "other": {"pct": 1.0}}
    assert safe is not unsafe
    assert safe["rows"] is not unsafe["rows"]
    assert safe["other"] is unsafe["other"]


def test_job_manifest_handles_empty_registry_snapshot_and_uncached_json() -> None:
    registry_snapshot_job = ModelOpsJobRegistry._job_manifest(
        ModelOpsJob(
            job_id="model-ops-0001",
            operation="registry_snapshot",
            source_model="melix-dev-text",
            output_dir="/runtime/snapshot",
        )
    )
    uncached_manifest = ModelOpsJobRegistry._job_manifest(
        ModelOpsJob(
            job_id="model-ops-0002",
            operation="activate_adapter",
            source_model="melix-dev-text",
            output_dir="/runtime/activate",
            manifest_json=json.dumps({"derived_model_id": "melix-dev-active"}),
            manifest_cached=False,
        )
    )

    assert registry_snapshot_job == {}
    assert uncached_manifest == {"derived_model_id": "melix-dev-active"}


def test_active_derived_model_manifests_avoids_full_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps({"adapter_name": "adapter-a", "adapter_set_hash": "hash-a"}),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    active_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    active_manifest = {
        "adapter_manifest_path": adapter_manifest_path,
        "adapter_set_hash": "hash-a",
        "derived_model_id": "melix-dev-active",
        "derived_model_path": "/runtime/activate/melix-dev-active",
        "activation_mode": "fused_derived_model",
    }
    registry.attach_manifest(active_job.job_id, json.dumps(active_manifest))
    registry.complete(active_job.job_id, "/runtime/activate/melix-dev-active/manifest.json")

    removed_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    removed_manifest = {
        "adapter_manifest_path": adapter_manifest_path,
        "adapter_set_hash": "hash-a",
        "derived_model_id": "melix-dev-removed",
        "derived_model_path": "/runtime/activate/melix-dev-removed",
        "activation_mode": "fused_derived_model",
    }
    registry.attach_manifest(removed_job.job_id, json.dumps(removed_manifest))
    registry.complete(removed_job.job_id, "/runtime/activate/melix-dev-removed/manifest.json")

    removal_job = registry.start("remove_derived_model", "melix-dev-text", "/runtime/remove")
    registry.attach_manifest(
        removal_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-removed",
                "activation_job_id": removed_job.job_id,
                "activation_manifest_path": "/runtime/activate/melix-dev-removed/manifest.json",
                "adapter_manifest_path": adapter_manifest_path,
            }
        ),
    )
    registry.complete(removal_job.job_id, "/runtime/remove/remove_derived_model.lifecycle.json")

    monkeypatch.setattr(
        registry,
        "snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("snapshot should not be used")),
    )

    assert registry.active_derived_model_manifests() == (active_manifest,)



def test_active_derived_model_manifests_skips_removed_manifest_path_without_job_id() -> None:
    registry = ModelOpsJobRegistry()

    activation_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    activation_manifest_path = "/runtime/activate/melix-dev-active/manifest.json"
    registry.attach_manifest(
        activation_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(activation_job.job_id, activation_manifest_path)

    removal_job = registry.start("remove_derived_model", "melix-dev-text", "/runtime/remove")
    registry.attach_manifest(
        removal_job.job_id,
        json.dumps({"activation_manifest_path": activation_manifest_path}),
    )
    registry.complete(removal_job.job_id, "/runtime/remove/remove_derived_model.lifecycle.json")

    assert registry.active_derived_model_manifests() == ()



def test_resolve_derived_model_target_avoids_snapshot_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps({"adapter_name": "adapter-a", "adapter_set_hash": "hash-a"}),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    active_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    active_output_path = "/runtime/activate/melix-dev-active/manifest.json"
    registry.attach_manifest(
        active_job.job_id,
        json.dumps(
            {
                "adapter_manifest_path": adapter_manifest_path,
                "adapter_weights_path": "/runtime/train/adapters.safetensors",
                "adapter_set_hash": "hash-a",
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "derived_model_alias": "active-alias",
                "source_model": "melix-dev-text",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(active_job.job_id, active_output_path)

    removed_job = registry.start("remove_derived_model", "melix-dev-text", "/runtime/remove")
    registry.attach_manifest(
        removed_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-removed",
                "activation_job_id": "model-ops-9999",
                "activation_manifest_path": "/runtime/activate/melix-dev-removed/manifest.json",
                "adapter_manifest_path": adapter_manifest_path,
            }
        ),
    )
    registry.complete(removed_job.job_id, "/runtime/remove/remove_derived_model.lifecycle.json")

    monkeypatch.setattr(
        ModelOpsJobRegistry,
        "_snapshot_job",
        staticmethod(lambda job: (_ for _ in ()).throw(AssertionError("_snapshot_job should not be used"))),
    )

    target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active")

    assert target == {
        "activation_job_id": active_job.job_id,
        "activation_manifest_path": active_output_path,
        "output_dir": "/runtime/activate",
        "source_model": "melix-dev-text",
        "derived_model_id": "melix-dev-active",
        "derived_model_path": "/runtime/activate/melix-dev-active",
        "derived_model_alias": "active-alias",
        "activation_mode": "fused_derived_model",
        "runtime_mode": 1,
        "adapter_manifest_path": adapter_manifest_path,
        "adapter_weights_path": "/runtime/train/adapters.safetensors",
    }


def test_resolve_derived_model_target_delays_path_resolution_until_id_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    target_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        target_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-target",
                "derived_model_path": "/runtime/activate/melix-dev-target",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(target_job.job_id, "/runtime/activate/melix-dev-target/manifest.json")

    removed_by_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        removed_by_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-removed-by-job",
                "derived_model_path": "/runtime/activate/melix-dev-removed-by-job",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    removed_by_job_path = "/runtime/activate/melix-dev-removed-by-job/manifest.json"
    registry.complete(removed_by_job.job_id, removed_by_job_path)
    removal_by_job = registry.start("remove_derived_model", "melix-dev-text", "/runtime/remove")
    registry.attach_manifest(
        removal_by_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-removed-by-job",
                "activation_job_id": removed_by_job.job_id,
                "activation_manifest_path": removed_by_job_path,
            }
        ),
    )
    registry.complete(removal_by_job.job_id, "/runtime/remove/removed-by-job.json")

    removed_by_model = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        removed_by_model.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-removed-by-model",
                "derived_model_path": "/runtime/activate/melix-dev-removed-by-model",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(removed_by_model.job_id, "/runtime/activate/melix-dev-removed-by-model/manifest.json")
    removal_by_model = registry.start("remove_derived_model", "melix-dev-text", "/runtime/remove")
    registry.attach_manifest(
        removal_by_model.job_id,
        json.dumps({"derived_model_id": "melix-dev-removed-by-model"}),
    )
    registry.complete(removal_by_model.job_id, "/runtime/remove/removed-by-model.json")

    for index in range(12):
        job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
        registry.attach_manifest(
            job.job_id,
            json.dumps(
                {
                    "derived_model_id": f"melix-dev-other-{index}",
                    "derived_model_path": f"/runtime/activate/melix-dev-other-{index}",
                    "activation_mode": "fused_derived_model",
                }
            ),
        )
        registry.complete(job.job_id, f"/runtime/activate/melix-dev-other-{index}/manifest.json")

    resolve_calls = 0

    def counted_resolve(self: Path) -> Path:
        nonlocal resolve_calls
        resolve_calls += 1
        return self

    monkeypatch.setattr(Path, "resolve", counted_resolve)

    target = registry.resolve_derived_model_target(derived_model_id="melix-dev-target")

    assert target is not None
    assert target["activation_job_id"] == target_job.job_id
    assert resolve_calls == 1
