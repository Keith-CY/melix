from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import time
from pathlib import Path
from typing import Any

from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


AGENT_RELIABILITY_ROW_SCHEMA_VERSION = "melix.agent_reliability_row.v1"
AGENT_RELIABILITY_SUMMARY_SCHEMA_VERSION = "melix.agent_reliability_summary.v1"
DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "evaluation"
    / "agent-reliability.dev.v1"
)

_GUARDRAIL_NAMES = (
    "response_rescue",
    "retry_nudges",
    "step_enforcement",
    "tool_error_recovery",
    "context_compaction",
)
_NUMERIC_METRIC_FIELDS = (
    "accuracy",
    "completeness",
    "wasted_tool_call_count",
    "retry_count",
    "nudge_count",
    "validation_error_count",
    "compaction_event_count",
    "elapsed_ms",
    "token_estimate",
    "cost_estimate_usd",
)
_COMPACT_JSON = {
    "ensure_ascii": False,
    "separators": (",", ":"),
    "sort_keys": True,
}


@dataclass(frozen=True)
class AgentReliabilityAblation:
    preset_id: str
    enabled_guardrails: dict[str, bool]
    description: str


@dataclass(frozen=True)
class AgentReliabilityScenario:
    scenario_id: str
    title: str
    tags: tuple[str, ...]
    input_text: str
    tool_backend: dict[str, Any]
    expected_output_contains: tuple[str, ...]
    expected_backend_state: dict[str, Any]
    responses_by_ablation: dict[str, str]
    metric_hints: dict[str, Any]


@dataclass(frozen=True)
class AgentReliabilityRunConfig:
    output_dir: Path
    model_id: str
    backend: str
    profile: str
    resume: bool = False


@dataclass(frozen=True)
class AgentReliabilityRunResult:
    rows: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


@dataclass(frozen=True)
class AgentReliabilityPersistedRun:
    rows: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    rows_path: Path
    summary_path: Path
    report_path: Path


def expand_ablation_presets() -> dict[str, AgentReliabilityAblation]:
    enabled = {name: True for name in _GUARDRAIL_NAMES}
    presets: dict[str, AgentReliabilityAblation] = {
        "baseline": AgentReliabilityAblation(
            preset_id="baseline",
            enabled_guardrails=dict(enabled),
            description="All runtime guardrails enabled.",
        )
    }
    single_disable = {
        "no_response_rescue": "response_rescue",
        "no_retry_nudges": "retry_nudges",
        "no_step_enforcement": "step_enforcement",
        "no_tool_error_recovery": "tool_error_recovery",
        "no_context_compaction": "context_compaction",
    }
    for preset_id, guardrail in single_disable.items():
        values = dict(enabled)
        values[guardrail] = False
        presets[preset_id] = AgentReliabilityAblation(
            preset_id=preset_id,
            enabled_guardrails=values,
            description=f"Disable {guardrail}.",
        )
    presets["all_guardrails_disabled"] = AgentReliabilityAblation(
        preset_id="all_guardrails_disabled",
        enabled_guardrails={name: False for name in _GUARDRAIL_NAMES},
        description="Disable all tracked runtime guardrails.",
    )
    return presets


