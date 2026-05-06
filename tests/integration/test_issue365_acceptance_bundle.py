from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "issue365_acceptance_bundle.py"
MODULE_SPEC = importlib.util.spec_from_file_location("issue365_acceptance_bundle", MODULE_PATH)
issue365_acceptance_bundle = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
sys.modules["issue365_acceptance_bundle"] = issue365_acceptance_bundle
MODULE_SPEC.loader.exec_module(issue365_acceptance_bundle)


class RecordingExecutor:
    def __init__(self, statuses: Sequence[str]) -> None:
        self.statuses = list(statuses)
        self.commands: list[list[str]] = []

    def run_json(self, command: Sequence[str]) -> dict[str, Any]:
        self.commands.append(list(command))
        status = self.statuses[min(len(self.commands) - 1, len(self.statuses) - 1)]
        return {
            "schema_version": "melix.pipeline.run.v1",
            "status": status,
            "summary_path": f"/tmp/issue365/{len(self.commands)}.json",
        }


class RaisingExecutor:
    def run_json(self, command: Sequence[str]) -> dict[str, Any]:
        raise RuntimeError(f"boom: {' '.join(command)}")


def _write_executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _real_config(
    tmp_path: Path,
    *,
    case_ids: tuple[str, ...] = (),
    execution_mode: str = "real",
) -> issue365_acceptance_bundle.Issue365AcceptanceConfig:
    prereqs = tmp_path / "real-prereqs"
    datasets = prereqs / "datasets"
    sft = datasets / "sft"
    preference = datasets / "preference_pair"
    prompt_candidate = datasets / "prompt_candidate"
    reward_scored = datasets / "reward_scored"
    calibration = datasets / "calibration"
    for path in (sft, preference, prompt_candidate, reward_scored, calibration):
        path.mkdir(parents=True, exist_ok=True)
    reward_manifest = prereqs / "reward-model" / "manifest.json"
    reward_manifest.parent.mkdir(parents=True, exist_ok=True)
    reward_manifest.write_text('{"schema_version":"melix.reward_model.v1"}\n', encoding="utf-8")
    melix_cli = _write_executable(prereqs / "melix")
    return issue365_acceptance_bundle.Issue365AcceptanceConfig(
        repo_root=Path(__file__).resolve().parents[2],
        output_dir=tmp_path / "bundle",
        execution_mode=execution_mode,
        melix_cli=str(melix_cli),
        sft_dataset_uri=str(sft),
        preference_dataset_uri=str(preference),
        prompt_candidate_dataset_uri=str(prompt_candidate),
        reward_scored_dataset_uri=str(reward_scored),
        calibration_dataset_uri=str(calibration),
        reward_model_manifest_path=str(reward_manifest),
        case_ids=case_ids,
        timestamp="2026-05-05T000000Z",
    )


