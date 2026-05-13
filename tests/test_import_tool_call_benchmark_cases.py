from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_tool_call_benchmark_cases.py"
MODULE_SPEC = importlib.util.spec_from_file_location("import_tool_call_benchmark_cases", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
import_tool_call_benchmark_cases = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = import_tool_call_benchmark_cases
MODULE_SPEC.loader.exec_module(import_tool_call_benchmark_cases)


def test_import_bfcl_snapshot_normalizes_expected_calls(tmp_path: Path) -> None:
    source = tmp_path / "bfcl.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "simple-1",
                        "question": "What is the weather in Beijing?",
                        "ground_truth": [
                            {
                                "name": "get_weather",
                                "arguments": {"location": "Beijing"},
                            }
                        ],
                    }
                ),
                json.dumps(
                    {
                        "id": "parallel-1",
                        "question": "Search two documents.",
                        "ground_truth": [
                            {"name": "search", "arguments": {"query": "A"}},
                            {"name": "search", "arguments": {"query": "B"}},
                        ],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cases = import_tool_call_benchmark_cases.import_bfcl(source, source_id="bfcl-fixture")

    assert [case["source_benchmark"] for case in cases] == ["BFCL", "BFCL"]
    assert cases[0]["expected_tool_calls"] == [
        {"name": "text_search", "arguments": {"location": "Beijing"}}
    ]
    assert cases[1]["tool_call_match_mode"] == "unordered"
    assert cases[1]["skip_runtime_validation"] is True


def test_import_toolbench_snapshot_normalizes_tool_selection_cases(tmp_path: Path) -> None:
    source = tmp_path / "toolbench.json"
    source.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "qid": "tb-1",
                        "query": "Open the local page.",
                        "api_list": [{"name": "browser"}],
                    },
                    {
                        "qid": "tb-2",
                        "query": "Send email.",
                        "api_list": [{"name": "email"}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = import_tool_call_benchmark_cases.import_toolbench(source, source_id="toolbench-fixture")

    assert len(cases) == 1
    assert cases[0]["source_benchmark"] == "ToolBench"
    assert cases[0]["expected_tool_calls"] == [{"name": "visit", "arguments": {}}]
    assert cases[0]["tool_argument_match_mode"] == "ignore"


def test_importer_cli_writes_jsonl(tmp_path: Path, capsys) -> None:
    source = tmp_path / "bfcl.jsonl"
    output = tmp_path / "cases.jsonl"
    source.write_text(
        json.dumps(
            {
                "id": "calc-1",
                "question": "Calculate 2 + 2.",
                "ground_truth": {"name": "calculator", "arguments": {"code": "2 + 2"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = import_tool_call_benchmark_cases.main(
        [
            "--benchmark",
            "bfcl",
            "--input",
            str(source),
            "--output",
            str(output),
            "--source-id",
            "bfcl-fixture",
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    written = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert exit_code == 0
    assert printed["case_count"] == 1
    assert written[0]["expected_tool_calls"][0]["name"] == "local_compute"


def test_import_bfcl_accepts_common_answer_shapes_and_limit(tmp_path: Path) -> None:
    source = tmp_path / "bfcl.json"
    source.write_text(
        json.dumps(
            [
                {"question_id": "skip-no-answer", "question": "No expected call."},
                {
                    "question_id": "string-answer",
                    "prompt": "Search alpha.",
                    "possible_answer": json.dumps({"name": "search", "arguments": "{\"query\":\"alpha\"}"}),
                },
                {
                    "question_id": "function-answer",
                    "user": "Calculate.",
                    "answers": [
                        {
                            "function": {
                                "name": "calculator",
                                "arguments": {"code": "3 + 4"},
                            }
                        }
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )

    cases = import_tool_call_benchmark_cases.import_bfcl(source, source_id="bfcl-fixture", limit=1)

    assert len(cases) == 1
    assert cases[0]["id"] == "bfcl-string-answer"
    assert cases[0]["expected_tool_calls"] == [
        {"name": "text_search", "arguments": {"query": "alpha"}}
    ]


def test_import_toolbench_accepts_direct_tool_fields_string_api_and_limit(tmp_path: Path) -> None:
    source = tmp_path / "toolbench.json"
    source.write_text(
        json.dumps(
            [
                {"id": "skip", "query": "No tool."},
                {"id": "direct", "instruction": "Search.", "tool_name": "text_search"},
                {"id": "api-string", "question": "Compute.", "api_list": ["calculator"]},
            ]
        ),
        encoding="utf-8",
    )

    cases = import_tool_call_benchmark_cases.import_toolbench(
        source,
        source_id="toolbench-fixture",
        limit=1,
    )

    assert len(cases) == 1
    assert cases[0]["id"] == "toolbench-direct"
    assert cases[0]["expected_tool_calls"] == [{"name": "text_search", "arguments": {}}]


def test_importer_rejects_invalid_record_shapes(tmp_path: Path) -> None:
    jsonl_non_object = tmp_path / "bad.jsonl"
    jsonl_non_object.write_text("[]\n", encoding="utf-8")
    dict_non_list = tmp_path / "bad-dict.json"
    dict_non_list.write_text(json.dumps({"data": {"bad": True}}), encoding="utf-8")
    list_non_object = tmp_path / "bad-list.json"
    list_non_object.write_text(json.dumps(["bad"]), encoding="utf-8")

    with pytest.raises(ValueError, match="must contain JSON objects"):
        import_tool_call_benchmark_cases._iter_json_records(jsonl_non_object)
    with pytest.raises(ValueError, match="does not contain a JSON record list"):
        import_tool_call_benchmark_cases._iter_json_records(dict_non_list)
    with pytest.raises(ValueError, match="record list must contain JSON objects"):
        import_tool_call_benchmark_cases._iter_json_records(list_non_object)


def test_importer_reports_jsonl_parse_errors_with_path_and_line(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text("{}\n{bad\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Invalid JSON in .*malformed\.jsonl:2:"):
        import_tool_call_benchmark_cases._iter_json_records(malformed)


def test_coercion_helpers_skip_invalid_values_and_unknown_tools() -> None:
    assert import_tool_call_benchmark_cases._coerce_calls("not-json") == []
    assert import_tool_call_benchmark_cases._coerce_calls(123) == []
    assert import_tool_call_benchmark_cases._coerce_calls(["not-json", 123]) == []
    assert import_tool_call_benchmark_cases._coerce_calls({"calls": []}) == []
    assert import_tool_call_benchmark_cases._coerce_arguments("not-json") == {}
    assert import_tool_call_benchmark_cases._normalize_call_for_melix({"name": "email", "arguments": {}}) == {}
    assert import_tool_call_benchmark_cases._first_non_empty("", None) == ""


def test_empty_snapshots_and_nested_function_arguments_are_handled(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    unknown_only = tmp_path / "unknown.jsonl"
    unknown_only.write_text(
        json.dumps({"question": "Unknown tool.", "ground_truth": {"name": "send_email", "arguments": {}}})
        + "\n",
        encoding="utf-8",
    )

    assert import_tool_call_benchmark_cases._iter_json_records(empty) == []
    assert import_tool_call_benchmark_cases.import_bfcl(unknown_only, source_id="bfcl-fixture") == []
    assert import_tool_call_benchmark_cases._coerce_calls(
        [{"function": {"name": "search", "arguments": "{\"query\":\"nested\"}"}}]
    ) == [{"name": "search", "arguments": {"query": "nested"}}]
    assert import_tool_call_benchmark_cases._coerce_calls([{"function": {"name": "search"}}]) == [
        {"name": "search", "arguments": {}}
    ]
    assert import_tool_call_benchmark_cases._toolbench_expected_tool({"api_list": ["calculator"]}) == "calculator"
