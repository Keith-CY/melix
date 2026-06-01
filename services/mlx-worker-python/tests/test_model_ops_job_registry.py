from __future__ import annotations

import builtins
import json
import math
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from worker.model_ops.job_registry import (
    ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD,
    ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD,
    ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD,
    ADAPTER_RUNTIME_SHARING_POLICY_FIELD,
    ADAPTER_RUNTIME_SWITCH_MODE_FIELD,
    ModelOpsJob,
    ModelOpsJobRegistry,
)


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


def test_restore_manifest_jobs_preserves_collected_manifest_order_without_resorting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = ModelOpsJobRegistry()
    first_manifest = tmp_path / "train_lora" / "model-ops-0002" / "train_lora.adapter.json"
    second_manifest = tmp_path / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
    first_manifest.parent.mkdir(parents=True)
    second_manifest.parent.mkdir(parents=True)
    first_manifest.write_bytes(
        json.dumps(
            {
                "job_id": "model-ops-0002",
                "operation": "train_lora",
                "source_model": "src-2",
            }
        ).encode("utf-8")
    )
    second_manifest.write_bytes(
        json.dumps(
            {
                "job_id": "model-ops-0001",
                "operation": "train_lora",
                "source_model": "src-1",
            }
        ).encode("utf-8")
    )
    ordered_manifest_paths = (first_manifest, second_manifest)
    original_sorted = builtins.sorted

    class RestoreResortDetected(Exception):
        pass

    def fail_on_restore_resort(iterable, *args, **kwargs):
        iterated_values = tuple(iterable)
        if iterated_values == ordered_manifest_paths:
            raise RestoreResortDetected(
                "_restore_manifest_jobs should not resort ordered manifest paths"
            )
        return original_sorted(iterated_values, *args, **kwargs)

    monkeypatch.setattr(builtins, "sorted", fail_on_restore_resort)

    with pytest.raises(RestoreResortDetected):
        sorted(list(ordered_manifest_paths))

    registry._restore_manifest_jobs(
        operation="train_lora",
        manifest_paths=ordered_manifest_paths,
        pct=0.97,
    )

    assert list(registry._jobs) == ["model-ops-0002", "model-ops-0001"]
    restored_job = registry._jobs["model-ops-0002"]
    assert restored_job.manifest_cached is True
    assert restored_job.manifest_json == ""
    assert restored_job.manifest == {
        "job_id": "model-ops-0002",
        "operation": "train_lora",
        "source_model": "src-2",
    }


def test_restore_manifest_operation_match_fast_path_preserves_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class OperationToken:
        def __str__(self) -> str:
            return " train_lora "

    manifest_paths = tuple(
        tmp_path / "train_lora" / f"model-ops-000{index}" / "train_lora.adapter.json"
        for index in range(1, 5)
    )
    payloads = {
        manifest_paths[0]: {"job_id": "model-ops-0001", "operation": "train_lora"},
        manifest_paths[1]: {"job_id": "model-ops-0002", "operation": " train_lora "},
        manifest_paths[2]: {"job_id": "model-ops-0003", "operation": OperationToken()},
        manifest_paths[3]: {"job_id": "model-ops-0004", "operation": "activate_adapter"},
    }
    monkeypatch.setattr(
        ModelOpsJobRegistry,
        "_read_manifest_dict",
        staticmethod(lambda path: payloads[path]),
    )

    registry = ModelOpsJobRegistry()
    registry._restore_manifest_jobs(operation="train_lora", manifest_paths=manifest_paths, pct=0.97)

    assert set(registry._jobs) == {"model-ops-0001", "model-ops-0002", "model-ops-0003"}


def test_job_registry_restore_reads_manifest_bytes_without_text_decode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jobs_root = tmp_path / "jobs"
    manifest_path = jobs_root / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(
        json.dumps(
            {
                "job_id": "model-ops-0001",
                "operation": "train_lora",
                "source_model": "melix-dev-text",
            }
        ).encode("utf-8")
    )

    read_bytes_calls: list[Path] = []
    original_read_bytes = Path.read_bytes

    def tracked_read_bytes(self: Path) -> bytes:
        read_bytes_calls.append(self)
        return original_read_bytes(self)

    def forbidden_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        raise AssertionError(f"restore manifests should be read as bytes: {self}")  # pragma: no cover

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
    monkeypatch.setattr(Path, "read_text", forbidden_read_text)

    registry = ModelOpsJobRegistry(jobs_root=jobs_root)

    assert "model-ops-0001" in registry._jobs
    assert read_bytes_calls == [manifest_path]


