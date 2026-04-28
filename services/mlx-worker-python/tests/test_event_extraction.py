from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

from worker.engine.evaluation_core import EvaluationCore
from worker.engine import evaluation_core
from worker.productization import event_extraction as event_extraction_module
from worker.productization.event_extraction import (
    EventExtractionClientResult,
    EventExtractionPromptSpec,
    GeminiGenerativeLanguageEventExtractionClient,
    OpenAICompatibleEventExtractionClient,
    RemoteProviderHTTPError,
    build_event_digest,
    evaluate_event_extraction,
    make_event_extraction_client,
    normalize_event_fields,
    RemoteEventExtractionTarget,
    write_event_prediction_rows,
)


def test_normalize_event_fields_nulls_empty_values_and_builds_digest() -> None:
    event = normalize_event_fields(
        {
            "actor": [" 我 ", "", "他"],
            "time": [],
            "location": ["公司"],
            "action": ["开会", "复盘"],
            "digest": "ignored",
        }
    )

    assert event == {
        "actor": ["我", "他"],
        "time": None,
        "location": ["公司"],
        "action": ["开会", "复盘"],
        "digest": "我和他公司开会,复盘",
    }
    assert build_event_digest(
        actor=["我", "他"],
        time=None,
        location=["公司"],
        action=["开会", "复盘"],
    ) == "我和他公司开会,复盘"


