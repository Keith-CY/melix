from __future__ import annotations

import json
from pathlib import Path

from worker.productization.event_feedback_patch_plan import (
    build_gemma_annotation_patch_plan,
    write_gemma_annotation_patch_plan,
)


def test_build_gemma_annotation_patch_plan_classifies_feedback_rows() -> None:
    annotation_rows = [
        _annotation("12", [_note("matched:1:1:1", "matched", 1, 1, "修改 Gold, 或者要求时间区间的表达方式")]),
        _annotation(
            "15",
            [
                _note("matched:0:0:0", "matched", 0, 0, "这里不是一起吃饭, 是同时在同一地点吃饭"),
                _note("unmatched_gold:3:none:3", "unmatched_gold", 3, None, "和 event 1 是重复的"),
            ],
        ),
        _annotation("17", [_note("matched:1:1:1", "matched", 1, 1, "缺少发信时间")]),
        _annotation("19", [_note("matched:0:0:0", "matched", 0, 0, "修改 Gold, 记录 Speaker 1 的同事")]),
        _annotation("2", [_note("matched:1:1:1", "matched", 1, 1, "pred 错误, speaker 1 27 号走, speaker 1 明天走")]),
        _annotation("20", [_note("matched:2:0:2", "matched", 2, 0, "pred 错误, 没有明确出发日期")]),
        _annotation("21", [_note("matched:2:2:2", "matched", 2, 2, "judge 可以认为 出来转转 和 见面,逛街 是一件事情")]),
        _annotation("22", [_note("matched:0:1:0", "matched", 0, 1, "改 Gold, 拆成 2 件事情")]),
        _annotation("22", [_note("unmatched_pred:none:0:0", "unmatched_pred", None, 0, "pred 错误, 2 次相同事件重复")]),
        _annotation("23", [_note("matched:1:1:1", "matched", 1, 1, 'Gold要改, 做的事情是 "做糖筛 或 做 唐筛", 可以简化为 "做检查"')]),
        _annotation("27", [_note("unmatched_pred:none:1:1", "unmatched_pred", None, 1, '不需要详细到 "拿位", 实际上是和 gold event 1 一样, 是见面')]),
        _annotation("3", [_note("unmatched_pred:none:0:0", "unmatched_pred", None, 0, "Gold 缺少这个事情")]),
        _annotation("4", [_note("matched:0:0:0", "matched", 0, 0, '"speaker_1 的表姐" 放到 action 里, 模糊的人物指代不需要放到 actor 里')]),
        _annotation("4", [_note("unmatched_pred:none:3:3", "unmatched_pred", None, 3, "幻觉")]),
        _annotation("6", [_note("matched:2:2:2", "matched", 2, 2, '"speaker_1的朋友" 这种模糊指代需要放到 action 里, "和朋友吃饭"')]),
    ]
    gold_rows = [_row(str(dialogue_id), 4) for dialogue_id in {row["dialogue_id"] for row in annotation_rows}]
    pred_rows = [_row(str(dialogue_id), 4) for dialogue_id in {row["dialogue_id"] for row in annotation_rows}]

    plan = build_gemma_annotation_patch_plan(annotation_rows, gold_rows, pred_rows)

    assert plan["annotation_row_count"] == 15
    assert plan["event_note_count"] == 16
    assert plan["summary"]["gold_patch"] == 7
    assert plan["summary"]["pred_error"] == 4
    assert plan["summary"]["prompt_rule"] == 4
    assert plan["summary"]["judge_or_scorer_rule"] == 1
    assert len(plan["items"]) == 16

    by_note = {item["review_note"]: item for item in plan["items"]}
    assert by_note["pred 错误, speaker 1 27 号走, speaker 1 明天走"]["category"] == "pred_error"
    assert by_note["pred 错误, speaker 1 27 号走, speaker 1 明天走"]["gold_patch_candidate"] is False
    assert by_note["幻觉"]["category"] == "pred_error"
    assert by_note["修改 Gold, 或者要求时间区间的表达方式"]["requires_human_confirmation"] is True
    assert by_note["修改 Gold, 或者要求时间区间的表达方式"]["feedback_targets"] == [
        "gold_patch",
        "evaluation_prompt",
    ]
    assert by_note["judge 可以认为 出来转转 和 见面,逛街 是一件事情"]["category"] == "judge_or_scorer_rule"
    assert by_note["judge 可以认为 出来转转 和 见面,逛街 是一件事情"]["feedback_targets"] == [
        "judge_prompt",
        "scorer",
    ]
    assert by_note['不需要详细到 "拿位", 实际上是和 gold event 1 一样, 是见面']["feedback_targets"] == [
        "evaluation_prompt",
        "judge_prompt",
        "scorer",
    ]
    assert by_note['Gold要改, 做的事情是 "做糖筛 或 做 唐筛", 可以简化为 "做检查"']["feedback_targets"] == [
        "gold_patch",
        "evaluation_prompt",
        "judge_prompt",
    ]
    assert by_note['"speaker_1的朋友" 这种模糊指代需要放到 action 里, "和朋友吃饭"']["category"] == "prompt_rule"
    assert by_note['"speaker_1的朋友" 这种模糊指代需要放到 action 里, "和朋友吃饭"']["feedback_targets"] == [
        "evaluation_prompt"
    ]
    assert by_note["Gold 缺少这个事情"]["category"] == "gold_patch"


