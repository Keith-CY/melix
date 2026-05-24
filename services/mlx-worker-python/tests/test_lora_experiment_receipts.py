from __future__ import annotations

import json
from pathlib import Path

from worker.productization.lora_experiment_store import LoraExperimentStore


def test_persist_training_run_preserves_lora_canary_receipts(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    manifest_path = jobs_root / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "job_id": "model-ops-0001",
        "operation": "train_lora",
        "adapter_name": "demo-adapter",
        "source_model": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "source_eos_token": "<|source-eos|>",
        "saved_eos_token": "<|source-eos|>",
        "tokenizer_config_path": "/tmp/base/tokenizer_config.json",
        "base_config_present": True,
        "processor_resume_mode": "processor_config",
        "aux_modules_restored": True,
        "merge_export_canary_result": "pass",
        "callback_api_drift_result": "pass",
        "completion_loss": 0.125,
        "round_trip_passed": True,
        "grad_norm": 0.75,
        "updated_at_unix_ms": 1_000,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    paths = LoraExperimentStore().persist_training_run(
        jobs_root=jobs_root,
        manifest=manifest,
        manifest_path=manifest_path,
    )
    run_payload = json.loads(paths["run"].read_text(encoding="utf-8"))

    assert run_payload["source_eos_token"] == "<|source-eos|>"
    assert run_payload["saved_eos_token"] == "<|source-eos|>"
    assert run_payload["tokenizer_config_path"] == "/tmp/base/tokenizer_config.json"
    assert run_payload["base_config_present"] is True
    assert run_payload["processor_resume_mode"] == "processor_config"
    assert run_payload["aux_modules_restored"] is True
    assert run_payload["merge_export_canary_result"] == "pass"
    assert run_payload["callback_api_drift_result"] == "pass"
    assert run_payload["completion_loss"] == 0.125
    assert run_payload["round_trip_passed"] is True
    assert run_payload["grad_norm"] == 0.75
