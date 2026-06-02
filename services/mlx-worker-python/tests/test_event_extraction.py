from __future__ import annotations

import builtins
import json
import runpy
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

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


def test_event_dialogue_diagnostics_keeps_top_five_without_full_sort(monkeypatch) -> None:
    traces = [
        {"dialogue_id": f"dlg-{index}", "line_number": index, "status": "ok", "total_duration_ms": float(index)}
        for index in range(30)
    ]
    traces[3]["provider_usage"] = {"prompt_tokens": 2.0, "ignored_bool": True}

    def fail_sorted(*args, **kwargs):  # pragma: no cover - exercised only on regression
        if args and args[0] is traces:
            raise AssertionError("slowest dialogue diagnostics should not fully sort all traces")
        return original_sorted(*args, **kwargs)

    original_sorted = builtins.sorted
    monkeypatch.setattr(builtins, "sorted", fail_sorted)

    diagnostics = EvaluationCore._event_extraction_dialogue_diagnostics(traces)

    assert diagnostics["provider_usage_totals"] == {"prompt_tokens": 2}
    assert diagnostics["dialogue_status_counts"] == {"ok": 30, "failed": 0, "aborted": 0}
    assert diagnostics["slowest_dialogues"] == [
        {"dialogue_id": "dlg-29", "line_number": 29, "duration_ms": 29.0, "status": "ok"},
        {"dialogue_id": "dlg-28", "line_number": 28, "duration_ms": 28.0, "status": "ok"},
        {"dialogue_id": "dlg-27", "line_number": 27, "duration_ms": 27.0, "status": "ok"},
        {"dialogue_id": "dlg-26", "line_number": 26, "duration_ms": 26.0, "status": "ok"},
        {"dialogue_id": "dlg-25", "line_number": 25, "duration_ms": 25.0, "status": "ok"},
    ]


def test_default_event_extraction_prompt_spec_uses_baseline_v6_feedback_rules() -> None:
    spec = event_extraction_module.default_event_extraction_prompt_spec()

    assert spec.prompt_id == event_extraction_module.EVENT_EXTRACTION_PROMPT_ID
    assert spec.revision_id == "baseline.v6"
    assert "连续时间区间" in spec.system_prompt
    assert "可用时间" in spec.system_prompt
    assert "模糊第三方关系词" in spec.system_prompt
    assert "反馈案例约束" in spec.system_prompt
    assert "召回强化" in spec.system_prompt
    assert "同地点同时吃饭" in spec.system_prompt
    assert "不要抽取为独立事件" in spec.system_prompt
    assert "周日新买裙子" in spec.system_prompt
    assert "明天打给你" in spec.system_prompt
    assert "周一晚上11点下飞机" in spec.system_prompt
    assert "周二晚上7点上飞机" in spec.system_prompt
    assert "同事/朋友/表姐" in spec.system_prompt
    assert spec.content_hash == event_extraction_module.event_prompt_content_hash(spec.system_prompt, [])


def test_local_event_extraction_disables_thinking_template_kwargs() -> None:
    captured: dict[str, object] = {}

    class FakeRuntime:
        def render_prompt(self, messages, *, loaded_model, template_kwargs=None, execution_ext=None):
            captured["messages"] = messages
            captured["loaded_model"] = loaded_model
            captured["template_kwargs"] = template_kwargs
            captured["execution_ext"] = execution_ext
            return "rendered prompt"

        def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
            captured["prompt"] = prompt
            yield SimpleNamespace(text='{"events":[{"actor":["speaker_1"],"time":["明天"],"location":null,"action":["开会"]}]}')

    class FakeRegistry:
        def __init__(self) -> None:
            self.runtime = FakeRuntime()
            self.finished_request_id = ""

        def runtime_for_loaded_model(self, loaded_model):
            return self.runtime

        def start_request(self, request_id, *, runtime_kind):
            return SimpleNamespace(cancel_event=threading.Event())

        def finish_request(self, request_id) -> None:
            self.finished_request_id = request_id

    registry = FakeRegistry()
    client = evaluation_core._LocalEventExtractionClient(
        registry=registry,
        loaded_model=SimpleNamespace(runtime_model={"model": "fixture"}, runtime_kind="text"),
        prompt_spec=event_extraction_module.default_event_extraction_prompt_spec(),
        max_output_tokens=128,
        seed=0,
    )

    events, raw_text = client.extract_events(["speaker_1: 明天我开会"], dialogue_id="dlg-local")

    assert captured["template_kwargs"] == {"enable_thinking": False}
    assert captured["prompt"] == "rendered prompt"
    assert registry.finished_request_id.startswith("event-extraction:local:dlg-local:")
    assert events == [{"actor": ["speaker_1"], "time": ["明天"], "location": None, "action": ["开会"]}]
    assert raw_text.startswith("{")


def test_parse_response_json_trims_partial_fenced_json_without_line_list() -> None:
    response = '```json\n{"events": [{"event_type": "delivery"}]}'

    assert event_extraction_module._parse_response_json(response) == {
        "events": [{"event_type": "delivery"}]
    }


def test_parse_response_json_trims_closing_fence_with_trailing_space() -> None:
    response = '```json\n{"events": []}\n```   '

    assert event_extraction_module._parse_response_json(response) == {"events": []}


def test_parse_response_json_accepts_leading_whitespace_before_fence() -> None:
    response = '  \n```json\n{"events": [{"event_type": "handoff"}]}\n```'

    assert event_extraction_module._parse_response_json(response) == {
        "events": [{"event_type": "handoff"}]
    }


def test_parse_response_json_accepts_generic_fence_after_fast_json_prefix() -> None:
    response = '```javascript\n{"events": [{"event_type": "generic"}]}\n```'

    assert event_extraction_module._parse_response_json(response) == {
        "events": [{"event_type": "generic"}]
    }


def test_parse_response_json_accepts_unfenced_json_without_pretrim_copy() -> None:
    response = '  {"events": [{"event_type": "pickup"}]}  '

    assert event_extraction_module._parse_response_json(response) == {
        "events": [{"event_type": "pickup"}]
    }


def test_parse_response_json_rejects_trailing_text_after_fenced_json() -> None:
    response = '```json\n{"events": []}\ntrailing text'

    with pytest.raises(json.JSONDecodeError, match="Extra data"):
        event_extraction_module._parse_response_json(response)


def test_parse_response_json_rejects_fenced_non_object_payload() -> None:
    response = "```json\n[]"

    with pytest.raises(ValueError, match="JSON object"):
        event_extraction_module._parse_response_json(response)


def test_local_event_extraction_parse_errors_keep_raw_response_for_diagnostics(tmp_path: Path) -> None:
    source = tmp_path / "top200_final.jsonl"
    _write_jsonl(
        source,
        [
            {
                "dialogue_id": "dlg-raw",
                "dialogue": ["speaker_1: 明天我开会"],
                "events": [{"actor": ["speaker_1"], "time": ["明天"], "location": None, "action": ["开会"]}],
            }
        ],
    )

    class FakeRuntime:
        def render_prompt(self, messages, *, loaded_model, template_kwargs=None, execution_ext=None):
            return "rendered prompt"

        def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
            yield SimpleNamespace(text="Thinking Process:")

    class FakeRegistry:
        def runtime_for_loaded_model(self, loaded_model):
            return FakeRuntime()

        def start_request(self, request_id, *, runtime_kind):
            return SimpleNamespace(cancel_event=threading.Event())

        def finish_request(self, request_id) -> None:
            return None

    loaded_model = SimpleNamespace(
        runtime_model={"model": "fixture"},
        runtime_kind="text",
    )
    core = EvaluationCore(jobs_root=tmp_path / "evals", registry=FakeRegistry())
    run = core._run_event_extraction_suite(
        model_id="local-qwen",
        suite_id="event_extraction",
        dataset_id="top200",
        sample_size=1,
        scoring_mode="event_extraction_weighted_f1",
        parameters={"event_source_jsonl": str(source), "dataset_id": "top200"},
        remote_target=None,
        loaded_model=loaded_model,
    )

    trace_path = Path(run.job.parameters["event_eval_dialogue_traces"])
    failure_path = Path(run.job.parameters["failure_jsonl"])
    trace = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    failure = json.loads(failure_path.read_text(encoding="utf-8").splitlines()[0])

    assert trace["status"] == "failed"
    assert trace["raw_response_chars"] == len("Thinking Process:")
    assert trace["response_body_bytes"] == len("Thinking Process:".encode("utf-8"))
    assert Path(trace["raw_response_path"]).read_text(encoding="utf-8") == "Thinking Process:"
    assert failure["raw_response_path"] == trace["raw_response_path"]


def test_semantic_judge_prompt_v4_documents_event_field_and_group_boundaries() -> None:
    assert event_extraction_module.SEMANTIC_JUDGE_PROMPT_VERSION == "semantic-judge.v4"
    prompt = event_extraction_module.SEMANTIC_JUDGE_SYSTEM_PROMPT
    assert "kind=event" in prompt
    assert "kind=field" in prompt
    assert "gold_values" in prompt
    assert "pred_values" in prompt
    assert "出来转转" in prompt
    assert "见面,逛街" in prompt
    assert "拿位" in prompt
    assert "吃饭见面" in prompt
    assert "吃饭\",\"见面" in prompt
    assert "做唐筛" in prompt
    assert "做检查" in prompt
    assert "见面聊天" in prompt
    assert "见面,聊聊" in prompt
    assert "今天直到夕阳西下" in prompt
    assert "有大聚会" in prompt
    assert "参加聚会" in prompt
    assert "speaker_1的朋友阿菜" in prompt
    assert "speaker_1的表姐" in prompt
    assert "明天" in prompt
    assert "27号" in prompt
    assert "同地点同时间" in prompt
    assert "幻觉" in prompt
    assert "重复预测" in prompt


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


def test_string_similarity_reuses_normalized_text_and_bigram_counts() -> None:
    event_extraction_module._string_similarity.cache_clear()
    event_extraction_module._normalize_similarity_text.cache_clear()
    event_extraction_module._character_bigram_items.cache_clear()
    event_extraction_module._character_bigram_stats.cache_clear()

    assert event_extraction_module._normalize_similarity_text(" Delivered-SUPPLY, CRATE! ") == "deliveredsupplycrate"
    first = event_extraction_module._string_similarity("Delivered supply crate", "delivered supply crates")
    second = event_extraction_module._string_similarity("Delivered supply crate", "delivered supply crates")
    third = event_extraction_module._string_similarity("Delivered supply crate 2", "delivered supply crates 2")
    fourth = event_extraction_module._string_similarity("Delivered supply crate 2", "delivered supply crates 2")

    assert first == second
    assert third == fourth
    assert first > 0.9
    assert third > 0.9
    assert event_extraction_module._string_similarity.cache_info().hits >= 2
    assert event_extraction_module._character_bigram_stats("aba") == ((("ab", 1), ("ba", 1)), 2)
    assert event_extraction_module._character_bigrams("aba") == {"ab": 1, "ba": 1}


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


def test_evaluate_event_extraction_reuses_alignment_payloads_for_matched_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_summary.json"
    details_path = tmp_path / "event_eval_details.jsonl"
    original_event_alignment = event_extraction_module._event_alignment
    call_count = 0

    def counted_event_alignment(gold_event: dict[str, object], pred_event: dict[str, object]) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        return original_event_alignment(gold_event, pred_event)

    monkeypatch.setattr(event_extraction_module, "_event_alignment", counted_event_alignment)
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-reuse",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["A"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""},
                    {"actor": ["B"], "time": ["周二"], "location": ["上海"], "action": ["出差"], "digest": ""},
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-reuse",
                "dialogue": ["A: hi"],
                "events": [
                    {"actor": ["A"], "time": ["周一"], "location": None, "action": ["开会"], "digest": ""},
                    {"actor": ["B"], "time": ["周二"], "location": ["上海"], "action": ["出差"], "digest": ""},
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
    assert summary["event_alignment"]["matched_pairs"] == 2
    assert [row["alignment_score"] for row in details] == [1.0, 1.0]
    assert call_count == 4


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


def test_evaluate_event_extraction_semantic_judge_matches_event_and_values(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-semantic",
                "dialogue": ["speaker_1: 下周六见面吧", "speaker_2: 好，下周周六约见"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["下周六"],
                        "location": None,
                        "action": ["见面"],
                        "digest": "",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-semantic",
                "dialogue": ["speaker_1: 下周六见面吧", "speaker_2: 好，下周周六约见"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["下周周六"],
                        "location": None,
                        "action": ["约见"],
                        "digest": "",
                    }
                ],
            }
        ],
    )

    class FakeJudge:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            request_json = json.dumps(request, ensure_ascii=False)
            assert "sk-secret" not in request_json
            assert "https://judge.example/v1" not in request_json
            self.requests.append(request)
            if request["kind"] == "event":
                return {
                    "equivalent": True,
                    "confidence": 0.97,
                    "reason_code": "same_event",
                    "short_reason": "Both events describe the same meeting plan.",
                }
            if request["kind"] == "field":
                key = (request["field_name"], request["gold_value"], request["pred_value"])
                equivalent = key in {
                    ("time", "下周六", "下周周六"),
                    ("action", "见面", "约见"),
                }
                return {
                    "equivalent": equivalent,
                    "confidence": 0.96 if equivalent else 0.0,
                    "reason_code": "same_value" if equivalent else "different_value",
                    "short_reason": "semantic value decision",
                }
            raise AssertionError(f"unexpected judge request kind: {request['kind']}")

    judge = FakeJudge()

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=judge,
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    row_audit = [json.loads(line) for line in row_audit_path.read_text(encoding="utf-8").splitlines()]
    judge_audit = [json.loads(line) for line in judge_audit_path.read_text(encoding="utf-8").splitlines()]
    assert summary["status"] == "completed"
    assert summary["scoring_mode"] == "event_extraction_semantic_weighted_f1"
    assert summary["overall_weighted_f1"] == 1.0
    assert summary["field_metrics"]["time"]["tp"] == 1
    assert summary["field_metrics"]["action"]["tp"] == 1
    assert summary["semantic_judge"]["judge_remote_server_id"] == "judge-server"
    assert summary["semantic_judge"]["judge_model_id"] == "judge-model"
    assert summary["semantic_judge"]["judge_prompt_version"] == "semantic-judge.v4"
    assert summary["semantic_judge"]["judge_prompt_hash"].startswith("sha256:")
    assert summary["semantic_judge"]["calls"] == 3
    assert details[0]["match_status"] == "matched"
    assert details[0]["fields"]["time"]["tp"] == 1
    assert details[0]["fields"]["action"]["tp"] == 1
    assert row_audit[0]["matched_pairs"] == [
        {"gold_event_index": 0, "pred_event_index": 0, "alignment_score": 0.97}
    ]
    assert [row["kind"] for row in judge_audit] == ["event", "field", "field"]
    assert all("api_key" not in json.dumps(row) for row in judge_audit)
    assert len(judge.requests) == 3


def test_semantic_field_values_reuses_cached_group_actor_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_extraction_module._cached_semantic_actor_field_values.cache_clear()
    event_extraction_module._expanded_semantic_actor_values.cache_clear()
    event_extraction_module._is_group_actor_alias.cache_clear()
    calls: list[str] = []
    original_normalize = event_extraction_module._normalize_similarity_text

    def counted_normalize(value: str) -> str:
        calls.append(value)
        return original_normalize(value)

    monkeypatch.setattr(event_extraction_module, "_normalize_similarity_text", counted_normalize)

    assert event_extraction_module._semantic_field_values(
        "actor",
        {"actor": [" 我们 ", "我们", "我 们", "speaker_1", "speaker_1", "咱们", "speaker_2", "双方"]},
    ) == ["speaker_1", "speaker_2"]
    assert calls == ["我 们"]
    event_extraction_module._cached_semantic_actor_field_values.cache_clear()
    event_extraction_module._expanded_semantic_actor_values.cache_clear()
    event_extraction_module._is_group_actor_alias.cache_clear()


def test_semantic_field_values_caches_repeated_group_actor_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_extraction_module._cached_semantic_actor_field_values.cache_clear()
    event_extraction_module._expanded_semantic_actor_values.cache_clear()
    event_extraction_module._is_group_actor_alias.cache_clear()
    calls: list[str] = []
    original_normalize = event_extraction_module._normalize_similarity_text

    def counted_normalize(value: str) -> str:
        calls.append(value)
        return original_normalize(value)

    monkeypatch.setattr(event_extraction_module, "_normalize_similarity_text", counted_normalize)
    event = {"actor": [" 我们 ", "我 们", "speaker_1", "咱们", "speaker_2", "双方"]}

    assert event_extraction_module._semantic_field_values("actor", event) == ["speaker_1", "speaker_2"]
    assert event_extraction_module._semantic_field_values("actor", event) == ["speaker_1", "speaker_2"]
    assert calls == ["我 们"]
    event_extraction_module._cached_semantic_actor_field_values.cache_clear()
    event_extraction_module._expanded_semantic_actor_values.cache_clear()
    event_extraction_module._is_group_actor_alias.cache_clear()


def test_semantic_field_values_normalizes_and_deduplicates_in_one_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        event_extraction_module,
        "_normalize_event_field",
        lambda value: (_ for _ in ()).throw(
            AssertionError("_semantic_field_values should not allocate an intermediate normalized list")
        ),
    )

    assert event_extraction_module._semantic_field_values(
        "action",
        {"action": [" 见面 ", "", "见面", "吃饭"]},
    ) == ["见面", "吃饭"]
    assert event_extraction_module._semantic_field_values("time", {"time": None}) == []
    assert event_extraction_module._semantic_field_values("actor", {"actor": None}) == []
    with pytest.raises(ValueError):
        event_extraction_module._semantic_field_values("actor", {"actor": "我们"})
    with pytest.raises(ValueError):
        event_extraction_module._semantic_field_values("actor", {"actor": ["我们", 1]})
    with pytest.raises(ValueError):
        event_extraction_module._semantic_field_values("time", {"time": "明天"})
    with pytest.raises(ValueError):
        event_extraction_module._semantic_field_values("time", {"time": ["明天", 1]})