def load_agent_reliability_scenarios(package_root: Path) -> tuple[AgentReliabilityScenario, ...]:
    package_root = Path(package_root)
    manifest_path = package_root / "manifest.json"
    scenarios_path = package_root / "scenarios.jsonl"
    manifest = _load_json_object(manifest_path)
    if manifest.get("schema_version") != "melix.agent_reliability_fixture.v1":
        raise ValueError(f"Unsupported agent reliability fixture manifest: {manifest_path}")
    scenarios: list[AgentReliabilityScenario] = []
    with scenarios_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {scenarios_path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Scenario in {scenarios_path}:{line_number} must be a JSON object.")
            scenarios.append(_scenario_from_payload(payload, source=f"{scenarios_path}:{line_number}"))
    expected_count = int(manifest.get("scenario_count", len(scenarios)) or len(scenarios))
    if expected_count != len(scenarios):
        raise ValueError(
            f"Agent reliability fixture scenario_count mismatch: expected {expected_count}, got {len(scenarios)}"
        )
    return tuple(scenarios)


def run_agent_reliability_track(
    config: AgentReliabilityRunConfig,
    *,
    scenarios: tuple[AgentReliabilityScenario, ...],
    ablations: tuple[AgentReliabilityAblation, ...],
) -> AgentReliabilityRunResult:
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        for ablation in ablations:
            rows.append(_run_scenario(config=config, scenario=scenario, ablation=ablation))
    summary = build_agent_reliability_summary(rows, resumed_row_count=0)
    return AgentReliabilityRunResult(rows=tuple(rows), summary=summary)


def persist_agent_reliability_run(
    config: AgentReliabilityRunConfig,
    *,
    scenarios: tuple[AgentReliabilityScenario, ...],
    ablations: tuple[AgentReliabilityAblation, ...],
) -> AgentReliabilityPersistedRun:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "agent-reliability-rows.jsonl"
    summary_path = output_dir / "agent-reliability-summary.json"
    report_path = output_dir / "agent-reliability-report.md"

    existing_rows = _load_existing_rows(rows_path) if config.resume else ()
    existing_by_identity = {
        str(row.get("row_identity", "")): row
        for row in existing_rows
        if str(row.get("row_identity", ""))
    }
    rows: list[dict[str, Any]] = list(existing_rows)
    for scenario in scenarios:
        for ablation in ablations:
            identity = row_identity(
                model_id=config.model_id,
                backend=config.backend,
                profile=config.profile,
                ablation_id=ablation.preset_id,
                scenario_id=scenario.scenario_id,
            )
            if identity in existing_by_identity:
                continue
            row = _run_scenario(config=config, scenario=scenario, ablation=ablation)
            rows.append(row)
            existing_by_identity[identity] = row

    summary = build_agent_reliability_summary(rows, resumed_row_count=len(existing_rows))
    _write_jsonl(rows_path, rows)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(render_agent_reliability_report(summary, rows), encoding="utf-8")
    return AgentReliabilityPersistedRun(
        rows=tuple(rows),
        summary=summary,
        rows_path=rows_path,
        summary_path=summary_path,
        report_path=report_path,
    )


def build_agent_reliability_summary(
    rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    *,
    resumed_row_count: int,
) -> dict[str, Any]:
    row_list = list(rows)
    by_ablation: dict[str, dict[str, Any]] = {}
    for ablation_id in sorted({str(row.get("ablation_id", "")) for row in row_list}):
        ablation_rows = [row for row in row_list if row.get("ablation_id") == ablation_id]
        by_ablation[ablation_id] = _aggregate_rows(ablation_rows)

    baseline = by_ablation.get("baseline", {})
    deltas: dict[str, dict[str, float]] = {}
    for ablation_id, aggregate in by_ablation.items():
        if ablation_id == "baseline":
            continue
        deltas[ablation_id] = {
            "completion_rate_delta": _round4(
                float(aggregate.get("completion_rate", 0.0))
                - float(baseline.get("completion_rate", 0.0))
            ),
            "accuracy_delta": _round4(
                float(aggregate.get("accuracy_mean", 0.0))
                - float(baseline.get("accuracy_mean", 0.0))
            ),
            "wasted_tool_call_delta": _round4(
                float(aggregate.get("wasted_tool_call_mean", 0.0))
                - float(baseline.get("wasted_tool_call_mean", 0.0))
            ),
        }
    return {
        "schema_version": AGENT_RELIABILITY_SUMMARY_SCHEMA_VERSION,
        "aggregate": {
            "row_count": len(row_list),
            "scenario_count": len({str(row.get("scenario_id", "")) for row in row_list}),
            "ablation_count": len(by_ablation),
            "resumed_row_count": resumed_row_count,
        },
        "by_ablation": by_ablation,
        "deltas_vs_baseline": deltas,
    }


def render_agent_reliability_report(
    summary: dict[str, Any],
    rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> str:
    lines = [
        "# Agent Reliability Report",
        "",
        f"Schema: `{summary.get('schema_version', '')}`",
        "",
        "## Per-Ablation Deltas",
        "",
        "| ablation | completion_rate | completion_rate_delta | wasted_tool_call_mean | wasted_tool_call_delta |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    by_ablation = _dict_value(summary.get("by_ablation"))
    deltas = _dict_value(summary.get("deltas_vs_baseline"))
    for ablation_id in sorted(by_ablation):
        aggregate = _dict_value(by_ablation.get(ablation_id))
        delta = _dict_value(deltas.get(ablation_id))
        lines.append(
            "| {ablation} | {completion:.4f} | {completion_delta:.4f} | {wasted:.4f} | {wasted_delta:.4f} |".format(
                ablation=ablation_id,
                completion=float(aggregate.get("completion_rate", 0.0)),
                completion_delta=float(delta.get("completion_rate_delta", 0.0)),
                wasted=float(aggregate.get("wasted_tool_call_mean", 0.0)),
                wasted_delta=float(delta.get("wasted_tool_call_delta", 0.0)),
            )
        )
    lines.extend(
        [
            "",
            "## Scenario Rows",
            "",
            "| scenario | ablation | accuracy | completeness | validation_errors | wasted_tool_calls |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        lines.append(
            "| {scenario} | {ablation} | {accuracy:.4f} | {completeness:.4f} | {errors:.1f} | {wasted:.1f} |".format(
                scenario=str(row.get("scenario_id", "")),
                ablation=str(row.get("ablation_id", "")),
                accuracy=float(row.get("accuracy", 0.0)),
                completeness=float(row.get("completeness", 0.0)),
                errors=float(row.get("validation_error_count", 0.0)),
                wasted=float(row.get("wasted_tool_call_count", 0.0)),
            )
        )
    return "\n".join(lines) + "\n"


def row_identity(
    *,
    model_id: str,
    backend: str,
    profile: str,
    ablation_id: str,
    scenario_id: str,
) -> str:
    return "|".join((model_id, backend, profile, ablation_id, scenario_id))


def _run_scenario(
    *,
    config: AgentReliabilityRunConfig,
    scenario: AgentReliabilityScenario,
    ablation: AgentReliabilityAblation,
) -> dict[str, Any]:
    started = time.perf_counter()
    raw_response = _response_for_ablation(scenario, ablation.preset_id)
    parsed = _parse_response(raw_response, allowed_tool_names=_tool_names(scenario.tool_backend))
    backend_state = copy.deepcopy(scenario.tool_backend.get("initial_state", {}))
    backend_events = _apply_fixture_tool_calls(parsed["tool_calls"], backend_state)
    output_contains = all(
        fragment in parsed["assistant_text"] for fragment in scenario.expected_output_contains
    )
    state_mismatches = _state_mismatches(
        expected=scenario.expected_backend_state,
        actual=backend_state,
    )
    backend_state_match = not state_mismatches
    parser_error_count = sum(
        float(value or 0)
        for key, value in parsed["parser_metrics"].items()
        if key.endswith("_count") and isinstance(value, (int, float))
    )
    validation_error_count = 0.0 if output_contains and backend_state_match and parser_error_count == 0 else 1.0
    completeness = 1.0 if output_contains and backend_state_match else 0.0
    accuracy = 1.0 if completeness == 1.0 and validation_error_count == 0.0 else 0.0
    metric_hints = _metric_hints_for_ablation(scenario.metric_hints, ablation.preset_id)
    elapsed_ms = _round4((time.perf_counter() - started) * 1000.0)
    token_estimate = float(metric_hints.get("token_estimate", _token_estimate(raw_response)))
    cost_estimate = float(metric_hints.get("cost_estimate_usd", 0.0))
    row = {
        "schema_version": AGENT_RELIABILITY_ROW_SCHEMA_VERSION,
        "row_identity": row_identity(
            model_id=config.model_id,
            backend=config.backend,
            profile=config.profile,
            ablation_id=ablation.preset_id,
            scenario_id=scenario.scenario_id,
        ),
        "model_id": config.model_id,
        "backend": config.backend,
        "profile": config.profile,
        "ablation_id": ablation.preset_id,
        "enabled_guardrails": dict(ablation.enabled_guardrails),
        "scenario_id": scenario.scenario_id,
        "scenario_title": scenario.title,
        "scenario_tags": list(scenario.tags),
        "accuracy": float(accuracy),
        "completeness": float(completeness),
        "wasted_tool_call_count": float(
            metric_hints.get("wasted_tool_call_count", _wasted_tool_call_count(parsed["tool_calls"], scenario))
        ),
        "retry_count": float(metric_hints.get("retry_count", 0.0)),
        "nudge_count": float(metric_hints.get("nudge_count", 0.0)),
        "validation_error_count": float(validation_error_count),
        "compaction_event_count": float(metric_hints.get("compaction_event_count", 0.0)),
        "elapsed_ms": elapsed_ms,
        "token_estimate": token_estimate,
        "cost_estimate_usd": cost_estimate,
        "backend_state_match": backend_state_match,
        "backend_state_mismatches": state_mismatches,
        "backend_state": backend_state,
        "backend_events": backend_events,
        "expected_backend_state": scenario.expected_backend_state,
        "assistant_text": parsed["assistant_text"],
        "tool_calls": parsed["tool_calls"],
        "parser_metrics": parsed["parser_metrics"],
    }
    for metric_name in _NUMERIC_METRIC_FIELDS:
        row[metric_name] = float(row[metric_name])
    return row


def _scenario_from_payload(payload: dict[str, Any], *, source: str) -> AgentReliabilityScenario:
    scenario_id = str(payload.get("id", "")).strip()
    if not scenario_id:
        raise ValueError(f"Agent reliability scenario in {source} must include id.")
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError(f"Agent reliability scenario {scenario_id} must include title.")
    tags = tuple(str(tag).strip() for tag in _list_value(payload.get("tags")) if str(tag).strip())
    if not tags:
        raise ValueError(f"Agent reliability scenario {scenario_id} must include tags.")
    responses = _dict_value(payload.get("responses_by_ablation"))
    if not responses:
        raise ValueError(f"Agent reliability scenario {scenario_id} must include responses_by_ablation.")
    return AgentReliabilityScenario(
        scenario_id=scenario_id,
        title=title,
        tags=tags,
        input_text=str(payload.get("input", "")),
        tool_backend=_dict_value(payload.get("tool_backend")),
        expected_output_contains=tuple(
            str(fragment)
            for fragment in _list_value(payload.get("expected_output_contains"))
            if str(fragment)
        ),
        expected_backend_state=_dict_value(payload.get("expected_backend_state")),
        responses_by_ablation={str(key): str(value) for key, value in responses.items()},
        metric_hints=_dict_value(payload.get("metric_hints")),
    )


def _parse_response(raw_response: str, *, allowed_tool_names: tuple[str, ...]) -> dict[str, Any]:
    assembler = RequestStreamAssembler(
        request_id="agent-reliability",
        reasoning_enabled=False,
        tool_parser_mode="qwen",
        tool_parser_fallback_mode="xml",
        allowed_tool_names=allowed_tool_names or None,
    )
    deltas = assembler.accept(StreamFragment(raw_text=raw_response))
    completion = assembler.completed()
    tool_calls: list[dict[str, Any]] = []
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
            {
                "id": delta.tool_call.call_id,
                "name": delta.tool_call.tool_name,
                "arguments": arguments,
            }
        )
    return {
        "tool_calls": tool_calls,
        "assistant_text": completion.assistant_text.strip(),
        "parser_metrics": dict(completion.metrics),
    }


def _apply_fixture_tool_calls(
    tool_calls: list[dict[str, Any]],
    backend_state: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for call in tool_calls:
        tool_name = str(call.get("name", ""))
        arguments = _dict_value(call.get("arguments"))
        if tool_name == "update_ticket":
            ticket_id = str(arguments.get("ticket_id", ""))
            status = str(arguments.get("status", ""))
            tickets = backend_state.setdefault("tickets", {})
            if not isinstance(tickets, dict):
                continue
            ticket = tickets.setdefault(ticket_id, {})
            if isinstance(ticket, dict):
                ticket["status"] = status
                events.append({"tool_name": tool_name, "ticket_id": ticket_id, "status": status})
            continue
        if tool_name == "search_docs":
            query = str(arguments.get("query", ""))
            events.append({"tool_name": tool_name, "query": query, "result_count": 1 if query else 0})
            continue
        if tool_name == "compact_context":
            events.append({"tool_name": tool_name, "mode": str(arguments.get("mode", ""))})
            continue
        events.append({"tool_name": tool_name, "unsupported": True})
    return events


def _state_mismatches(
    *,
    expected: dict[str, Any],
    actual: dict[str, Any],
    prefix: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for key in sorted(expected):
        path = (*prefix, str(key))
        expected_value = expected[key]
        if not isinstance(actual, dict) or key not in actual:
            mismatches.append({"path": ".".join(path), "expected": expected_value, "actual": None})
            continue
        actual_value = actual[key]
        if isinstance(expected_value, dict):
            mismatches.extend(
                _state_mismatches(
                    expected=expected_value,
                    actual=actual_value if isinstance(actual_value, dict) else {},
                    prefix=path,
                )
            )
            continue
        if actual_value != expected_value:
            mismatches.append(
                {
                    "path": ".".join(path),
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )
    return mismatches


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    completed = sum(1 for row in rows if float(row.get("completeness", 0.0)) >= 1.0)
    return {
        "row_count": count,
        "completion_rate": _round4(completed / max(count, 1)),
        "accuracy_mean": _mean(rows, "accuracy"),
        "completeness_mean": _mean(rows, "completeness"),
        "wasted_tool_call_mean": _mean(rows, "wasted_tool_call_count"),
        "retry_count_mean": _mean(rows, "retry_count"),
        "nudge_count_mean": _mean(rows, "nudge_count"),
        "validation_error_count_mean": _mean(rows, "validation_error_count"),
        "compaction_event_count_mean": _mean(rows, "compaction_event_count"),
    }


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return _round4(sum(float(row.get(key, 0.0) or 0.0) for row in rows) / max(len(rows), 1))


def _load_existing_rows(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        return ()
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and str(payload.get("row_identity", "")):
                rows.append(payload)
    return tuple(rows)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, **_COMPACT_JSON) + "\n")


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _response_for_ablation(scenario: AgentReliabilityScenario, ablation_id: str) -> str:
    return scenario.responses_by_ablation.get(
        ablation_id,
        scenario.responses_by_ablation.get("baseline", ""),
    )


def _metric_hints_for_ablation(metric_hints: dict[str, Any], ablation_id: str) -> dict[str, Any]:
    merged = dict(_dict_value(metric_hints.get("default")))
    merged.update(_dict_value(metric_hints.get(ablation_id)))
    return merged


def _tool_names(tool_backend: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(tool.get("name", ""))
        for tool in _dict_list(tool_backend.get("tools"))
        if str(tool.get("name", "")).strip()
    )


def _wasted_tool_call_count(
    tool_calls: list[dict[str, Any]],
    scenario: AgentReliabilityScenario,
) -> float:
    expected_names = {
        str(tool.get("name", ""))
        for tool in _dict_list(scenario.tool_backend.get("tools"))
        if tool.get("required")
    }
    if not expected_names:
        return 0.0
    return float(
        sum(1 for call in tool_calls if str(call.get("name", "")) not in expected_names)
    )


def _token_estimate(text: str) -> float:
    return float(max(1, len(text.split())))


def _round4(value: float) -> float:
    return round(float(value), 4)


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []
