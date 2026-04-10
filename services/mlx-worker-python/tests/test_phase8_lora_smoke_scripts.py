from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script(module_name: str):
    module_path = REPO_ROOT / "scripts" / f"{module_name}.py"
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("module_name", "marker_payload"),
    [
        (
            "phase8_lora_cli_smoke",
            {
                "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "positive": {
                    "train": {"training_mode": "qlora"},
                    "activate": {"activation_mode": "adapter_backed_runtime"},
                    "compare": {"target_model_ids": ["melix-qwen35-acceptance"]},
                    "export": {"row_count": 1},
                    "remove_derived": {"job_id": "remove-job-1"},
                },
                "negative": {
                    "train_missing_adapter_name": "--adapter-name is required for melix lora train.",
                    "activate_missing_adapter_path": "--adapter-path is required for melix lora activate.",
                    "compare_missing_target": "At least one --target-model-id is required for melix eval compare.",
                    "export_missing_job": "No evaluation rows were found for job eval-missing.",
                    "remove_missing_target": "Either --derived-model-id or --manifest-path is required for melix lora remove-derived.",
                },
            },
        ),
        (
            "phase8_lora_window_smoke",
            {
                "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "positive": {
                    "training_mode": "qlora",
                    "activation_mode": "adapter_backed_runtime",
                    "compare_target_model_ids": ["melix-qwen35-acceptance"],
                    "evaluation_export_format": "summary.csv",
                    "remove_derived_model_id": "melix-qwen35-acceptance",
                },
                "negative": {
                    "train_without_model_dispatch_count": 0,
                    "activate_without_adapter_dispatch_count": 0,
                    "compare_error": "Select at least one compare target model before running Evaluation Compare.",
                    "export_error": "No evaluation summary rows are available for CSV export.",
                    "remove_error": "Select an activated adapter before removing its derived model.",
                },
                "rendered_controls": [
                    "QLoRA",
                    "Adapter-backed Runtime",
                    "Run Comparison",
                    "Remove Derived Model",
                ],
            },
        ),
    ],
)
def test_run_smoke_projects_the_swift_payload(
    module_name: str,
    marker_payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script(module_name)
    monkeypatch.setattr(module, "run_swift_smoke", lambda repo_root: marker_payload)

    payload = module.run_smoke(tmp_path)

    assert payload["ok"] is True
    assert payload["repo_root"] == str(tmp_path)
    assert payload["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert "positive" in payload
    assert "negative" in payload


@pytest.mark.parametrize(
    ("module_name", "success_message"),
    [
        ("phase8_lora_cli_smoke", "Phase 8 LoRA CLI smoke passed."),
        ("phase8_lora_window_smoke", "Phase 8 LoRA Window smoke passed."),
    ],
)
def test_main_supports_json_and_text_output(
    module_name: str,
    success_message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    module = _load_script(module_name)
    monkeypatch.setattr(
        module,
        "run_smoke",
        lambda repo_root: {"ok": True, "repo_root": str(repo_root), "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"},
    )
    monkeypatch.setattr(
        module.sys,
        "argv",
        [f"{module_name}.py", "--json", "--repo-root", str(tmp_path)],
    )

    assert module.main() == 0
    json_output = capsys.readouterr().out
    assert '"ok": true' in json_output
    assert "mlx-community/Qwen3.5-0.8B-OptiQ-4bit" in json_output

    monkeypatch.setattr(
        module.sys,
        "argv",
        [f"{module_name}.py", "--repo-root", str(tmp_path)],
    )

    assert module.main() == 0
    text_output = capsys.readouterr().out
    assert success_message in text_output
    assert str(tmp_path) in text_output


@pytest.mark.parametrize(
    ("module_name", "marker"),
    [
        ("phase8_lora_cli_smoke", "PHASE8_LORA_CLI_SMOKE"),
        ("phase8_lora_window_smoke", "PHASE8_LORA_WINDOW_SMOKE"),
    ],
)
def test_run_swift_smoke_requires_marker(
    module_name: str,
    marker: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script(module_name)

    class _Completed:
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: _Completed())

    with pytest.raises(RuntimeError, match=marker):
        module.run_swift_smoke(tmp_path)