def test_actor_alias_probe_default_mix_keeps_normalization_fallback_covered(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_EVENT_ACTOR_ALIAS_PROBE_VALUE_COUNT", "30")
    monkeypatch.setenv("MELIX_EVENT_ACTOR_ALIAS_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_EVENT_ACTOR_ALIAS_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path.cwd() / "scripts/event_extraction_actor_alias_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert 0.0 < metrics["normalize_calls_mean"] < 90.0


def test_evaluate_event_extraction_semantic_expands_group_actor_aliases(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-group-actor",
                "dialogue": ["我们 周四 才 拍照"],
                "events": [
                    {"actor": ["我们"], "time": ["周四"], "location": None, "action": ["拍照"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-group-actor",
                "dialogue": ["我们 周四 才 拍照"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["周四"],
                        "location": None,
                        "action": ["拍照"],
                        "digest": "",
                    }
                ],
            }
        ],
    )

    class EventIdentityJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            assert request["kind"] == "event"
            return {
                "equivalent": True,
                "confidence": 0.96,
                "reason_code": "same_event",
                "short_reason": "Same photo event.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=EventIdentityJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    detail = json.loads(details_path.read_text(encoding="utf-8").splitlines()[0])
    assert summary["overall_weighted_f1"] == 1.0
    assert summary["field_metrics"]["actor"]["tp"] == 2
    assert detail["fields"]["actor"]["gold"] == ["speaker_1", "speaker_2"]
    assert detail["fields"]["actor"]["pred"] == ["speaker_1", "speaker_2"]


def test_evaluate_event_extraction_semantic_actor_relation_aliases_and_slot_guard(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-actor-alias",
                "dialogue": [
                    "speaker_1: 我的朋友阿菜后天来",
                    "speaker_2: 你表姐23号也来吗",
                ],
                "events": [
                    {
                        "actor": ["speaker_1的朋友阿菜"],
                        "time": ["后天"],
                        "location": None,
                        "action": ["来访"],
                        "digest": "",
                    },
                    {
                        "actor": ["speaker_1的表姐"],
                        "time": ["23号"],
                        "location": None,
                        "action": ["来访"],
                        "digest": "",
                    },
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-actor-alias",
                "dialogue": [
                    "speaker_1: 我的朋友阿菜后天来",
                    "speaker_2: 你表姐23号也来吗",
                ],
                "events": [
                    {
                        "actor": ["阿菜"],
                        "time": ["后天"],
                        "location": None,
                        "action": ["来"],
                        "digest": "",
                    },
                    {
                        "actor": ["speaker_1"],
                        "time": ["23号"],
                        "location": None,
                        "action": ["来访"],
                        "digest": "",
                    },
                ],
            }
        ],
    )

    class ActorAliasJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            if request["kind"] == "event":
                return {
                    "equivalent": True,
                    "confidence": 0.95,
                    "reason_code": "same_event",
                    "short_reason": "Same visit event.",
                }
            if request["field_name"] == "actor":
                return {
                    "equivalent": True,
                    "confidence": 0.94,
                    "reason_code": "same_value",
                    "short_reason": "Over-permissive actor judge.",
                }
            return {
                "equivalent": True,
                "confidence": 0.9,
                "reason_code": "same_value",
                "short_reason": "Same value.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=ActorAliasJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    assert summary["field_metrics"]["actor"]["tp"] == 1
    assert summary["field_metrics"]["actor"]["fp"] == 1
    assert summary["field_metrics"]["actor"]["fn"] == 1
    assert details[0]["fields"]["actor"]["semantic_matches"] == [
        {"gold_value": "speaker_1的朋友阿菜", "pred_value": "阿菜", "score": 0.94}
    ]
    assert details[1]["fields"]["actor"]["semantic_matches"] == []


def test_evaluate_event_extraction_semantic_rejects_obvious_time_conflicts(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-time-conflict",
                "dialogue": ["speaker_1: 明天走", "speaker_2: 我 27 走"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["明天"], "location": None, "action": ["离开"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-time-conflict",
                "dialogue": ["speaker_1: 明天走", "speaker_2: 我 27 走"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["27"], "location": None, "action": ["离开"], "digest": ""}
                ],
            }
        ],
    )

    class OverPermissiveJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            return {
                "equivalent": True,
                "confidence": 0.95,
                "reason_code": "same_value",
                "short_reason": "Overly permissive judge.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=OverPermissiveJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    detail = json.loads(details_path.read_text(encoding="utf-8").splitlines()[0])
    assert detail["match_status"] == "matched"
    assert detail["fields"]["time"]["tp"] == 0
    assert detail["fields"]["time"]["fp"] == 1
    assert detail["fields"]["time"]["fn"] == 1
    assert detail["fields"]["time"]["semantic_matches"] == []
    assert summary["field_metrics"]["time"]["f1"] == 0.0


def test_evaluate_event_extraction_semantic_judge_keeps_non_equivalent_events_unmatched(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-different",
                "dialogue": ["speaker_1: 明天吃饭"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["明天"], "location": None, "action": ["吃饭"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-different",
                "dialogue": ["speaker_1: 明天吃饭"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["周末"], "location": None, "action": ["看电影"], "digest": ""}
                ],
            }
        ],
    )

    class RejectingJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            return {
                "equivalent": False,
                "confidence": 0.95,
                "reason_code": "different_event",
                "short_reason": "Different time and action.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=RejectingJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    assert summary["overall_weighted_f1"] == 0.0
    assert summary["summary"]["events_matched"] == 0
    assert summary["summary"]["events_unmatched_gold"] == 1
    assert summary["summary"]["events_unmatched_pred"] == 1
    assert [row["match_status"] for row in details] == ["unmatched_gold", "unmatched_pred"]


def test_evaluate_event_extraction_semantic_aligns_micro_action_without_action_tp(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-micro-action",
                "dialogue": ["speaker_1: 下周二见面", "speaker_2: 我先去拿位"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["下周二"],
                        "location": None,
                        "action": ["见面"],
                        "digest": "",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-micro-action",
                "dialogue": ["speaker_1: 下周二见面", "speaker_2: 我先去拿位"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["下周二"],
                        "location": None,
                        "action": ["拿位"],
                        "digest": "",
                    }
                ],
            }
        ],
    )

    class MicroActionJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            if request["kind"] == "event":
                return {
                    "equivalent": True,
                    "confidence": 0.93,
                    "reason_code": "same_event",
                    "short_reason": "拿位 is preparation for the same meetup.",
                }
            assert request["kind"] == "field"
            return {
                "equivalent": False,
                "confidence": 0.94,
                "reason_code": "different_value",
                "short_reason": "拿位 is not the same action value as 见面.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=MicroActionJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    detail = json.loads(details_path.read_text(encoding="utf-8").splitlines()[0])
    assert summary["summary"]["events_matched"] == 1
    assert detail["match_status"] == "matched"
    assert detail["fields"]["action"]["tp"] == 0
    assert detail["fields"]["action"]["fp"] == 1
    assert detail["fields"]["action"]["fn"] == 1
    assert detail["fields"]["action"]["semantic_matches"] == []


def test_evaluate_event_extraction_semantic_matches_bidirectional_action_split_merge(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-action-merge",
                "dialogue": ["speaker_1: 明天吃饭见面", "speaker_2: 好，明天吃饭见面"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["明天"],
                        "location": None,
                        "action": ["吃饭", "见面"],
                        "digest": "",
                    }
                ],
            },
            {
                "dialogue_id": "dlg-action-split",
                "dialogue": ["speaker_1: 明天吃饭见面", "speaker_2: 好，明天吃饭见面"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["明天"],
                        "location": None,
                        "action": ["吃饭见面"],
                        "digest": "",
                    }
                ],
            },
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-action-merge",
                "dialogue": ["speaker_1: 明天吃饭见面", "speaker_2: 好，明天吃饭见面"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["明天"],
                        "location": None,
                        "action": ["吃饭见面"],
                        "digest": "",
                    }
                ],
            },
            {
                "dialogue_id": "dlg-action-split",
                "dialogue": ["speaker_1: 明天吃饭见面", "speaker_2: 好，明天吃饭见面"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["明天"],
                        "location": None,
                        "action": ["吃饭", "见面"],
                        "digest": "",
                    }
                ],
            },
        ],
    )

    class ActionGroupJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            if request["kind"] == "event":
                return {
                    "equivalent": True,
                    "confidence": 0.95,
                    "reason_code": "same_event",
                    "short_reason": "Same meal meetup event.",
                }
            if request.get("comparison_type") == "action_group":
                equivalent = (
                    request.get("gold_values") == ["吃饭", "见面"]
                    and request.get("pred_values") == ["吃饭见面"]
                ) or (
                    request.get("gold_values") == ["吃饭见面"]
                    and request.get("pred_values") == ["吃饭", "见面"]
                )
                return {
                    "equivalent": equivalent,
                    "confidence": 0.96 if equivalent else 0.0,
                    "reason_code": "same_value" if equivalent else "different_value",
                    "short_reason": "action group decision.",
                }
            return {
                "equivalent": False,
                "confidence": 0.0,
                "reason_code": "different_value",
                "short_reason": "single action values do not cover the compound action.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=ActionGroupJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    assert summary["field_metrics"]["action"]["tp"] == 2
    assert summary["field_metrics"]["action"]["fp"] == 0
    assert summary["field_metrics"]["action"]["fn"] == 0
    for detail in details:
        action = detail["fields"]["action"]
        assert action["f1"] == 1.0
        assert action["semantic_matches"][0]["gold_values"] in (["吃饭", "见面"], ["吃饭见面"])
        assert action["semantic_matches"][0]["pred_values"] in (["吃饭", "见面"], ["吃饭见面"])
        assert action["semantic_matches"][0]["score"] == 0.96


def test_semantic_value_groups_are_cached_and_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    event_extraction_module._semantic_value_groups.cache_clear()

    first = event_extraction_module._semantic_value_groups(4)
    second = event_extraction_module._semantic_value_groups(4)

    assert first is second
    assert first == (
        (0, 1),
        (0, 2),
        (0, 3),
        (1, 2),
        (1, 3),
        (2, 3),
        (0, 1, 2),
        (0, 1, 3),
        (0, 2, 3),
        (1, 2, 3),
    )
    assert event_extraction_module._semantic_value_groups(1) == ()

    event_extraction_module._semantic_value_groups.cache_clear()
    monkeypatch.setattr(event_extraction_module, "SEMANTIC_ACTION_GROUP_MAX_SIZE", 4)
    assert event_extraction_module._semantic_value_groups(4)[-1] == (0, 1, 2, 3)
    event_extraction_module._semantic_value_groups.cache_clear()


def test_evaluate_event_extraction_semantic_matches_specific_check_action(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-check-action",
                "dialogue": ["speaker_1: 上上周五做了唐筛", "speaker_2: 这个检查挺重要"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["上上周五"], "location": None, "action": ["做唐筛"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-check-action",
                "dialogue": ["speaker_1: 上上周五做了唐筛", "speaker_2: 这个检查挺重要"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["上上周五"], "location": None, "action": ["做检查"], "digest": ""}
                ],
            }
        ],
    )

    class CheckActionJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            if request["kind"] == "event":
                return {
                    "equivalent": True,
                    "confidence": 0.95,
                    "reason_code": "same_event",
                    "short_reason": "Same medical check event.",
                }
            key = (request["field_name"], request["gold_value"], request["pred_value"])
            return {
                "equivalent": key == ("action", "做唐筛", "做检查"),
                "confidence": 0.92,
                "reason_code": "same_value_more_specific",
                "short_reason": "唐筛 is the specific check in context.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=CheckActionJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    detail = json.loads(details_path.read_text(encoding="utf-8").splitlines()[0])
    assert summary["field_metrics"]["action"]["tp"] == 1
    assert detail["fields"]["action"]["semantic_matches"] == [
        {"gold_value": "做唐筛", "pred_value": "做检查", "score": 0.92}
    ]


def test_evaluate_event_extraction_semantic_matches_v4_action_and_time_examples(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-v3-examples",
                "dialogue": ["speaker_1: 今天一直待到夕阳西下，咱们见面聊天", "speaker_2: 好，今天见面聊聊"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["今天直到夕阳西下"],
                        "location": None,
                        "action": ["见面聊天"],
                        "digest": "",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-v3-examples",
                "dialogue": ["speaker_1: 今天一直待到夕阳西下，咱们见面聊天", "speaker_2: 好，今天见面聊聊"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["今天"],
                        "location": None,
                        "action": ["见面", "聊聊"],
                        "digest": "",
                    }
                ],
            }
        ],
    )

    class V3ExampleJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            if request["kind"] == "event":
                return {
                    "equivalent": True,
                    "confidence": 0.95,
                    "reason_code": "same_event",
                    "short_reason": "Same meeting and chatting event.",
                }
            if request.get("comparison_type") == "action_group":
                return {
                    "equivalent": request.get("gold_values") == ["见面聊天"]
                    and request.get("pred_values") == ["见面", "聊聊"],
                    "confidence": 0.94,
                    "reason_code": "same_value",
                    "short_reason": "v4 action group decision.",
                }
            key = (request["field_name"], request["gold_value"], request["pred_value"])
            equivalent = key in {
                ("time", "今天直到夕阳西下", "今天"),
                ("action", "见面聊天", "见面"),
                ("action", "见面聊天", "聊聊"),
            }
            return {
                "equivalent": equivalent,
                "confidence": 0.91 if equivalent else 0.0,
                "reason_code": "same_value" if equivalent else "different_value",
                "short_reason": "v3 example decision.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=V3ExampleJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    detail = json.loads(details_path.read_text(encoding="utf-8").splitlines()[0])
    assert summary["field_metrics"]["time"]["tp"] == 1
    assert summary["field_metrics"]["action"]["tp"] == 1
    assert detail["fields"]["time"]["semantic_matches"] == [
        {"gold_value": "今天直到夕阳西下", "pred_value": "今天", "score": 0.91}
    ]
    assert detail["fields"]["action"]["tp"] == 1
    assert detail["fields"]["action"]["fp"] == 0
    assert detail["fields"]["action"]["fn"] == 0
    assert detail["fields"]["action"]["semantic_matches"] == [
        {"gold_values": ["见面聊天"], "pred_values": ["见面", "聊聊"], "score": 0.94}
    ]


def test_evaluate_event_extraction_semantic_flags_low_quality_event_alignment(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-low-quality-party",
                "dialogue": ["speaker_1: 23号周六有大聚会", "speaker_2: 我那天也有别的安排"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["23号周六"], "location": None, "action": ["有大聚会"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-low-quality-party",
                "dialogue": ["speaker_1: 23号周六有大聚会", "speaker_2: 我那天也有别的安排"],
                "events": [
                    {"actor": ["speaker_2"], "time": ["23号周六"], "location": None, "action": ["参加聚会"], "digest": ""}
                ],
            }
        ],
    )

    class PartyJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            if request["kind"] == "event":
                return {
                    "equivalent": True,
                    "confidence": 0.93,
                    "reason_code": "same_event_related_party",
                    "short_reason": "Both sides refer to the same party mention.",
                }
            return {
                "equivalent": False,
                "confidence": 0.9,
                "reason_code": "different_value",
                "short_reason": "Field value is not equivalent enough for TP.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=PartyJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    detail = json.loads(details_path.read_text(encoding="utf-8").splitlines()[0])
    row_audit = json.loads(row_audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert summary["summary"]["events_matched"] == 1
    assert detail["fields"]["actor"]["tp"] == 0
    assert detail["fields"]["action"]["tp"] == 0
    assert detail["fields"]["time"]["tp"] == 1
    assert detail["weighted_f1"] < event_extraction_module.SEMANTIC_LOW_QUALITY_ALIGNMENT_WEIGHTED_F1_THRESHOLD
    assert row_audit["low_quality_alignment"] is True
    assert row_audit["low_quality_alignment_pairs"] == [
        {
            "gold_event_index": 0,
            "pred_event_index": 0,
            "weighted_f1": detail["weighted_f1"],
            "alignment_score": 0.93,
        }
    ]


def test_evaluate_event_extraction_semantic_does_not_merge_same_place_different_actors(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-same-place",
                "dialogue": ["speaker_1: 我明晚在你店里请人吃饭", "speaker_2: 我明晚也和朋友吃饭"],
                "events": [
                    {
                        "actor": ["speaker_1"],
                        "time": ["明晚"],
                        "location": ["speaker_2店里"],
                        "action": ["请人吃饭"],
                        "digest": "",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-same-place",
                "dialogue": ["speaker_1: 我明晚在你店里请人吃饭", "speaker_2: 我明晚也和朋友吃饭"],
                "events": [
                    {
                        "actor": ["speaker_2"],
                        "time": ["明晚"],
                        "location": ["speaker_2店里"],
                        "action": ["和朋友吃饭"],
                        "digest": "",
                    }
                ],
            }
        ],
    )

    class SamePlaceJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            assert request["kind"] == "event"
            return {
                "equivalent": False,
                "confidence": 0.96,
                "reason_code": "different_event",
                "short_reason": "Same place and time, but different participants and meal events.",
            }

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=SamePlaceJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    details = [json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()]
    assert summary["summary"]["events_matched"] == 0
    assert [row["match_status"] for row in details] == ["unmatched_gold", "unmatched_pred"]


def test_evaluate_event_extraction_semantic_judge_failure_marks_partial_and_uses_cache(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    rows = [
        {
            "dialogue_id": "dlg-cache-1",
            "dialogue": ["speaker_1: 下周六见面"],
            "events": [
                {"actor": ["speaker_1"], "time": ["下周六"], "location": None, "action": ["见面"], "digest": ""}
            ],
        },
        {
            "dialogue_id": "dlg-cache-2",
            "dialogue": ["speaker_1: 下周六见面"],
            "events": [
                {"actor": ["speaker_1"], "time": ["下周六"], "location": None, "action": ["见面"], "digest": ""}
            ],
        },
        {
            "dialogue_id": "dlg-failure",
            "dialogue": ["speaker_1: 明天吃饭"],
            "events": [
                {"actor": ["speaker_1"], "time": ["明天"], "location": None, "action": ["吃饭"], "digest": ""}
            ],
        },
    ]
    predictions = [
        {
            "dialogue_id": "dlg-cache-1",
            "dialogue": ["speaker_1: 下周周六约见"],
            "events": [
                {"actor": ["speaker_1"], "time": ["下周周六"], "location": None, "action": ["约见"], "digest": ""}
            ],
        },
        {
            "dialogue_id": "dlg-cache-2",
            "dialogue": ["speaker_1: 下周周六约见"],
            "events": [
                {"actor": ["speaker_1"], "time": ["下周周六"], "location": None, "action": ["约见"], "digest": ""}
            ],
        },
        {
            "dialogue_id": "dlg-failure",
            "dialogue": ["speaker_1: 明天吃饭"],
            "events": [
                {"actor": ["speaker_1"], "time": ["周末"], "location": None, "action": ["看电影"], "digest": ""}
            ],
        },
    ]
    _write_jsonl(gold, rows)
    _write_jsonl(pred, predictions)

    class CachingJudge:
        def __init__(self) -> None:
            self.calls = 0

        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if request["dialogue_id"] == "dlg-failure":
                raise RuntimeError("judge unavailable")
            return {
                "equivalent": True,
                "confidence": 0.92,
                "reason_code": "same_value",
                "short_reason": "Reusable semantic decision.",
            }

    judge = CachingJudge()
    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=judge,
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    judge_audit = [json.loads(line) for line in judge_audit_path.read_text(encoding="utf-8").splitlines()]
    assert summary["status"] == "partial"
    assert summary["semantic_judge"]["failures"] == 1
    assert summary["semantic_judge"]["cache_hits"] > 0
    assert any(row["source"] == "cache" for row in judge_audit)
    assert any(row["status"] == "failed" and row["error_code"] == "judge_error" for row in judge_audit)
    assert judge.calls < 9


def test_evaluate_event_extraction_semantic_judge_audit_summarizes_http_failures(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-judge-http-failure",
                "dialogue": ["speaker_1: 明天吃饭"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["明天"], "location": None, "action": ["吃饭"], "digest": ""}
                ],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-judge-http-failure",
                "dialogue": ["speaker_1: 明天看电影"],
                "events": [
                    {"actor": ["speaker_1"], "time": ["明天"], "location": None, "action": ["看电影"], "digest": ""}
                ],
            }
        ],
    )

    class FailingJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            raise RemoteProviderHTTPError(
                status_code=502,
                response_body='{"error_name":"origin_bad_gateway","detail":"large body that should not be stored"}',
            )

    event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=FailingJudge(),
        judge_remote_server_id="judge-server",
        judge_model_id="judge-model",
    )

    audit_rows = [json.loads(line) for line in judge_audit_path.read_text(encoding="utf-8").splitlines()]
    failed = next(row for row in audit_rows if row["status"] == "failed")
    assert failed["failure_reason"] == "remote provider HTTP 502"
    assert failed["short_reason"] == "remote provider HTTP 502"
    assert "origin_bad_gateway" not in json.dumps(failed, ensure_ascii=False)


