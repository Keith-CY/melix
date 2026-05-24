from __future__ import annotations

import json
import os
from pathlib import Path

from worker.productization import lora_experiment_store as lora_experiment_store_module
from worker.productization.lora_experiment_store import LoraExperimentStore


def _write_run_record(
    jobs_root: Path,
    *,
    run_id: str,
    group_id: str,
    manifest_path: str,
    updated_at_unix_ms: int,
    loss_best: float | None = None,
    loss_final: float | None = None,
    checkpoint_count: int = 0,
    latest_checkpoint_path: str = "",
    resume_source_path: str = "",
    resume_ready: bool = False,
) -> None:
    run_dir = jobs_root / "train_lora" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "melix.lora_experiment_run.v1",
        "run_id": run_id,
        "group_id": group_id,
        "group_title": "Nightly Qwen",
        "adapter_name": "demo-adapter",
        "source_model": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "status": "completed",
        "manifest_path": manifest_path,
        "checkpoint_count": checkpoint_count,
        "latest_checkpoint_path": latest_checkpoint_path,
        "resume_source_path": resume_source_path,
        "resume_ready": resume_ready,
        "updated_at_unix_ms": updated_at_unix_ms,
    }
    if loss_best is not None:
        payload["loss_best"] = loss_best
    if loss_final is not None:
        payload["loss_final"] = loss_final
    (run_dir / LoraExperimentStore.run_record_name).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_manifest(
    jobs_root: Path,
    *,
    run_id: str,
    operation: str = "train_lora",
    adapter_name: str = "demo-adapter",
    group_id: str = "nightly-qwen",
    updated_at_unix_ms: int = 0,
    created_at_unix_ms: int | None = None,
    extra: dict[str, object] | None = None,
) -> Path:
    manifest_dir = jobs_root / "train_lora" / run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "train_lora.adapter.json"
    payload = {
        "job_id": run_id,
        "operation": operation,
        "adapter_name": adapter_name,
        "source_model": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "experiment_group_id": group_id,
        "updated_at_unix_ms": updated_at_unix_ms,
    }
    if created_at_unix_ms is not None:
        payload["created_at_unix_ms"] = created_at_unix_ms
    if extra is not None:
        payload.update(extra)
    manifest_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_iter_lora_run_dirs_sorts_names_without_reading_entry_paths(tmp_path: Path, monkeypatch) -> None:
    train_root = tmp_path / "train_lora"
    path_reads = 0

    class FakeEntry:
        def __init__(self, name: str, *, is_dir: bool = True, raises: bool = False) -> None:
            self.name = name
            self._is_dir = is_dir
            self._raises = raises

        @property
        def path(self) -> str:  # pragma: no cover - executed only if the regression returns
            nonlocal path_reads
            path_reads += 1
            raise AssertionError("_iter_lora_run_dirs should rebuild paths from entry names")

        def is_dir(self) -> bool:
            if self._raises:
                raise OSError("unreadable")
            return self._is_dir

    class FakeScandir:
        def __enter__(self):
            return iter(
                [
                    FakeEntry("model-ops-0002"),
                    FakeEntry("ignored-prefix"),
                    FakeEntry("model-ops-file", is_dir=False),
                    FakeEntry("model-ops-unreadable", raises=True),
                    FakeEntry("model-ops-0001"),
                ]
            )

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(lora_experiment_store_module.os, "scandir", lambda path: FakeScandir())

    assert lora_experiment_store_module._iter_lora_run_dirs(train_root) == (
        train_root / "model-ops-0001",
        train_root / "model-ops-0002",
    )
    assert path_reads == 0


def test_rebuild_index_prefers_runs_with_reported_loss_for_best_run(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/train_lora.adapter.json",
        updated_at_unix_ms=1_000,
        loss_best=0.42,
        checkpoint_count=1,
        latest_checkpoint_path="/tmp/model-ops-0001/adapter/checkpoint-1/adapters.safetensors",
        resume_ready=True,
    )
    _write_run_record(
        jobs_root,
        run_id="model-ops-0002",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0002/train_lora.adapter.json",
        updated_at_unix_ms=2_000,
        checkpoint_count=2,
        latest_checkpoint_path="/tmp/model-ops-0002/adapter/checkpoint-2/adapters.safetensors",
        resume_source_path="/tmp/model-ops-0001/adapter/checkpoint-1/adapters.safetensors",
        resume_ready=True,
    )

    payload = LoraExperimentStore().rebuild_index(jobs_root)

    assert payload["groups"][0]["latest_run_id"] == "model-ops-0002"
    assert payload["groups"][0]["best_run_id"] == "model-ops-0001"
    assert payload["groups"][0]["best_loss"] == 0.42
    assert payload["groups"][0]["latest_checkpoint_path"].endswith("checkpoint-2/adapters.safetensors")
    assert payload["groups"][0]["latest_resume_source_path"].endswith("checkpoint-1/adapters.safetensors")
    assert payload["groups"][0]["resume_ready_run_ids"] == ["model-ops-0002", "model-ops-0001"]
    assert payload["groups"][0]["checkpoint_lineage"][0]["run_id"] == "model-ops-0002"
    assert payload["groups"][0]["best_known_adapter"]["run_id"] == "model-ops-0001"
    assert payload["groups"][0]["best_known_adapter"]["latest_checkpoint_path"].endswith("checkpoint-1/adapters.safetensors")


