from __future__ import annotations

import importlib.util
import json
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
    if hasattr(module, "swift_root_package"):
        monkeypatch.setattr(module.swift_root_package, "current_swift_toolchain_slug", lambda: "swift-6-3")

    class _Completed:
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: _Completed())

    with pytest.raises(RuntimeError, match=marker):
        module.run_swift_smoke(tmp_path)


def test_phase8_lora_cli_run_swift_smoke_uses_root_package_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script("phase8_lora_cli_smoke")
    monkeypatch.setattr(module.swift_root_package, "current_swift_toolchain_slug", lambda: "swift-6-3")
    captured: dict[str, object] = {}

    class _Completed:
        stdout = 'PHASE8_LORA_CLI_SMOKE={"model_id":"mlx-community/Qwen3.5-0.8B-OptiQ-4bit","positive":{},"negative":{}}\n'
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return _Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_swift_smoke(tmp_path)

    assert payload["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert captured["command"] == [
        "xcrun",
        "swift",
        "test",
        "--package-path",
        str(tmp_path),
        "--scratch-path",
        str(tmp_path / ".build" / "root-package" / "swift-6-3"),
        "--disable-sandbox",
        "--filter",
        "Phase8LoRACLISmokeTests",
    ]
    assert captured["cwd"] == tmp_path
    env = captured["env"]
    assert env["HOME"] == str(tmp_path / ".swift-home" / "root-package" / "swift-6-3")
    assert env["CLANG_MODULE_CACHE_PATH"] == str(
        tmp_path / ".build" / "ModuleCache.noindex" / "root-package" / "swift-6-3"
    )


def test_phase8_lora_window_run_swift_smoke_uses_menubar_package_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script("phase8_lora_window_smoke")
    monkeypatch.setattr(module.swift_root_package, "current_swift_toolchain_slug", lambda: "swift-6-3")
    captured: dict[str, object] = {}

    class _Completed:
        stdout = (
            'PHASE8_LORA_WINDOW_SMOKE={"model_id":"mlx-community/Qwen3.5-0.8B-OptiQ-4bit",'
            '"positive":{},"negative":{},"rendered_controls":[]}\n'
        )
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return _Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_swift_smoke(tmp_path)

    assert payload["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert captured["command"] == [
        "xcrun",
        "swift",
        "test",
        "--package-path",
        str(tmp_path / "apps" / "macos-menubar"),
        "--scratch-path",
        str(tmp_path / ".build" / "macos-menubar" / "swift-6-3"),
        "--disable-sandbox",
        "--filter",
        "Phase8LoRAWindowSmokeTests",
    ]
    assert captured["cwd"] == tmp_path
    env = captured["env"]
    assert env["HOME"] == str(tmp_path / ".swift-home" / "macos-menubar" / "swift-6-3")
    assert env["CLANG_MODULE_CACHE_PATH"] == str(
        tmp_path / ".build" / "ModuleCache.noindex" / "macos-menubar" / "swift-6-3"
    )
    assert env["MELIX_HOME"] == str(tmp_path / ".runtime" / "phase8" / "smoke-home")


def test_lora_runtime_acceptance_materializes_dialogue_training_package(tmp_path: Path) -> None:
    module = _load_script("lora_runtime_acceptance")

    payload = module.run_acceptance(
        repo_root=REPO_ROOT,
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit",
        dataset_id="top200.event-extraction.top20.v1",
        output_dir=tmp_path / "acceptance",
        sample_limit=2,
        max_steps=1,
        skip_training=True,
    )

    assert payload["ok"] is True
    assert payload["skipped_training"] is True
    assert payload["model_id"] == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert payload["dataset_id"] == "top200.event-extraction.top20.v1"
    manifest_path = Path(payload["training_dataset_manifest_path"])
    samples_path = manifest_path.parent / "samples.jsonl"
    assert manifest_path.is_file()
    assert samples_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["format"] == "chat_messages"
    assert manifest["source_evaluation_dataset_id"] == "top200.event-extraction.top20.v1"
    assert manifest["sample_count"] == 2
    sample = json.loads(samples_path.read_text(encoding="utf-8").splitlines()[0])
    assert sample["messages"][0]["role"] == "user"
    assert "Dialogue:" in sample["messages"][0]["content"]
    assert sample["messages"][1]["role"] == "assistant"
    assert "events" in json.loads(sample["messages"][1]["content"])
