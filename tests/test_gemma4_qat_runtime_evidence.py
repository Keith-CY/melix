from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "gemma4_qat_runtime_evidence.py"


def load_runtime_evidence_module():
    assert MODULE_PATH.exists(), f"Expected runtime evidence entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_gemma4_qat_runtime_evidence", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    def __init__(self) -> None:
        self.loaded_specs: list[object] = []
        self.closed_models: list[object] = []
        self.acceleration_policies: list[object] = []

    def load_model(self, model_spec):
        self.loaded_specs.append(model_spec)
        return {
            "model": SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
            "processor": SimpleNamespace(),
            "metadata": dict(model_spec.ext),
        }

    def close_loaded_model(self, loaded_model) -> None:
        self.closed_models.append(loaded_model)

    def render_prompt(self, messages, *, loaded_model):
        _ = loaded_model
        return SimpleNamespace(prompt_text=messages[0].parts[0].text)

    def generate_tokens(self, loaded_model, prepared, sampling, cancel_event, *, acceleration_policy=None):
        _ = loaded_model, prepared, sampling, cancel_event
        if acceleration_policy is None:
            yield SimpleNamespace(
                text="baseline ",
                prompt_tokens=11,
                completion_tokens=3,
                generation_tps=30.0,
                peak_memory=1.25,
                speculative_fallback_count=None,
                speculative_num_draft_tokens=None,
                speculative_draft_model_configured=None,
                speculative_acceptance_rate=None,
                speculative_rollback_rate=None,
                speculative_accepted_tokens=None,
                speculative_rejected_tokens=None,
            )
            yield SimpleNamespace(
                text="ok",
                prompt_tokens=11,
                completion_tokens=4,
                generation_tps=32.0,
                peak_memory=1.5,
                speculative_fallback_count=None,
                speculative_num_draft_tokens=None,
                speculative_draft_model_configured=None,
                speculative_acceptance_rate=None,
                speculative_rollback_rate=None,
                speculative_accepted_tokens=None,
                speculative_rejected_tokens=None,
            )
            return

        self.acceleration_policies.append(acceleration_policy)
        yield SimpleNamespace(
            text="mtp ok",
            prompt_tokens=11,
            completion_tokens=5,
            generation_tps=45.0,
            peak_memory=1.75,
            speculative_fallback_count=0,
            speculative_num_draft_tokens=6,
            speculative_draft_model_configured=True,
            speculative_acceptance_rate=0.6,
            speculative_rollback_rate=0.4,
            speculative_accepted_tokens=12,
            speculative_rejected_tokens=8,
        )


def test_runtime_evidence_collects_baseline_and_mtp_metrics_without_download(tmp_path: Path) -> None:
    module = load_runtime_evidence_module()
    target_dir = tmp_path / "target"
    draft_dir = tmp_path / "draft"
    target_dir.mkdir()
    draft_dir.mkdir()
    runtime = FakeRuntime()

    report = module.run_runtime_evidence(
        target_model_id="mlx-community/gemma-4-E2B-it-qat-4bit",
        target_model_path=target_dir,
        draft_model_id="mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
        draft_model_path=draft_dir,
        prompt="Say hello.",
        max_tokens=16,
        num_draft_tokens=6,
        runtime_factory=lambda: runtime,
        download=False,
    )

    assert report["schema_version"] == "melix.gemma4_qat_runtime_evidence.v1"
    assert report["status"] == "passed"
    assert report["target"]["model_id"] == "mlx-community/gemma-4-E2B-it-qat-4bit"
    assert report["draft_companion"]["model_id"] == "mlx-community/gemma-4-E2B-it-qat-assistant-bf16"
    assert report["runtime"]["download_requested"] is False
    assert report["runtime"]["download_performed"] is False
    assert report["baseline"]["status"] == "passed"
    assert report["baseline"]["text"] == "baseline ok"
    assert report["baseline"]["completion_tokens"] == 4
    assert report["baseline"]["decode_tokens_per_second"] > 0.0
    assert report["baseline"]["peak_memory_gb"] == 1.5
    assert report["speculative_decode"]["status"] == "passed"
    assert report["speculative_decode"]["text"] == "mtp ok"
    assert report["speculative_decode"]["draft_model_configured"] is True
    assert report["speculative_decode"]["fallback_count"] == 0
    assert report["speculative_decode"]["acceptance_rate"] == 0.6
    assert report["speculative_decode"]["accepted_tokens"] == 12
    assert report["speculative_decode"]["decode_tokens_per_second"] > report["baseline"]["decode_tokens_per_second"]
    assert report["metrics"]["baseline_passed"] == 1.0
    assert report["metrics"]["speculative_passed"] == 1.0
    assert report["metrics"]["speculative_acceptance_rate"] == 0.6
    assert len(runtime.loaded_specs) == 1
    assert runtime.loaded_specs[0].model_path == str(target_dir)
    assert runtime.loaded_specs[0].ext["melix.qat.enabled"] == "true"
    assert runtime.acceleration_policies[0].draft_model_id == str(draft_dir)
    assert runtime.closed_models