def test_issue365_acceptance_bundle_plan_covers_required_cli_matrix(tmp_path: Path) -> None:
    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=Path(__file__).resolve().parents[2],
            output_dir=tmp_path,
            execution_mode="plan",
            timestamp="2026-05-05T000000Z",
        )
    )

    assert bundle["schema_version"] == "melix.issue365.acceptance_bundle.v1"
    assert bundle["issue_url"] == "https://github.com/Keith-CY/melix/issues/365"
    assert bundle["execution_mode"] == "plan"
    assert bundle["release_ready"] is False
    assert bundle["summary"]["case_count"] == 10
    assert bundle["summary"]["planned_count"] == 10
    assert bundle["summary"]["blocked_count"] == 0
    assert bundle["real_runtime_preflight"]["status"] == "not_run"

    case_ids = {case["case_id"] for case in bundle["cases"]}
    assert case_ids == {
        "lora_export_inference",
        "qlora_export_inference",
        "dora_export_inference",
        "lora_dpo_export_inference",
        "lora_orpo_export_inference",
        "lora_cpo_export_inference",
        "lora_grpo_export_inference",
        "lora_rlhf_export_inference",
        "lora_preference_ptq_quantized_inference",
        "qat_quantized_inference",
    }

    pipelines = [
        json.loads(Path(case["pipeline_path"]).read_text(encoding="utf-8"))
        for case in bundle["cases"]
    ]
    for pipeline in pipelines:
        assert pipeline["schema_version"] == "melix.pipeline.v1"
        assert pipeline["steps"]

    all_steps = [step for pipeline in pipelines for step in pipeline["steps"]]
    commands = {step["command"] for step in all_steps}
    assert {"lora.train", "alignment.train", "lora.publish", "quantize", "chat.run", "eval.run"} <= commands
    publish_steps = [step for step in all_steps if step["command"] == "lora.publish"]
    assert publish_steps
    assert all(step["args"]["publish_backend"] == "local_filesystem" for step in publish_steps)
    assert all(step["args"]["local_publish_root"] == "${inputs.local_publish_root}" for step in publish_steps)

    lora_pipeline = next(
        pipeline for pipeline in pipelines if pipeline["name"] == "issue365-lora_export_inference"
    )
    lora_steps = {step["id"]: step for step in lora_pipeline["steps"]}
    assert lora_steps["lora_activate"]["args"]["adapter_path"] == "${steps.lora_train.result.output_path}"
    assert lora_steps["lora_chat"]["args"]["model_id"] == "${steps.lora_activate.result.derived_model_id}"

    lora_modes = {
        step["args"].get("training_mode")
        for step in all_steps
        if step["command"] == "lora.train" and "training_mode" in step["args"]
    }
    assert {"lora", "qlora", "dora"} <= lora_modes

    alignment_algorithms = {
        step["args"]["algorithm"]
        for step in all_steps
        if step["command"] == "alignment.train"
    }
    assert alignment_algorithms == {"dpo", "orpo", "cpo", "grpo", "rlhf"}
    grpo_pipeline = next(
        pipeline
        for pipeline in pipelines
        if pipeline["name"] == "issue365-lora_grpo_export_inference"
    )
    grpo_steps = {step["id"]: step for step in grpo_pipeline["steps"]}
    assert grpo_steps["grpo_align"]["args"]["candidate_generation_mode"] == "runtime_generate"
    assert grpo_steps["grpo_align"]["args"]["candidate_scoring_mode"] == "reward_model"
    assert grpo_steps["grpo_align"]["args"]["reward_model_manifest_path"] == (
        "${inputs.reward_model_manifest_path}"
    )
    assert grpo_steps["grpo_align"]["args"]["candidate_generation_max_tokens"] == 16

    quantization_modes = {
        step["args"]["quantization_mode"]
        for step in all_steps
        if step["command"] == "quantize"
    }
    assert quantization_modes == {"ptq", "qat"}
    ptq_pipeline = next(
        pipeline
        for pipeline in pipelines
        if pipeline["name"] == "issue365-lora_preference_ptq_quantized_inference"
    )
    ptq_steps = {step["id"]: step for step in ptq_pipeline["steps"]}
    assert ptq_steps["ptq_fuse_merged_model"]["command"] == "lora.activate"
    assert ptq_steps["ptq_fuse_merged_model"]["args"]["activation_mode"] == "fused_derived_model"
    assert ptq_steps["ptq_publish_export"]["args"]["merged_model_path"] == (
        "${steps.ptq_fuse_merged_model.result.derived_model_path}"
    )
    assert ptq_steps["ptq_publish_export"]["args"]["export_kind"] == "merged"
    assert ptq_steps["ptq_quantize"]["args"]["source_artifact_kind"] == "merged_adapter"
    assert ptq_steps["ptq_quantize"]["args"]["quantization_backend"] == "mlx_lm_convert"
    assert ptq_steps["ptq_quantize"]["args"]["mlx_lm_q_mode"] == "affine"
    assert ptq_steps["ptq_quantize"]["args"]["local_inference_smoke_mode"] == "runtime_generate"
    assert ptq_steps["ptq_quantize"]["checks"]["equals"] == {
        "result.local_inference_smoke.status": "passed",
        "result.local_inference_smoke.evidence_kind": "local_runtime_generate",
        "result.local_inference_smoke.smoke_mode": "runtime_generate",
        "result.release_gate.local_inference_smoke_result": "passed",
    }
    assert all(step["command"] != "chat.run" for step in ptq_pipeline["steps"])
    qat_pipeline = next(
        pipeline
        for pipeline in pipelines
        if pipeline["name"] == "issue365-qat_quantized_inference"
    )
    qat_steps = {step["id"]: step for step in qat_pipeline["steps"]}
    assert qat_steps["qat_train"]["args"]["total_layers"] == 2
    assert qat_steps["qat_train"]["args"]["num_layers"] == 2
    assert qat_steps["qat_fuse_merged_model"]["command"] == "lora.activate"
    assert qat_steps["qat_fuse_merged_model"]["args"]["activation_mode"] == "fused_derived_model"
    assert qat_steps["qat_publish_export"]["args"]["merged_model_path"] == (
        "${steps.qat_fuse_merged_model.result.derived_model_path}"
    )
    assert qat_steps["qat_publish_export"]["args"]["export_kind"] == "merged"
    assert qat_steps["qat_quantize"]["args"]["source_artifact_kind"] == "merged_adapter"
    assert qat_steps["qat_quantize"]["args"]["quantization_backend"] == "mlx_lm_convert"
    assert qat_steps["qat_quantize"]["args"]["mlx_lm_q_mode"] == "affine"
    assert qat_steps["qat_quantize"]["args"]["local_inference_smoke_mode"] == "runtime_generate"
    assert qat_steps["qat_quantize"]["checks"] == ptq_steps["ptq_quantize"]["checks"]
    assert all(step["command"] != "chat.run" for step in qat_pipeline["steps"])
    assert any("real_local_runtime" in gap for gap in bundle["known_gaps"])
    assert all(case["evidence_tier"] == "planning_matrix" for case in bundle["cases"])
    assert all(case["release_ready"] is False for case in bundle["cases"])


