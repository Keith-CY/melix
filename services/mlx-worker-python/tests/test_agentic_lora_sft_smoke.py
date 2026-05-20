from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "agentic_lora_sft_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("agentic_lora_sft_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
agentic_lora_sft_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(agentic_lora_sft_smoke)


def test_agentic_lora_sft_smoke_runs_pipeline_and_persists_evidence(
    tmp_path: Path,
) -> None:
    payload = agentic_lora_sft_smoke.run_smoke(
        REPO_ROOT,
        output_dir=tmp_path / "smoke-output",
    )

    assert payload["passed"] is True
    assert all(payload["checks"].values())
    assert payload["training_backend"] == "native"
    assert payload["manifest"] == {
        "dataset_id": "agentic-lora-sft-smoke.dev.v1",
        "dataset_format": "agentic_tool_trace",
        "trainer_dataset_format": "chat_messages",
        "training_objective": "agentic_sft",
        "dataset_contract": "agentic_tool_trace",
        "trajectory_dataset_id": "agentic-lora-sft-smoke",
        "trajectory_trace_digest": payload["manifest"]["trajectory_trace_digest"],
        "trajectory_provenance_field_count": payload["manifest"][
            "trajectory_provenance_field_count"
        ],
    }
    assert payload["manifest"]["trajectory_trace_digest"]
    assert payload["manifest"]["trajectory_provenance_field_count"] >= 10
    assert payload["metrics"]["agentic_lora_sft_smoke.source_trace_count"] == 1.0
    assert (
        payload["metrics"]["agentic_lora_sft_smoke.source_trace_validation_sample_count"]
        == 1.0
    )
    assert payload["metrics"]["agentic_lora_sft_smoke.trainer_row_count"] == 2.0
    assert payload["metrics"]["agentic_lora_sft_smoke.trainer_validation_row_count"] == 2.0
    assert payload["metrics"]["agentic_lora_sft_smoke.tool_call_count"] == 2.0
    assert payload["metrics"]["agentic_lora_sft_smoke.observation_count"] == 2.0
    assert payload["metrics"]["agentic_lora_sft_smoke.response_only_boundary_count"] == 4.0
    assert payload["projection_metrics"]["final_answer_count"] == 2
    assert payload["token_metrics"]["estimator"] == "whitespace_v1"
    assert payload["token_metrics"]["source_trace_count"] == 2
    assert payload["quality_metrics"]["dirty_count"] == 0
    assert payload["quality_metrics"]["leakage_count"] == 0

    normalized_manifest_path = Path(payload["normalized_dataset_manifest_path"])
    adapter_manifest_path = Path(payload["adapter_manifest_path"])
    assert normalized_manifest_path.is_file()
    assert adapter_manifest_path.is_file()

    normalized_dir = normalized_manifest_path.parent
    train_rows = _jsonl_rows(normalized_dir / "train.jsonl")
    valid_rows = _jsonl_rows(normalized_dir / "valid.jsonl")
    trace_train_rows = _jsonl_rows(normalized_dir / "agentic-traces.train.jsonl")
    trace_valid_rows = _jsonl_rows(normalized_dir / "agentic-traces.valid.jsonl")
    assert [row["response_only_boundary"]["trainable_kind"] for row in train_rows] == [
        "tool_call",
        "final_answer",
    ]
    assert [row["response_only_boundary"]["trainable_kind"] for row in valid_rows] == [
        "tool_call",
        "final_answer",
    ]
    assert trace_train_rows[0]["trace_id"] == "agentic-smoke-train-1"
    assert trace_valid_rows[0]["trace_id"] == "agentic-smoke-valid-1"

    adapter_manifest = json.loads(adapter_manifest_path.read_text(encoding="utf-8"))
    assert adapter_manifest["training.agentic_sft.source_trace_count"] == 2
    assert adapter_manifest["training.agentic_sft.tool_call_tokens"] > 0
    assert adapter_manifest["training.agentic_sft.observation_tokens"] > 0
    assert adapter_manifest["training.agentic_sft.final_answer_tokens"] > 0


def test_agentic_lora_sft_smoke_main_supports_json_and_text_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        agentic_lora_sft_smoke,
        "run_smoke",
        lambda repo_root, output_dir=None, fixture_id="agentic-lora-sft-smoke.dev.v1": {
            "passed": True,
            "repo_root": str(repo_root),
            "output_dir": str(output_dir or tmp_path),
            "fixture_id": fixture_id,
            "metrics": {"agentic_lora_sft_smoke.trainer_row_count": 4.0},
        },
    )
    monkeypatch.setattr(
        agentic_lora_sft_smoke.sys,
        "argv",
        [
            "agentic_lora_sft_smoke.py",
            "--repo-root",
            str(REPO_ROOT),
            "--output-dir",
            str(tmp_path / "json-output"),
            "--json",
        ],
    )

    assert agentic_lora_sft_smoke.main() == 0
    json_output = capsys.readouterr().out
    assert '"passed": true' in json_output
    assert '"agentic_lora_sft_smoke.trainer_row_count": 4.0' in json_output

    monkeypatch.setattr(
        agentic_lora_sft_smoke.sys,
        "argv",
        [
            "agentic_lora_sft_smoke.py",
            "--repo-root",
            str(REPO_ROOT),
            "--output-dir",
            str(tmp_path / "text-output"),
        ],
    )

    assert agentic_lora_sft_smoke.main() == 0
    text_output = capsys.readouterr().out
    assert "Agentic LoRA SFT smoke passed." in text_output
    assert "agentic-lora-sft-smoke.dev.v1" in text_output


def test_agentic_lora_sft_smoke_main_returns_nonzero_when_check_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        agentic_lora_sft_smoke,
        "run_smoke",
        lambda repo_root, output_dir=None, fixture_id="agentic-lora-sft-smoke.dev.v1": {
            "passed": False,
            "fixture_id": fixture_id,
            "checks": {"trainer_chat_messages": False},
        },
    )
    monkeypatch.setattr(
        agentic_lora_sft_smoke.sys,
        "argv",
        ["agentic_lora_sft_smoke.py", "--repo-root", str(REPO_ROOT), "--json"],
    )

    assert agentic_lora_sft_smoke.main() == 1
    output = capsys.readouterr().out
    assert '"passed": false' in output
    assert '"trainer_chat_messages": false' in output


def test_agentic_lora_sft_smoke_covers_default_output_and_missing_inputs(
    tmp_path: Path,
) -> None:
    payload = agentic_lora_sft_smoke.run_smoke(REPO_ROOT)

    assert payload["passed"] is True
    assert Path(payload["output_dir"]).name.startswith("melix-agentic-lora-sft-smoke-")
    assert Path(payload["adapter_manifest_path"]).is_file()
    assert agentic_lora_sft_smoke._read_jsonl(tmp_path / "missing.jsonl") == []

    with pytest.raises(FileNotFoundError):
        agentic_lora_sft_smoke.run_smoke(REPO_ROOT, fixture_id="missing-fixture")


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