def test_runtime_evidence_requires_cached_target_snapshot_without_download(tmp_path: Path) -> None:
    module = load_runtime_evidence_module()
    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="target model path does not exist"):
        module.run_runtime_evidence(
            target_model_id="mlx-community/gemma-4-E2B-it-qat-4bit",
            target_model_path=tmp_path / "missing-target",
            draft_model_id="mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
            draft_model_path=draft_dir,
            prompt="Say hello.",
            max_tokens=16,
            num_draft_tokens=6,
            runtime_factory=FakeRuntime,
            download=False,
        )


def test_runtime_evidence_requires_cached_draft_snapshot_without_download(tmp_path: Path) -> None:
    module = load_runtime_evidence_module()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="draft model path does not exist"):
        module.run_runtime_evidence(
            target_model_id="mlx-community/gemma-4-E2B-it-qat-4bit",
            target_model_path=target_dir,
            draft_model_id="mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
            draft_model_path=tmp_path / "missing-draft",
            prompt="Say hello.",
            max_tokens=16,
            num_draft_tokens=6,
            runtime_factory=FakeRuntime,
            download=False,
        )


def test_runtime_evidence_downloads_target_and_draft_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_runtime_evidence_module()
    target_dir = tmp_path / "downloaded-target"
    draft_dir = tmp_path / "downloaded-draft"
    target_dir.mkdir()
    draft_dir.mkdir()
    calls: list[str] = []

    def fake_download(model_id: str) -> Path:
        calls.append(model_id)
        return target_dir if "assistant" not in model_id else draft_dir

    runtime = FakeRuntime()
    monkeypatch.setattr(module, "download_snapshot", fake_download)

    report = module.run_runtime_evidence(
        target_model_id="mlx-community/gemma-4-E2B-it-qat-4bit",
        target_model_path=tmp_path / "missing-target",
        draft_model_id="mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
        draft_model_path=tmp_path / "missing-draft",
        prompt="Say hello.",
        max_tokens=16,
        num_draft_tokens=6,
        runtime_factory=lambda: runtime,
        download=True,
    )

    assert calls == [
        "mlx-community/gemma-4-E2B-it-qat-4bit",
        "mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
    ]
    assert report["runtime"]["download_requested"] is True
    assert report["runtime"]["download_performed"] is True
    assert report["draft_companion"]["model_path"] == str(draft_dir)
    assert runtime.acceleration_policies[0].draft_model_id == str(draft_dir)


def test_runtime_evidence_downloads_when_paths_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_runtime_evidence_module()
    target_dir = tmp_path / "downloaded-target"
    draft_dir = tmp_path / "downloaded-draft"
    target_dir.mkdir()
    draft_dir.mkdir()
    calls: list[str] = []

    def fake_download(model_id: str) -> Path:
        calls.append(model_id)
        return target_dir if "assistant" not in model_id else draft_dir

    runtime = FakeRuntime()
    monkeypatch.setattr(module, "download_snapshot", fake_download)

    report = module.run_runtime_evidence(
        target_model_id="mlx-community/gemma-4-E2B-it-qat-4bit",
        target_model_path=None,
        draft_model_id="mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
        draft_model_path=None,
        prompt="Say hello.",
        max_tokens=16,
        num_draft_tokens=6,
        runtime_factory=lambda: runtime,
        download=True,
    )

    assert calls == [
        "mlx-community/gemma-4-E2B-it-qat-4bit",
        "mlx-community/gemma-4-E2B-it-qat-assistant-bf16",
    ]
    assert report["runtime"]["download_performed"] is True
    assert report["target"]["model_path"] == str(target_dir)
    assert report["draft_companion"]["model_path"] == str(draft_dir)


def test_metrics_mode_emits_numeric_dry_run_payload(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    module = load_runtime_evidence_module()
    monkeypatch.setenv("MELIX_GEMMA4_QAT_RUNTIME_EVIDENCE_METRIC_ITERATIONS", "2")
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["gemma4_qat_runtime_evidence.py", "--metrics", "--dry-run"],
    )

    assert module.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_ok"] == 1.0
    assert payload["dry_run"] == 1.0
    assert payload["download_performed"] == 0.0
    assert payload["target_count"] == 2.0
    assert payload["iteration_count"] == 2.0
    assert payload["elapsed_ms_mean"] >= 0.0