def test_issue365_acceptance_bundle_dry_run_invokes_pipeline_runner_without_release_ready(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor(statuses=["planned"])
    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=Path(__file__).resolve().parents[2],
            output_dir=tmp_path,
            execution_mode="dry-run",
            melix_cli="/tmp/melix",
            timestamp="2026-05-05T000000Z",
        ),
        executor=executor,
    )

    assert len(executor.commands) == 10
    assert all(command[:3] == ["/tmp/melix", "pipeline", "run"] for command in executor.commands)
    assert all("--dry-run" in command for command in executor.commands)
    assert bundle["release_ready"] is False
    assert bundle["summary"]["planned_count"] == 10
    assert all(case["evidence_tier"] == "deterministic_dry_run" for case in bundle["cases"])
    assert all("non_dry_run_execution" in case["missing_evidence"] for case in bundle["cases"])


def test_issue365_acceptance_bundle_real_success_is_release_ready_only_after_all_cases_pass(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor(statuses=["succeeded"])
    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        _real_config(tmp_path),
        executor=executor,
    )

    assert len(executor.commands) == 10
    assert all("--dry-run" not in command for command in executor.commands)
    assert bundle["release_ready"] is True
    assert bundle["known_gaps"] == []
    assert bundle["summary"]["release_ready_case_count"] == 10
    assert bundle["real_runtime_preflight"]["status"] == "ready"
    assert all(case["evidence_tier"] == "real_local_runtime" for case in bundle["cases"])
    assert all(case["missing_evidence"] == [] for case in bundle["cases"])
    assert all(case["real_runtime_preflight"]["ready"] is True for case in bundle["cases"])


def test_issue365_acceptance_bundle_real_failure_keeps_bundle_not_release_ready(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor(statuses=["succeeded", "failed"])
    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        _real_config(tmp_path),
        executor=executor,
    )

    assert bundle["release_ready"] is False
    assert bundle["summary"]["failed_count"] == 9
    assert bundle["summary"]["release_ready_case_count"] == 1
    assert "passing_pipeline_summary" in bundle["known_gaps"]


def test_issue365_acceptance_bundle_real_preflight_blocks_missing_local_inputs(
    tmp_path: Path,
) -> None:
    melix_cli = _write_executable(tmp_path / "melix")
    executor = RecordingExecutor(statuses=["succeeded"])

    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=Path(__file__).resolve().parents[2],
            output_dir=tmp_path / "bundle",
            execution_mode="real",
            melix_cli=str(melix_cli),
            sft_dataset_uri=str(tmp_path / "missing-sft"),
            reward_scored_dataset_uri=str(tmp_path / "missing-reward-scored"),
            reward_model_manifest_path=str(tmp_path / "missing-reward-model.json"),
            case_ids=("lora_export_inference", "lora_rlhf_export_inference"),
            timestamp="2026-05-05T000000Z",
        ),
        executor=executor,
    )

    assert executor.commands == []
    assert bundle["release_ready"] is False
    assert bundle["real_runtime_preflight"]["status"] == "blocked"
    assert bundle["summary"]["case_count"] == 2
    assert bundle["summary"]["blocked_count"] == 2
    assert all(case["status"] == "blocked" for case in bundle["cases"])
    assert all("real_local_runtime_preflight" in case["missing_evidence"] for case in bundle["cases"])
    rlhf = next(case for case in bundle["cases"] if case["case_id"] == "lora_rlhf_export_inference")
    blocker_codes = {blocker["code"] for blocker in rlhf["real_runtime_preflight"]["blockers"]}
    assert {"missing_sft_dataset_uri", "missing_reward_scored_dataset_uri", "missing_reward_model_manifest_path"} <= blocker_codes


