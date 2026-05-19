from __future__ import annotations

import copy
import json
from typing import Any, Iterable, Mapping

AGENTIC_SFT_FORMATTER_ID = "melix.agentic_tool_trace.sft_formatter.v1"


def new_projection_metrics() -> dict[str, int]:
    return {
        "sample_count": 0,
        "tool_call_count": 0,
        "tool_observation_count": 0,
        "media_ref_count": 0,
        "final_answer_count": 0,
    }


def merge_projection_metrics(
    *metrics_items: Mapping[str, Any],
) -> dict[str, int]:
    merged = new_projection_metrics()
    for metrics in metrics_items:
        for key in merged:
            try:
                merged[key] += int(metrics.get(key, 0) or 0)
            except (TypeError, ValueError):
                continue
    return merged


def format_trace_rows(
    samples: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    metrics = new_projection_metrics()
    for sample in samples:
        rows.append(format_trace_row(sample, metrics))
    return rows, metrics


def format_trace_row(
    sample: dict[str, Any],
    metrics: dict[str, int] | None = None,
) -> dict[str, Any]:
    counters = metrics if metrics is not None else new_projection_metrics()
    counters["sample_count"] += 1

    messages: list[dict[str, str]] = []
    media_refs = sample.get("media_refs")
    media_context = ""
    emitted_media_context = False
    if isinstance(media_refs, list) and media_refs:
        counters["media_ref_count"] += len(media_refs)
        media_context = "Media references:\n" + "\n".join(
            _format_media_ref(media_ref) for media_ref in media_refs
        )

    for raw_turn in sample.get("turns", []):
        if not isinstance(raw_turn, dict):
            continue
        role = str(raw_turn.get("role", "")).strip()
        if role in {"system", "user"}:
            content = str(raw_turn.get("content", "")).strip()
            if content:
                if role == "system" and media_context and not emitted_media_context:
                    content = f"{media_context}\n\n{content}"
                    emitted_media_context = True
                messages.append({"role": role, "content": content})
            continue
        if role == "assistant":
            content = _format_assistant_turn(raw_turn)
            if content:
                if isinstance(raw_turn.get("tool_call"), dict):
                    counters["tool_call_count"] += 1
                messages.append({"role": "assistant", "content": content})
            continue
        if role == "tool":
            content = _format_tool_turn(raw_turn)
            if content:
                counters["tool_observation_count"] += 1
                messages.append({"role": "tool", "content": content})

    if media_context and not emitted_media_context:
        messages.insert(0, {"role": "system", "content": media_context})

    final_answer = str(sample.get("final_answer", "")).strip()
    if final_answer:
        counters["final_answer_count"] += 1
        final_content = f"Final answer: {final_answer}"
        if messages and messages[-1]["role"] == "assistant":
            existing_content = messages[-1]["content"].strip()
            if existing_content == final_answer:
                messages[-1] = {"role": "assistant", "content": final_content}
            elif final_content not in existing_content:
                messages[-1] = {
                    "role": "assistant",
                    "content": f"{existing_content}\n\n{final_content}",
                }
        else:
            messages.append({"role": "assistant", "content": final_content})

    row: dict[str, Any] = {
        "messages": messages,
    }
    if isinstance(sample.get("tools"), list):
        row["tools"] = copy.deepcopy(sample["tools"])
    return row


def _format_media_ref(media_ref: Any) -> str:
    if not isinstance(media_ref, Mapping):
        return f"- {media_ref}"
    ref_id = str(media_ref.get("id", "")).strip()
    uri = str(media_ref.get("uri", "")).strip()
    mime_type = str(media_ref.get("mime_type", "")).strip()
    parts = []
    if ref_id:
        parts.append(f"id={ref_id}")
    if uri:
        parts.append(f"uri={uri}")
    if mime_type:
        parts.append(f"mime_type={mime_type}")
    if not parts:
        return "- {}"
    return "- " + "; ".join(parts)


def _format_assistant_turn(turn: Mapping[str, Any]) -> str:
    content = str(turn.get("content", "")).strip()
    tool_call = turn.get("tool_call")
    if not isinstance(tool_call, Mapping):
        return content
    call_id = str(tool_call.get("id", "")).strip()
    name = str(tool_call.get("name", "")).strip()
    arguments = tool_call.get("arguments")
    payload = {
        "id": call_id,
        "name": name,
        "arguments": arguments if isinstance(arguments, Mapping) else {},
    }
    rendered = "Tool call: " + json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if content:
        return f"{content}\n{rendered}"
    return rendered


def _format_tool_turn(turn: Mapping[str, Any]) -> str:
    tool_call_id = str(turn.get("tool_call_id", "")).strip()
    observation = turn.get("observation")
    if isinstance(observation, Mapping):
        rendered_observation = json.dumps(
            observation,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    else:
        rendered_observation = str(observation or "").strip()
    if not rendered_observation:
        return ""
    if tool_call_id:
        return f"Tool observation for {tool_call_id}: {rendered_observation}"
    return f"Tool observation: {rendered_observation}"
