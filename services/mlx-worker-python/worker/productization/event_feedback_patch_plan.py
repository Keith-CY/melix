from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


def build_gemma_annotation_patch_plan(
    annotation_rows: Iterable[Mapping[str, Any]],
    gold_rows: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    pred_rows: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    *,
    source: str = "google_gemma-4-31B-it-annotations.jsonl",
) -> dict[str, Any]:
    annotations = [dict(row) for row in annotation_rows]
    gold_by_dialogue = _rows_by_dialogue(gold_rows)
    pred_by_dialogue = _rows_by_dialogue(pred_rows)
    items: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()

    for annotation in annotations:
        dialogue_id = str(annotation.get("dialogue_id") or "").strip()
        if not dialogue_id:
            continue
        gold_events = _events_for_dialogue(gold_by_dialogue, dialogue_id)
        pred_events = _events_for_dialogue(pred_by_dialogue, dialogue_id)
        event_notes = annotation.get("event_notes")
        if not isinstance(event_notes, list):
            continue
        for event_note in event_notes:
            if not isinstance(event_note, Mapping):
                continue
            item = _build_patch_plan_item(
                dialogue_id=dialogue_id,
                event_note=event_note,
                gold_events=gold_events,
                pred_events=pred_events,
            )
            items.append(item)
            summary[str(item["category"])] += 1

    artifact_names = sorted(
        {
            str(row.get("artifact"))
            for row in annotations
            if isinstance(row.get("artifact"), str) and str(row.get("artifact")).strip()
        }
    )
    event_note_count = len(items)
    return {
        "artifact": artifact_names[0] if len(artifact_names) == 1 else artifact_names,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": source,
        "annotation_row_count": len(annotations),
        "event_note_count": event_note_count,
        "summary": {category: summary.get(category, 0) for category in _CATEGORY_ORDER},
        "items": items,
    }