def test_evaluate_event_extraction_weighted_f1_outputs_summary_and_details(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_summary.json"
    details_path = tmp_path / "event_eval_details.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-1",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["我", "他"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""},
                    {"actor": None, "time": ["周二"], "location": None, "action": ["出差"], "digest": ""},
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-1",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["我"], "time": ["周一", "周三"], "location": None, "action": ["开会"], "digest": ""},
                    {"actor": ["额外"], "time": ["周二"], "location": None, "action": ["出差"], "digest": ""},
                    {"actor": ["额外"], "time": None, "location": None, "action": ["跑步"], "digest": ""},
                ],
            }
        ],
    )

    summary = evaluate_event_extraction(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    assert summary["summary"]["events_evaluated"] == 3
    assert summary["summary"]["events_matched"] == 2
    assert summary["summary"]["events_unmatched_pred"] == 1
    assert summary["overall_weighted_f1"] == 0.487654
    assert summary["summary"]["overall_weighted_f1"] == 0.487654
    assert summary["field_metrics"]["actor"]["tp"] == 1
    assert summary["field_metrics"]["actor"]["fp"] == 2
    assert summary["field_metrics"]["actor"]["fn"] == 1
    assert summary["rates"]["hallucination_rate_by_field"]["actor"] == 0.666667
    assert details[0]["weighted_f1"] == 0.796296
    assert details[1]["weighted_f1"] == 0.666667
    assert details[2]["match_status"] == "unmatched_pred"
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary


def test_evaluate_event_extraction_counts_unmatched_gold(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_summary.json"
    details_path = tmp_path / "event_eval_details.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-1",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["A"], "time": None, "location": None, "action": ["planned"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(pred, [{"dialogue_id": "dlg-1", "dialogue": ["A: hi"], "events": []}])

    summary = evaluate_event_extraction(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    assert summary["summary"]["events_unmatched_gold"] == 1
    assert summary["field_metrics"]["actor"]["fn"] == 1
    assert details[0]["match_status"] == "unmatched_gold"
    assert details[0]["weighted_f1"] == 0.0


def test_evaluate_event_extraction_aligns_reordered_events_before_exact_scoring(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_summary.json"
    details_path = tmp_path / "event_eval_details.jsonl"
    row_audit_path = tmp_path / "event_eval_row_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-reordered",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["A"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""},
                    {"actor": ["B"], "time": ["周二"], "location": ["上海"], "action": ["出差"], "digest": ""},
                    {"actor": ["C"], "time": ["周三"], "location": None, "action": ["聚餐"], "digest": ""},
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-reordered",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["B"], "time": ["周二"], "location": ["上海"], "action": ["出差"], "digest": ""},
                    {"actor": ["A"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""},
                    {"actor": ["C"], "time": ["周三"], "location": None, "action": ["聚餐"], "digest": ""},
                ],
            }
        ],
    )

    summary = evaluate_event_extraction(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    audit = [json.loads(line) for line in row_audit_path.read_text(encoding="utf-8").splitlines()]
    assert summary["overall_weighted_f1"] == 1.0
    assert summary["alignment_strategy"] == "optimal_soft_event_alignment"
    assert summary["event_alignment"]["matched_pairs"] == 3
    assert [(row["gold_event_index"], row["pred_event_index"]) for row in details] == [(0, 1), (1, 0), (2, 2)]
    assert all(row["match_status"] == "matched" for row in details)
    assert details[0]["event_index"] == 0
    assert details[0]["alignment_score"] == 1.0
    assert audit[0]["matched_pairs"] == [
        {"gold_event_index": 0, "pred_event_index": 1, "alignment_score": 1.0},
        {"gold_event_index": 1, "pred_event_index": 0, "alignment_score": 1.0},
        {"gold_event_index": 2, "pred_event_index": 2, "alignment_score": 1.0},
    ]


def test_evaluate_event_extraction_uses_soft_alignment_but_exact_field_scores(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_summary.json"
    details_path = tmp_path / "event_eval_details.jsonl"
    row_audit_path = tmp_path / "event_eval_row_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-soft",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["我"], "time": ["明天"], "location": None, "action": ["开会"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-soft",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["我"], "time": ["明天"], "location": None, "action": ["明天开会"], "digest": ""}
                ],
            }
        ],
    )

    summary = evaluate_event_extraction(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
    )

    detail = json.loads(details_path.read_text(encoding="utf-8").splitlines()[0])
    assert detail["match_status"] == "matched"
    assert detail["alignment_score"] >= 0.30
    assert detail["fields"]["action"]["tp"] == 0
    assert detail["fields"]["action"]["fp"] == 1
    assert detail["fields"]["action"]["fn"] == 1
    assert summary["field_metrics"]["action"]["f1"] == 0.0
    assert summary["overall_weighted_f1"] == 0.611111


def test_evaluate_event_extraction_keeps_low_similarity_events_unmatched(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_summary.json"
    details_path = tmp_path / "event_eval_details.jsonl"
    row_audit_path = tmp_path / "event_eval_row_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-extra",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["A"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-extra",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["A"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""},
                    {"actor": ["Z"], "time": ["明年"], "location": ["火星"], "action": ["跑步"], "digest": ""},
                ],
            }
        ],
    )

    summary = evaluate_event_extraction(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    audit = [json.loads(line) for line in row_audit_path.read_text(encoding="utf-8").splitlines()]
    assert [row["match_status"] for row in details] == ["matched", "unmatched_pred"]
    assert details[1]["event_index"] == 1
    assert details[1]["gold_event_index"] is None
    assert details[1]["pred_event_index"] == 1
    assert summary["summary"]["events_unmatched_pred"] == 1
    assert audit[0]["unmatched_pred_indices"] == [1]


def test_event_alignment_uses_global_optimum_not_greedy() -> None:
    matches = event_extraction_module._maximum_weight_event_matching(
        [
            [0.90, 0.80],
            [0.80, 0.10],
        ],
        [
            [True, True],
            [True, True],
        ],
    )

    assert matches == [(0, 1, 0.80), (1, 0, 0.80)]


def test_write_event_prediction_rows_preserves_input_order_and_records_failures(tmp_path: Path) -> None:
    output = tmp_path / "predictions.jsonl"
    failures = tmp_path / "failures.jsonl"
    rows = [
        {
            "dialogue_id": "dlg-1",
            "dialogue": ["A: hi"],
            "events": [
                {"actor": ["A"], "time": None, "location": None, "action": ["arrived"]},
                {"actor": [], "time": [], "location": [], "action": []},
            ],
        },
        {
            "dialogue_id": "dlg-2",
            "dialogue": ["B: tomorrow"],
            "events": [{"actor": ["B"], "time": ["tomorrow"], "location": None, "action": ["plans"]}],
        },
    ]

    report = write_event_prediction_rows(rows=rows, output_path=output, failure_path=failures)

    written = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    failure_rows = [json.loads(line) for line in failures.read_text(encoding="utf-8").splitlines()]
    assert report == {"dialogues_written": 2, "events_written": 2, "events_failed": 1}
    assert [row["dialogue_id"] for row in written] == ["dlg-1", "dlg-2"]
    assert written[0]["events"] == [
        {"actor": ["A"], "time": None, "location": None, "action": ["arrived"], "digest": "Aarrived"}
    ]
    assert failure_rows == [
        {
            "dialogue_id": "dlg-1",
            "line_number": 1,
            "event_index": 1,
            "reason": "extracted event must contain at least one non-empty field",
        }
    ]


def test_write_event_prediction_rows_accepts_string_dialogue_and_skips_non_object_events(tmp_path: Path) -> None:
    output = tmp_path / "predictions.jsonl"
    failures = tmp_path / "failures.jsonl"

    report = write_event_prediction_rows(
        rows=[
            {
                "dialogue_id": "dlg-1",
                "dialogue": " A: hi\n\nB: tomorrow ",
                "events": [
                    "bad",
                    {"actor": ["B"], "time": ["tomorrow"], "location": None, "action": ["travels"]},
                ],
            },
            {
                "dialogue_id": "dlg-2",
                "dialogue": 42,
                "events": "not-a-list",
            },
        ],
        output_path=output,
        failure_path=failures,
    )

    written = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    failure_rows = [json.loads(line) for line in failures.read_text(encoding="utf-8").splitlines()]
    assert report == {"dialogues_written": 2, "events_written": 1, "events_failed": 1}
    assert written[0]["dialogue"] == ["A: hi", "B: tomorrow"]
    assert written[1]["dialogue"] == []
    assert failure_rows[0]["reason"] == "extracted event must be a JSON object"


def test_evaluation_core_runs_event_extraction_with_remote_target_without_persisting_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "top200_final.jsonl"
    _write_jsonl(
        source,
        [
            {
                "dialogue_id": "dlg-1",
                "dialogue": ["A: 周一我和他开会"],
                "events": [
                    {"actor": ["我", "他"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""}
                ],
            }
        ],
    )

    class FakeClient:
        def __init__(self, target):
            self.target = target

        def extract_events(self, dialogue, dialogue_id=""):
            assert dialogue_id == "dlg-1"
            return EventExtractionClientResult(
                events=[{"actor": ["我", "他"], "time": ["周一"], "location": None, "action": ["开会"]}],
                raw_response='{"events":[]}',
                request_body_bytes=123,
                response_body_bytes=456,
                provider_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )

    class FakeTarget:
        remote_server_id = "sub2api"
        provider_kind = "openai-compatible"
        base_url = "https://sub2api.example/v1"
        api_key = "sk-secret"
        model_id = "gemini-2.5-flash"
        timeout_seconds = 30
        rate_limit_per_minute = 0

    captured = {}

    def fake_client_factory(target, prompt_spec=None):
        captured["prompt_spec"] = prompt_spec
        return FakeClient(target)

    monkeypatch.setattr(evaluation_core, "make_event_extraction_client", fake_client_factory)

    core = EvaluationCore(jobs_root=tmp_path / "evals")
    run = core.run_local_suite(
        model_id="gemini-2.5-flash",
        suite_id="event_extraction",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="event_extraction_weighted_f1",
        parameters={
            "dataset_id": "top200",
            "event_source_jsonl": str(source),
            "remote_server_id": "sub2api",
            "remote_model_id": "gemini-2.5-flash",
            "eval_prompt_id": "event-prod",
            "eval_prompt_revision_id": "rev-1",
            "eval_prompt_content_hash": "sha256:prompt",
            "eval_prompt_title": "Event Prod",
            "eval_prompt_system_prompt": "Extract only events from this dialogue.",
            "eval_prompt_examples_json": "[]",
        },
        remote_target=FakeTarget(),
    )

    output_dir = Path(run.job.output_dir)
    assert run.result.primary_score_name == "overall_weighted_f1"
    assert run.result.primary_score_value == 1.0
    assert run.job.parameters["remote_server_id"] == "sub2api"
    assert "sk-secret" not in run.job.parameters.values()
    assert "eval_prompt_system_prompt" not in run.job.parameters
    assert run.job.parameters["prompt_id"] == "event-prod"
    assert run.job.parameters["prompt_revision_id"] == "rev-1"
    assert run.job.parameters["prompt_content_hash"] == "sha256:prompt"
    assert run.job.parameters["event_eval_dialogue_traces"].endswith("event_eval_dialogue_traces.jsonl")
    assert run.job.parameters["event_eval_row_audit"].endswith("event_eval_row_audit.jsonl")
    assert captured["prompt_spec"].system_prompt == "Extract only events from this dialogue."
    assert (output_dir / "predictions" / "gemini-2.5-flash.jsonl").is_file()
    summary_path = output_dir / "reports" / "gemini-2.5-flash" / "event_eval_summary.json"
    trace_path = output_dir / "reports" / "gemini-2.5-flash" / "event_eval_dialogue_traces.jsonl"
    row_audit_path = output_dir / "reports" / "gemini-2.5-flash" / "event_eval_row_audit.jsonl"
    assert summary_path.is_file()
    assert row_audit_path.is_file()
    traces = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert traces == [
        {
            "dialogue_id": "dlg-1",
            "line_number": 1,
            "status": "ok",
            "total_duration_ms": traces[0]["total_duration_ms"],
            "request_duration_ms": traces[0]["request_duration_ms"],
            "throttle_sleep_ms": 0.0,
            "normalization_duration_ms": traces[0]["normalization_duration_ms"],
            "dialogue_line_count": 1,
            "dialogue_char_count": 10,
            "request_body_bytes": 123,
            "response_body_bytes": 456,
            "raw_response_chars": 13,
            "raw_response_path": str(output_dir / "raw-responses" / "gemini-2.5-flash" / "0001-dlg-1.txt"),
            "predicted_event_count": 1,
            "normalized_event_count": 1,
            "normalization_failure_count": 0,
            "error_code": None,
            "failure_reason": None,
            "provider_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    ]
    assert traces[0]["total_duration_ms"] >= traces[0]["request_duration_ms"] >= 0
    assert traces[0]["normalization_duration_ms"] >= 0
    trace_json = json.dumps(traces, ensure_ascii=False)
    assert "sk-secret" not in trace_json
    assert "https://sub2api.example/v1" not in trace_json
    assert "Extract only events from this dialogue." not in trace_json
    assert "digest" not in trace_json
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    diagnostics = summary["dialogue_diagnostics"]
    assert diagnostics["dialogue_status_counts"] == {"ok": 1, "failed": 0, "aborted": 0}
    assert diagnostics["raw_response_chars"]["mean"] == 13.0
    assert diagnostics["provider_usage_totals"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert diagnostics["slowest_dialogues"] == [
        {
            "dialogue_id": "dlg-1",
            "line_number": 1,
            "duration_ms": traces[0]["total_duration_ms"],
            "status": "ok",
        }
    ]
    prompt_snapshot = json.loads((output_dir / "prompt_snapshot.json").read_text(encoding="utf-8"))
    assert prompt_snapshot["prompt_id"] == "event-prod"
    assert prompt_snapshot["system_prompt"] == "Extract only events from this dialogue."


def test_evaluation_core_event_extraction_records_client_and_normalization_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "top200_final.jsonl"
    _write_jsonl(
        source,
        [
            {
                "dialogue_id": "dlg-fail-client",
                "dialogue": ["A: first"],
                "events": [{"actor": ["A"], "time": None, "location": None, "action": ["first"], "digest": ""}],
            },
            {
                "dialogue_id": "dlg-fail-normalize",
                "dialogue": "B: second",
                "events": [{"actor": ["B"], "time": None, "location": None, "action": ["second"], "digest": ""}],
            },
        ],
    )

    class FakeClient:
        def __init__(self, target):
            self.target = target
            self.calls = 0

        def extract_events(self, dialogue, dialogue_id=""):
            self.calls += 1
            assert dialogue_id in {"dlg-fail-client", "dlg-fail-normalize"}
            if self.calls == 1:
                raise RuntimeError("provider unavailable")
            return ([{"actor": [1], "time": None, "location": None, "action": ["bad"]}], '{"events":[]}')

    class FakeTarget:
        provider_kind = "openai-compatible"
        base_url = "https://sub2api.example/v1"
        api_key = "sk-secret"
        model_id = "remote/model"
        timeout_seconds = 30
        rate_limit_per_minute = 0

    monkeypatch.setattr(evaluation_core, "make_event_extraction_client", lambda target, prompt_spec=None: FakeClient(target))

    run = EvaluationCore(jobs_root=tmp_path / "evals").run_local_suite(
        model_id="remote/model",
        suite_id="event_extraction",
        dataset_root=tmp_path,
        sample_size=2,
        scoring_mode="event_extraction_weighted_f1",
        parameters={"event_source_jsonl": str(source)},
        remote_target=FakeTarget(),
    )

    output_dir = Path(run.job.output_dir)
    prediction_rows = [
        json.loads(line)
        for line in (output_dir / "predictions" / "remote_model.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    failures = [
        json.loads(line)
        for line in (output_dir / "predictions" / "remote_model.failures.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert prediction_rows[0]["events"] == []
    assert prediction_rows[1]["dialogue"] == ["B: second"]
    assert len(failures) == 2
    assert failures[0]["reason"] == "provider unavailable"
    assert failures[1]["event_index"] == 0
    assert "actor must be null or an array of strings" in failures[1]["reason"]
    traces = [
        json.loads(line)
        for line in (
            output_dir / "reports" / "remote_model" / "event_eval_dialogue_traces.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert [trace["status"] for trace in traces] == ["failed", "ok"]
    assert traces[0]["failure_reason"] == "provider unavailable"
    assert traces[0]["predicted_event_count"] == 0
    assert traces[1]["normalization_failure_count"] == 1


def test_evaluation_core_event_extraction_records_rate_limit_sleep_in_dialogue_traces(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "top200_final.jsonl"
    _write_jsonl(
        source,
        [
            {
                "dialogue_id": "dlg-one",
                "dialogue": ["A: first"],
                "events": [{"actor": ["A"], "time": None, "location": None, "action": ["first"], "digest": ""}],
            },
            {
                "dialogue_id": "dlg-two",
                "dialogue": ["B: second"],
                "events": [{"actor": ["B"], "time": None, "location": None, "action": ["second"], "digest": ""}],
            },
        ],
    )

    class FakeClock:
        def __init__(self) -> None:
            self.now = 100.0
            self.sleeps: list[float] = []

        def perf_counter(self) -> float:
            value = self.now
            self.now += 0.001
            return value

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

    fake_clock = FakeClock()

    class FakeClient:
        def extract_events(self, dialogue, dialogue_id=""):
            return EventExtractionClientResult(
                events=[{"actor": [dialogue[0][0]], "time": None, "location": None, "action": [dialogue[0][3:]]}],
                raw_response='{"events":[]}',
            )

    class FakeTarget:
        provider_kind = "openai-compatible"
        base_url = "https://sub2api.example/v1"
        api_key = "sk-secret"
        model_id = "remote/model"
        timeout_seconds = 30
        rate_limit_per_minute = 60

    monkeypatch.setattr(evaluation_core, "make_event_extraction_client", lambda target, prompt_spec=None: FakeClient())
    monkeypatch.setattr(evaluation_core.time, "perf_counter", fake_clock.perf_counter)
    monkeypatch.setattr(evaluation_core.time, "sleep", fake_clock.sleep)

    run = EvaluationCore(jobs_root=tmp_path / "evals").run_local_suite(
        model_id="remote/model",
        suite_id="event_extraction",
        dataset_root=tmp_path,
        sample_size=2,
        scoring_mode="event_extraction_weighted_f1",
        parameters={"event_source_jsonl": str(source)},
        remote_target=FakeTarget(),
    )

    output_dir = Path(run.job.output_dir)
    traces = [
        json.loads(line)
        for line in (
            output_dir / "reports" / "remote_model" / "event_eval_dialogue_traces.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads(
        (output_dir / "reports" / "remote_model" / "event_eval_summary.json").read_text(encoding="utf-8")
    )

    assert traces[0]["throttle_sleep_ms"] == 0.0
    assert traces[1]["throttle_sleep_ms"] > 900.0
    assert summary["dialogue_diagnostics"]["total_throttle_sleep_ms"] == traces[1]["throttle_sleep_ms"]
    assert fake_clock.sleeps


def test_evaluation_core_event_extraction_aborts_on_provider_rate_limit_and_writes_error_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "top200_final.jsonl"
    _write_jsonl(
        source,
        [
            {
                "dialogue_id": "dlg-rate-1",
                "dialogue": ["A: first"],
                "events": [{"actor": ["A"], "time": None, "location": None, "action": ["first"], "digest": ""}],
            },
            {
                "dialogue_id": "dlg-rate-2",
                "dialogue": ["B: second"],
                "events": [{"actor": ["B"], "time": None, "location": None, "action": ["second"], "digest": ""}],
            },
        ],
    )

    captured = {}

    class FakeClient:
        def __init__(self, target):
            self.target = target
            self.calls = 0

        def extract_events(self, dialogue, dialogue_id=""):
            self.calls += 1
            raise RemoteProviderHTTPError(status_code=429, response_body='{"error":"rate"}')

    class FakeTarget:
        remote_server_id = "deepseek"
        provider_kind = "openai-compatible"
        base_url = "https://api.deepseek.com/v1"
        api_key = "sk-secret"
        model_id = "remote/model"
        timeout_seconds = 30
        rate_limit_per_minute = 0

    def fake_client_factory(target, prompt_spec=None):
        client = FakeClient(target)
        captured["client"] = client
        return client

    monkeypatch.setattr(evaluation_core, "make_event_extraction_client", fake_client_factory)

    try:
        EvaluationCore(jobs_root=tmp_path / "evals").run_local_suite(
            model_id="remote/model",
            suite_id="event_extraction",
            dataset_root=tmp_path,
            sample_size=2,
            scoring_mode="event_extraction_weighted_f1",
            parameters={"event_source_jsonl": str(source)},
            remote_target=FakeTarget(),
        )
    except RuntimeError as exc:
        assert "event extraction aborted after remote provider HTTP 429" in str(exc)
        assert "event_eval_error.json" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected provider rate limit to abort evaluation")

    output_dir = tmp_path / "evals" / "event-extraction" / "eval-0001"
    error_log = output_dir / "reports" / "remote_model" / "event_eval_error.json"
    failure_log = output_dir / "predictions" / "remote_model.failures.jsonl"
    prediction_log = output_dir / "predictions" / "remote_model.jsonl"

    error_payload = json.loads(error_log.read_text(encoding="utf-8"))
    assert error_payload["code"] == "remote_provider_rate_limited"
    assert error_payload["status_code"] == 429
    assert error_payload["line_number"] == 1
    assert error_payload["dialogue_id"] == "dlg-rate-1"
    assert error_payload["rows_total"] == 2
    assert error_payload["rows_attempted"] == 1
    assert error_payload["remote_server_id"] == "deepseek"
    assert error_payload["event_eval_dialogue_traces"].endswith("event_eval_dialogue_traces.jsonl")
    assert "sk-secret" not in json.dumps(error_payload)
    assert "https://api.deepseek.com/v1" not in json.dumps(error_payload)
    assert captured["client"].calls == 1

    failures = [json.loads(line) for line in failure_log.read_text(encoding="utf-8").splitlines()]
    assert len(failures) == 1
    assert failures[0]["reason"] == 'remote provider HTTP 429: {"error":"rate"}'
    assert failures[0]["code"] == "remote_provider_rate_limited"
    assert prediction_log.read_text(encoding="utf-8") == ""
    trace_log = output_dir / "reports" / "remote_model" / "event_eval_dialogue_traces.jsonl"
    traces = [json.loads(line) for line in trace_log.read_text(encoding="utf-8").splitlines()]
    assert len(traces) == 1
    assert traces[0]["dialogue_id"] == "dlg-rate-1"
    assert traces[0]["status"] == "aborted"
    assert traces[0]["error_code"] == "remote_provider_rate_limited"
    assert traces[0]["failure_reason"] == 'remote provider HTTP 429: {"error":"rate"}'
    assert "sk-secret" not in json.dumps(traces, ensure_ascii=False)


def test_evaluation_core_reserves_unique_job_ids_for_concurrent_runs(tmp_path: Path) -> None:
    jobs_root = tmp_path / "evals"
    (jobs_root / "runs" / "eval-0001").mkdir(parents=True)
    core = EvaluationCore(jobs_root=jobs_root)

    with ThreadPoolExecutor(max_workers=4) as executor:
        job_ids = list(executor.map(lambda _: core._next_job_id(), range(4)))

    assert sorted(job_ids) == ["eval-0002", "eval-0003", "eval-0004", "eval-0005"]
    for job_id in job_ids:
        assert (jobs_root / "runs" / job_id).is_dir()


def test_evaluation_core_event_extraction_validates_source_target_and_rows(tmp_path: Path) -> None:
    core = EvaluationCore(jobs_root=tmp_path / "evals")

    try:
        core.run_local_suite(
            model_id="remote",
            suite_id="event_extraction",
            dataset_root=tmp_path,
            sample_size=1,
            scoring_mode="event_extraction_weighted_f1",
            parameters={},
            remote_target=object(),
        )
    except ValueError as exc:
        assert str(exc) == "event_extraction_weighted_f1 requires a local JSONL source."
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected missing source validation")

    source = tmp_path / "rows.jsonl"
    _write_jsonl(source, [{"dialogue_id": "dlg-1", "dialogue": [], "events": []}])
    try:
        core.run_local_suite(
            model_id="remote",
            suite_id="event_extraction",
            dataset_root=tmp_path,
            sample_size=1,
            scoring_mode="event_extraction_weighted_f1",
            parameters={"event_source_jsonl": str(source)},
            remote_target=None,
        )
    except ValueError as exc:
        assert str(exc) == "event_extraction_weighted_f1 requires a remote provider target."
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected missing remote target validation")

    invalid_cases = [
        ("[]\n", "expected JSON object"),
        (json.dumps({"dialogue_id": "", "events": []}) + "\n", "missing dialogue_id"),
        (json.dumps({"dialogue_id": "dlg-1", "events": {}}) + "\n", "events must be a list"),
        ("\n", "event extraction source JSONL is empty"),
    ]
    for raw, expected in invalid_cases:
        source.write_text(raw, encoding="utf-8")
        try:
            EvaluationCore._read_event_extraction_rows(source, sample_size=1)
        except ValueError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected row validation")


def test_evaluation_core_event_extraction_rejects_prompt_example_overlap(tmp_path: Path) -> None:
    source = tmp_path / "top200_final.jsonl"
    _write_jsonl(
        source,
        [
            {
                "dialogue_id": "dlg-1",
                "dialogue": ["A: tomorrow"],
                "events": [{"actor": ["A"], "time": ["tomorrow"], "location": None, "action": ["plan"], "digest": ""}],
            }
        ],
    )

    class FakeTarget:
        provider_kind = "openai-compatible"
        base_url = "https://sub2api.example/v1"
        api_key = "sk-secret"
        model_id = "remote-model"
        timeout_seconds = 30
        rate_limit_per_minute = 0

    try:
        EvaluationCore(jobs_root=tmp_path / "evals").run_local_suite(
            model_id="remote-model",
            suite_id="event_extraction",
            dataset_root=tmp_path,
            sample_size=1,
            scoring_mode="event_extraction_weighted_f1",
            parameters={
                "event_source_jsonl": str(source),
                "eval_prompt_id": "event-prod",
                "eval_prompt_revision_id": "rev-1",
                "eval_prompt_system_prompt": "Use examples.",
                "eval_prompt_examples_json": json.dumps(
                    [
                        {
                            "dialogue_id": "dlg-1",
                            "dialogue": ["example"],
                            "events": [],
                        }
                    ]
                ),
            },
            remote_target=FakeTarget(),
        )
    except ValueError as exc:
        assert str(exc) == "event extraction prompt examples overlap evaluation rows: dlg-1"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected prompt example overlap validation")


def test_evaluation_core_event_extraction_prompt_spec_validates_examples_and_derives_hash() -> None:
    spec = EvaluationCore._event_extraction_prompt_spec(
        {
            "eval_prompt_id": "event-prod",
            "eval_prompt_revision_id": "rev-2",
            "eval_prompt_title": "Event Prod",
            "eval_prompt_system_prompt": "Extract frozen events.",
            "eval_prompt_examples_json": json.dumps(
                [
                    {
                        "dialogue_id": "example-1",
                        "dialogue": ["A: 明天开会"],
                        "events": [
                            {
                                "actor": ["A"],
                                "time": ["明天"],
                                "location": None,
                                "action": ["开会"],
                            }
                        ],
                    }
                ]
            ),
        }
    )

    assert spec.prompt_id == "event-prod"
    assert spec.revision_id == "rev-2"
    assert spec.title == "Event Prod"
    assert spec.content_hash.startswith("sha256:")
    assert spec.examples[0]["dialogue_id"] == "example-1"

    invalid_cases = [
        (
            {"eval_prompt_system_prompt": "Prompt", "eval_prompt_examples_json": "not json"},
            "eval_prompt_examples_json must be valid JSON",
        ),
        (
            {"eval_prompt_system_prompt": "Prompt", "eval_prompt_examples_json": "{}"},
            "eval_prompt_examples_json must be a JSON array",
        ),
        (
            {"eval_prompt_system_prompt": "Prompt", "eval_prompt_examples_json": "[1]"},
            "eval prompt example 0 must be a JSON object",
        ),
        (
            {"eval_prompt_system_prompt": "Prompt", "eval_prompt_examples_json": '[{"dialogue":[]}]'},
            "eval prompt example 0 is missing dialogue_id",
        ),
    ]
    for parameters, expected in invalid_cases:
        try:
            EvaluationCore._event_extraction_prompt_spec(parameters)
        except ValueError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected prompt example validation")


def test_event_extraction_client_factory_supports_openai_and_gemini() -> None:
    openai_client = make_event_extraction_client(
        RemoteEventExtractionTarget(
            provider_kind="openai-compatible",
            base_url="https://sub2api.example/v1",
            api_key="sk-secret",
            model_id="kimi-2.6",
        )
    )
    gemini_client = make_event_extraction_client(
        RemoteEventExtractionTarget(
            provider_kind="gemini-generative-language",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="AIza-secret",
            model_id="gemini-2.5-flash",
        )
    )

    assert type(openai_client).__name__ == "OpenAICompatibleEventExtractionClient"
    assert isinstance(gemini_client, GeminiGenerativeLanguageEventExtractionClient)


def test_event_extraction_client_factory_rejects_unsupported_providers() -> None:
    target = RemoteEventExtractionTarget(
        provider_kind="anthropic",
        base_url="https://example.invalid",
        api_key="secret",
        model_id="model",
    )

    try:
        make_event_extraction_client(target)
    except ValueError as exc:
        assert str(exc) == "unsupported remote provider kind: anthropic"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected unsupported provider error")


def test_event_extraction_client_constructors_reject_mismatched_provider_kind() -> None:
    openai_target = RemoteEventExtractionTarget(
        provider_kind="gemini-generative-language",
        base_url="https://example.invalid",
        api_key="secret",
        model_id="model",
    )
    gemini_target = RemoteEventExtractionTarget(
        provider_kind="openai-compatible",
        base_url="https://example.invalid",
        api_key="secret",
        model_id="model",
    )

    for constructor, target in [
        (OpenAICompatibleEventExtractionClient, openai_target),
        (GeminiGenerativeLanguageEventExtractionClient, gemini_target),
    ]:
        try:
            constructor(target)
        except ValueError as exc:
            assert "unsupported remote provider kind" in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected constructor to reject mismatched provider")


def test_openai_event_extraction_posts_chat_completions_and_parses_response(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "events": [
                                            {
                                                "actor": ["我"],
                                                "time": ["明天"],
                                                "location": None,
                                                "action": ["开会"],
                                            }
                                        ]
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(event_extraction_module, "urlopen", fake_urlopen)

    client = OpenAICompatibleEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="openai-compatible",
            base_url="https://sub2api.example/v1/",
            api_key="sk-secret",
            model_id="kimi-2.6",
            timeout_seconds=37,
        )
    )

    events, raw_text = client.extract_events(["speaker_1: 明天我开会"], dialogue_id="dlg-smoke")

    assert events == [{"actor": ["我"], "time": ["明天"], "location": None, "action": ["开会"]}]
    assert raw_text.startswith("{")
    assert captured["url"] == "https://sub2api.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-secret"
    assert captured["timeout"] == 37
    assert captured["body"]["model"] == "kimi-2.6"
    assert captured["body"]["messages"][0]["role"] == "system"
    request_payload = json.loads(captured["body"]["messages"][1]["content"])
    assert request_payload["segment"] == {
        "segment_id": "dlg-smoke",
        "dialogue_id": "dlg-smoke",
        "message_count": 1,
    }
    assert request_payload["participant_set"] == [
        {"participant_id": "speaker_1", "display_name": "speaker_1"}
    ]
    assert request_payload["conversation"] == [
        {
            "message_id": "m1",
            "sender": "speaker_1",
            "participant_id": "speaker_1",
            "timestamp": None,
            "text": "明天我开会",
        }
    ]
    assert captured["body"]["temperature"] == 0


def test_event_extraction_clients_use_selected_prompt_and_examples(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"events":[]}'}}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(event_extraction_module, "urlopen", fake_urlopen)

    prompt = EventExtractionPromptSpec(
        prompt_id="event-prod",
        revision_id="rev-1",
        title="Event Prod",
        system_prompt="Use the frozen production prompt.",
        content_hash="sha256:prompt",
        examples=(
            {
                "dialogue_id": "example-1",
                "dialogue": ["A: tomorrow we meet"],
                "events": [
                    {
                        "actor": ["we"],
                        "time": ["tomorrow"],
                        "location": None,
                        "action": ["meet"],
                        "digest": "ignored",
                    }
                ],
            },
        ),
    )
    client = OpenAICompatibleEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="openai-compatible",
            base_url="https://sub2api.example/v1",
            api_key="sk-secret",
            model_id="kimi-2.6",
        ),
        prompt,
    )

    events, _ = client.extract_events(["A: current dialogue has no gold answer"])

    assert events == []
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "Use the frozen production prompt."},
        {"role": "user", "content": "A: tomorrow we meet"},
        {
            "role": "assistant",
            "content": '{"events":[{"actor":["we"],"time":["tomorrow"],"location":null,"action":["meet"]}]}',
        },
        {"role": "user", "content": "A: current dialogue has no gold answer"},
    ]
    assert "digest" not in json.dumps(captured["body"], ensure_ascii=False)


def test_event_extraction_clients_expose_standardized_provider_usage(monkeypatch) -> None:
    responses = [
        {
            "choices": [{"message": {"content": '{"events":[]}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        },
        {
            "candidates": [{"content": {"parts": [{"text": '{"events":[]}'}]}}],
            "usageMetadata": {"promptTokenCount": 13, "candidatesTokenCount": 5, "totalTokenCount": 18},
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(event_extraction_module, "urlopen", fake_urlopen)

    openai_result = OpenAICompatibleEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="openai-compatible",
            base_url="https://sub2api.example/v1",
            api_key="sk-secret",
            model_id="deepseek-v4-pro",
        )
    ).extract_events(["A: tomorrow"])
    gemini_result = GeminiGenerativeLanguageEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="gemini-generative-language",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="AIza-secret",
            model_id="gemini-2.5-flash",
        )
    ).extract_events(["A: tomorrow"])

    assert openai_result.provider_usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert gemini_result.provider_usage == {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18}
    assert openai_result.response_body_bytes > openai_result.raw_response_chars
    assert gemini_result.request_body_bytes > 0


def test_remote_event_extraction_http_clients_map_request_failures(monkeypatch) -> None:
    openai_client = OpenAICompatibleEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="openai-compatible",
            base_url="https://sub2api.example/v1",
            api_key="sk-secret",
            model_id="kimi-2.6",
        )
    )
    gemini_client = GeminiGenerativeLanguageEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="gemini-generative-language",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="AIza-secret",
            model_id="models/gemini 2.5/flash",
        )
    )

    def raise_http_error(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, BytesIO(b'{"error":"rate"}'))

    monkeypatch.setattr(event_extraction_module, "urlopen", raise_http_error)
    for client in [openai_client, gemini_client]:
        try:
            client._post_json({})  # type: ignore[attr-defined]
        except ValueError as exc:
            assert str(exc) == 'remote provider HTTP 429: {"error":"rate"}'
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected HTTP error mapping")

    def raise_url_error(request, timeout):
        raise URLError("timed out")

    monkeypatch.setattr(event_extraction_module, "urlopen", raise_url_error)
    for client in [openai_client, gemini_client]:
        try:
            client._post_json({})  # type: ignore[attr-defined]
        except ValueError as exc:
            assert str(exc) == "remote provider request failed: timed out"
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected URL error mapping")


def test_remote_event_extraction_http_clients_validate_base_url_and_json(monkeypatch) -> None:
    class FakeListResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"[]"

    monkeypatch.setattr(event_extraction_module, "urlopen", lambda request, timeout: FakeListResponse())

    for client in [
        OpenAICompatibleEventExtractionClient(
            RemoteEventExtractionTarget(
                provider_kind="openai-compatible",
                base_url=" ",
                api_key="secret",
                model_id="model",
            )
        ),
        GeminiGenerativeLanguageEventExtractionClient(
            RemoteEventExtractionTarget(
                provider_kind="gemini-generative-language",
                base_url=" ",
                api_key="secret",
                model_id="model",
            )
        ),
    ]:
        try:
            client._post_json({})  # type: ignore[attr-defined]
        except ValueError as exc:
            assert str(exc) == "remote provider base_url is empty"
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected empty base url validation")

    for client in [
        OpenAICompatibleEventExtractionClient(
            RemoteEventExtractionTarget(
                provider_kind="openai-compatible",
                base_url="https://sub2api.example/v1",
                api_key="secret",
                model_id="model",
            )
        ),
        GeminiGenerativeLanguageEventExtractionClient(
            RemoteEventExtractionTarget(
                provider_kind="gemini-generative-language",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key="secret",
                model_id="model",
            )
        ),
    ]:
        try:
            client._post_json({})  # type: ignore[attr-defined]
        except ValueError as exc:
            assert str(exc) == "remote provider response must be a JSON object"
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected object response validation")


def test_gemini_event_extraction_posts_generate_content_and_parses_response(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "events": [
                                                    {
                                                        "actor": ["我"],
                                                        "time": ["明天"],
                                                        "location": None,
                                                        "action": ["开会"],
                                                    }
                                                ]
                                            },
                                            ensure_ascii=False,
                                        )
                                    }
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(event_extraction_module, "urlopen", fake_urlopen)

    client = GeminiGenerativeLanguageEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="gemini-generative-language",
            base_url="https://generativelanguage.googleapis.com/v1beta/",
            api_key="AIza-secret",
            model_id="gemini-2.5-flash",
            timeout_seconds=45,
        ),
        EventExtractionPromptSpec(
            prompt_id="event-gemini",
            revision_id="rev-1",
            system_prompt="Gemini selected frozen prompt.",
            content_hash="sha256:gemini",
            examples=(
                {
                    "dialogue_id": "example-gemini",
                    "dialogue": ["A: 后天复盘"],
                    "events": [
                        {
                            "actor": ["A"],
                            "time": ["后天"],
                            "location": None,
                            "action": ["复盘"],
                        }
                    ],
                },
            ),
        ),
    )

    events, raw_text = client.extract_events(["A: 明天我开会"])

    assert events == [{"actor": ["我"], "time": ["明天"], "location": None, "action": ["开会"]}]
    assert raw_text.startswith("{")
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-2.5-flash:generateContent?key=AIza-secret"
    )
    assert "Authorization" not in captured["headers"]
    assert captured["timeout"] == 45
    assert captured["body"]["generationConfig"]["temperature"] == 0
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "Gemini selected frozen prompt."
    assert captured["body"]["contents"] == [
        {"role": "user", "parts": [{"text": "A: 后天复盘"}]},
        {
            "role": "model",
            "parts": [
                {
                    "text": '{"events":[{"actor":["A"],"time":["后天"],"location":null,"action":["复盘"]}]}'
                }
            ],
        },
        {"role": "user", "parts": [{"text": "A: 明天我开会"}]}
    ]


