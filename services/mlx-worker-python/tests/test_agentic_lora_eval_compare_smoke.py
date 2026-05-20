from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "agentic_lora_eval_compare_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "agentic_lora_eval_compare_smoke",
    MODULE_PATH,
)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
agentic_lora_eval_compare_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(agentic_lora_eval_compare_smoke)


def test_agentic_lora_eval_compare_smoke_persists_paired_evidence(
    tmp_path: Path,
) -> None:
    payload = agentic_lora_eval_compare_smoke.run_eval_compare_smoke(
        REPO_ROOT,
        output_dir=tmp_path / "eval-compare-output",
    )

    assert payload["passed"] is True
    assert all(payload["checks"].values())
    assert payload["activation"]["activation_mode"] == "adapter_backed_runtime"
    assert payload["activation"]["activation_backend"] == "internal"
    assert payload["compare"]["base_accuracy"] == 0.0
    assert payload["compare"]["target_accuracy"] == 1.0
    assert payload["compare"]["delta_accuracy"] == 1.0
    assert payload["compare"]["win_count"] == 1
    assert payload["compare"]["loss_count"] == 0
    assert payload["compare"]["regression_count"] == 0
    assert payload["paired_sample"] == {
        "sample_id": "agentic-smoke-valid-1",
        "target_model_id": payload["activation"]["derived_model_id"],
        "target": "VX-204",
        "base_raw_response": "Answer: VX-000",
        "target_raw_response": "Answer: VX-204",
        "base_extracted_result": "VX-000",
        "target_extracted_result": "VX-204",
        "base_typed_score": 0.0,
        "target_typed_score": 1.0,
        "outcome": "win",
        "regression_kind": "",
    }
    assert payload["metrics"]["agentic_lora_eval_compare.paired_sample_count"] == 1.0
    assert payload["metrics"]["agentic_lora_eval_compare.activated_adapter_target_count"] == 1.0

    artifacts = payload["artifacts"]
    for path in artifacts.values():
        assert Path(path).is_file()

    activation_manifest = json.loads(
        Path(artifacts["activation_manifest"]).read_text(encoding="utf-8")
    )
    assert activation_manifest["derived_model_id"] == payload["activation"]["derived_model_id"]
    assert activation_manifest["activation_mode"] == "adapter_backed_runtime"

    compare_job = json.loads(
        Path(artifacts["compare_job"]).read_text(encoding="utf-8")
    )
    assert compare_job["base_model_id"] == "agentic-lora-sft-smoke-model"
    assert compare_job["target_model_ids"] == [payload["activation"]["derived_model_id"]]
    assert compare_job["target_lineage"] == [
        {
            "target_model_id": payload["activation"]["derived_model_id"],
            "materialization_kind": "registered",
            "adapter_manifest_path": "",
            "adapter_weights_path": "",
            "adapter_set_hash": "",
            "derived_from_model_id": "",
        }
    ]
    assert compare_job["parameters"]["activation_manifest_path"] == artifacts["activation_manifest"]
    assert compare_job["parameters"]["source_training_objective"] == "agentic_sft"

    compare_samples = _jsonl_rows(Path(artifacts["compare_samples_jsonl"]))
    assert compare_samples == [
        {
            "schema_version": "melix.evaluation_compare_sample.v2",
            "job_id": payload["compare"]["job_id"],
            "suite_id": "agentic_tool_trace_eval",
            "dataset_id": "agentic-lora-sft-smoke.eval.v1",
            "sample_id": "agentic-smoke-valid-1",
            "target_model_id": payload["activation"]["derived_model_id"],
            "input_text": compare_samples[0]["input_text"],
            "target": "VX-204",
            "base_extracted_result": "VX-000",
            "target_extracted_result": "VX-204",
            "base_raw_response": "Answer: VX-000",
            "target_raw_response": "Answer: VX-204",
            "base_typed_score": 0.0,
            "target_typed_score": 1.0,
            "outcome": "win",
            "regression_kind": "",
            "base_time_s": compare_samples[0]["base_time_s"],
            "target_time_s": compare_samples[0]["target_time_s"],
            "base_extraction_status": "extracted",
            "target_extraction_status": "extracted",
            "base_validation_status": "validated",
            "target_validation_status": "validated",
            "base_failure_reason": "",
            "target_failure_reason": "",
            "base_parse_status": "extracted",
            "target_parse_status": "extracted",
            "code_language": "",
            "code_entry_point": "",
            "base_code_compile_status": "",
            "target_code_compile_status": "",
            "base_code_runtime_status": "",
            "target_code_runtime_status": "",
            "base_code_timeout_status": "",
            "target_code_timeout_status": "",
            "base_code_test_status": "",
            "target_code_test_status": "",
            "base_code_tests_passed": 0,
            "target_code_tests_passed": 0,
            "base_code_tests_total": 0,
            "target_code_tests_total": 0,
            "base_code_failure_detail": "",
            "target_code_failure_detail": "",
            "category_label": "agentic_tool_trace",
            "subject_label": "activated_adapter_compare",
        }
    ]
    assert "Agentic tool observations:" in compare_samples[0]["input_text"]
    assert "VX-204" in compare_samples[0]["input_text"]

    evidence = json.loads(Path(artifacts["evidence_json"]).read_text(encoding="utf-8"))
    assert evidence == payload