def write_gemma_annotation_patch_plan(
    plan: Mapping[str, Any],
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_patch_plan_markdown(plan), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if not isinstance(row, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            rows.append(row)
    return rows


def _build_patch_plan_item(
    *,
    dialogue_id: str,
    event_note: Mapping[str, Any],
    gold_events: list[dict[str, Any]],
    pred_events: list[dict[str, Any]],
) -> dict[str, Any]:
    note = str(event_note.get("note") or "").strip()
    match_status = str(event_note.get("match_status") or "").strip()
    gold_event_index = _optional_int(event_note.get("gold_event_index"))
    pred_event_index = _optional_int(event_note.get("pred_event_index"))
    category = _classify_note(note=note, match_status=match_status)
    return {
        "dialogue_id": dialogue_id,
        "event_key": str(event_note.get("event_key") or ""),
        "match_status": match_status,
        "gold_event_index": gold_event_index,
        "pred_event_index": pred_event_index,
        "review_note": note,
        "category": category,
        "feedback_targets": _feedback_targets(note=note, category=category, match_status=match_status),
        "gold_patch_candidate": category == "gold_patch",
        "requires_human_confirmation": category in {"gold_patch", "needs_triage"},
        "suggested_change": _suggested_change(note=note, category=category, match_status=match_status),
        "gold_event": _event_at(gold_events, gold_event_index),
        "pred_event": _event_at(pred_events, pred_event_index),
    }


def _classify_note(*, note: str, match_status: str) -> str:
    normalized = note.lower()
    if "pred 没有探测到" in normalized or "pred没有探测到" in normalized:
        return "pred_error"
    if "pred 错误" in note or "幻觉" in note:
        return "pred_error"
    if match_status == "unmatched_pred" and ("重复" in note or "相同事件" in note):
        return "pred_error"
    if "judge" in normalized:
        return "judge_or_scorer_rule"
    if any(token in note for token in ("Gold 和 PRed 要改", "Gold 和 Pred 要改", "Gold 要改")):
        return "gold_patch"
    if any(token in note for token in ("模糊", "放到 action", "放到action", "拿位", "不需要详细到", "不是一起")):
        return "prompt_rule"
    if any(token in note for token in ("修改 Gold", "改 Gold", "Gold要改", "Gold 缺少", "缺少发信时间")):
        return "gold_patch"
    if "重复" in note and match_status == "unmatched_gold":
        return "gold_patch"
    return "needs_triage"


def _feedback_targets(*, note: str, category: str, match_status: str) -> list[str]:
    if category == "pred_error":
        targets = ["prediction"]
        normalized = note.lower()
        if "pred 没有探测到" in normalized or "pred没有探测到" in normalized:
            targets.append("evaluation_prompt")
        return _unique_targets(targets)
    if category == "judge_or_scorer_rule":
        return ["judge_prompt", "scorer"]

    targets: list[str] = []
    if category == "gold_patch":
        targets.append("gold_patch")
    if category == "prompt_rule":
        targets.append("evaluation_prompt")

    if "时间区间" in note:
        targets.extend(["gold_patch", "evaluation_prompt"])
    if "不是一起" in note or "同一地点" in note:
        targets.append("evaluation_prompt")
    if "重复" in note and match_status == "unmatched_gold":
        targets.extend(["gold_patch", "evaluation_prompt"])
    if "拿位" in note:
        targets.extend(["evaluation_prompt", "judge_prompt", "scorer"])
    if "做检查" in note or "唐筛" in note or "糖筛" in note:
        targets.extend(["gold_patch", "evaluation_prompt", "judge_prompt"])
    if "模糊" in note or "放到 action" in note or "放到action" in note:
        targets.append("evaluation_prompt")
    if "拆成 2" in note:
        targets.append("gold_patch")
    if "缺少发信时间" in note or "Gold 缺少" in note or ("同事" in note and category == "gold_patch"):
        targets.append("gold_patch")
    if not targets:
        targets.append("manual_triage")
    return _unique_targets(targets)


def _suggested_change(*, note: str, category: str, match_status: str) -> str:
    if category == "pred_error":
        normalized = note.lower()
        if "pred 没有探测到" in normalized or "pred没有探测到" in normalized:
            return "Do not patch gold by default. Treat this as a model recall miss and feed it back into the evaluation prompt."
        return "Do not patch gold. Treat this annotation as a model prediction error."
    if category == "judge_or_scorer_rule":
        return "Review semantic judge/scorer handling; keep final metric formula local."
    if category == "prompt_rule":
        if "拿位" in note:
            return "Prompt should merge micro preparation actions into the main meetup or meal event."
        if "不是一起" in note:
            return "Prompt should not infer shared actors only because events happen at the same place and time."
        if "模糊" in note or "放到 action" in note or "放到action" in note:
            return "Prompt should keep vague third-party relation words in action detail unless the third party is the event subject."
        return "Prompt should discourage this extraction pattern in baseline.v4."
    if category == "gold_patch":
        if "时间区间" in note:
            return "Human review: keep continuous ranges as a single time expression, or adjust gold if the range is currently over/under-specified."
        if "重复" in note:
            return "Human review: remove or merge duplicate gold event if it has no independent action value."
        if "拆成 2" in note:
            return "Human review: split the gold event into two separately supported events."
        if "做检查" in note:
            return "Human review: normalize the gold action to a safer parent action such as 做检查."
        if "同事" in note:
            return "Human review: decide whether the coworker should be represented in actor or action detail."
        if "缺少" in note and match_status == "unmatched_pred":
            return "Human review: consider adding the missing gold event if directly supported by the dialogue."
        return "Human review: update gold only after checking the original dialogue evidence."
    return "Needs manual triage before deciding whether to patch gold, prompt, judge, or scorer."


def _rows_by_dialogue(
    rows: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if isinstance(rows, Mapping):
        return {str(dialogue_id): row for dialogue_id, row in rows.items()}
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        dialogue_id = str(row.get("dialogue_id") or "").strip()
        if dialogue_id:
            result[dialogue_id] = row
    return result


def _events_for_dialogue(rows_by_dialogue: Mapping[str, Mapping[str, Any]], dialogue_id: str) -> list[dict[str, Any]]:
    row = rows_by_dialogue.get(dialogue_id)
    if row is None:
        return []
    events = row.get("events")
    if not isinstance(events, list):
        return []
    return [dict(event) for event in events if isinstance(event, Mapping)]


def _event_at(events: list[dict[str, Any]], index: int | None) -> dict[str, Any] | None:
    if index is None:
        return None
    if index < 0 or index >= len(events):
        return None
    return events[index]


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _patch_plan_markdown(plan: Mapping[str, Any]) -> str:
    lines = [
        "# Gemma 4 Annotation Gold Patch Plan",
        "",
        f"- artifact: `{plan.get('artifact')}`",
        f"- annotation rows: `{plan.get('annotation_row_count')}`",
        f"- event notes: `{plan.get('event_note_count')}`",
        "",
        "## Summary",
        "",
    ]
    summary = plan.get("summary") if isinstance(plan.get("summary"), Mapping) else {}
    for category in _CATEGORY_ORDER:
        lines.append(f"- {category}: `{summary.get(category, 0)}`")
    lines.extend(
        [
            "",
            "## Items",
            "",
            "| dialogue_id | status | gold | pred | category | targets | human review | note | suggestion |",
            "| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    items = plan.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(item.get("dialogue_id")),
                        _md_cell(item.get("match_status")),
                        _md_cell(item.get("gold_event_index")),
                        _md_cell(item.get("pred_event_index")),
                        _md_cell(item.get("category")),
                        _md_cell(",".join(item.get("feedback_targets", [])) if isinstance(item.get("feedback_targets"), list) else ""),
                        _md_cell(item.get("requires_human_confirmation")),
                        _md_cell(item.get("review_note")),
                        _md_cell(item.get("suggested_change")),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def _md_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _unique_targets(values: list[str]) -> list[str]:
    ordered = ["gold_patch", "evaluation_prompt", "judge_prompt", "scorer", "prediction", "manual_triage"]
    seen = set(values)
    return [target for target in ordered if target in seen]


_CATEGORY_ORDER = ("gold_patch", "prompt_rule", "judge_or_scorer_rule", "pred_error", "needs_triage")