def test_build_group_payloads_evaluates_best_loss_once_per_run(monkeypatch) -> None:
    runs = [
        {
            "run_id": "model-ops-0001",
            "group_id": "nightly-qwen",
            "updated_at_unix_ms": 1_000,
            "loss_best": 0.42,
        },
        {
            "run_id": "model-ops-0002",
            "group_id": "nightly-qwen",
            "updated_at_unix_ms": 2_000,
            "loss_best": 0.37,
        },
        {
            "run_id": "model-ops-0003",
            "group_id": "nightly-qwen",
            "updated_at_unix_ms": 3_000,
        },
    ]
    call_count = 0
    original_best_loss = lora_experiment_store_module._best_loss_value

    def tracked_best_loss(item: dict[str, object]) -> float | None:
        nonlocal call_count
        call_count += 1
        return original_best_loss(item)

    monkeypatch.setattr(lora_experiment_store_module, "_best_loss_value", tracked_best_loss)

    groups = LoraExperimentStore()._build_group_payloads(runs)

    assert call_count == len(runs)
    assert groups[0]["latest_run_id"] == "model-ops-0003"
    assert groups[0]["best_run_id"] == "model-ops-0002"
    assert groups[0]["best_loss"] == 0.37


def test_rebuild_index_prefers_run_record_over_manifest_when_both_exist(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    _write_manifest(
        jobs_root,
        run_id="model-ops-0001",
        adapter_name="manifest-adapter",
        updated_at_unix_ms=250,
    )
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/from-run-record.json",
        updated_at_unix_ms=1_000,
        checkpoint_count=2,
    )

    payload = LoraExperimentStore().rebuild_index(jobs_root)

    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["manifest_path"] == "/tmp/model-ops-0001/from-run-record.json"
    assert payload["runs"][0]["checkpoint_count"] == 2
    assert payload["runs"][0]["adapter_name"] == "demo-adapter"

    _write_manifest(
        jobs_root,
        run_id="model-ops-0002",
        adapter_name="manifest-only-adapter",
        updated_at_unix_ms=1_500,
        extra={
            "source_eos_token": "<eos>",
            "saved_eos_token": "<eos>",
            "merge_export_canary_result": "passed",
            "round_trip_passed": True,
        },
    )

    payload = LoraExperimentStore().rebuild_index(jobs_root)
    manifest_only_run = next(run for run in payload["runs"] if run["run_id"] == "model-ops-0002")

    assert manifest_only_run["adapter_name"] == "manifest-only-adapter"
    assert manifest_only_run["source_eos_token"] == "<eos>"
    assert manifest_only_run["saved_eos_token"] == "<eos>"
    assert manifest_only_run["merge_export_canary_result"] == "passed"
    assert manifest_only_run["round_trip_passed"] is True


def test_rebuild_index_skips_manifest_parse_when_run_record_exists(tmp_path: Path, monkeypatch) -> None:
    jobs_root = tmp_path / "model-ops"
    manifest_path = _write_manifest(jobs_root, run_id="model-ops-0001")
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/from-run-record.json",
        updated_at_unix_ms=1_000,
    )

    original_read_payload = LoraExperimentStore._read_payload

    def _read_payload(path: Path) -> dict[str, object]:
        if path == manifest_path:
            raise AssertionError("manifest should not be reparsed when a run record already exists")
        return original_read_payload(path)

    monkeypatch.setattr(LoraExperimentStore, "_read_payload", staticmethod(_read_payload))

    payload = LoraExperimentStore().rebuild_index(jobs_root)

    assert [run["run_id"] for run in payload["runs"]] == ["model-ops-0001"]