def test_issue365_acceptance_bundle_real_preflight_blocks_grpo_without_reward_model(
    tmp_path: Path,
) -> None:
    melix_cli = _write_executable(tmp_path / "melix")
    sft = tmp_path / "datasets" / "sft"
    prompt_candidate = tmp_path / "datasets" / "prompt_candidate"
    sft.mkdir(parents=True)
    prompt_candidate.mkdir(parents=True)
    executor = RecordingExecutor(statuses=["succeeded"])

    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=Path(__file__).resolve().parents[2],
            output_dir=tmp_path / "bundle",
            execution_mode="real",
            melix_cli=str(melix_cli),
            sft_dataset_uri=str(sft),
            prompt_candidate_dataset_uri=str(prompt_candidate),
            reward_model_manifest_path=str(tmp_path / "missing-reward-model.json"),
            case_ids=("lora_grpo_export_inference",),
            timestamp="2026-05-05T000000Z",
        ),
        executor=executor,
    )

    assert executor.commands == []
    assert bundle["summary"]["blocked_count"] == 1
    blockers = bundle["cases"][0]["real_runtime_preflight"]["blockers"]
    assert {blocker["code"] for blocker in blockers} == {"missing_reward_model_manifest_path"}


def test_issue365_acceptance_bundle_real_case_filter_runs_only_selected_ready_case(
    tmp_path: Path,
) -> None:
    prereqs = tmp_path / "minimal-real-prereqs"
    sft = prereqs / "datasets" / "sft"
    sft.mkdir(parents=True)
    melix_cli = _write_executable(prereqs / "melix")
    executor = RecordingExecutor(statuses=["succeeded"])

    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=prereqs,
            output_dir=tmp_path / "bundle",
            execution_mode="real",
            melix_cli=str(melix_cli),
            sft_dataset_uri="datasets/sft",
            preference_dataset_uri=str(tmp_path / "missing-preference"),
            prompt_candidate_dataset_uri=str(tmp_path / "missing-prompt-candidate"),
            reward_scored_dataset_uri=str(tmp_path / "missing-reward-scored"),
            calibration_dataset_uri=str(tmp_path / "missing-calibration"),
            reward_model_manifest_path=str(tmp_path / "missing-reward-model.json"),
            case_ids=("lora_export_inference",),
            timestamp="2026-05-05T000000Z",
        ),
        executor=executor,
    )

    assert len(executor.commands) == 1
    assert bundle["release_ready"] is True
    assert bundle["selected_case_ids"] == ["lora_export_inference"]
    assert bundle["summary"]["case_count"] == 1
    assert bundle["cases"][0]["real_runtime_preflight"]["required_inputs"] == ["sft_dataset_uri"]
    input_check = bundle["cases"][0]["real_runtime_preflight"]["checks"]["inputs"][0]
    assert input_check["resolved_path"] == str(sft)


def test_issue365_acceptance_bundle_real_preflight_blocks_empty_required_inputs(
    tmp_path: Path,
) -> None:
    prereqs = tmp_path / "empty-required-prereqs"
    sft = prereqs / "datasets" / "sft"
    reward_scored = prereqs / "datasets" / "reward_scored"
    sft.mkdir(parents=True)
    reward_scored.mkdir(parents=True)
    melix_cli = _write_executable(prereqs / "melix")
    executor = RecordingExecutor(statuses=["succeeded"])

    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=Path(__file__).resolve().parents[2],
            output_dir=tmp_path / "bundle",
            execution_mode="real",
            melix_cli=str(melix_cli),
            sft_dataset_uri=str(sft),
            reward_scored_dataset_uri=str(reward_scored),
            reward_model_manifest_path="",
            case_ids=("lora_rlhf_export_inference",),
            timestamp="2026-05-05T000000Z",
        ),
        executor=executor,
    )

    assert executor.commands == []
    assert bundle["summary"]["blocked_count"] == 1
    blockers = bundle["cases"][0]["real_runtime_preflight"]["blockers"]
    assert {blocker["code"] for blocker in blockers} == {"empty_reward_model_manifest_path"}