def test_semantic_internal_helpers_cover_boundary_and_error_branches(tmp_path: Path) -> None:
    assert event_extraction_module._is_retryable_semantic_judge_error(  # type: ignore[attr-defined]
        event_extraction_module.RemoteProviderHTTPError(status_code=429, response_body="rate")
    )
    assert event_extraction_module._is_retryable_semantic_judge_error(  # type: ignore[attr-defined]
        event_extraction_module.RemoteProviderHTTPError(status_code=502, response_body="bad gateway")
    )
    assert not event_extraction_module._is_retryable_semantic_judge_error(  # type: ignore[attr-defined]
        event_extraction_module.RemoteProviderHTTPError(status_code=400, response_body="bad request")
    )
    assert event_extraction_module._is_retryable_semantic_judge_error(  # type: ignore[attr-defined]
        event_extraction_module.RemoteProviderRequestError(reason="timed out")
    )
    assert not event_extraction_module._is_retryable_semantic_judge_error(ValueError("local"))  # type: ignore[attr-defined]

    for factory in (
        event_extraction_module.make_semantic_judge_client,
        event_extraction_module.RemoteSemanticJudgeClient,
    ):
        try:
            factory(
                event_extraction_module.RemoteSemanticJudgeTarget(
                    provider_kind="unsupported",
                    base_url="https://judge.example/v1",
                    api_key="secret",
                    model_id="judge",
                )
            )
        except ValueError as exc:
            assert "unsupported semantic judge provider kind" in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected unsupported judge provider validation")

    assert not event_extraction_module._obvious_time_conflict("", "27号")  # type: ignore[attr-defined]
    assert not event_extraction_module._obvious_time_conflict("明天", "明天")  # type: ignore[attr-defined]
    assert event_extraction_module._obvious_time_conflict("明天", "27号")  # type: ignore[attr-defined]
    assert event_extraction_module._actor_slot_relation_conflict("speaker_1", "speaker_2")  # type: ignore[attr-defined]
    assert event_extraction_module._actor_slot_relation_conflict("speaker_1", "speaker_1的表姐")  # type: ignore[attr-defined]
    assert not event_extraction_module._actor_slot_relation_conflict("阿菜", "speaker_1的朋友阿菜")  # type: ignore[attr-defined]

    assert event_extraction_module._semantic_decision_score({"equivalent": False, "confidence": 1.0}) == 0.0  # type: ignore[attr-defined]
    assert event_extraction_module._semantic_decision_score({"equivalent": True, "confidence": True}) == 0.0  # type: ignore[attr-defined]
    assert event_extraction_module._semantic_decision_score({"equivalent": True, "confidence": "high"}) == 0.0  # type: ignore[attr-defined]
    assert event_extraction_module._semantic_decision_score({"equivalent": True, "confidence": 2.0}) == 1.0  # type: ignore[attr-defined]

    assert event_extraction_module._normalize_semantic_judge_decision("bad")["reason_code"] == "malformed_response"  # type: ignore[attr-defined]
    assert event_extraction_module._normalize_semantic_judge_decision({"confidence": 0.5})["reason_code"] == "malformed_response"  # type: ignore[attr-defined]
    uncertain = event_extraction_module._normalize_semantic_judge_decision(  # type: ignore[attr-defined]
        {"equivalent": True, "confidence": 0.9, "reason_code": "uncertain"}
    )
    assert uncertain["equivalent"] is False
    assert event_extraction_module._parse_semantic_judge_response("not json")["reason_code"] == "malformed_response"  # type: ignore[attr-defined]
    assert (
        event_extraction_module._semantic_judge_failure_reason(  # type: ignore[attr-defined]
            event_extraction_module.RemoteProviderRequestError(reason="timed out")
        )
        == "remote provider request failed"
    )
    assert event_extraction_module._semantic_judge_failure_reason(Exception("\n")) == "Exception"  # type: ignore[attr-defined]
    assert event_extraction_module._unique_preserving_order(["a", "b", "a"]) == ["a", "b"]  # type: ignore[attr-defined]

    stage1_prompt = EventExtractionPromptSpec(
        prompt_id="p",
        revision_id="stage1",
        title="",
        system_prompt="stage-1 conversation event_candidates",
        content_hash="h",
    )
    direct_prompt = EventExtractionPromptSpec(
        prompt_id="p",
        revision_id="direct",
        title="",
        system_prompt='你是中文对话事件抽取器 "dialogue_id" "source_order"',
        content_hash="h",
    )
    assert event_extraction_module._prompt_input_mode(stage1_prompt) == "stage1"  # type: ignore[attr-defined]
    assert event_extraction_module._prompt_input_mode(direct_prompt) == "direct_event_json"  # type: ignore[attr-defined]
    assert event_extraction_module._prompt_input_mode(EventExtractionPromptSpec("p", "raw", "", "plain", "h")) == "raw_dialogue"  # type: ignore[attr-defined]
    assert "conversation" in event_extraction_module._dialogue_user_content(["speaker_1: 见面"], "dlg", "stage1")  # type: ignore[attr-defined]
    direct_user = json.loads(event_extraction_module._dialogue_user_content([" speaker_1: 见面 "], "dlg", "direct_event_json"))  # type: ignore[attr-defined]
    assert direct_user == {"dialogue_id": "dlg", "dialogue": ["speaker_1: 见面"]}

    example = {
        "dialogue_id": "ex-1",
        "dialogue": ["speaker_1: 周五吃饭"],
        "events": [{"actor": ["speaker_1"], "time": ["周五"], "location": None, "action": ["吃饭"]}],
    }
    assert "event_candidates" in event_extraction_module._example_response_text(example, "stage1")  # type: ignore[attr-defined]
    direct_response = json.loads(event_extraction_module._example_response_text(example, "direct_event_json"))  # type: ignore[attr-defined]
    assert direct_response["dialogue_id"] == "ex-1"
    assert direct_response["events"][0]["source_order"] == 1
    assert direct_response["events"][0]["digest"] == "speaker_1周五吃饭"

    invalid_rows = [
        ("not-object", "[]", "expected JSON object"),
        ("missing-id", '{"events":[]}', "missing dialogue_id"),
        ("events-not-list", '{"dialogue_id":"dlg","events":{}}', "events must be a list"),
    ]
    for name, payload, expected in invalid_rows:
        path = tmp_path / f"{name}.jsonl"
        path.write_text("\n" + payload + "\n", encoding="utf-8")
        try:
            event_extraction_module._read_dialogue_jsonl_rows(path)  # type: ignore[attr-defined]
        except ValueError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError(f"expected {expected}")