def test_rebuild_index_reuses_cached_run_and_manifest_payloads(tmp_path: Path, monkeypatch) -> None:
    jobs_root = tmp_path / "model-ops"
    store = LoraExperimentStore()
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/from-run-record.json",
        updated_at_unix_ms=1_000,
    )
    manifest_path = _write_manifest(
        jobs_root,
        run_id="model-ops-0002",
        adapter_name="manifest-only-adapter",
        updated_at_unix_ms=2_000,
    )

    first_payload = store.rebuild_index(jobs_root)
    run_path = jobs_root / "train_lora" / "model-ops-0001" / LoraExperimentStore.run_record_name
    original_read_payload = LoraExperimentStore._read_payload

    def _read_payload(path: Path) -> dict[str, object]:
        if path in {run_path, manifest_path}:
            raise AssertionError("rebuild_index should reuse cached unchanged payloads")
        return original_read_payload(path)

    monkeypatch.setattr(LoraExperimentStore, "_read_payload", staticmethod(_read_payload))

    second_payload = store.rebuild_index(jobs_root)

    assert second_payload == first_payload



def test_rebuild_index_invalidates_cached_payload_when_run_record_changes(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    store = LoraExperimentStore()
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/train_lora.adapter.json",
        updated_at_unix_ms=1_000,
        checkpoint_count=1,
    )

    original_payload = store.rebuild_index(jobs_root)
    run_path = jobs_root / "train_lora" / "model-ops-0001" / LoraExperimentStore.run_record_name
    original_stat = run_path.stat()
    run_record = json.loads(run_path.read_text(encoding="utf-8"))
    run_record["checkpoint_count"] = 7
    run_path.write_text(json.dumps(run_record, indent=2) + "\n", encoding="utf-8")
    os.utime(run_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000))

    refreshed_payload = store.rebuild_index(jobs_root)

    assert original_payload["runs"][0]["checkpoint_count"] == 1
    assert refreshed_payload["runs"][0]["checkpoint_count"] == 7



def test_cache_payload_drops_entries_for_missing_paths(tmp_path: Path) -> None:
    store = LoraExperimentStore()
    missing_path = tmp_path / "missing.json"

    store._cache_payload(path=missing_path, payload={"run_id": "missing"})

    assert missing_path not in store._cached_payloads



def test_rebuild_index_falls_back_to_manifest_when_run_record_is_invalid(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    manifest_path = _write_manifest(
        jobs_root,
        run_id="model-ops-0001",
        adapter_name="manifest-fallback-adapter",
        updated_at_unix_ms=333,
        created_at_unix_ms=222,
    )
    run_dir = jobs_root / "train_lora" / "model-ops-0001"
    (run_dir / LoraExperimentStore.run_record_name).write_text("{not-json}\n", encoding="utf-8")

    payload = LoraExperimentStore().rebuild_index(jobs_root)

    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["run_id"] == "model-ops-0001"
    assert payload["runs"][0]["manifest_path"] == str(manifest_path)
    assert payload["runs"][0]["adapter_name"] == "manifest-fallback-adapter"
    assert payload["runs"][0]["created_at_unix_ms"] == 222


def test_rebuild_index_skips_empty_failed_job_directories(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    _write_manifest(
        jobs_root,
        run_id="model-ops-0002",
        adapter_name="successful-adapter",
        updated_at_unix_ms=333,
        created_at_unix_ms=222,
    )
    failed_dir = jobs_root / "train_lora" / "model-ops-0001"
    failed_dir.mkdir(parents=True)

    payload = LoraExperimentStore().rebuild_index(jobs_root)

    assert [run["run_id"] for run in payload["runs"]] == ["model-ops-0002"]
    assert payload["runs"][0]["adapter_name"] == "successful-adapter"


def test_load_index_uses_existing_index_and_rebuilds_when_missing(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    store = LoraExperimentStore()
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/train_lora.adapter.json",
        updated_at_unix_ms=1_000,
    )

    rebuilt = store.load_index(jobs_root)
    cached = store.load_index(jobs_root)

    assert rebuilt == cached
    assert cached["runs"][0]["run_id"] == "model-ops-0001"


def test_load_index_reuses_cached_index_without_reparsing_unchanged_file(tmp_path: Path, monkeypatch) -> None:
    jobs_root = tmp_path / "model-ops"
    store = LoraExperimentStore()
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/train_lora.adapter.json",
        updated_at_unix_ms=1_000,
    )

    first_payload = store.load_index(jobs_root)
    original_read_payload = LoraExperimentStore._read_payload

    def _read_payload(path: Path) -> dict[str, object]:
        if path == jobs_root / "train_lora" / LoraExperimentStore.index_record_name:
            raise AssertionError("load_index should reuse an unchanged cached index")
        return original_read_payload(path)

    monkeypatch.setattr(LoraExperimentStore, "_read_payload", staticmethod(_read_payload))

    second_payload = store.load_index(jobs_root)

    assert second_payload == first_payload


def test_load_index_invalidates_cached_index_when_index_file_changes(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    store = LoraExperimentStore()
    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/train_lora.adapter.json",
        updated_at_unix_ms=1_000,
    )

    cached_payload = store.load_index(jobs_root)
    index_path = jobs_root / "train_lora" / LoraExperimentStore.index_record_name
    original_stat = index_path.stat()
    mutated_payload = {
        **cached_payload,
        "runs": [{**cached_payload["runs"][0], "run_id": "mutated-run-id"}],
    }
    index_path.write_text(json.dumps(mutated_payload, indent=2) + "\n", encoding="utf-8")
    os.utime(index_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000))

    refreshed_payload = store.load_index(jobs_root)

    assert refreshed_payload["runs"][0]["run_id"] == "mutated-run-id"


