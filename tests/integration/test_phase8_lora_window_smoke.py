from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "phase8_lora_window_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("phase8_lora_window_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
phase8_lora_window_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(phase8_lora_window_smoke)


def test_phase8_lora_window_smoke_exercises_positive_and_negative_acceptance_paths() -> None:
    payload = phase8_lora_window_smoke.run_smoke(Path(__file__).resolve().parents[2])

    assert payload["ok"] is True
    assert payload["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"

    positive = payload["positive"]
    assert positive["training_mode"] == "qlora"
    assert positive["activation_mode"] == "adapter_backed_runtime"
    assert positive["compare_target_model_ids"] == ["melix-qwen35-acceptance"]
    assert positive["evaluation_export_format"] == "summary.csv"
    assert positive["remove_derived_model_id"] == "melix-qwen35-acceptance"

    negative = payload["negative"]
    assert negative["train_without_model_dispatch_count"] == 0
    assert negative["activate_without_adapter_dispatch_count"] == 0
    assert negative["compare_error"] == "Select at least one compare target model before running Evaluation Compare."
    assert negative["export_error"] == "No evaluation summary rows are available for CSV export."
    assert negative["remove_error"] == "Select an activated adapter before removing its derived model."

    assert set(payload["rendered_controls"]) >= {
        "QLoRA",
        "Adapter-backed Serving",
        "Run Comparison",
        "Remove Derived Model",
    }