def test_semantic_evaluation_uses_pred_dialogue_fallback_and_prefilter(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    summary_path = tmp_path / "event_eval_semantic_summary.json"
    details_path = tmp_path / "event_eval_semantic_details.jsonl"
    row_audit_path = tmp_path / "event_eval_semantic_row_audit.jsonl"
    judge_audit_path = tmp_path / "event_eval_judge_audit.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "dialogue_id": "dlg-prefilter",
                "dialogue": [],
                "events": [{"actor": ["alice"], "time": ["周一"], "location": ["公司"], "action": ["开会"]}],
            }
        ],
    )
    _write_jsonl(
        pred,
        [
            {
                "dialogue_id": "dlg-prefilter",
                "dialogue": ["speaker_2: 火星历去月球潜水"],
                "events": [{"actor": ["zzzz"], "time": ["火星历"], "location": ["月球"], "action": ["潜水"]}],
            }
        ],
    )

    class NoCallJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            raise AssertionError(f"prefiltered candidate should not call judge: {request}")

    summary = event_extraction_module.evaluate_event_extraction_semantic(
        gold_jsonl=gold,
        pred_jsonl=pred,
        summary_output=summary_path,
        details_output=details_path,
        row_audit_output=row_audit_path,
        judge_audit_output=judge_audit_path,
        judge=NoCallJudge(),
        judge_remote_server_id="judge",
        judge_model_id="judge-model",
    )

    row_audit = [json.loads(line) for line in row_audit_path.read_text(encoding="utf-8").splitlines()]
    assert summary["event_alignment"]["matched_pairs"] == 0
    assert row_audit[0]["candidate_scores"][0]["source"] == "prefilter"