def test_agentic_lora_eval_compare_smoke_main_supports_json_and_text_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        agentic_lora_eval_compare_smoke,
        "run_eval_compare_smoke",
        lambda repo_root, output_dir=None, fixture_id="agentic-lora-sft-smoke.dev.v1": {
            "passed": True,
            "repo_root": str(repo_root),
            "output_dir": str(output_dir or tmp_path),
            "fixture_id": fixture_id,
            "metrics": {"agentic_lora_eval_compare.delta_accuracy": 1.0},
        },
    )
    monkeypatch.setattr(
        agentic_lora_eval_compare_smoke.sys,
        "argv",
        [
            "agentic_lora_eval_compare_smoke.py",
            "--repo-root",
            str(REPO_ROOT),
            "--output-dir",
            str(tmp_path / "json-output"),
            "--json",
        ],
    )

    assert agentic_lora_eval_compare_smoke.main() == 0
    json_output = capsys.readouterr().out
    assert '"passed": true' in json_output
    assert '"agentic_lora_eval_compare.delta_accuracy": 1.0' in json_output

    monkeypatch.setattr(
        agentic_lora_eval_compare_smoke.sys,
        "argv",
        [
            "agentic_lora_eval_compare_smoke.py",
            "--repo-root",
            str(REPO_ROOT),
            "--output-dir",
            str(tmp_path / "text-output"),
        ],
    )

    assert agentic_lora_eval_compare_smoke.main() == 0
    text_output = capsys.readouterr().out
    assert "Agentic LoRA eval compare smoke passed." in text_output
    assert "agentic-lora-sft-smoke.dev.v1" in text_output


def test_agentic_lora_eval_compare_smoke_main_returns_nonzero_when_check_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        agentic_lora_eval_compare_smoke,
        "run_eval_compare_smoke",
        lambda repo_root, output_dir=None, fixture_id="agentic-lora-sft-smoke.dev.v1": {
            "passed": False,
            "fixture_id": fixture_id,
            "checks": {"target_improves_base": False},
        },
    )
    monkeypatch.setattr(
        agentic_lora_eval_compare_smoke.sys,
        "argv",
        ["agentic_lora_eval_compare_smoke.py", "--repo-root", str(REPO_ROOT), "--json"],
    )

    assert agentic_lora_eval_compare_smoke.main() == 1
    output = capsys.readouterr().out
    assert '"passed": false' in output
    assert '"target_improves_base": false' in output


def test_agentic_lora_eval_compare_smoke_covers_default_output_and_missing_inputs(
    tmp_path: Path,
) -> None:
    payload = agentic_lora_eval_compare_smoke.run_eval_compare_smoke(REPO_ROOT)

    assert payload["passed"] is True
    assert Path(payload["output_dir"]).name.startswith("melix-agentic-lora-eval-compare-")
    assert Path(payload["artifacts"]["evidence_json"]).is_file()
    assert agentic_lora_eval_compare_smoke._read_jsonl(tmp_path / "missing.jsonl") == []

    with pytest.raises(FileNotFoundError):
        agentic_lora_eval_compare_smoke.run_eval_compare_smoke(
            REPO_ROOT,
            fixture_id="missing-fixture",
        )


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
