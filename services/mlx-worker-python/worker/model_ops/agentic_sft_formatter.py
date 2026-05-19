from __future__ import annotations

import copy
import json
from typing import Any, Iterable, Mapping

AGENTIC_SFT_FORMATTER_ID = "melix.agentic_tool_trace.sft_formatter.v1"
AGENTIC_SFT_BOUNDARY_POLICY_ID = "melix.agentic_tool_trace.response_only_boundaries.v1"


def new_projection_metrics() -> dict[str, int]:
    return {
        "sample_count": 0,
        "trainer_row_count": 0,
        "tool_call_count": 0,
        "tool_observation_count": 0,
        "media_ref_count": 0,
        "final_answer_count": 0,
        "response_only_boundary_count": 0,
        "mask_prompt_boundary_count": 0,
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


def count_trace_trainer_rows(samples: Iterable[dict[str, Any]]) -> int:
    row_count = 0
    for sample in samples:
        for raw_turn in sample.get("turns", []):
            if (
                isinstance(raw_turn, Mapping)
                and str(raw_turn.get("role", "")).strip() == "assistant"
                and isinstance(raw_turn.get("tool_call"), Mapping)
            ):
                row_count += 1
        if str(sample.get("final_answer", "")).strip():
            row_count += 1
    return row_count


def format_trace_rows(
    samples: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    metrics = new_projection_metrics()
    for sample in samples:
        rows.extend(format_trace_row(sample, metrics))
    return rows, metrics


def format_trace_row(
    sample: dict[str, Any],
    metrics: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    counters = metrics if metrics is not None else new_projection_metrics()
    counters["sample_count"] += 1

    context_messages: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    tools = copy.deepcopy(sample["tools"]) if isinstance(sample.get("tools"), list) else None
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
                context_messages.append({"role": role, "content": content})
            continue
        if role == "assistant":
            content = _format_assistant_turn(raw_turn)
            if content:
                if isinstance(raw_turn.get("tool_call"), dict):
                    counters["tool_call_count"] += 1
                    if media_context and not emitted_media_context:
                        context_messages.insert(
                            0, {"role": "system", "content": media_context}
                        )
                        emitted_media_context = True
                    rows.append(
                        _build_supervised_row(
                            context_messages,
                            {"role": "assistant", "content": content},
                            tools=tools,
                            trace_id=sample.get("trace_id"),
                            trainable_kind="tool_call",
                            counters=counters,
                        )
                    )
                context_messages.append({"role": "assistant", "content": content})
            continue
        if role == "tool":
            content = _format_tool_turn(raw_turn)
            if content:
                counters["tool_observation_count"] += 1
                context_messages.append({"role": "tool", "content": content})

    if media_context and not emitted_media_context:
        context_messages.insert(0, {"role": "system", "content": media_context})

    final_answer = str(sample.get("final_answer", "")).strip()
    if final_answer:
        counters["final_answer_count"] += 1
        final_content = f"Final answer: {final_answer}"
        if context_messages and context_messages[-1]["role"] == "assistant":
            existing_content = context_messages[-1]["content"].strip()
            if existing_content == final_answer:
                context_messages[-1] = {"role": "assistant", "content": final_content}
            elif final_content not in existing_content:
                context_messages[-1] = {
                    "role": "assistant",
                    "content": f"{existing_content}\n\n{final_content}",
                }
        else:
            context_messages.append({"role": "assistant", "content": final_content})

        if context_messages and context_messages[-1]["role"] == "assistant":
            rows.append(
                _build_supervised_row(
                    context_messages[:-1],
                    context_messages[-1],
                    tools=tools,
                    trace_id=sample.get("trace_id"),
                    trainable_kind="final_answer",
                    counters=counters,
                )
            )

    return rows


def _build_supervised_row(
    prefix_messages: list[dict[str, str]],
    assistant_message: dict[str, str],
    *,
    tools: list[Any] | None,
    trace_id: Any,
    trainable_kind: str,
    counters: dict[str, int],
) -> dict[str, Any]:
    counters["trainer_row_count"] += 1
    counters["response_only_boundary_count"] += 1
    counters["mask_prompt_boundary_count"] += 1
    row: dict[str, Any] = {
        "messages": [
            copy.deepcopy(message)
            for message in [*prefix_messages, assistant_message]
        ],
        "response_only_boundary": {
            "policy_id": AGENTIC_SFT_BOUNDARY_POLICY_ID,
            "mask_prompt": True,
            "trainable_role": "assistant",
            "trainable_kind": trainable_kind,
            "trainable_message_index": len(prefix_messages),
        },
    }
    trace_id_value = str(trace_id or "").strip()
    if trace_id_value:
        row["response_only_boundary"]["trace_id"] = trace_id_value
    if tools is not None:
        row["tools"] = copy.deepcopy(tools)
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