def test_response_parsing_and_normalization_validation_errors(tmp_path: Path) -> None:
    assert event_extraction_module.extract_events_from_response_text(
        """```json
{"events":[{"actor":["A"],"time":null,"location":null,"action":["arrived"]}]}
```"""
    ) == [{"actor": ["A"], "time": None, "location": None, "action": ["arrived"]}]
    assert event_extraction_module.extract_events_from_response_text(
        json.dumps(
            {
                "boundary_decision": {
                    "starts_new_dialogue": False,
                    "new_dialogue_start_message_id": None,
                    "boundary_confidence": 0.0,
                    "boundary_reason": "no_restart",
                },
                "entity_mentions": [],
                "time_mentions": [],
                "location_mentions": [],
                "topic_candidates": [],
                "digest_candidates": [],
                "event_candidates": [
                    {
                        "participants": ["speaker_1", "speaker_2"],
                        "time": ["周六晚上"],
                        "location": [],
                        "action": "见面吃饭",
                        "status": "planned",
                        "detail": None,
                        "confidence": 0.7,
                        "evidence": ["m1", "m2"],
                    }
                ],
                "issues": [],
            },
            ensure_ascii=False,
        )
    ) == [
        {
            "actor": ["speaker_1", "speaker_2"],
            "time": ["周六晚上"],
            "location": [],
            "action": ["见面吃饭"],
        }
    ]

    invalid_inputs = [
        ("{}", "LLM response must include an events or event_candidates array"),
        ('{"events":["bad"]}', "each event must be a JSON object"),
        ('{"event_candidates":["bad"]}', "each event candidate must be a JSON object"),
        ("[]", "LLM response must be a JSON object"),
    ]
    for response_text, expected in invalid_inputs:
        try:
            event_extraction_module.extract_events_from_response_text(response_text)
        except ValueError as exc:
            assert str(exc) == expected
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected response parsing validation")

    for payload, expected in [
        ([], "LLM response must be a JSON object"),
        ({"actor": "A", "time": None, "location": None, "action": ["arrived"]}, "actor must be null or an array of strings"),
        ({"actor": [1], "time": None, "location": None, "action": ["arrived"]}, "actor must be null or an array of strings"),
    ]:
        try:
            normalize_event_fields(payload)  # type: ignore[arg-type]
        except ValueError as exc:
            assert str(exc) == expected
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected field normalization validation")

    bad_jsonl = tmp_path / "bad.jsonl"
    for raw, expected in [
        ("[]\n", "expected JSON object"),
        (json.dumps({"dialogue_id": "", "events": []}) + "\n", "missing dialogue_id"),
        (json.dumps({"dialogue_id": "dlg-1", "events": {}}) + "\n", "events must be a list"),
    ]:
        bad_jsonl.write_text(raw, encoding="utf-8")
        try:
            evaluate_event_extraction(
                gold_jsonl=bad_jsonl,
                pred_jsonl=bad_jsonl,
                summary_output=tmp_path / "summary.json",
                details_output=tmp_path / "details.jsonl",
            )
        except ValueError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected jsonl validation")


