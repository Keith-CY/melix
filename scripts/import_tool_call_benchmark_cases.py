#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.tool_call_system_prompt_eval import validate_cases


TOOL_NAME_MAP = {
    "get_weather": "text_search",
    "weather": "text_search",
    "search": "text_search",
    "text_search": "text_search",
    "image_search": "image_search",
    "visit": "visit",
    "browser": "visit",
    "layout_parse": "layout_parse",
    "image_crop": "image_crop",
    "local_compute": "local_compute",
    "calculator": "local_compute",
    "calculate": "local_compute",
}


def import_bfcl(input_path: Path, *, source_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, row in enumerate(_iter_json_records(input_path), start=1):
        expected_calls = _bfcl_expected_calls(row)
        if not expected_calls:
            continue
        expected_calls = [
            call
            for call in (_normalize_call_for_melix(call) for call in expected_calls)
            if call
        ]
        if not expected_calls:
            continue
        case_id = str(row.get("id") or row.get("question_id") or f"{source_id}-{index:04d}")
        prompt = _first_non_empty(row.get("question"), row.get("prompt"), row.get("user"), row.get("query"))
        cases.append(
            {
                "id": f"bfcl-{case_id}",
                "category": "tool_schema_and_argument_fidelity",
                "risk": "external_bfcl_calibration",
                "source_benchmark": "BFCL",
                "source_id": source_id,
                "system": "You are a Melix provider for an agent. Emit parser-compliant Melix tool calls only.",
                "user": prompt,
                "allowed_tools": sorted({call["name"] for call in expected_calls}),
                "expected_tool_calls": expected_calls,
                "tool_call_match_mode": "unordered" if len(expected_calls) > 1 else "ordered",
                "public_text_policy": "none",
                "skip_runtime_validation": True,
                "fixture_response": _fixture_response(expected_calls),
            }
        )
        if limit is not None and len(cases) >= limit:
            break
    validate_cases(cases, dataset_path=input_path)
    return cases


def import_toolbench(input_path: Path, *, source_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, row in enumerate(_iter_json_records(input_path), start=1):
        tool_name = _toolbench_expected_tool(row)
        if not tool_name:
            continue
        normalized_tool = TOOL_NAME_MAP.get(tool_name, tool_name if tool_name in TOOL_NAME_MAP.values() else "")
        if not normalized_tool:
            continue
        case_id = str(row.get("id") or row.get("qid") or row.get("query_id") or f"{source_id}-{index:04d}")
        prompt = _first_non_empty(row.get("query"), row.get("question"), row.get("instruction"), row.get("user"))
        expected_calls = [{"name": normalized_tool, "arguments": {}}]
        cases.append(
            {
                "id": f"toolbench-{case_id}",
                "category": "tool_schema_and_argument_fidelity",
                "risk": "external_toolbench_selection_calibration",
                "source_benchmark": "ToolBench",
                "source_id": source_id,
                "system": "You are a Melix provider for an agent. Select the best available Melix tool.",
                "user": prompt,
                "allowed_tools": [normalized_tool],
                "expected_tool_calls": expected_calls,
                "tool_argument_match_mode": "ignore",
                "public_text_policy": "none",
                "skip_runtime_validation": True,
                "fixture_response": _fixture_response(expected_calls),
            }
        )
        if limit is not None and len(cases) >= limit:
            break
    validate_cases(cases, dataset_path=input_path)
    return cases


def _iter_json_records(input_path: Path) -> list[dict[str, Any]]:
    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if input_path.suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{input_path}:{line_number} must contain JSON objects.")
            records.append(row)
        return records
    payload = json.loads(text)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data") or payload.get("questions") or payload.get("examples") or []
    else:
        rows = []
    if not isinstance(rows, list):
        raise ValueError(f"{input_path} does not contain a JSON record list.")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{input_path} record list must contain JSON objects.")
    return rows


def _bfcl_expected_calls(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("ground_truth", "possible_answer", "answers", "expected_tool_calls"):
        calls = _coerce_calls(row.get(key))
        if calls:
            return calls
    return []


def _coerce_calls(value: object) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, dict):
        value = value.get("tool_calls") or value.get("function_calls") or value.get("calls") or value
    if isinstance(value, dict):
        name = _first_non_empty(value.get("name"), value.get("function"), value.get("tool_name"))
        if name:
            return [{"name": name, "arguments": _coerce_arguments(value.get("arguments", {}))}]
        return []
    if not isinstance(value, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except json.JSONDecodeError:
                continue
        if not isinstance(item, dict):
            continue
        function_payload = item.get("function")
        name = _first_non_empty(item.get("name"), item.get("tool_name"))
        if not name and isinstance(function_payload, dict):
            name = _first_non_empty(function_payload.get("name"))
        if not name:
            name = _first_non_empty(function_payload)
        arguments = item.get("arguments")
        if arguments is None and isinstance(function_payload, dict):
            arguments = function_payload.get("arguments")
        if name:
            calls.append({"name": name, "arguments": _coerce_arguments(arguments)})
    return calls


def _normalize_call_for_melix(call: dict[str, Any]) -> dict[str, Any]:
    raw_name = str(call.get("name", "")).strip()
    name = TOOL_NAME_MAP.get(raw_name, raw_name if raw_name in TOOL_NAME_MAP.values() else "")
    if not name:
        return {}
    arguments = call.get("arguments", {})
    return {
        "name": name,
        "arguments": dict(arguments) if isinstance(arguments, dict) else {},
    }


def _toolbench_expected_tool(row: dict[str, Any]) -> str:
    for key in ("tool", "tool_name", "api_name", "name"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    api_list = row.get("api_list")
    if isinstance(api_list, list) and api_list:
        first = api_list[0]
        if isinstance(first, dict):
            return _first_non_empty(first.get("name"), first.get("api_name"), first.get("tool_name"))
        return str(first)
    return ""


def _coerce_arguments(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _fixture_response(calls: list[dict[str, Any]]) -> str:
    return "".join(
        f"<tool_call>{json.dumps(call, ensure_ascii=False, separators=(',', ':'))}</tool_call>"
        for call in calls
    )


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import external tool-use benchmark snapshots into Melix eval cases.")
    parser.add_argument("--benchmark", choices=("bfcl", "toolbench"), required=True)
    parser.add_argument("--input", type=Path, required=True, help="Pinned local JSON or JSONL snapshot.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path for normalized cases.")
    parser.add_argument("--source-id", required=True, help="Stable source snapshot id for traceability.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum imported cases.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    if args.benchmark == "bfcl":
        cases = import_bfcl(args.input, source_id=args.source_id, limit=args.limit)
    else:
        cases = import_toolbench(args.input, source_id=args.source_id, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    print(json.dumps({"benchmark": args.benchmark, "case_count": len(cases), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