def test_json_safe_reuses_clean_containers_and_copies_only_changed_branch() -> None:
    clean = {"rows": [{"pct": 1.0, "label": "ready"}]}

    assert ModelOpsJobRegistry._json_safe(clean) is clean

    unsafe = {"rows": [{"pct": math.nan, "label": "bad"}], "other": {"pct": 1.0}}
    safe = ModelOpsJobRegistry._json_safe(unsafe)

    assert safe == {"rows": [{"pct": None, "label": "bad"}], "other": {"pct": 1.0}}
    assert safe is not unsafe
    assert safe["rows"] is not unsafe["rows"]
    assert safe["other"] is unsafe["other"]


def test_job_manifest_handles_empty_registry_snapshot_and_uncached_empty_manifest_json() -> None:
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
            manifest_json="",
            manifest_cached=False,
        )
    )

    assert registry_snapshot_job == {}
    assert uncached_manifest == {}


def test_job_manifest_returns_cached_manifest_for_restored_job_with_empty_manifest_json() -> None:
    restored_manifest = {
        "job_id": "model-ops-0007",
        "operation": "activate_adapter",
        "derived_model_id": "melix-dev-active",
    }

    manifest = ModelOpsJobRegistry._job_manifest(
        ModelOpsJob(
            job_id="model-ops-0007",
            operation="activate_adapter",
            source_model="melix-dev-text",
            output_dir="/runtime/activate",
            manifest_json="",
            manifest=restored_manifest,
            manifest_cached=True,
        )
    )

    assert manifest == restored_manifest


def test_snapshot_job_handles_empty_manifest_for_uncached_non_snapshot_job() -> None:
    snapshot = ModelOpsJobRegistry._snapshot_job(
        ModelOpsJob(
            job_id="model-ops-0008",
            operation="train_lora",
            source_model="melix-dev-text",
            output_dir="/runtime/train",
            manifest_json="",
            manifest_cached=False,
            stage_history=[("write_manifest", 0.97)],
            output_path="/runtime/train/model-ops-0008/train_lora.adapter.json",
            status="completed",
        )
    )

    assert snapshot["manifest"] == {}


def test_snapshot_job_returns_cached_manifest_for_restored_job_with_empty_manifest_json() -> None:
    restored_manifest = {
        "job_id": "model-ops-0009",
        "operation": "train_lora",
        "adapter_name": "adapter-a",
    }

    snapshot = ModelOpsJobRegistry._snapshot_job(
        ModelOpsJob(
            job_id="model-ops-0009",
            operation="train_lora",
            source_model="melix-dev-text",
            output_dir="/runtime/train",
            manifest_json="",
            manifest=restored_manifest,
            manifest_cached=True,
            stage_history=[("write_manifest", 0.97)],
            output_path="/runtime/train/model-ops-0009/train_lora.adapter.json",
            status="completed",
        )
    )

    assert snapshot["manifest"] == restored_manifest


def test_strict_activation_receipt_fixture_requires_completed_integrity_passed() -> None:
    completed_receipt = {
        "operation_id": "managed_model_install:abc",
        "target_scope": "hub:mlx-community/demo@main",
        "operation_kind": "managed_model_install",
        "status": "completed",
        "terminal_state": "completed",
        "artifact_integrity": {
            "verification_mode": "receipt_fixture",
            "policy_present": True,
            "digest": "sha256:abc",
            "checked_at": "2026-05-24T00:00:00Z",
            "failure_reason": "",
            "status": "passed",
        },
    }
    in_progress_receipt = {
        **completed_receipt,
        "status": "in_progress",
        "terminal_state": "in_progress",
    }
    failed_integrity_receipt = {
        **completed_receipt,
        "artifact_integrity": {
            **completed_receipt["artifact_integrity"],
            "status": "failed",
            "failure_reason": "digest_mismatch",
        },
    }

    assert ModelOpsJobRegistry.strict_activation_receipt_passed(completed_receipt) is True
    assert ModelOpsJobRegistry.strict_activation_receipt_passed(in_progress_receipt) is False
    assert ModelOpsJobRegistry.strict_activation_receipt_passed(failed_integrity_receipt) is False


def test_strict_activation_receipt_rejects_missing_core_receipt_fields() -> None:
    completed_receipt = {
        "operation_id": "managed_model_install:abc",
        "target_scope": "hub:mlx-community/demo@main",
        "operation_kind": "managed_model_install",
        "status": "completed",
        "terminal_state": "completed",
        "artifact_integrity": {
            "verification_mode": "receipt_fixture",
            "policy_present": True,
            "digest": "sha256:abc",
            "checked_at": "2026-05-24T00:00:00Z",
            "failure_reason": "",
            "status": "passed",
        },
    }

    assert ModelOpsJobRegistry.strict_activation_receipt_passed(completed_receipt) is True
    for key in ("operation_id", "target_scope", "operation_kind"):
        incomplete = dict(completed_receipt)
        incomplete[key] = ""
        assert ModelOpsJobRegistry.strict_activation_receipt_passed(incomplete) is False

    for key in ("verification_mode", "digest", "checked_at"):
        incomplete_integrity = dict(completed_receipt["artifact_integrity"])
        incomplete_integrity[key] = ""
        assert (
            ModelOpsJobRegistry.strict_activation_receipt_passed(
                {**completed_receipt, "artifact_integrity": incomplete_integrity}
            )
            is False
        )

    missing_policy = dict(completed_receipt["artifact_integrity"])
    missing_policy.pop("policy_present")
    assert (
        ModelOpsJobRegistry.strict_activation_receipt_passed(
            {**completed_receipt, "artifact_integrity": missing_policy}
        )
        is False
    )

    failed_with_pass_status = {
        **completed_receipt["artifact_integrity"],
        "failure_reason": "digest_mismatch",
    }
    assert (
        ModelOpsJobRegistry.strict_activation_receipt_passed(
            {**completed_receipt, "artifact_integrity": failed_with_pass_status}
        )
        is False
    )
    pending_integrity = {
        **completed_receipt["artifact_integrity"],
        "status": "pending",
    }
    assert (
        ModelOpsJobRegistry.strict_activation_receipt_passed(
            {**completed_receipt, "artifact_integrity": pending_integrity}
        )
        is False
    )


def test_download_registry_snapshot_exposes_operation_receipt_fields() -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("download", "mlx-community/demo", "/runtime/download")
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "status": "completed",
                "terminal_state": "completed",
                "operation_id": "managed_model_install:abc",
                "target_scope": "hub:mlx-community/demo@main",
                "operation_kind": "managed_model_install",
                "attempts": 1,
                "timeout_ms": 250,
                "retry_after_ms": 500,
                "last_error": "",
                "artifact_integrity": {
                    "verification_mode": "receipt_fixture",
                    "policy_present": True,
                    "digest": "sha256:abc",
                    "checked_at": "2026-05-24T00:00:00Z",
                    "failure_reason": "",
                    "status": "passed",
                },
            }
        ),
    )
    registry.complete(job.job_id, "/runtime/download/download.artifact")

    snapshot = registry.snapshot()
    download = snapshot["downloads"][0]

    assert download["operation_id"] == "managed_model_install:abc"
    assert download["target_scope"] == "hub:mlx-community/demo@main"
    assert download["operation_kind"] == "managed_model_install"
    assert download["attempts"] == 1
    assert download["timeout_ms"] == 250
    assert download["retry_after_ms"] == 500
    assert download["last_error"] == ""
    assert download["artifact_integrity_status"] == "passed"
    assert download["artifact_integrity"]["policy_present"] is True

    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "status": "completed",
                "terminal_state": "completed",
                "operation_id": "managed_model_install:def",
                "target_scope": "hub:mlx-community/demo@main",
                "operation_kind": "managed_model_install",
                "artifact_integrity": "not-a-receipt",
            }
        ),
    )
    refreshed_download = registry.snapshot()["downloads"][0]

    assert refreshed_download["operation_id"] == "managed_model_install:def"
    assert refreshed_download["artifact_integrity"] == {}
    assert refreshed_download["artifact_integrity_status"] == ""


def test_find_download_by_operation_receipt_matches_only_scoped_active_or_completed_jobs() -> None:
    registry = ModelOpsJobRegistry()
    wrong_operation = registry.start("quantize", "mlx-community/demo", "/runtime/quantize")
    registry.attach_manifest(
        wrong_operation.job_id,
        json.dumps(
            {
                "operation_id": "managed_model_install:abc",
                "target_scope": "scope-a",
                "operation_kind": "managed_model_install",
                "terminal_state": "completed",
            }
        ),
    )
    failed_download = registry.start("download", "mlx-community/demo", "/runtime/failed")
    registry.attach_manifest(
        failed_download.job_id,
        json.dumps(
            {
                "operation_id": "managed_model_install:abc",
                "target_scope": "scope-a",
                "operation_kind": "managed_model_install",
                "terminal_state": "failed",
            }
        ),
    )
    active_download = registry.start("download", "mlx-community/demo", "/runtime/active")
    registry.attach_manifest(
        active_download.job_id,
        json.dumps(
            {
                "operation_id": "managed_model_install:abc",
                "target_scope": "scope-a",
                "operation_kind": "managed_model_install",
                "terminal_state": "in_progress",
            }
        ),
    )

    assert (
        registry.find_download_by_operation_receipt(
            operation_id=" managed_model_install:abc ",
            target_scope=" scope-a ",
            operation_kind=" managed_model_install ",
        )
        is active_download
    )
    assert registry.find_download_by_operation_receipt(
        operation_id="",
        target_scope="scope-a",
        operation_kind="managed_model_install",
    ) is None
    assert registry.find_download_by_operation_receipt(
        operation_id="managed_model_install:abc",
        target_scope="scope-b",
        operation_kind="managed_model_install",
    ) is None

    registry.fail(active_download.job_id, "download_failed", "failed after receipt")

    assert registry.find_download_by_operation_receipt(
        operation_id="managed_model_install:abc",
        target_scope="scope-a",
        operation_kind="managed_model_install",
    ) is None


def test_find_download_by_operation_receipt_rebuilds_stale_index_entry() -> None:
    registry = ModelOpsJobRegistry()
    stale_download = registry.start("download", "mlx-community/demo", "/runtime/stale")
    registry.attach_manifest(
        stale_download.job_id,
        json.dumps(
            {
                "operation_id": "managed_model_install:abc",
                "target_scope": "scope-a",
                "operation_kind": "managed_model_install",
                "terminal_state": "in_progress",
            }
        ),
    )
    current_download = registry.start("download", "mlx-community/demo", "/runtime/current")
    registry.attach_manifest(
        current_download.job_id,
        json.dumps(
            {
                "operation_id": "managed_model_install:def",
                "target_scope": "scope-b",
                "operation_kind": "managed_model_install",
                "terminal_state": "in_progress",
            }
        ),
    )
    registry._download_operation_receipt_index[
        ("managed_model_install:def", "scope-b", "managed_model_install")
    ] = stale_download.job_id

    assert registry.find_download_by_operation_receipt(
        operation_id="managed_model_install:def",
        target_scope="scope-b",
        operation_kind="managed_model_install",
    ) is current_download


def test_find_download_by_operation_receipt_cache_miss_avoids_sorting_all_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    for index in range(5):
        registry.start("train_lora", "melix-dev-text", f"/runtime/train-{index}")
    download = registry.start("download", "mlx-community/demo", "/runtime/download")
    registry.attach_manifest(
        download.job_id,
        json.dumps(
            {
                "operation_id": "managed_model_install:abc",
                "target_scope": "scope-a",
                "operation_kind": "managed_model_install",
                "terminal_state": "in_progress",
            }
        ),
    )
    registry._download_operation_receipt_index.clear()

    sort_key = Mock(side_effect=AssertionError("download receipt cache misses should not sort registry jobs"))
    monkeypatch.setattr(ModelOpsJobRegistry, "_job_sort_key", sort_key)

    assert registry.find_download_by_operation_receipt(
        operation_id="managed_model_install:abc",
        target_scope="scope-a",
        operation_kind="managed_model_install",
    ) is download
    sort_key.assert_not_called()


def test_download_operation_receipt_key_rejects_missing_fields() -> None:
    job = ModelOpsJob(
        job_id="model-ops-0001",
        operation="download",
        source_model="mlx-community/demo",
        output_dir="/runtime/download",
        status="completed",
    )

    assert (
        ModelOpsJobRegistry._download_operation_receipt_key(
            job,
            {
                "operation_id": "managed_model_install:abc",
                "target_scope": "scope-a",
                "operation_kind": "",
                "terminal_state": "completed",
            },
        )
        is None
    )