def test_provider_response_content_validation_errors() -> None:
    openai_payloads = [
        ({}, "remote provider response did not include choices"),
        ({"choices": ["bad"]}, "remote provider choice must be a JSON object"),
        ({"choices": [{}]}, "remote provider choice did not include a message"),
        ({"choices": [{"message": {"content": 1}}]}, "remote provider message content must be a string"),
    ]
    for payload, expected in openai_payloads:
        try:
            event_extraction_module._assistant_content(payload)
        except ValueError as exc:
            assert str(exc) == expected
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected OpenAI content validation")

    gemini_payloads = [
        ({}, "remote provider response did not include candidates"),
        ({"candidates": ["bad"]}, "remote provider candidate must be a JSON object"),
        ({"candidates": [{}]}, "remote provider candidate did not include content"),
        ({"candidates": [{"content": {}}]}, "remote provider candidate content did not include parts"),
        ({"candidates": [{"content": {"parts": [{}]}}]}, "remote provider candidate parts did not include text"),
    ]
    for payload, expected in gemini_payloads:
        try:
            event_extraction_module._gemini_content(payload)
        except ValueError as exc:
            assert str(exc) == expected
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected Gemini content validation")

    assert event_extraction_module._gemini_model_path("models/gemini 2.5/flash") == "models/gemini%202.5/flash"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