def test_iter_lora_run_dirs_filters_before_sorting(tmp_path: Path) -> None:
    train_root = tmp_path / "train_lora"
    train_root.mkdir()
    (train_root / "model-ops-0002").mkdir()
    (train_root / "model-ops-0001").mkdir()
    (train_root / "notes").mkdir()
    (train_root / "model-ops-not-a-dir").write_text("ignore\n", encoding="utf-8")

    assert [path.name for path in lora_experiment_store_module._iter_lora_run_dirs(train_root)] == [
        "model-ops-0001",
        "model-ops-0002",
    ]
    assert lora_experiment_store_module._iter_lora_run_dirs(train_root / "missing") == ()


def test_rebuild_index_skips_non_directories_duplicate_manifests_and_non_train_lora_entries(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    train_root = jobs_root / "train_lora"
    train_root.mkdir(parents=True, exist_ok=True)
    (train_root / "model-ops-not-a-dir").write_text("placeholder\n", encoding="utf-8")

    _write_run_record(
        jobs_root,
        run_id="model-ops-0001",
        group_id="nightly-qwen",
        manifest_path="/tmp/model-ops-0001/train_lora.adapter.json",
        updated_at_unix_ms=1_000,
    )
    _write_manifest(
        jobs_root,
        run_id="model-ops-0002",
        operation="evaluate",
        updated_at_unix_ms=200,
    )
    _write_manifest(
        jobs_root,
        run_id="model-ops-0003",
        updated_at_unix_ms=300,
    )
    duplicate_manifest = train_root / "model-ops-0003" / "train_lora.adapter.json"
    duplicate_payload = json.loads(duplicate_manifest.read_text(encoding="utf-8"))
    duplicate_payload["job_id"] = "model-ops-0001"
    duplicate_manifest.write_text(json.dumps(duplicate_payload, indent=2) + "\n", encoding="utf-8")
    _write_run_record(
        jobs_root,
        run_id="model-ops-0004",
        group_id="",
        manifest_path="/tmp/model-ops-0004/train_lora.adapter.json",
        updated_at_unix_ms=1_100,
    )

    payload = LoraExperimentStore().rebuild_index(jobs_root)

    assert [run["run_id"] for run in payload["runs"]] == ["model-ops-0004", "model-ops-0001"]
    assert payload["groups"][0]["group_id"] == "nightly-qwen"
    assert len(payload["groups"]) == 1


def test_optional_finite_float_rejects_invalid_and_non_finite_values() -> None:
    assert lora_experiment_store_module._optional_finite_float(object()) is None
    assert lora_experiment_store_module._optional_finite_float("not-a-number") is None
    assert lora_experiment_store_module._optional_finite_float(float("inf")) is None


def test_persist_training_run_rewrites_non_finite_metrics_to_null(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    manifest_path = jobs_root / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}\n", encoding="utf-8")

    result = LoraExperimentStore().persist_training_run(
        jobs_root=jobs_root,
        manifest={
            "job_id": "model-ops-0001",
            "source_model": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "adapter_name": "demo-adapter",
            "tokens_per_second": float("inf"),
            "peak_memory_gb": float("nan"),
            "loss_best": float("inf"),
            "loss_final": float("nan"),
        },
        manifest_path=manifest_path,
    )

    run_text = result["run"].read_text(encoding="utf-8")
    index_text = result["index"].read_text(encoding="utf-8")

    assert "Infinity" not in run_text
    assert "NaN" not in run_text
    assert "Infinity" not in index_text
    assert "NaN" not in index_text