def test_non_download_manifest_updates_do_not_refresh_download_receipt_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    refresh = Mock(
        side_effect=AssertionError("non-download jobs should not refresh the download receipt index")
    )

    monkeypatch.setattr(registry, "_refresh_download_operation_receipt_index", refresh)

    registry.attach_manifest(
        train_job.job_id,
        json.dumps({"adapter_name": "adapter-a", "adapter_set_hash": "hash-a"}),
    )
    registry.complete(train_job.job_id, "/runtime/train/train_lora.adapter.json")

    failed_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.fail(failed_job.job_id, "activation_failed", "boom")
    refresh.assert_not_called()


def test_strict_activation_receipt_rejects_missing_integrity_object() -> None:
    assert (
        ModelOpsJobRegistry.strict_activation_receipt_passed(
            {"status": "completed", "artifact_integrity": "passed"}
        )
        is False
    )


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


def test_job_registry_snapshot_preserves_adapter_runtime_fields() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps({"adapter_name": "adapter-a", "adapter_set_hash": "hash-a"}),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    active_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        active_job.job_id,
        json.dumps(
            {
                "adapter_manifest_path": adapter_manifest_path,
                "adapter_weights_path": "/runtime/train/adapters.safetensors",
                "adapter_set_hash": "hash-a",
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "source_model": "melix-dev-text",
                "activation_mode": "adapter_backed_runtime",
                "adapter_runtime.base_reuse_key": "base-runtime-key",
                "adapter_runtime.adapter_isolation_key": "adapter-runtime-key",
                "adapter_runtime.switch_mode": "base_reuse_adapter_swap",
                "adapter_runtime.sharing_policy": "shared_base_isolated_adapter",
                "adapter_runtime.compatibility_status": "compatible",
            }
        ),
    )
    registry.complete(active_job.job_id, "/runtime/activate/melix-dev-active/manifest.json")

    snapshot = registry.snapshot()
    adapter = snapshot["adapters"][0]
    derived_model = snapshot["derived_models"][0]
    for row in (adapter, derived_model):
        assert row[ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD] == "base-runtime-key"
        assert row[ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD] == "adapter-runtime-key"
        assert row[ADAPTER_RUNTIME_SWITCH_MODE_FIELD] == "base_reuse_adapter_swap"
        assert row[ADAPTER_RUNTIME_SHARING_POLICY_FIELD] == "shared_base_isolated_adapter"
        assert row[ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD] == "compatible"

    target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active")
    assert target is not None
    assert target[ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD] == "base-runtime-key"
    assert target[ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD] == "adapter-runtime-key"


def test_job_registry_omits_partial_adapter_runtime_fields() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps({"adapter_name": "adapter-a", "adapter_set_hash": "hash-a"}),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    active_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        active_job.job_id,
        json.dumps(
            {
                "adapter_manifest_path": adapter_manifest_path,
                "adapter_weights_path": "/runtime/train/adapters.safetensors",
                "adapter_set_hash": "hash-a",
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "source_model": "melix-dev-text",
                "activation_mode": "adapter_backed_runtime",
                "adapter_runtime.base_reuse_key": "base-runtime-key",
                "adapter_runtime.switch_mode": "base_reuse_adapter_swap",
            }
        ),
    )
    registry.complete(active_job.job_id, "/runtime/activate/melix-dev-active/manifest.json")

    snapshot = registry.snapshot()
    adapter = snapshot["adapters"][0]
    derived_model = snapshot["derived_models"][0]
    for row in (adapter, derived_model):
        assert ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD not in row
        assert ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD not in row
        assert ADAPTER_RUNTIME_SWITCH_MODE_FIELD not in row
        assert ADAPTER_RUNTIME_SHARING_POLICY_FIELD not in row
        assert ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD not in row

    target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active")
    assert target is not None
    assert ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD not in target
    assert ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD not in target


