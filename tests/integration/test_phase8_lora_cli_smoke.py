from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "phase8_lora_cli_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("phase8_lora_cli_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
phase8_lora_cli_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(phase8_lora_cli_smoke)


def test_phase8_lora_cli_smoke_exercises_positive_and_negative_acceptance_paths() -> None:
    payload = phase8_lora_cli_smoke.run_smoke(Path(__file__).resolve().parents[2])

    assert payload["ok"] is True
    assert payload["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"

    positive = payload["positive"]
    assert positive["train"]["training_mode"] == "qlora"
    assert positive["activate"]["activation_mode"] == "adapter_backed_runtime"
    assert positive["compare"]["target_model_ids"] == ["melix-qwen35-acceptance"]
    assert positive["export"]["row_count"] == 1
    assert positive["remove_derived"]["job_id"] == "remove-job-1"

    negative = payload["negative"]
    assert negative["train_missing_adapter_name"] == "--adapter-name is required for melix lora train."
    assert negative["activate_missing_adapter_path"] == "--adapter-path is required for melix lora activate."
    assert negative["compare_missing_target"] == "At least one --target-model-id is required for melix eval compare."
    assert negative["export_missing_job"] == "No evaluation rows were found for job eval-missing."
    assert negative["remove_missing_target"] == "Either --derived-model-id or --manifest-path is required for melix lora remove-derived."