def test_evaluation_core_semantic_setup_failure_and_extra_body_validation(tmp_path: Path, monkeypatch) -> None:
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    _write_jsonl(gold, [{"dialogue_id": "dlg", "dialogue": [], "events": []}])
    _write_jsonl(pred, [{"dialogue_id": "dlg", "dialogue": [], "events": []}])

    monkeypatch.setattr(
        evaluation_core,
        "make_semantic_judge_client",
        lambda target: (_ for _ in ()).throw(RuntimeError("judge setup unavailable")),
        raising=False,
    )

    summary = EvaluationCore._run_event_extraction_semantic_scoring(
        gold_subset_path=gold,
        prediction_path=pred,
        semantic_summary_path=tmp_path / "summary.json",
        semantic_details_path=tmp_path / "details.jsonl",
        semantic_row_audit_path=tmp_path / "rows.jsonl",
        judge_audit_path=tmp_path / "judge.jsonl",
        judge_target=event_extraction_module.RemoteSemanticJudgeTarget(
            provider_kind="openai-compatible",
            base_url="https://judge.example/v1",
            api_key="secret",
            model_id="judge",
        ),
        judge_remote_server_id="judge",
        judge_model_id="judge",
    )

    assert summary["status"] == "failed"
    assert summary["semantic_judge"]["error_code"] == "semantic_judge_setup_failed"
    assert "judge setup unavailable" in summary["semantic_judge"]["failure_reason"]
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert (tmp_path / "details.jsonl").read_text(encoding="utf-8") == ""
    assert json.loads((tmp_path / "judge.jsonl").read_text(encoding="utf-8"))["source"] == "setup"

    assert EvaluationCore._remote_provider_extra_body({}) == {}
    for raw_value, expected in [
        ("{bad", "must be valid JSON"),
        ("[]", "must be a JSON object"),
    ]:
        try:
            EvaluationCore._remote_provider_extra_body({"remote_provider_extra_body_json": raw_value})
        except ValueError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError(f"expected {expected}")


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


def test_event_alignment_precomputes_only_accepted_sparse_edges(monkeypatch) -> None:
    scores = [
        [0.91, 0.0, 0.0, 0.77],
        [0.0, 0.82, 0.0, 0.0],
        [0.80, 0.0, 0.79, 0.0],
    ]
    accepted = [
        [True, False, False, True],
        [False, True, False, False],
        [True, False, True, False],
    ]
    round_calls: list[float] = []
    original_round_metric = event_extraction_module._round_metric

    def counted_round_metric(value: float) -> float:
        round_calls.append(value)
        return original_round_metric(value)

    monkeypatch.setattr(event_extraction_module, "_round_metric", counted_round_metric)

    edges = event_extraction_module._accepted_event_matching_edges(scores, accepted)
    precomputed_round_calls = len(round_calls)
    matches = event_extraction_module._maximum_weight_event_matching(scores, accepted)

    assert precomputed_round_calls == 0
    assert edges == (
        ((0, 0.91), (3, 0.77)),
        ((1, 0.82),),
        ((0, 0.80), (2, 0.79)),
    )
    assert matches == [(0, 0, 0.91), (1, 1, 0.82), (2, 2, 0.79)]


def test_event_alignment_tie_breaks_on_rounded_match_tuples() -> None:
    matches = event_extraction_module._maximum_weight_event_matching(
        [[0.5, 0.5]],
        [[True, True]],
    )

    assert matches == [(0, 0, 0.5)]


