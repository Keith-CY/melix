from __future__ import annotations

import json
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