def test_active_derived_model_row_cache_reuses_rows_and_invalidates() -> None:
    registry = ModelOpsJobRegistry()
    active_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        active_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(active_job.job_id, "/runtime/activate/melix-dev-active/manifest.json")

    first_rows = registry._cached_active_derived_model_job_rows()
    second_rows = registry._cached_active_derived_model_job_rows()
    first_manifests = registry.active_derived_model_manifests()
    second_manifests = registry.active_derived_model_manifests()

    assert first_rows is second_rows
    assert not hasattr(first_rows[0][0], "__dict__")
    assert first_manifests is registry._active_derived_model_manifests_cache
    assert first_manifests is second_manifests
    assert first_manifests == (
        {
            "derived_model_id": "melix-dev-active",
            "derived_model_path": "/runtime/activate/melix-dev-active",
            "activation_mode": "fused_derived_model",
        },
    )

    removal_job = registry.start("remove_derived_model", "melix-dev-text", "/runtime/remove")
    registry.attach_manifest(
        removal_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "activation_job_id": active_job.job_id,
                "activation_manifest_path": "/runtime/activate/melix-dev-active/manifest.json",
            }
        ),
    )
    registry.complete(removal_job.job_id, "/runtime/remove/remove_derived_model.lifecycle.json")

    assert registry._cached_active_derived_model_job_rows() is not first_rows
    assert registry.active_derived_model_manifests() == ()



def test_resolve_derived_model_target_reuses_active_row_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    active_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        active_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(active_job.job_id, "/runtime/activate/melix-dev-active/manifest.json")

    build_calls = 0
    original_builder = ModelOpsJobRegistry._active_derived_model_job_rows.__func__

    def counted_builder(cls, jobs):
        nonlocal build_calls
        build_calls += 1
        return original_builder(cls, jobs)

    monkeypatch.setattr(
        ModelOpsJobRegistry,
        "_active_derived_model_job_rows",
        classmethod(counted_builder),
    )

    assert registry.resolve_derived_model_target(derived_model_id="melix-dev-active") is not None
    assert registry.resolve_derived_model_target(derived_model_id="melix-dev-active") is not None
    by_id_cache = registry._active_derived_model_by_id_cache
    assert by_id_cache is not None
    cached_lookup = by_id_cache["melix-dev-active"]
    assert not hasattr(cached_lookup, "__dict__")
    assert build_calls == 1


def test_resolve_derived_model_target_uses_cached_model_id_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    for index in range(25):
        job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
        registry.attach_manifest(
            job.job_id,
            json.dumps(
                {
                    "derived_model_id": f"melix-dev-active-{index:02d}",
                    "derived_model_path": f"/runtime/activate/melix-dev-active-{index:02d}",
                    "activation_mode": "fused_derived_model",
                }
            ),
        )
        registry.complete(job.job_id, f"/runtime/activate/melix-dev-active-{index:02d}/manifest.json")

    rows = registry._cached_active_derived_model_job_rows()
    row_iterations = 0

    def counted_rows():
        nonlocal row_iterations
        for row in rows:
            row_iterations += 1
            yield row

    monkeypatch.setattr(registry, "_cached_active_derived_model_job_rows", counted_rows)

    target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active-00")
    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active-00"
    assert row_iterations == len(rows)

    row_iterations = 0
    target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active-00")
    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active-00"
    assert row_iterations == 0


def test_resolve_derived_model_target_trimmed_id_reuses_lookup_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(job.job_id, "/runtime/activate/melix-dev-active/manifest.json")

    original_lookup = registry._cached_active_derived_model_by_id
    lookup_calls = 0

    def counted_lookup() -> dict[str, Any]:
        nonlocal lookup_calls
        lookup_calls += 1
        return original_lookup()

    monkeypatch.setattr(registry, "_cached_active_derived_model_by_id", counted_lookup)

    target = registry.resolve_derived_model_target(derived_model_id=" melix-dev-active ")

    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active"
    assert lookup_calls == 1


def test_resolve_derived_model_target_model_id_uses_cached_resolved_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    manifest_path = "/runtime/activate/melix-dev-active/manifest.json"
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(job.job_id, manifest_path)

    first_target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active")
    assert first_target is not None
    assert first_target["activation_manifest_path"] == manifest_path

    def fail_resolve(self: Path, *args: Any, **kwargs: Any) -> Path:
        raise AssertionError("resolved activation manifest path should be cached")  # pragma: no cover

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    second_target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active")
    assert second_target is not None
    assert second_target["activation_manifest_path"] == manifest_path