def test_build_gemma_annotation_patch_plan_classifies_v5_feedback_rows() -> None:
    annotation_rows = [
        _annotation("1", [_note("unmatched_gold:0:none:0", "unmatched_gold", 0, None, "Pred 没有探测到这个事件")]),
        _annotation("3", [_note("unmatched_pred:none:0:0", "unmatched_pred", None, 0, "Gold 缺少这个事情")]),
        _annotation(
            "4",
            [
                _note("matched:0:0:0", "matched", 0, 0, "Judge 要改, 有大聚会和参加聚会是同一件事"),
                _note("unmatched_pred:none:3:3", "unmatched_pred", None, 3, "幻觉"),
            ],
        ),
        _annotation("6", [_note("matched:2:2:2", "matched", 2, 2, "Pred 应该把 Speaker 1 的朋友放到 Action 里, 模糊的人物指代不需要放到 actor 里")]),
        _annotation("8", [_note("matched:0:0:0", "matched", 0, 0, 'Judge 要改, "今天直到夕阳西下" 和 "今天" 可以视为同一个')]),
        _annotation("9", [_note("matched:0:0:0", "matched", 0, 0, 'judge 要改, action 里的 "见面聊天" 和"见面, 聊聊" 是同一个')]),
        _annotation("10", [_note("unmatched_gold:1:none:1", "unmatched_gold", 1, None, "Pred 没有探测到这个事件")]),
        _annotation("12", [_note("matched:1:1:1", "matched", 1, 1, "修改 Gold, 或者要求时间区间的表达方式")]),
        _annotation("15", [_note("matched:0:0:0", "matched", 0, 0, "这里不是一起吃饭, 是同时在同一地点吃饭")]),
        _annotation("17", [_note("matched:1:1:1", "matched", 1, 1, "缺少发信时间")]),
        _annotation(
            "18",
            [
                _note("unmatched_gold:0:none:0", "unmatched_gold", 0, None, "Pred 没有探测到这个事件"),
                _note("unmatched_gold:1:none:1", "unmatched_gold", 1, None, "Pred 没有探测到这个事件"),
            ],
        ),
        _annotation("19", [_note("matched:0:0:0", "matched", 0, 0, "Pred 应该把 Speaker 1 的同事放到 Action 里, 模糊的人物指代不需要放到 actor 里")]),
        _annotation("27", [_note("unmatched_pred:none:1:1", "unmatched_pred", None, 1, '不需要详细到 "拿位", 实际上是和 gold event 1 一样, 是见面')]),
        _annotation("29", [_note("matched:0:0:0", "matched", 0, 0, "Gold 和 PRed 要改, 同事是模糊第三方, actor 只保留 speaker_2")]),
    ]
    annotation_rows[2]["event_notes"].extend(
        [
            _note("matched:1:1:1", "matched", 1, 1, "Gold 要改, event 1 和 event 2 是重复的"),
            _note("matched:2:2:2", "matched", 2, 2, "Judge 要改, 不要因为同日同主题把不同主体事件强行配对"),
            _note("matched:3:3:3", "matched", 3, 3, "Gold 要改, 这里 action 应该更稳"),
            _note("matched:4:4:4", "matched", 4, 4, "Pred 没有探测到这个事件"),
        ]
    )
    gold_rows = [_row(str(dialogue_id), 5) for dialogue_id in {row["dialogue_id"] for row in annotation_rows}]
    pred_rows = [_row(str(dialogue_id), 5) for dialogue_id in {row["dialogue_id"] for row in annotation_rows}]

    plan = build_gemma_annotation_patch_plan(annotation_rows, gold_rows, pred_rows)

    assert plan["annotation_row_count"] == 14
    assert plan["event_note_count"] == 20
    by_note = {item["review_note"]: item for item in plan["items"]}
    assert by_note["Pred 没有探测到这个事件"]["category"] == "pred_error"
    assert by_note["Pred 没有探测到这个事件"]["feedback_targets"] == [
        "evaluation_prompt",
        "prediction",
    ]
    assert by_note['Judge 要改, "今天直到夕阳西下" 和 "今天" 可以视为同一个']["category"] == (
        "judge_or_scorer_rule"
    )
    assert by_note['Judge 要改, "今天直到夕阳西下" 和 "今天" 可以视为同一个']["feedback_targets"] == [
        "judge_prompt",
        "scorer",
    ]
    assert by_note['judge 要改, action 里的 "见面聊天" 和"见面, 聊聊" 是同一个']["feedback_targets"] == [
        "judge_prompt",
        "scorer",
    ]
    assert by_note["Pred 应该把 Speaker 1 的同事放到 Action 里, 模糊的人物指代不需要放到 actor 里"][
        "category"
    ] == "prompt_rule"
    assert by_note["Pred 应该把 Speaker 1 的同事放到 Action 里, 模糊的人物指代不需要放到 actor 里"][
        "feedback_targets"
    ] == ["evaluation_prompt"]
    assert by_note["Gold 和 PRed 要改, 同事是模糊第三方, actor 只保留 speaker_2"]["category"] == "gold_patch"
    assert by_note["Gold 和 PRed 要改, 同事是模糊第三方, actor 只保留 speaker_2"]["feedback_targets"] == [
        "gold_patch",
        "evaluation_prompt",
    ]


