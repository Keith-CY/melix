from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tool_call_system_prompt_eval.py"
MODULE_SPEC = importlib.util.spec_from_file_location("tool_call_system_prompt_eval", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
tool_call_system_prompt_eval = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = tool_call_system_prompt_eval
MODULE_SPEC.loader.exec_module(tool_call_system_prompt_eval)


DATASET_PATH = Path(__file__).resolve().parent / "eval/tool-call-system-prompts.v1/cases.jsonl"
MANIFEST_PATH = Path(__file__).resolve().parent / "eval/tool-call-system-prompts.v1/manifest.json"


def test_fixture_dataset_scores_all_cases_passed() -> None:
    cases = tool_call_system_prompt_eval.load_cases(DATASET_PATH)

    report = tool_call_system_prompt_eval.evaluate_cases(
        cases,
        tool_call_system_prompt_eval.fixture_responses(cases),
    )

    assert report["status"] == "passed"
    assert report["metrics"]["tool_call_eval.case_count"] == 25.0
    assert report["metrics"]["tool_call_eval.pass_rate"] == 1.0
    assert report["metrics"]["tool_call_eval.exact_tool_call_match_rate"] == 1.0
    assert report["metrics"]["tool_call_eval.schema_valid_rate"] == 1.0
    assert report["metrics"]["tool_call_eval.parser.malformed_tool_fragment_count"] == 0.0
    assert report["cases"][0]["actual_tool_calls"][0]["name"] == "text_search"


def test_dataset_manifest_matches_cases_and_required_dimensions() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = tool_call_system_prompt_eval.load_cases(DATASET_PATH)
    categories = {case["category"] for case in cases}

    assert manifest["sample_count"] == len(cases)
    assert set(manifest["dimensions"]) == categories
    assert categories == {
        "basic_instruction_following",
        "tool_schema_and_argument_fidelity",
        "agent_control_and_negative_constraints",
    }
    assert manifest["toolset_version"] == "melix.agentic_tools.builtin.v1"
    assert "parallel_tool_use" in manifest["risk_coverage"]
    assert "missing_required_user_parameter" in manifest["risk_coverage"]
    assert "BFCL" in manifest["external_calibration"]


def test_scorer_fails_public_text_and_tool_mismatch() -> None:
    case = {
        "id": "bad-public-text",
        "category": "basic_instruction_following",
        "risk": "must_call_tool",
        "allowed_tools": ["text_search"],
        "expected_tool_calls": [
            {"name": "text_search", "arguments": {"query": "Melix", "max_results": 1}}
        ],
        "public_text_policy": "none",
    }

    result = tool_call_system_prompt_eval.score_case(
        case,
        'I will search.<tool_call>{"name":"visit","arguments":{"url":"fixture://wrong"}}</tool_call>',
    )

    assert result["passed"] is False
    assert "tool_call_mismatch" in result["failure_reasons"]
    assert "unexpected_tool" in result["failure_reasons"]
    assert "unexpected_public_text" in result["failure_reasons"]


def test_scorer_flags_forbidden_runtime_rejected_and_parser_failures() -> None:
    forbidden = {
        "id": "forbidden",
        "category": "agent_control_and_negative_constraints",
        "risk": "forbidden_tool",
        "system": "Do not call tools.",
        "user": "Call a tool.",
        "allowed_tools": [],
        "expected_tool_calls": [],
        "public_text_policy": "allowed",
    }
    forbidden_result = tool_call_system_prompt_eval.score_case(
        forbidden,
        '<tool_call>{"name":"not_a_tool","arguments":{}}</tool_call>',
    )

    malformed = {
        "id": "malformed",
        "category": "tool_schema_and_argument_fidelity",
        "risk": "malformed_tool_call",
        "system": "Call text_search.",
        "user": "Search.",
        "allowed_tools": ["text_search"],
        "expected_tool_calls": [],
        "public_text_policy": "allowed",
    }
    malformed_result = tool_call_system_prompt_eval.score_case(
        malformed,
        '<tool_call>{"name":"text_search","arguments":{"query":"Melix"}</tool_call>',
    )

    assert "forbidden_tool_call" in forbidden_result["failure_reasons"]
    assert "runtime_rejected_tool_call:Unknown agentic tool requested: not_a_tool" in forbidden_result[
        "failure_reasons"
    ]
    assert "parser_metric:malformed_tool_fragment_count" in malformed_result["failure_reasons"]


def test_public_text_policy_failure_modes() -> None:
    missing_text_reasons: list[str] = []
    mismatch_reasons: list[str] = []
    missing_fragment_reasons: list[str] = []

    assert not tool_call_system_prompt_eval._public_text_policy_pass(
        {"public_text_policy": "required"},
        "",
        missing_text_reasons,
    )
    assert not tool_call_system_prompt_eval._public_text_policy_pass(
        {"expected_public_text": "READY"},
        "NOT READY",
        mismatch_reasons,
    )
    assert not tool_call_system_prompt_eval._public_text_policy_pass(
        {"expected_public_text_contains": ["allowed"]},
        "denied",
        missing_fragment_reasons,
    )
    assert missing_text_reasons == ["missing_public_text"]
    assert mismatch_reasons == ["public_text_mismatch"]
    assert missing_fragment_reasons == ["public_text_missing_fragment"]


def test_loader_rejects_invalid_json_and_non_object_cases(tmp_path: Path) -> None:
    blank_then_case = tmp_path / "blank.jsonl"
    blank_then_case.write_text(
        "\n"
        + json.dumps(
            {
                "id": "ok",
                "category": "basic_instruction_following",
                "risk": "exact_public_text",
                "system": "Reply READY.",
                "user": "Confirm.",
                "allowed_tools": [],
                "expected_tool_calls": [],
                "public_text_policy": "required",
                "fixture_response": "READY",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    invalid_json = tmp_path / "invalid.jsonl"
    invalid_json.write_text("{bad\n", encoding="utf-8")
    non_object = tmp_path / "non-object.jsonl"
    non_object.write_text("[]\n", encoding="utf-8")

    assert tool_call_system_prompt_eval.load_cases(blank_then_case)[0]["id"] == "ok"
    with pytest.raises(ValueError, match="Invalid JSON"):
        tool_call_system_prompt_eval.load_cases(invalid_json)
    with pytest.raises(ValueError, match="must be a JSON object"):
        tool_call_system_prompt_eval.load_cases(non_object)


def test_hermes_provider_builds_quiet_model_command(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="READY\n", stderr="")

    monkeypatch.setattr(tool_call_system_prompt_eval.subprocess, "run", fake_run)

    responses = tool_call_system_prompt_eval.hermes_responses(
        [
            {
                "id": "hermes-1",
                "system": "Return READY.",
                "user": "Confirm.",
                "allowed_tools": [],
            }
        ],
        hermes_command="hermes",
        model="unsloth/gemma-4-31b-8bit",
        timeout_seconds=7,
    )

    assert responses == {"hermes-1": "READY"}
    assert observed["command"][:3] == ["hermes", "chat", "-q"]
    assert observed["command"][-3:] == ["-m", "unsloth/gemma-4-31b-8bit", "-Q"]
    assert observed["kwargs"]["timeout"] == 7


def test_hermes_provider_reports_failed_command(monkeypatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="no model")

    monkeypatch.setattr(tool_call_system_prompt_eval.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Hermes failed"):
        tool_call_system_prompt_eval.hermes_responses(
            [{"id": "bad", "system": "", "user": ""}],
            hermes_command="hermes",
            model="model",
            timeout_seconds=1,
        )


def test_main_returns_failure_for_failed_fixture_dataset(tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "will-fail",
                "category": "basic_instruction_following",
                "risk": "must_call_tool",
                "system": "Search with the tool.",
                "user": "Search Melix.",
                "allowed_tools": ["text_search"],
                "expected_tool_calls": [{"name": "text_search", "arguments": {"query": "Melix"}}],
                "public_text_policy": "none",
                "fixture_response": "plain text",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = tool_call_system_prompt_eval.main(["--dataset", str(dataset), "--provider", "fixture"])

    printed = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert printed["status"] == "failed"


def test_helper_branches_cover_invalid_expected_and_schema_payloads(monkeypatch) -> None:
    assert tool_call_system_prompt_eval._expected_calls({"expected_tool_calls": "bad"}) == []
    assert tool_call_system_prompt_eval._expected_calls({"expected_tool_calls": ["bad"]}) == []

    reasons: list[str] = []
    assert not tool_call_system_prompt_eval._schema_valid(
        [{"name": "", "arguments": []}],
        reasons,
    )
    assert reasons == ["invalid_tool_schema"]

    assert tool_call_system_prompt_eval._parser_metric_totals([{"parser_metrics": "bad"}]) == {}

    class FakeCall:
        call_id = "fake"
        tool_name = "text_search"
        arguments_json_fragment = "[]"

    class FakeDelta:
        tool_call = FakeCall()

    class FakeCompletion:
        assistant_text = ""
        metrics = {}

    class FakeAssembler:
        def __init__(self, **kwargs: object) -> None:
            pass

        def accept(self, fragment: object) -> list[FakeDelta]:
            return [FakeDelta()]

        def completed(self) -> FakeCompletion:
            return FakeCompletion()

    monkeypatch.setattr(tool_call_system_prompt_eval, "RequestStreamAssembler", FakeAssembler)

    parsed_calls, _, _ = tool_call_system_prompt_eval.parse_tool_calls("ignored")
    assert parsed_calls[0].arguments == {}


def test_unordered_parallel_tool_calls_and_runtime_skip_are_explicit() -> None:
    unordered_case = {
        "id": "parallel",
        "category": "tool_schema_and_argument_fidelity",
        "risk": "parallel_tool_use",
        "system": "Emit both calls.",
        "user": "Search two cities.",
        "allowed_tools": ["text_search"],
        "tool_call_match_mode": "unordered",
        "expected_tool_calls": [
            {"name": "text_search", "arguments": {"query": "A"}},
            {"name": "text_search", "arguments": {"query": "B"}},
        ],
        "public_text_policy": "none",
    }
    unordered_result = tool_call_system_prompt_eval.score_case(
        unordered_case,
        '<tool_call>{"name":"text_search","arguments":{"query":"B"}}</tool_call>'
        '<tool_call>{"name":"text_search","arguments":{"query":"A"}}</tool_call>',
    )

    skip_case = {
        "id": "future-tool",
        "category": "tool_schema_and_argument_fidelity",
        "risk": "parameter_extraction",
        "system": "Extract params.",
        "user": "Normalize a schedule.",
        "allowed_tools": ["local_compute"],
        "expected_tool_calls": [
            {"name": "local_compute", "arguments": {"code": "normalize_schedule('2024-05-13', '14:00')"}}
        ],
        "public_text_policy": "none",
        "skip_runtime_validation": True,
    }
    skip_result = tool_call_system_prompt_eval.score_case(
        skip_case,
        '<tool_call>{"name":"local_compute","arguments":{"code":"normalize_schedule(\'2024-05-13\', \'14:00\')"}}</tool_call>',
    )

    assert unordered_result["passed"] is True
    assert unordered_result["tool_call_match_mode"] == "unordered"
    assert skip_result["passed"] is True
    assert skip_result["runtime_validation_skipped"] is True


def test_tool_argument_match_mode_can_score_toolbench_selection_only_cases() -> None:
    case = {
        "id": "tool-selection",
        "category": "tool_schema_and_argument_fidelity",
        "risk": "tool_selection",
        "system": "Pick the right tool.",
        "user": "Need search.",
        "allowed_tools": ["text_search"],
        "expected_tool_calls": [{"name": "text_search", "arguments": {}}],
        "tool_argument_match_mode": "ignore",
        "public_text_policy": "none",
    }

    result = tool_call_system_prompt_eval.score_case(
        case,
        '<tool_call>{"name":"text_search","arguments":{"query":"any extracted query"}}</tool_call>',
    )

    assert result["passed"] is True
    assert result["tool_argument_match_mode"] == "ignore"


def test_json_policy_soft_judge_and_validator_failures(tmp_path: Path) -> None:
    json_reasons: list[str] = []
    assert not tool_call_system_prompt_eval._json_text_policy_pass(
        {"expected_public_json": {"status": "ok"}},
        "```json\n{\"status\":\"ok\"}\n```",
        json_reasons,
    )
    assert json_reasons == ["public_json_parse_error"]

    semantic_case = {
        "id": "semantic",
        "category": "agent_control_and_negative_constraints",
        "risk": "soft_judge_semantic_refusal",
        "system": "Refuse unavailable request.",
        "user": "Book a flight.",
        "allowed_tools": [],
        "expected_tool_calls": [],
        "public_text_policy": "required",
        "requires_soft_judge": True,
        "semantic_expectation": "Must say flight booking is unavailable.",
    }
    no_judge = tool_call_system_prompt_eval.score_case(semantic_case, "Cannot book flights.")
    yes_judge = tool_call_system_prompt_eval.score_case(
        semantic_case,
        "Cannot book flights.",
        soft_judge=lambda case, raw, parsed: {"passed": True, "rationale": "Equivalent refusal."},
    )
    duplicate_dataset = tmp_path / "duplicate.jsonl"
    duplicate_dataset.write_text(
        "\n".join(json.dumps({**semantic_case, "id": case_id}) for case_id in ["dup", "dup"]) + "\n",
        encoding="utf-8",
    )

    assert no_judge["passed"] is True
    assert no_judge["soft_judge"]["status"] == "not_run"
    assert yes_judge["passed"] is True
    assert yes_judge["soft_judge"]["passed"] is True
    with pytest.raises(ValueError, match="Duplicate case id"):
        tool_call_system_prompt_eval.load_cases(duplicate_dataset)


def test_command_soft_judge_and_required_cli_flag(monkeypatch, tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["stdin"] = kwargs.get("input")
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout='{"passed": true, "rationale": "ok"}', stderr="")

    monkeypatch.setattr(tool_call_system_prompt_eval.subprocess, "run", fake_run)
    judge = tool_call_system_prompt_eval.make_command_soft_judge(
        "judge --case {case_id} --literal {not_a_placeholder}",
        timeout_seconds=17,
    )
    result = judge(
        {"id": "case-1", "semantic_expectation": "Equivalent."},
        "raw",
        {"assistant_text": "raw"},
    )

    assert result["passed"] is True
    assert observed["command"] == ["judge", "--case", "case-1", "--literal", "{not_a_placeholder}"]
    assert json.loads(str(observed["stdin"]))["case"]["id"] == "case-1"
    assert observed["kwargs"]["timeout"] == 17

    dataset = tmp_path / "semantic.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "semantic",
                "category": "agent_control_and_negative_constraints",
                "risk": "soft_judge_semantic_refusal",
                "system": "Refuse unavailable request.",
                "user": "Book a flight.",
                "allowed_tools": [],
                "expected_tool_calls": [],
                "public_text_policy": "required",
                "requires_soft_judge": True,
                "semantic_expectation": "Must say unavailable.",
                "fixture_response": "Cannot book flights.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="--require-soft-judge"):
        tool_call_system_prompt_eval.main(
            ["--dataset", str(dataset), "--provider", "fixture", "--require-soft-judge"]
        )


def test_dataset_validator_rejects_required_case_contract_errors(tmp_path: Path) -> None:
    valid = {
        "id": "valid",
        "category": "basic_instruction_following",
        "risk": "must_call_tool",
        "system": "Use a tool.",
        "user": "Search.",
        "allowed_tools": ["text_search"],
        "expected_tool_calls": [{"name": "text_search", "arguments": {"query": "Melix"}}],
        "public_text_policy": "none",
        "fixture_response": "<tool_call>{\"name\":\"text_search\",\"arguments\":{\"query\":\"Melix\"}}</tool_call>",
    }
    cases = [
        ({**valid, "id": ""}, "non-empty id"),
        ({**valid, "category": ""}, "non-empty category"),
        ({**valid, "expected_tool_calls": "bad"}, "expected_tool_calls"),
        ({**valid, "allowed_tools": [], "expected_tool_calls": valid["expected_tool_calls"]}, "outside allowed_tools"),
        ({**valid, "public_text_policy": "sometimes"}, "unsupported public_text_policy"),
        ({**valid, "tool_call_match_mode": "fuzzy"}, "unsupported tool_call_match_mode"),
        ({**valid, "tool_argument_match_mode": "fuzzy"}, "unsupported tool_argument_match_mode"),
        (
            {**valid, "requires_soft_judge": True, "semantic_expectation": ""},
            "requires_soft_judge",
        ),
    ]

    for index, (payload, message) in enumerate(cases):
        path = tmp_path / f"case-{index}.jsonl"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            tool_call_system_prompt_eval.load_cases(path)


def test_json_policy_and_soft_judge_failure_branches(monkeypatch) -> None:
    missing_reasons: list[str] = []
    mismatch_reasons: list[str] = []
    assert not tool_call_system_prompt_eval._json_text_policy_pass(
        {"expected_public_json": {"status": "ok"}},
        "",
        missing_reasons,
    )
    assert not tool_call_system_prompt_eval._json_text_policy_pass(
        {"expected_public_json": {"status": "ok"}},
        '{"status":"bad"}',
        mismatch_reasons,
    )
    assert missing_reasons == ["missing_public_json"]
    assert mismatch_reasons == ["public_json_mismatch"]

    case = {
        "id": "semantic",
        "category": "agent_control_and_negative_constraints",
        "risk": "soft_judge_semantic_refusal",
        "system": "Refuse.",
        "user": "Book a flight.",
        "allowed_tools": [],
        "expected_tool_calls": [],
        "public_text_policy": "required",
        "requires_soft_judge": True,
        "semantic_expectation": "Refuse.",
    }
    failed = tool_call_system_prompt_eval.score_case(
        case,
        "Cannot do that.",
        soft_judge=lambda case, raw, parsed: {"passed": False},
    )
    errored = tool_call_system_prompt_eval.score_case(
        case,
        "Cannot do that.",
        soft_judge=lambda case, raw, parsed: (_ for _ in ()).throw(RuntimeError("judge down")),
    )

    assert "soft_judge_failed" in failed["failure_reasons"]
    assert failed["soft_judge"]["status"] == "failed"
    assert any(reason.startswith("soft_judge_error:judge down") for reason in errored["failure_reasons"])

    with pytest.raises(ValueError, match="non-empty"):
        tool_call_system_prompt_eval.make_command_soft_judge("")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="down")

    monkeypatch.setattr(tool_call_system_prompt_eval.subprocess, "run", fake_run)
    command_failed = tool_call_system_prompt_eval.make_command_soft_judge("judge")(
        {"id": "case"}, "raw", {}
    )
    assert command_failed["status"] == "command_failed"

    def fake_bad_json(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="not-json", stderr="")

    monkeypatch.setattr(tool_call_system_prompt_eval.subprocess, "run", fake_bad_json)
    invalid_json = tool_call_system_prompt_eval.make_command_soft_judge("judge")(
        {"id": "case"}, "raw", {}
    )
    assert invalid_json["status"] == "invalid_judge_json"

    def fake_non_object(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

    monkeypatch.setattr(tool_call_system_prompt_eval.subprocess, "run", fake_non_object)
    invalid_payload = tool_call_system_prompt_eval.make_command_soft_judge("judge")(
        {"id": "case"}, "raw", {}
    )
    assert invalid_payload["status"] == "invalid_judge_payload"


def test_main_uses_hermes_provider(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        tool_call_system_prompt_eval,
        "hermes_responses",
        lambda cases, **kwargs: {str(case["id"]): str(case["fixture_response"]) for case in cases},
    )
    output_path = tmp_path / "hermes-report.json"

    exit_code = tool_call_system_prompt_eval.main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--provider",
            "hermes",
            "--output",
            str(output_path),
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert printed["status"] == "passed"
    assert report["provider"] == "hermes"


def test_cli_writes_fixture_report(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "report.json"

    exit_code = tool_call_system_prompt_eval.main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--provider",
            "fixture",
            "--output",
            str(output_path),
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert printed["status"] == "passed"
    assert report["schema_version"] == "melix.tool_call_system_prompt_eval_report.v1"
    assert report["provider"] == "fixture"
