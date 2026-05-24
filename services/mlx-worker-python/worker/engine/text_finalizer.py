from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextFinalizationUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class TextFinalizationReceipt:
    response_id: str
    created: str
    stream_mode: bool
    finish_reason: str
    usage: TextFinalizationUsage
    usage_trailer_emitted: bool
    reasoning_finalized: bool
    tool_calls_finalized: bool
    malformed_channel_recovered: bool
    finalizer_path: str

    def parser_metrics(self) -> dict[str, str]:
        return {
            "response_id": self.response_id,
            "created": self.created,
            "stream_mode": _bool_text(self.stream_mode),
            "finish_reason": self.finish_reason,
            "usage_prompt_tokens": str(self.usage.prompt_tokens),
            "usage_completion_tokens": str(self.usage.completion_tokens),
            "usage_total_tokens": str(self.usage.total_tokens),
            "usage_trailer_emitted": _bool_text(self.usage_trailer_emitted),
            "reasoning_finalized": _bool_text(self.reasoning_finalized),
            "tool_calls_finalized": _bool_text(self.tool_calls_finalized),
            "malformed_channel_recovered": _bool_text(self.malformed_channel_recovered),
            "finalizer_path": self.finalizer_path,
        }


def finalize_text_response(
    *,
    response_id: str,
    created: str,
    stream_mode: bool,
    finish_reason: str,
    usage: TextFinalizationUsage,
    usage_trailer_emitted: bool,
    reasoning_text: str,
    tool_call_count: int,
    parser_metrics: dict[str, int | str],
) -> TextFinalizationReceipt:
    return TextFinalizationReceipt(
        response_id=response_id,
        created=created,
        stream_mode=stream_mode,
        finish_reason=finish_reason,
        usage=usage,
        usage_trailer_emitted=usage_trailer_emitted,
        reasoning_finalized=bool(reasoning_text)
        or _metric_positive(parser_metrics, "generated_reasoning_delta_count")
        or _metric_positive(parser_metrics, "harmony_channel_hidden_count"),
        tool_calls_finalized=tool_call_count > 0
        or _metric_positive(parser_metrics, "generated_tool_call_delta_count")
        or _metric_positive(parser_metrics, "malformed_tool_fragment_count"),
        malformed_channel_recovered=_metric_positive(
            parser_metrics,
            "reasoning_channel_recovery_count",
        )
        or _metric_positive(parser_metrics, "malformed_tool_fragment_count"),
        finalizer_path="stream" if stream_mode else "non_stream",
    )


def finalize_text_response_metrics(
    *,
    response_id: str,
    created: str,
    stream_mode: bool,
    finish_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
    usage_trailer_emitted: bool,
    reasoning_text: str,
    tool_call_count: int,
    parser_metrics: dict[str, int | str],
) -> dict[str, str]:
    reasoning_finalized = (
        bool(reasoning_text)
        or _metric_positive(parser_metrics, "generated_reasoning_delta_count")
        or _metric_positive(parser_metrics, "harmony_channel_hidden_count")
    )
    tool_calls_finalized = (
        tool_call_count > 0
        or _metric_positive(parser_metrics, "generated_tool_call_delta_count")
        or _metric_positive(parser_metrics, "malformed_tool_fragment_count")
    )
    malformed_channel_recovered = _metric_positive(
        parser_metrics,
        "reasoning_channel_recovery_count",
    ) or _metric_positive(parser_metrics, "malformed_tool_fragment_count")
    return {
        "response_id": response_id,
        "created": created,
        "stream_mode": _bool_text(stream_mode),
        "finish_reason": finish_reason,
        "usage_prompt_tokens": str(prompt_tokens),
        "usage_completion_tokens": str(completion_tokens),
        "usage_total_tokens": str(prompt_tokens + completion_tokens),
        "usage_trailer_emitted": _bool_text(usage_trailer_emitted),
        "reasoning_finalized": _bool_text(reasoning_finalized),
        "tool_calls_finalized": _bool_text(tool_calls_finalized),
        "malformed_channel_recovered": _bool_text(malformed_channel_recovered),
        "finalizer_path": "stream" if stream_mode else "non_stream",
    }


def apply_text_response_metrics(
    parser_metrics: dict[str, str],
    *,
    response_id: str,
    created: str,
    stream_mode: bool,
    finish_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
    usage_trailer_emitted: bool,
    reasoning_finalized: bool,
    tool_calls_finalized: bool,
    malformed_channel_recovered: bool,
) -> None:
    parser_metrics["response_id"] = response_id
    parser_metrics["created"] = created
    parser_metrics["stream_mode"] = _bool_text(stream_mode)
    parser_metrics["finish_reason"] = finish_reason
    parser_metrics["usage_prompt_tokens"] = str(prompt_tokens)
    parser_metrics["usage_completion_tokens"] = str(completion_tokens)
    parser_metrics["usage_total_tokens"] = str(prompt_tokens + completion_tokens)
    parser_metrics["usage_trailer_emitted"] = _bool_text(usage_trailer_emitted)
    parser_metrics["reasoning_finalized"] = _bool_text(reasoning_finalized)
    parser_metrics["tool_calls_finalized"] = _bool_text(tool_calls_finalized)
    parser_metrics["malformed_channel_recovered"] = _bool_text(malformed_channel_recovered)
    parser_metrics["finalizer_path"] = "stream" if stream_mode else "non_stream"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _metric_positive(metrics: dict[str, int | str], key: str) -> bool:
    try:
        return int(metrics.get(key, 0) or 0) > 0
    except (TypeError, ValueError):
        return False