def test_event_alignment_reuses_normalized_action_values(monkeypatch) -> None:
    calls = 0
    original = event_extraction_module._normalize_event_field

    def counted_normalize(value: object) -> list[str]:
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(event_extraction_module, "_normalize_event_field", counted_normalize)

    alignment = event_extraction_module._event_alignment(
        {"actor": ["A"], "time": ["Monday"], "location": ["Office"], "action": ["meet"]},
        {"actor": ["A"], "time": ["Monday"], "location": ["Office"], "action": ["call"]},
    )

    assert calls == len(event_extraction_module.FIELD_NAMES) * 2
    assert alignment["fields"]["action"] < event_extraction_module.EVENT_ALIGNMENT_ACTION_THRESHOLD
    assert alignment["accepted"] is False


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
        captured["target"] = target
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
            "remote_provider_extra_body_json": json.dumps(
                {"max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}}
            ),
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
    assert captured["target"].extra_body == {"max_tokens": 1024, "chat_template_kwargs": {"enable_thinking": False}}
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


def test_event_extraction_dialogue_diagnostics_uses_top_k_for_slowest_dialogues(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []
    original_nlargest = evaluation_core.heapq.nlargest

    def counting_nlargest(count, iterable, *, key=None):
        items = list(iterable)
        calls.append((count, len(items)))
        return original_nlargest(count, items, key=key)

    monkeypatch.setattr(evaluation_core.heapq, "nlargest", counting_nlargest)
    traces = [
        {
            "dialogue_id": f"dlg-{index}",
            "line_number": index,
            "status": "ok",
            "request_duration_ms": float(index),
            "total_duration_ms": float(index),
            "raw_response_chars": 10 + index,
        }
        for index in range(12)
    ]

    diagnostics = EvaluationCore._event_extraction_dialogue_diagnostics(traces)

    assert calls == [(5, 12)]
    assert diagnostics["slowest_dialogues"] == [
        {"dialogue_id": "dlg-11", "line_number": 11, "duration_ms": 11.0, "status": "ok"},
        {"dialogue_id": "dlg-10", "line_number": 10, "duration_ms": 10.0, "status": "ok"},
        {"dialogue_id": "dlg-9", "line_number": 9, "duration_ms": 9.0, "status": "ok"},
        {"dialogue_id": "dlg-8", "line_number": 8, "duration_ms": 8.0, "status": "ok"},
        {"dialogue_id": "dlg-7", "line_number": 7, "duration_ms": 7.0, "status": "ok"},
    ]


def test_event_extraction_dialogue_diagnostics_streams_raw_response_and_throttle_aggregates(monkeypatch) -> None:
    original_numeric_trace_values = EvaluationCore._numeric_trace_values

    def fail_materialized_numeric_values(traces, field_name):
        if field_name in {"raw_response_chars", "throttle_sleep_ms"}:
            raise AssertionError(f"{field_name} should be streamed without materializing a list")  # pragma: no cover
        return original_numeric_trace_values(traces, field_name)

    monkeypatch.setattr(EvaluationCore, "_numeric_trace_values", staticmethod(fail_materialized_numeric_values))
    traces = [
        {
            "dialogue_id": "dlg-1",
            "line_number": 1,
            "status": "ok",
            "request_duration_ms": 2.0,
            "total_duration_ms": 7.0,
            "raw_response_chars": 10,
            "throttle_sleep_ms": 1.25,
        },
        {
            "dialogue_id": "dlg-2",
            "line_number": 2,
            "status": "failed",
            "request_duration_ms": 4.0,
            "total_duration_ms": 5.0,
            "raw_response_chars": 40,
            "throttle_sleep_ms": 2,
        },
        {
            "dialogue_id": "dlg-3",
            "line_number": 3,
            "status": "aborted",
            "request_duration_ms": 6.0,
            "total_duration_ms": 3.0,
            "raw_response_chars": True,
            "throttle_sleep_ms": False,
        },
    ]

    diagnostics = EvaluationCore._event_extraction_dialogue_diagnostics(traces)

    assert diagnostics["total_throttle_sleep_ms"] == 3.25
    assert diagnostics["raw_response_chars"] == {"mean": 25.0, "max": 40.0}


def test_evaluation_core_writes_semantic_judge_artifacts_without_persisting_judge_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "top200_final.jsonl"
    _write_jsonl(
        source,
        [
            {
                "dialogue_id": "dlg-semantic",
                "dialogue": ["speaker_1: 下周六见面吧", "speaker_2: 好，下周周六约见"],
                "events": [
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["下周六"],
                        "location": None,
                        "action": ["见面"],
                        "digest": "",
                    }
                ],
            }
        ],
    )

    class FakeClient:
        def extract_events(self, dialogue, dialogue_id=""):
            return EventExtractionClientResult(
                events=[
                    {
                        "actor": ["speaker_1", "speaker_2"],
                        "time": ["下周周六"],
                        "location": None,
                        "action": ["约见"],
                    }
                ],
                raw_response='{"events":[]}',
            )

    class FakeJudge:
        def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
            return {
                "equivalent": True,
                "confidence": 0.94,
                "reason_code": "same_event_or_value",
                "short_reason": "The compared items describe the same schedule.",
            }

    class FakeTarget:
        remote_server_id = "evaluated-server"
        provider_kind = "openai-compatible"
        base_url = "https://evaluated.example/v1"
        api_key = "sk-evaluated-secret"
        model_id = "evaluated-model"
        timeout_seconds = 30
        rate_limit_per_minute = 0

    captured = {}

    def fake_judge_factory(target):
        captured["judge_target"] = target
        return FakeJudge()

    monkeypatch.setattr(evaluation_core, "make_event_extraction_client", lambda target, prompt_spec=None: FakeClient())
    monkeypatch.setattr(evaluation_core, "make_semantic_judge_client", fake_judge_factory, raising=False)

    run = EvaluationCore(jobs_root=tmp_path / "evals").run_local_suite(
        model_id="evaluated-model",
        suite_id="event_extraction",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="event_extraction_weighted_f1",
        parameters={
            "event_source_jsonl": str(source),
            "semantic_judge_remote_server_id": "judge-server",
            "semantic_judge_provider_kind": "openai-compatible",
            "semantic_judge_base_url": "https://judge.example/v1",
            "semantic_judge_api_key": "sk-judge-secret",
            "semantic_judge_model_id": "judge-model",
            "semantic_judge_timeout_seconds": "42",
            "semantic_judge_rate_limit_per_minute": "0",
        },
        remote_target=FakeTarget(),
    )

    output_dir = Path(run.job.output_dir)
    safe_job_parameters = json.dumps(run.job.parameters, ensure_ascii=False)
    assert "sk-judge-secret" not in safe_job_parameters
    assert "https://judge.example/v1" not in safe_job_parameters
    assert run.job.parameters["semantic_judge_remote_server_id"] == "judge-server"
    assert run.job.parameters["semantic_judge_model_id"] == "judge-model"
    assert run.job.parameters["event_eval_semantic_summary"].endswith("event_eval_semantic_summary.json")
    assert run.job.parameters["event_eval_judge_audit"].endswith("event_eval_judge_audit.jsonl")
    assert run.result.primary_score_name == "overall_weighted_f1"
    semantic_metric = next(
        metric
        for metric in run.result.metrics
        if metric.name == "eval.event_extraction.semantic_overall_weighted_f1"
    )
    assert semantic_metric.value == 1.0
    assert captured["judge_target"].api_key == "sk-judge-secret"

    semantic_summary_path = output_dir / "reports" / "evaluated-model" / "event_eval_semantic_summary.json"
    semantic_summary = json.loads(semantic_summary_path.read_text(encoding="utf-8"))
    assert semantic_summary["status"] == "completed"
    assert semantic_summary["overall_weighted_f1"] == 1.0
    assert semantic_summary["semantic_judge"]["judge_remote_server_id"] == "judge-server"
    assert semantic_summary["semantic_judge"]["judge_model_id"] == "judge-model"
    assert "sk-judge-secret" not in json.dumps(semantic_summary, ensure_ascii=False)
    assert "https://judge.example/v1" not in json.dumps(semantic_summary, ensure_ascii=False)


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


def test_evaluation_core_write_jsonl_rows_streams_each_row_via_path_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "rows.jsonl"
    writes: list[str] = []

    class RecordingFile:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def write(self, chunk: str) -> int:
            writes.append(chunk)
            return len(chunk)

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> RecordingFile:
        assert self == output_path
        assert mode == "w"
        assert kwargs.get("encoding") == "utf-8"
        return RecordingFile()

    def fail_write_text(self: Path, data: str, encoding: str | None = None) -> int:
        raise AssertionError("_write_jsonl_rows should not use Path.write_text")

    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr(Path, "write_text", fail_write_text)

    EvaluationCore._write_jsonl_rows(
        output_path,
        [
            {"dialogue_id": "dlg-1", "events": []},
            {"dialogue_id": "dlg-2", "events": [{"actor": ["A"]}]},
        ],
    )

    assert writes == [
        json.dumps({"dialogue_id": "dlg-1", "events": []}, ensure_ascii=False) + "\n",
        json.dumps({"dialogue_id": "dlg-2", "events": [{"actor": ["A"]}]}, ensure_ascii=False) + "\n",
    ]


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

    observed_paths: list[Path] = []
    original_write_jsonl_rows = EvaluationCore._write_jsonl_rows

    def recording_write_jsonl_rows(path: Path, rows: list[dict[str, object]]) -> None:
        observed_paths.append(path)
        original_write_jsonl_rows(path, rows)

    monkeypatch.setattr(evaluation_core, "make_event_extraction_client", fake_client_factory)
    monkeypatch.setattr(EvaluationCore, "_write_jsonl_rows", staticmethod(recording_write_jsonl_rows))

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
    assert output_dir / "gold_subset.jsonl" in observed_paths
    assert prediction_log in observed_paths
    assert failure_log in observed_paths
    trace_log = output_dir / "reports" / "remote_model" / "event_eval_dialogue_traces.jsonl"
    traces = [json.loads(line) for line in trace_log.read_text(encoding="utf-8").splitlines()]
    assert len(traces) == 1
    assert traces[0]["dialogue_id"] == "dlg-rate-1"
    assert traces[0]["status"] == "aborted"
    assert traces[0]["error_code"] == "remote_provider_rate_limited"
    assert traces[0]["failure_reason"] == 'remote provider HTTP 429: {"error":"rate"}'
    assert "sk-secret" not in json.dumps(traces, ensure_ascii=False)


def test_evaluation_core_event_extraction_routes_jsonl_outputs_through_write_jsonl_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "top200_final.jsonl"
    source_rows = [
        {
            "dialogue_id": "dlg-1",
            "dialogue": ["speaker_1: 明天见面"],
            "events": [
                {
                    "actor": ["speaker_1"],
                    "time": ["明天"],
                    "location": None,
                    "action": ["见面"],
                    "digest": "",
                }
            ],
        }
    ]
    _write_jsonl(source, source_rows)

    class FakeClient:
        def extract_events(self, dialogue, dialogue_id=""):
            assert dialogue == ["speaker_1: 明天见面"]
            assert dialogue_id == "dlg-1"
            return EventExtractionClientResult(
                events=[
                    {
                        "actor": ["speaker_1"],
                        "time": ["明天"],
                        "location": None,
                        "action": ["见面"],
                    }
                ],
                raw_response='{"events":[]}',
            )

    class FakeTarget:
        provider_kind = "openai-compatible"
        base_url = "https://sub2api.example/v1"
        api_key = "sk-secret"
        model_id = "remote-model"
        timeout_seconds = 30
        rate_limit_per_minute = 0

    observed_paths: list[Path] = []
    original_write_jsonl_rows = EvaluationCore._write_jsonl_rows

    def recording_write_jsonl_rows(path: Path, rows: list[dict[str, object]]) -> None:
        observed_paths.append(path)
        original_write_jsonl_rows(path, rows)

    monkeypatch.setattr(evaluation_core, "make_event_extraction_client", lambda target, prompt_spec=None: FakeClient())
    monkeypatch.setattr(EvaluationCore, "_write_jsonl_rows", staticmethod(recording_write_jsonl_rows))

    run = EvaluationCore(jobs_root=tmp_path / "evals").run_local_suite(
        model_id="remote-model",
        suite_id="event_extraction",
        dataset_root=tmp_path,
        sample_size=1,
        scoring_mode="event_extraction_weighted_f1",
        parameters={"event_source_jsonl": str(source)},
        remote_target=FakeTarget(),
    )

    output_dir = Path(run.job.output_dir)
    gold_subset_path = output_dir / "gold_subset.jsonl"
    prediction_path = output_dir / "predictions" / "remote-model.jsonl"
    failure_path = output_dir / "predictions" / "remote-model.failures.jsonl"
    expected_gold_subset = json.dumps(source_rows[0], ensure_ascii=False) + "\n"
    expected_prediction = (
        json.dumps(
            {
                "dialogue_id": "dlg-1",
                "dialogue": ["speaker_1: 明天见面"],
                "events": [
                    {
                        "actor": ["speaker_1"],
                        "time": ["明天"],
                        "location": None,
                        "action": ["见面"],
                        "digest": "speaker_1明天见面",
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n"
    )

    assert gold_subset_path.read_text(encoding="utf-8") == expected_gold_subset
    assert prediction_path.read_text(encoding="utf-8") == expected_prediction
    assert failure_path.read_text(encoding="utf-8") == ""
    assert gold_subset_path in observed_paths
    assert prediction_path in observed_paths
    assert failure_path in observed_paths


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
        assert str(exc) == "event_extraction_weighted_f1 requires a remote provider target or a loaded local model."
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
                                        "dialogue_id": "dlg-smoke",
                                        "events": [
                                            {
                                                "actor": ["我"],
                                                "time": ["明天"],
                                                "location": None,
                                                "action": ["开会"],
                                                "digest": "ignored",
                                                "source_order": 1,
                                            }
                                        ],
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

    assert events == [
        {
            "actor": ["我"],
            "time": ["明天"],
            "location": None,
            "action": ["开会"],
            "digest": "ignored",
            "source_order": 1,
        }
    ]
    assert raw_text.startswith("{")
    assert captured["url"] == "https://sub2api.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-secret"
    assert captured["timeout"] == 37
    assert captured["body"]["model"] == "kimi-2.6"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert "你是中文对话事件抽取器" in captured["body"]["messages"][0]["content"]
    request_payload = json.loads(captured["body"]["messages"][1]["content"])
    assert request_payload == {
        "dialogue_id": "dlg-smoke",
        "dialogue": ["speaker_1: 明天我开会"],
    }
    assert captured["body"]["temperature"] == 0


def test_openai_event_extraction_merges_remote_extra_body_without_core_overrides(monkeypatch) -> None:
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

    client = OpenAICompatibleEventExtractionClient(
        RemoteEventExtractionTarget(
            provider_kind="openai-compatible",
            base_url="https://sub2api.example/v1",
            api_key="sk-secret",
            model_id="qwen",
            extra_body={
                "max_tokens": 1024,
                "chat_template_kwargs": {"enable_thinking": False},
                "model": "wrong-model",
                "messages": [],
                "stream": True,
            },
        )
    )

    client.extract_events(["speaker_1: 明天我开会"], dialogue_id="dlg-extra-body")

    assert captured["body"]["model"] == "qwen"
    assert captured["body"]["messages"]
    assert captured["body"]["stream"] is False
    assert captured["body"]["max_tokens"] == 1024
    assert captured["body"]["chat_template_kwargs"] == {"enable_thinking": False}


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


def test_remote_semantic_judge_clients_post_strict_json_requests(monkeypatch) -> None:
    captured = []
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "equivalent": True,
                                "confidence": 0.91,
                                "reason_code": "same_value",
                                "short_reason": "same schedule",
                            }
                        )
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "equivalent": False,
                                        "confidence": 0.88,
                                        "reason_code": "different_value",
                                        "short_reason": "different action",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
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
        captured.append(
            {
                "url": request.full_url,
                "headers": dict(request.headers),
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(event_extraction_module, "urlopen", fake_urlopen)

    openai_decision = event_extraction_module.make_semantic_judge_client(
        event_extraction_module.RemoteSemanticJudgeTarget(
            provider_kind="openai-compatible",
            base_url="https://judge.example/v1",
            api_key="sk-judge",
            model_id="judge-model",
            timeout_seconds=31,
        )
    ).judge_semantic_equivalence(
        {
            "kind": "field",
            "dialogue_id": "dlg-1",
            "field_name": "time",
            "gold_value": "下周六",
            "pred_value": "下周周六",
        }
    )
    gemini_decision = event_extraction_module.make_semantic_judge_client(
        event_extraction_module.RemoteSemanticJudgeTarget(
            provider_kind="gemini-generative-language",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="AIza-judge",
            model_id="gemini-2.5-flash",
            timeout_seconds=32,
        )
    ).judge_semantic_equivalence(
        {
            "kind": "field",
            "dialogue_id": "dlg-1",
            "field_name": "action",
            "gold_value": "吃饭",
            "pred_value": "看电影",
        }
    )

    assert openai_decision["equivalent"] is True
    assert gemini_decision["equivalent"] is False
    assert captured[0]["url"] == "https://judge.example/v1/chat/completions"
    assert captured[0]["headers"]["Authorization"] == "Bearer sk-judge"
    assert captured[0]["timeout"] == 31
    assert captured[0]["body"]["temperature"] == 0
    assert captured[0]["body"]["messages"][0]["content"].startswith("You are a semantic judge")
    assert "For kind=\"event\"" in captured[0]["body"]["messages"][0]["content"]
    assert "sk-judge" not in json.dumps(captured[0]["body"])
    assert captured[1]["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-2.5-flash:generateContent?key=AIza-judge"
    )
    assert "Authorization" not in captured[1]["headers"]
    assert captured[1]["body"]["generationConfig"]["temperature"] == 0
    assert captured[1]["body"]["systemInstruction"]["parts"][0]["text"].startswith("You are a semantic judge")
    assert "AIza-judge" not in json.dumps(captured[1]["body"])


def test_remote_semantic_judge_retries_retryable_http_errors(monkeypatch) -> None:
    attempts = []

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
                                        "equivalent": True,
                                        "confidence": 0.9,
                                        "reason_code": "same_event",
                                        "short_reason": "retry succeeded",
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise HTTPError(
                request.full_url,
                502,
                "Bad Gateway",
                hdrs=None,
                fp=BytesIO(b'{"error_name":"origin_bad_gateway"}'),
            )
        return FakeResponse()

    monkeypatch.setattr(event_extraction_module, "urlopen", fake_urlopen)
    monkeypatch.setattr(event_extraction_module.time, "sleep", lambda _: None)

    decision = event_extraction_module.make_semantic_judge_client(
        event_extraction_module.RemoteSemanticJudgeTarget(
            provider_kind="openai-compatible",
            base_url="https://judge.example/v1",
            api_key="sk-judge",
            model_id="judge-model",
            timeout_seconds=31,
        )
    ).judge_semantic_equivalence({"kind": "event", "dialogue_id": "dlg-1"})

    assert decision["equivalent"] is True
    assert len(attempts) == 2


def test_remote_semantic_judge_client_validates_edges_and_terminal_errors(monkeypatch) -> None:
    sleep_calls: list[float] = []
    perf_values = iter([100.0, 100.2, 101.2])
    throttled_client = event_extraction_module.RemoteSemanticJudgeClient(
        event_extraction_module.RemoteSemanticJudgeTarget(
            provider_kind="openai-compatible",
            base_url="https://judge.example/v1",
            api_key="secret",
            model_id="judge",
            rate_limit_per_minute=60,
        )
    )
    monkeypatch.setattr(event_extraction_module.time, "perf_counter", lambda: next(perf_values))
    monkeypatch.setattr(event_extraction_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    throttled_client._throttle_if_needed()  # type: ignore[attr-defined]
    throttled_client._throttle_if_needed()  # type: ignore[attr-defined]
    assert sleep_calls == [0.7999999999999972]

    for method_name, target in [
        (
            "_post_openai",
            event_extraction_module.RemoteSemanticJudgeTarget(
                provider_kind="openai-compatible",
                base_url=" ",
                api_key="secret",
                model_id="judge",
            ),
        ),
        (
            "_post_gemini",
            event_extraction_module.RemoteSemanticJudgeTarget(
                provider_kind="gemini-generative-language",
                base_url=" ",
                api_key="secret",
                model_id="judge",
            ),
        ),
    ]:
        client = event_extraction_module.RemoteSemanticJudgeClient(target)
        try:
            getattr(client, method_name)({})  # type: ignore[misc]
        except ValueError as exc:
            assert str(exc) == "semantic judge base_url is empty"
        else:  # pragma: no cover - assertion guard
            raise AssertionError("expected empty base URL validation")

    client = event_extraction_module.RemoteSemanticJudgeClient(
        event_extraction_module.RemoteSemanticJudgeTarget(
            provider_kind="openai-compatible",
            base_url="https://judge.example/v1",
            api_key="secret",
            model_id="judge",
        )
    )

    def raise_non_retryable_http(request, timeout):
        raise HTTPError(request.full_url, 400, "Bad Request", {}, BytesIO(b'{"error":"bad"}'))

    monkeypatch.setattr(event_extraction_module, "urlopen", raise_non_retryable_http)
    try:
        client._post_json_request(event_extraction_module.Request("https://judge.example/v1/chat/completions"))  # type: ignore[attr-defined]
    except RemoteProviderHTTPError as exc:
        assert exc.status_code == 400
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected non-retryable HTTP error")

    def raise_url_error(request, timeout):
        raise URLError("network down")

    monkeypatch.setattr(event_extraction_module, "urlopen", raise_url_error)
    monkeypatch.setattr(event_extraction_module.time, "sleep", lambda seconds: None)
    try:
        client._post_json_request(event_extraction_module.Request("https://judge.example/v1/chat/completions"))  # type: ignore[attr-defined]
    except event_extraction_module.RemoteProviderRequestError as exc:
        assert exc.reason == "network down"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected terminal request error")

    class FakeListResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"[]"

    monkeypatch.setattr(event_extraction_module, "urlopen", lambda request, timeout: FakeListResponse())
    try:
        client._post_json_request(event_extraction_module.Request("https://judge.example/v1/chat/completions"))  # type: ignore[attr-defined]
    except ValueError as exc:
        assert str(exc) == "semantic judge response must be a JSON object"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected object response validation")


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