def test_write_gemma_annotation_patch_plan_outputs_json_and_markdown(tmp_path: Path) -> None:
    plan = build_gemma_annotation_patch_plan(
        [_annotation("4", [_note("unmatched_pred:none:3:3", "unmatched_pred", None, 3, "幻觉")])],
        [_row("4", 1)],
        [_row("4", 4)],
    )

    json_path = tmp_path / "patch-plan.json"
    md_path = tmp_path / "patch-plan.md"
    write_gemma_annotation_patch_plan(plan, json_path=json_path, markdown_path=md_path)

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["event_note_count"] == 1
    markdown = md_path.read_text(encoding="utf-8")
    assert "# Gemma 4 Annotation Gold Patch Plan" in markdown
    assert "dialogue_id" in markdown
    assert "targets" in markdown
    assert "pred_error" in markdown
    assert "幻觉" in markdown


def _annotation(dialogue_id: str, event_notes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "artifact": "google_gemma-4-31B-it",
        "dialogue_id": dialogue_id,
        "event_notes": event_notes,
    }


def _note(
    event_key: str,
    match_status: str,
    gold_event_index: int | None,
    pred_event_index: int | None,
    note: str,
) -> dict[str, object]:
    return {
        "event_key": event_key,
        "match_status": match_status,
        "gold_event_index": gold_event_index,
        "pred_event_index": pred_event_index,
        "note": note,
    }


def _row(dialogue_id: str, event_count: int) -> dict[str, object]:
    return {
        "dialogue_id": dialogue_id,
        "dialogue": [f"speaker_1: dialogue {dialogue_id}"],
        "events": [
            {
                "actor": ["speaker_1"],
                "time": [f"time-{index}"],
                "location": None,
                "action": [f"action-{index}"],
                "digest": f"digest-{index}",
            }
            for index in range(event_count)
        ],
    }