def test_resolve_derived_model_target_caches_payload_without_sharing_return_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    manifest_path = "/runtime/activate/melix-dev-active/manifest.json"
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(job.job_id, manifest_path)

    build_calls = 0
    original_payload_builder = ModelOpsJobRegistry._derived_model_target_payload

    def counted_payload_builder(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal build_calls
        build_calls += 1
        return original_payload_builder(*args, **kwargs)

    monkeypatch.setattr(
        ModelOpsJobRegistry,
        "_derived_model_target_payload",
        staticmethod(counted_payload_builder),
    )

    first_target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active")
    assert first_target is not None
    first_target["derived_model_id"] = "mutated-by-caller"

    second_target = registry.resolve_derived_model_target(derived_model_id="melix-dev-active")

    assert second_target is not None
    assert second_target["derived_model_id"] == "melix-dev-active"
    assert build_calls == 1


def test_resolve_derived_model_target_id_lookup_negative_paths() -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(job.job_id, "/runtime/activate/melix-dev-active/manifest.json")

    assert registry.resolve_derived_model_target(derived_model_id="melix-dev-missing") is None
    assert (
        registry.resolve_derived_model_target(
            derived_model_id="melix-dev-active",
            manifest_path="/runtime/activate/other/manifest.json",
        )
        is None
    )


def test_resolve_derived_model_target_trims_model_id_before_lookup() -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    manifest_path = "/runtime/activate/melix-dev-active/manifest.json"
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(job.job_id, manifest_path)

    target = registry.resolve_derived_model_target(derived_model_id=" melix-dev-active ")

    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active"
    assert target["activation_manifest_path"] == manifest_path


def test_resolve_derived_model_target_manifest_only_uses_payload_helper() -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    manifest_path = "/runtime/activate/melix-dev-active/manifest.json"
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": "/runtime/activate/melix-dev-active",
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(job.job_id, manifest_path)

    target = registry.resolve_derived_model_target(manifest_path=manifest_path)

    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active"
    assert target["activation_manifest_path"] == manifest_path


def test_resolve_derived_model_target_resolves_manifest_path_before_lookup(tmp_path: Path) -> None:
    registry = ModelOpsJobRegistry()
    job = registry.start("activate_adapter", "melix-dev-text", str(tmp_path / "activate"))
    manifest_path = tmp_path / "activate" / "melix-dev-active" / "manifest.json"
    registry.attach_manifest(
        job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-active",
                "derived_model_path": str(manifest_path.parent),
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(job.job_id, str(manifest_path))

    target = registry.resolve_derived_model_target(
        manifest_path=str(manifest_path.parent / ".." / "melix-dev-active" / "manifest.json")
    )

    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active"
    assert target["activation_manifest_path"] == str(manifest_path.resolve())


def test_resolve_derived_model_target_uses_cached_manifest_path_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelOpsJobRegistry()
    for index in range(25):
        job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
        registry.attach_manifest(
            job.job_id,
            json.dumps(
                {
                    "derived_model_id": f"melix-dev-active-{index:02d}",
                    "derived_model_path": f"/runtime/activate/melix-dev-active-{index:02d}",
                    "activation_mode": "fused_derived_model",
                }
            ),
        )
        registry.complete(job.job_id, f"/runtime/activate/melix-dev-active-{index:02d}/manifest.json")

    rows = registry._cached_active_derived_model_job_rows()
    row_iterations = 0

    def counted_rows():
        nonlocal row_iterations
        for row in rows:
            row_iterations += 1
            yield row

    monkeypatch.setattr(registry, "_cached_active_derived_model_job_rows", counted_rows)

    target_manifest_path = "/runtime/activate/melix-dev-active-00/manifest.json"
    target = registry.resolve_derived_model_target(manifest_path=target_manifest_path)
    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active-00"
    assert row_iterations == len(rows)

    row_iterations = 0
    target = registry.resolve_derived_model_target(manifest_path=target_manifest_path)
    assert target is not None
    assert target["derived_model_id"] == "melix-dev-active-00"
    assert row_iterations == 0
    assert registry.resolve_derived_model_target(manifest_path="/runtime/missing/manifest.json") is None


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

    assert target is not None
    expected = {
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
    for key, value in expected.items():
        assert target[key] == value
    assert ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD not in target
    assert ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD not in target
    assert ADAPTER_RUNTIME_SWITCH_MODE_FIELD not in target
    assert ADAPTER_RUNTIME_SHARING_POLICY_FIELD not in target
    assert ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD not in target


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