def test_issue365_acceptance_bundle_records_executor_errors(tmp_path: Path) -> None:
    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=Path(__file__).resolve().parents[2],
            output_dir=tmp_path,
            execution_mode="dry-run",
            melix_cli="/tmp/melix",
            timestamp="2026-05-05T000000Z",
        ),
        executor=RaisingExecutor(),
    )

    assert bundle["release_ready"] is False
    assert bundle["summary"]["failed_count"] == 10
    assert all(case["status"] == "failed" for case in bundle["cases"])
    assert all(case["error"].startswith("boom: /tmp/melix pipeline run") for case in bundle["cases"])


def test_issue365_acceptance_bundle_uses_default_subprocess_executor_when_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created: list[Path] = []

    class FakeSubprocessExecutor:
        def __init__(self, *, repo_root: Path) -> None:
            created.append(repo_root)

        def run_json(self, command: Sequence[str]) -> dict[str, Any]:
            return {
                "schema_version": "melix.pipeline.run.v1",
                "status": "planned",
                "summary_path": "/tmp/issue365/default-executor.json",
            }

    monkeypatch.setattr(issue365_acceptance_bundle, "SubprocessJSONExecutor", FakeSubprocessExecutor)

    bundle = issue365_acceptance_bundle.build_acceptance_bundle(
        issue365_acceptance_bundle.Issue365AcceptanceConfig(
            repo_root=Path("/tmp/repo"),
            output_dir=tmp_path,
            execution_mode="dry-run",
            melix_cli="/tmp/melix",
            timestamp="2026-05-05T000000Z",
        )
    )

    assert created == [Path("/tmp/repo")]
    assert bundle["summary"]["planned_count"] == 10


def test_issue365_acceptance_bundle_rejects_invalid_execution_mode(tmp_path: Path) -> None:
    try:
        issue365_acceptance_bundle.build_acceptance_bundle(
            issue365_acceptance_bundle.Issue365AcceptanceConfig(
                repo_root=Path(__file__).resolve().parents[2],
                output_dir=tmp_path,
                execution_mode="screenshots",
            )
        )
    except ValueError as exc:
        assert "execution_mode" in str(exc)
    else:
        raise AssertionError("Expected invalid execution mode to raise")


def test_issue365_acceptance_bundle_rejects_unknown_case_id(tmp_path: Path) -> None:
    try:
        issue365_acceptance_bundle.build_acceptance_bundle(
            issue365_acceptance_bundle.Issue365AcceptanceConfig(
                repo_root=Path(__file__).resolve().parents[2],
                output_dir=tmp_path,
                case_ids=("missing_case",),
            )
        )
    except ValueError as exc:
        assert "missing_case" in str(exc)
    else:
        raise AssertionError("Expected unknown case_id to raise")


def test_subprocess_json_executor_covers_success_and_failure_edges(tmp_path: Path) -> None:
    executor = issue365_acceptance_bundle.SubprocessJSONExecutor(repo_root=tmp_path, environment={})

    payload = executor.run_json(
        [
            sys.executable,
            "-c",
            "import json; print(json.dumps({'status': 'succeeded'}))",
        ]
    )
    assert payload == {"status": "succeeded"}

    for command, expected in [
        ([sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(3)"], "exit code 3"),
        ([sys.executable, "-c", "print('not json')"], "did not return JSON"),
        ([sys.executable, "-c", "import json; print(json.dumps([1, 2]))"], "non-object JSON"),
    ]:
        try:
            executor.run_json(command)
        except RuntimeError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"Expected {command} to fail")


def test_issue365_acceptance_bundle_main_writes_json_and_text_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    json_output_dir = tmp_path / "json"
    result = issue365_acceptance_bundle.main(
        [
            "--execution-mode",
            "plan",
            "--output-dir",
            str(json_output_dir),
            "--timestamp",
            "2026-05-05T000000Z",
            "--case-id",
            "lora_export_inference",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert payload["bundle_path"] == str(json_output_dir.resolve() / "bundle.json")
    assert payload["release_ready"] is False
    assert payload["selected_case_ids"] == ["lora_export_inference"]

    text_output_dir = tmp_path / "text"
    result = issue365_acceptance_bundle.main(
        [
            "--execution-mode",
            "plan",
            "--output-dir",
            str(text_output_dir),
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert str(text_output_dir.resolve() / "bundle.json") in captured.out
    assert "release_ready=false" in captured.out
