#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = REPO_ROOT / "services" / "mlx-worker-python"
for path in (REPO_ROOT, WORKER_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from worker.runtime.agentic_tools import AgenticToolRuntimeError, execute_agentic_tool_calls
from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


REPORT_SCHEMA_VERSION = "melix.tool_call_system_prompt_eval_report.v1"
VALID_PUBLIC_TEXT_POLICIES = {"none", "required", "allowed"}
VALID_TOOL_CALL_MATCH_MODES = {"ordered", "unordered"}
VALID_TOOL_ARGUMENT_MATCH_MODES = {"exact", "ignore"}
PARSER_FAILURE_METRICS = (
    "malformed_tool_fragment_count",
    "tool_call_markup_leak_count",
    "duplicate_tool_delta_count",
    "reasoning_leak_count",
)
SoftJudge = Callable[[dict[str, Any], str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ParsedToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "arguments": dict(self.arguments),
        }
        if self.call_id:
            payload["id"] = self.call_id
        return payload


def load_cases(dataset_path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {dataset_path}:{line_number}: {exc}") from exc
            if not isinstance(case, dict):
                raise ValueError(f"Case in {dataset_path}:{line_number} must be a JSON object.")
            cases.append(case)
    validate_cases(cases, dataset_path=dataset_path)
    return cases


def validate_cases(cases: list[dict[str, Any]], *, dataset_path: Path | None = None) -> None:
    seen_ids: set[str] = set()
    source = str(dataset_path or "dataset")
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            raise ValueError(f"Case {source}:{index} must include a non-empty id.")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate case id in {source}: {case_id}")
        seen_ids.add(case_id)

        for field_name in ("category", "risk", "system", "user"):
            if not str(case.get(field_name, "")).strip():
                raise ValueError(f"Case {case_id} must include non-empty {field_name}.")

        expected_calls = _expected_calls(case)
        raw_expected_calls = case.get("expected_tool_calls", [])
        if not isinstance(raw_expected_calls, list) or len(expected_calls) != len(raw_expected_calls):
            raise ValueError(f"Case {case_id} expected_tool_calls must be a list of valid tool call objects.")

        allowed_tools = set(_string_list(case.get("allowed_tools")))
        expected_tool_names = {str(call.get("name", "")) for call in expected_calls}
        unexpected_expected_tools = sorted(expected_tool_names - allowed_tools)
        if unexpected_expected_tools:
            joined = ", ".join(unexpected_expected_tools)
            raise ValueError(f"Case {case_id} expects tool calls outside allowed_tools: {joined}")

        policy = _public_text_policy(case)
        if policy not in VALID_PUBLIC_TEXT_POLICIES:
            raise ValueError(f"Case {case_id} has unsupported public_text_policy: {policy}")

        match_mode = _tool_call_match_mode(case)
        if match_mode not in VALID_TOOL_CALL_MATCH_MODES:
            raise ValueError(f"Case {case_id} has unsupported tool_call_match_mode: {match_mode}")

        argument_match_mode = _tool_argument_match_mode(case)
        if argument_match_mode not in VALID_TOOL_ARGUMENT_MATCH_MODES:
            raise ValueError(f"Case {case_id} has unsupported tool_argument_match_mode: {argument_match_mode}")

        if case.get("requires_soft_judge") and not case.get("semantic_expectation"):
            raise ValueError(f"Case {case_id} requires_soft_judge must include semantic_expectation.")


def parse_tool_calls(raw_response: str) -> tuple[list[ParsedToolCall], str, dict[str, int | str]]:
    assembler = RequestStreamAssembler(
        request_id="tool-call-eval",
        reasoning_enabled=False,
        tool_parser_mode="qwen",
    )
    deltas = assembler.accept(StreamFragment(raw_text=raw_response))
    completion = assembler.completed()
    tool_calls: list[ParsedToolCall] = []
    for delta in deltas:
        if delta.tool_call is None:
            continue
        try:
            arguments = json.loads(delta.tool_call.arguments_json_fragment or "{}")
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_calls.append(
            ParsedToolCall(
                call_id=delta.tool_call.call_id,
                name=delta.tool_call.tool_name,
                arguments=arguments,
            )
        )
    return tool_calls, completion.assistant_text.strip(), completion.metrics


def score_case(
    case: dict[str, Any],
    raw_response: str,
    *,
    soft_judge: SoftJudge | None = None,
) -> dict[str, Any]:
    parsed_calls, assistant_text, parser_metrics = parse_tool_calls(raw_response)
    expected_calls = _expected_calls(case)
    allowed_tools = set(_string_list(case.get("allowed_tools")))
    failure_reasons: list[str] = []

    actual_calls = [call.to_dict() for call in parsed_calls]
    tool_call_match = _calls_match(
        actual_calls,
        expected_calls,
        match_mode=_tool_call_match_mode(case),
        argument_match_mode=_tool_argument_match_mode(case),
    )
    if not tool_call_match:
        failure_reasons.append("tool_call_mismatch")

    unexpected_tools = [
        call["name"]
        for call in actual_calls
        if allowed_tools and str(call.get("name")) not in allowed_tools
    ]
    if unexpected_tools:
        failure_reasons.append("unexpected_tool")

    if not allowed_tools and actual_calls:
        failure_reasons.append("forbidden_tool_call")

    schema_valid = _schema_valid(actual_calls, failure_reasons)
    public_text_pass = _public_text_policy_pass(case, assistant_text, failure_reasons)
    parser_pass = _parser_metrics_pass(parser_metrics, failure_reasons)
    json_text_pass = _json_text_policy_pass(case, assistant_text, failure_reasons)
    soft_judge_result = _soft_judge_result(
        case,
        raw_response,
        {
            "actual_tool_calls": actual_calls,
            "assistant_text": assistant_text,
            "parser_metrics": parser_metrics,
        },
        soft_judge=soft_judge,
        failure_reasons=failure_reasons,
    )

    runtime_validation_skipped = bool(case.get("skip_runtime_validation"))
    if not runtime_validation_skipped:
        try:
            execute_agentic_tool_calls(actual_calls)
        except AgenticToolRuntimeError as exc:
            if actual_calls:
                failure_reasons.append(f"runtime_rejected_tool_call:{exc}")
                schema_valid = False

    passed = not failure_reasons
    return {
        "id": str(case.get("id", "")),
        "category": str(case.get("category", "")),
        "risk": str(case.get("risk", "")),
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "failure_reasons": failure_reasons,
        "expected_tool_calls": expected_calls,
        "actual_tool_calls": actual_calls,
        "assistant_text": assistant_text,
        "raw_response": raw_response,
        "schema_valid": schema_valid,
        "runtime_validation_skipped": runtime_validation_skipped,
        "tool_call_match": tool_call_match,
        "tool_call_match_mode": _tool_call_match_mode(case),
        "tool_argument_match_mode": _tool_argument_match_mode(case),
        "public_text_policy_pass": public_text_pass,
        "json_text_policy_pass": json_text_pass,
        "parser_metrics_pass": parser_pass,
        "soft_judge": soft_judge_result,
        "parser_metrics": parser_metrics,
    }


def evaluate_cases(
    cases: list[dict[str, Any]],
    responses: dict[str, str],
    *,
    soft_judge: SoftJudge | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    case_results = [
        score_case(
            case,
            responses.get(str(case.get("id", "")), str(case.get("fixture_response", ""))),
            soft_judge=soft_judge,
        )
        for case in cases
    ]
    duration_seconds = round(time.perf_counter() - started_at, 6)
    case_count = len(case_results)
    pass_count = sum(1 for result in case_results if result["passed"])
    metrics = {
        "tool_call_eval.case_count": float(case_count),
        "tool_call_eval.pass_count": float(pass_count),
        "tool_call_eval.pass_rate": _ratio(pass_count, case_count),
        "tool_call_eval.exact_tool_call_match_rate": _ratio(
            sum(1 for result in case_results if result["tool_call_match"]),
            case_count,
        ),
        "tool_call_eval.schema_valid_rate": _ratio(
            sum(1 for result in case_results if result["schema_valid"]),
            case_count,
        ),
        "tool_call_eval.public_text_policy_pass_rate": _ratio(
            sum(1 for result in case_results if result["public_text_policy_pass"]),
            case_count,
        ),
        "tool_call_eval.json_text_policy_pass_rate": _ratio(
            sum(1 for result in case_results if result["json_text_policy_pass"]),
            case_count,
        ),
        "tool_call_eval.soft_judge_pass_rate": _ratio(
            sum(1 for result in case_results if _soft_judge_passed(result)),
            sum(1 for result in case_results if result["soft_judge"]["required"]),
        ),
        "tool_call_eval.duration_seconds": duration_seconds,
        **_parser_metric_totals(case_results),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "passed" if pass_count == case_count else "failed",
        "metrics": metrics,
        "cases": case_results,
    }


def fixture_responses(cases: list[dict[str, Any]]) -> dict[str, str]:
    return {str(case.get("id", "")): str(case.get("fixture_response", "")) for case in cases}


def hermes_responses(
    cases: list[dict[str, Any]],
    *,
    hermes_command: str,
    model: str,
    timeout_seconds: float,
) -> dict[str, str]:
    responses: dict[str, str] = {}
    for case in cases:
        prompt = _hermes_prompt(case=case, model=model)
        command = [hermes_command, "chat", "-q", prompt, "-m", model, "-Q"]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(
                f"Hermes failed for case {case.get('id')}: exit={completed.returncode} stderr={stderr}"
            )
        responses[str(case.get("id", ""))] = completed.stdout.strip()
    return responses


def _hermes_prompt(*, case: dict[str, Any], model: str) -> str:
    tools = ", ".join(_string_list(case.get("allowed_tools"))) or "none"
    expected_schema = json.dumps(
        {
            "name": "tool_name",
            "arguments": {"argument_name": "argument_value"},
        },
        separators=(",", ":"),
    )
    return "\n".join(
        [
            f"Model under test: {model}",
            "Follow the system instruction exactly.",
            "When a tool call is required, output only this Melix qwen XML shape:",
            f"<tool_call>{expected_schema}</tool_call>",
            "Do not use call:name(...), markdown, prose, or any non-JSON argument syntax.",
            "",
            f"System: {case.get('system', '')}",
            f"Allowed tools: {tools}",
            f"User: {case.get('user', '')}",
        ]
    )


def _expected_calls(case: dict[str, Any]) -> list[dict[str, Any]]:
    raw_calls = case.get("expected_tool_calls", [])
    if not isinstance(raw_calls, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        name = str(raw_call.get("name", "")).strip()
        arguments = raw_call.get("arguments", {})
        normalized.append(
            {
                "name": name,
                "arguments": dict(arguments) if isinstance(arguments, dict) else {},
            }
        )
    return normalized


def _calls_match(
    actual_calls: list[dict[str, Any]],
    expected_calls: list[dict[str, Any]],
    *,
    match_mode: str = "ordered",
    argument_match_mode: str = "exact",
) -> bool:
    comparable_actual = [_comparable_call(call, argument_match_mode=argument_match_mode) for call in actual_calls]
    comparable_expected = [_comparable_call(call, argument_match_mode=argument_match_mode) for call in expected_calls]
    if match_mode == "unordered":
        return _call_counter(comparable_actual) == _call_counter(comparable_expected)
    return comparable_actual == comparable_expected


def _comparable_call(call: dict[str, Any], *, argument_match_mode: str) -> dict[str, Any]:
    comparable = {"name": str(call.get("name", ""))}
    if argument_match_mode != "ignore":
        comparable["arguments"] = dict(call.get("arguments", {}))
    return comparable


def _call_counter(calls: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        json.dumps(
            {"name": str(call.get("name", "")), "arguments": dict(call.get("arguments", {}))},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for call in calls
    )


def _schema_valid(actual_calls: list[dict[str, Any]], failure_reasons: list[str]) -> bool:
    schema_valid = True
    for call in actual_calls:
        name = str(call.get("name", "")).strip()
        arguments = call.get("arguments")
        if not name or not isinstance(arguments, dict):
            schema_valid = False
            failure_reasons.append("invalid_tool_schema")
    return schema_valid


def _public_text_policy_pass(
    case: dict[str, Any],
    assistant_text: str,
    failure_reasons: list[str],
) -> bool:
    policy = _public_text_policy(case)
    if policy == "none" and assistant_text:
        failure_reasons.append("unexpected_public_text")
        return False
    if policy == "required" and not assistant_text:
        failure_reasons.append("missing_public_text")
        return False
    expected_exact = str(case.get("expected_public_text", "")).strip()
    if expected_exact and assistant_text.strip() != expected_exact:
        failure_reasons.append("public_text_mismatch")
        return False
    for fragment in _string_list(case.get("expected_public_text_contains")):
        if fragment not in assistant_text:
            failure_reasons.append("public_text_missing_fragment")
            return False
    return True


def _json_text_policy_pass(
    case: dict[str, Any],
    assistant_text: str,
    failure_reasons: list[str],
) -> bool:
    expected_json = case.get("expected_public_json")
    if expected_json is None:
        return True
    if not assistant_text:
        failure_reasons.append("missing_public_json")
        return False
    try:
        parsed = json.loads(assistant_text)
    except json.JSONDecodeError:
        failure_reasons.append("public_json_parse_error")
        return False
    if parsed != expected_json:
        failure_reasons.append("public_json_mismatch")
        return False
    return True


def _parser_metrics_pass(
    parser_metrics: dict[str, int | str],
    failure_reasons: list[str],
) -> bool:
    failed = False
    for key in PARSER_FAILURE_METRICS:
        value = int(parser_metrics.get(key, 0) or 0)
        if value:
            failed = True
            failure_reasons.append(f"parser_metric:{key}")
    return not failed


def _parser_metric_totals(case_results: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for result in case_results:
        parser_metrics = result.get("parser_metrics", {})
        if not isinstance(parser_metrics, dict):
            continue
        for key in PARSER_FAILURE_METRICS:
            totals[f"tool_call_eval.parser.{key}"] = totals.get(
                f"tool_call_eval.parser.{key}",
                0.0,
            ) + float(parser_metrics.get(key, 0) or 0)
    return {key: round(value, 4) for key, value in sorted(totals.items())}


def _soft_judge_result(
    case: dict[str, Any],
    raw_response: str,
    parsed: dict[str, Any],
    *,
    soft_judge: SoftJudge | None,
    failure_reasons: list[str],
) -> dict[str, Any]:
    required = bool(case.get("requires_soft_judge"))
    if not required:
        return {"required": False, "status": "not_required", "passed": True}
    if soft_judge is None:
        return {"required": True, "status": "not_run", "passed": None}
    try:
        result = soft_judge(case, raw_response, parsed)
    except Exception as exc:  # pragma: no cover - defensive around external judge commands
        failure_reasons.append(f"soft_judge_error:{exc}")
        return {"required": True, "status": "error", "passed": False, "error": str(exc)}
    passed = bool(result.get("passed"))
    if not passed:
        failure_reasons.append("soft_judge_failed")
    normalized = dict(result)
    normalized.setdefault("status", "passed" if passed else "failed")
    normalized["required"] = True
    normalized["passed"] = passed
    return normalized


def _soft_judge_passed(result: dict[str, Any]) -> bool:
    judge = result.get("soft_judge", {})
    return bool(isinstance(judge, dict) and judge.get("required") and judge.get("passed"))


def make_command_soft_judge(command_template: str, *, timeout_seconds: float = 60.0) -> SoftJudge:
    command_template = command_template.strip()
    if not command_template:
        raise ValueError("soft judge command template must be non-empty.")
    template_parts = shlex.split(command_template)

    def judge(case: dict[str, Any], raw_response: str, parsed: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "case": case,
            "raw_response": raw_response,
            "parsed": parsed,
        }
        command = [part.replace("{case_id}", str(case.get("id", ""))) for part in template_parts]
        completed = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            return {
                "passed": False,
                "status": "command_failed",
                "exit_code": completed.returncode,
                "stderr": completed.stderr.strip(),
            }
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return {
                "passed": False,
                "status": "invalid_judge_json",
                "error": str(exc),
                "stdout": completed.stdout.strip(),
            }
        if not isinstance(result, dict):
            return {"passed": False, "status": "invalid_judge_payload"}
        return result

    return judge


def _public_text_policy(case: dict[str, Any]) -> str:
    return str(case.get("public_text_policy", "allowed")).strip() or "allowed"


def _tool_call_match_mode(case: dict[str, Any]) -> str:
    return str(case.get("tool_call_match_mode", "ordered")).strip() or "ordered"


def _tool_argument_match_mode(case: dict[str, Any]) -> str:
    return str(case.get("tool_argument_match_mode", "exact")).strip() or "exact"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / max(denominator, 1), 4)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Melix tool-call system prompt adherence.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "tests/eval/tool-call-system-prompts.v1/cases.jsonl",
        help="Path to the JSONL golden dataset.",
    )
    parser.add_argument(
        "--provider",
        choices=("fixture", "hermes"),
        default="fixture",
        help="Response provider. fixture is CI-safe; hermes is local-only.",
    )
    parser.add_argument("--hermes-command", default="hermes", help="Hermes executable name or path.")
    parser.add_argument("--model", default="unsloth/gemma-4-31b-8bit", help="Model id for report metadata.")
    parser.add_argument("--timeout-seconds", type=float, default=120.0, help="Hermes per-case timeout.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path.")
    parser.add_argument(
        "--soft-judge-command",
        default="",
        help=(
            "Optional command template for cases with requires_soft_judge=true. "
            "The command receives JSON on stdin and must emit JSON with a boolean passed field."
        ),
    )
    parser.add_argument(
        "--soft-judge-timeout-seconds",
        type=float,
        default=60.0,
        help="External soft judge command timeout per case.",
    )
    parser.add_argument(
        "--require-soft-judge",
        action="store_true",
        help="Fail if any case requires a soft judge and --soft-judge-command is not provided.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    cases = load_cases(args.dataset)
    if args.require_soft_judge and any(case.get("requires_soft_judge") for case in cases) and not args.soft_judge_command:
        raise RuntimeError("--require-soft-judge needs --soft-judge-command for semantic cases.")
    if args.provider == "fixture":
        responses = fixture_responses(cases)
    else:
        responses = hermes_responses(
            cases,
            hermes_command=args.hermes_command,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
    soft_judge = (
        make_command_soft_judge(
            args.soft_judge_command,
            timeout_seconds=args.soft_judge_timeout_seconds,
        )
        if args.soft_judge_command
        else None
    )
    report = evaluate_cases(cases, responses, soft_judge=soft_judge)
    report["provider"] = args.provider
    report["model"] = args.model
    report["dataset"] = str(args.dataset)
    report["soft_judge"] = {
        "enabled": soft_judge is not None,
        "command": args.soft_judge_command if soft_judge is not None else "",
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "metrics": report["metrics"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
