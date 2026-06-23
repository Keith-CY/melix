from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import math
import re
import time
from typing import Any

_perf_counter = time.perf_counter


_STEP_PROGRESS_RE = re.compile(
    r"(?:step|iter(?:ation)?)\s*[=: ]\s*(?P<step>\d+)"
    r"(?:\s*/\s*(?P<total>\d+))?",
    re.IGNORECASE,
)
_FRACTION_PROGRESS_RE = re.compile(r"(?P<step>\d+)\s*/\s*(?P<total>\d+)")
_LOSS_RE = re.compile(
    r"(?<!validation[_ -])(?<!val[_ -])(?<!eval[_ -])"
    r"(?:train[_ -])?loss\s*[=: ]\s*(?P<loss>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)",
    re.IGNORECASE,
)
_VALIDATION_LOSS_RE = re.compile(
    r"(?:validation|val|eval)[_ -]?loss\s*[=: ]\s*(?P<loss>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)",
    re.IGNORECASE,
)
_LEARNING_RATE_RE = re.compile(
    r"(?:learning[_ -]?rate|lr)\s*[=: ]\s*(?P<learning_rate>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)",
    re.IGNORECASE,
)
_TOKENS_RE = re.compile(r"(?:trained[_ -]?tokens|tokens[_ -]?seen)\s*[=: ]\s*(?P<tokens>\d+)", re.IGNORECASE)
_EXAMPLES_RE = re.compile(r"(?:trained[_ -]?examples|examples[_ -]?seen)\s*[=: ]\s*(?P<examples>\d+)", re.IGNORECASE)
_ETA_RE = re.compile(
    r"(?:eta|remaining)\s*[=: ]\s*(?P<eta>[0-9]+(?::[0-9]{2}){1,2}|[0-9]+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds|m|min|mins|minutes|h|hr|hrs|hours))",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"(?:duration|elapsed|train(?:ing)?[_ -]?time)\s*[=: ]\s*(?P<duration>[0-9]+(?::[0-9]{2}){1,2}|[0-9]+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds|m|min|mins|minutes|h|hr|hrs|hours))",
    re.IGNORECASE,
)
_FINAL_RE = re.compile(r"\b(?:final summary|training complete|completed training|finished training)\b", re.IGNORECASE)
_OOM_RE = re.compile(r"\b(?:out of memory|oom|memoryerror|metal out of memory)\b", re.IGNORECASE)
_METAL_WATCHDOG_RE = re.compile(r"\b(?:metal(?: gpu)? watchdog|gpu watchdog|watchdog timeout|command buffer.*watchdog)\b", re.IGNORECASE)
_STALLED_RE = re.compile(r"\b(?:stalled progress|no progress|training stalled|progress timeout|heartbeat timeout)\b", re.IGNORECASE)
_RISING_LOSS_RE = re.compile(r"\b(?:rising loss|loss diverged|loss divergence|diverging loss|nan loss|loss is nan)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TrainingLogEvent:
    event_type: str
    severity: str
    source: str
    line_number: int
    step: int | None = None
    total_steps: int | None = None
    loss: float | None = None
    validation_loss: float | None = None
    learning_rate: float | None = None
    tokens_seen: int | None = None
    examples_seen: int | None = None
    eta_seconds: float | None = None
    duration_ms: float | None = None
    operator_message: str = ""
    evidence_pointer: str = ""
    raw_line_redacted: str = ""

    def to_manifest_row(self) -> dict[str, object]:
        row = {
            key: value
            for key, value in asdict(self).items()
            if value is not None and value != ""
        }
        return row


@dataclass(frozen=True)
class TrainingLogParseSummary:
    schema_version: str
    status: str
    input_line_count: int
    parsed_row_count: int
    alert_row_count: int
    unparsed_line_count: int
    parser_error_count: int
    parse_duration_ms: float
    final_step: int
    final_total_steps: int
    final_loss: float | None
    best_loss: float | None
    final_validation_loss: float | None
    best_validation_loss: float | None
    final_learning_rate: float | None
    tokens_seen: int
    examples_seen: int
    terminal_event_type: str

    def to_manifest(self) -> dict[str, object]:
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }


@dataclass(frozen=True)
class TrainingLogParseResult:
    summary: TrainingLogParseSummary
    events: list[TrainingLogEvent]

    def manifest_fields(self, *, preview_limit: int = 20) -> dict[str, object]:
        bounded_limit = max(int(preview_limit), 0)
        preview = self.events[:bounded_limit]
        return {
            "training_log_events": self.summary.to_manifest(),
            "training_log_event_preview_limit": bounded_limit,
            "training_log_event_preview": [event.to_manifest_row() for event in preview],
        }


def parse_training_log_events(
    lines: Iterable[str],
    *,
    source: str = "training_log",
) -> TrainingLogParseResult:
    started_at = _perf_counter()
    events: list[TrainingLogEvent] = []
    input_line_count = 0
    unparsed_line_count = 0
    parser_error_count = 0

    for line_number, raw_line in enumerate(lines, start=1):
        input_line_count += 1
        line = str(raw_line).strip()
        if not line:
            continue
        try:
            parsed = _parse_line(line, line_number=line_number, source=source)
        except (TypeError, ValueError, OverflowError):
            parser_error_count += 1
            continue
        if parsed is None:
            unparsed_line_count += 1
            continue
        events.append(parsed)

    summary = _summarize_events(
        events,
        input_line_count=input_line_count,
        unparsed_line_count=unparsed_line_count,
        parser_error_count=parser_error_count,
        parse_duration_ms=(_perf_counter() - started_at) * 1000.0,
    )
    return TrainingLogParseResult(summary=summary, events=events)


def safe_training_log_manifest_fields(
    lines: Iterable[str],
    *,
    source: str = "training_log",
    preview_limit: int = 20,
) -> dict[str, object]:
    try:
        return parse_training_log_events(lines, source=source).manifest_fields(
            preview_limit=preview_limit
        )
    except Exception:
        summary = TrainingLogParseSummary(
            schema_version="melix.training_log_events.v1",
            status="parser_error",
            input_line_count=0,
            parsed_row_count=0,
            alert_row_count=0,
            unparsed_line_count=0,
            parser_error_count=1,
            parse_duration_ms=0.0,
            final_step=0,
            final_total_steps=0,
            final_loss=None,
            best_loss=None,
            final_validation_loss=None,
            best_validation_loss=None,
            final_learning_rate=None,
            tokens_seen=0,
            examples_seen=0,
            terminal_event_type="",
        )
        return {
            "training_log_events": summary.to_manifest(),
            "training_log_event_preview_limit": max(int(preview_limit), 0),
            "training_log_event_preview": [],
        }


def _parse_line(line: str, *, line_number: int, source: str) -> TrainingLogEvent | None:
    redacted = _redacted_line(line)
    alert = _alert_event(line, line_number=line_number, source=source, redacted=redacted)
    if alert is not None:
        return alert

    step, total_steps = _progress_fields(line)
    validation_loss = _float_match(_VALIDATION_LOSS_RE, line, "loss")
    loss = None if validation_loss is not None else _float_match(_LOSS_RE, line, "loss")
    learning_rate = _float_match(_LEARNING_RATE_RE, line, "learning_rate")
    tokens_seen = _int_match(_TOKENS_RE, line, "tokens")
    examples_seen = _int_match(_EXAMPLES_RE, line, "examples")
    eta_seconds = _seconds_match(_ETA_RE, line, "eta")
    duration_ms = _milliseconds_match(_DURATION_RE, line, "duration")
    final = _FINAL_RE.search(line) is not None

    if not any(
        value is not None
        for value in (
            step,
            loss,
            validation_loss,
            learning_rate,
            tokens_seen,
            examples_seen,
            eta_seconds,
            duration_ms,
        )
    ) and not final:
        return None

    if final:
        event_type = "final_summary"
    elif validation_loss is not None:
        event_type = "validation_loss"
    elif loss is not None:
        event_type = "loss"
    else:
        event_type = "progress"

    return TrainingLogEvent(
        event_type=event_type,
        severity="info",
        source=source,
        line_number=line_number,
        step=step,
        total_steps=total_steps,
        loss=loss,
        validation_loss=validation_loss,
        learning_rate=learning_rate,
        tokens_seen=tokens_seen,
        examples_seen=examples_seen,
        eta_seconds=eta_seconds,
        duration_ms=duration_ms,
        operator_message=_operator_message_for(event_type),
        evidence_pointer=f"{source}:line:{line_number}",
        raw_line_redacted=redacted,
    )


def _alert_event(
    line: str,
    *,
    line_number: int,
    source: str,
    redacted: str,
) -> TrainingLogEvent | None:
    cases = (
        (_OOM_RE, "oom", "error", "Training ran out of memory. Reduce batch size, sequence length, or LoRA scope."),
        (_METAL_WATCHDOG_RE, "metal_watchdog", "error", "Metal watchdog interrupted training. Reduce GPU pressure before retrying."),
        (_STALLED_RE, "stalled_progress", "warning", "Training progress stalled. Check runtime health and recent checkpoints."),
        (_RISING_LOSS_RE, "rising_loss", "warning", "Training loss is rising or diverging. Review learning rate, data quality, and recent checkpoints."),
    )
    for pattern, event_type, severity, message in cases:
        if pattern.search(line) is None:
            continue
        step, total_steps = _progress_fields(line)
        return TrainingLogEvent(
            event_type=event_type,
            severity=severity,
            source=source,
            line_number=line_number,
            step=step,
            total_steps=total_steps,
            loss=_float_match(_LOSS_RE, line, "loss"),
            validation_loss=_float_match(_VALIDATION_LOSS_RE, line, "loss"),
            operator_message=message,
            evidence_pointer=f"{source}:line:{line_number}",
            raw_line_redacted=redacted,
        )
    return None


def _summarize_events(
    events: list[TrainingLogEvent],
    *,
    input_line_count: int,
    unparsed_line_count: int,
    parser_error_count: int,
    parse_duration_ms: float,
) -> TrainingLogParseSummary:
    losses = [event.loss for event in events if event.loss is not None]
    validation_losses = [
        event.validation_loss for event in events if event.validation_loss is not None
    ]
    steps = [event.step for event in events if event.step is not None]
    total_steps = [event.total_steps for event in events if event.total_steps is not None]
    learning_rates = [
        event.learning_rate for event in events if event.learning_rate is not None
    ]
    tokens_seen = [event.tokens_seen for event in events if event.tokens_seen is not None]
    examples_seen = [
        event.examples_seen for event in events if event.examples_seen is not None
    ]
    alerts = [event for event in events if event.severity in {"warning", "error"}]
    terminal = next((event.event_type for event in reversed(events) if event.event_type == "final_summary"), "")
    status = "ok" if parser_error_count == 0 else "parser_errors"
    if any(event.severity == "error" for event in events):
        status = "alerts"
    elif alerts:
        status = "warnings"

    return TrainingLogParseSummary(
        schema_version="melix.training_log_events.v1",
        status=status,
        input_line_count=input_line_count,
        parsed_row_count=len(events),
        alert_row_count=len(alerts),
        unparsed_line_count=unparsed_line_count,
        parser_error_count=parser_error_count,
        parse_duration_ms=round(max(parse_duration_ms, 0.0), 3),
        final_step=max(steps) if steps else 0,
        final_total_steps=max(total_steps) if total_steps else 0,
        final_loss=losses[-1] if losses else None,
        best_loss=min(losses) if losses else None,
        final_validation_loss=validation_losses[-1] if validation_losses else None,
        best_validation_loss=min(validation_losses) if validation_losses else None,
        final_learning_rate=learning_rates[-1] if learning_rates else None,
        tokens_seen=max(tokens_seen) if tokens_seen else 0,
        examples_seen=max(examples_seen) if examples_seen else 0,
        terminal_event_type=terminal,
    )


def _progress_fields(line: str) -> tuple[int | None, int | None]:
    match = _STEP_PROGRESS_RE.search(line) or _FRACTION_PROGRESS_RE.search(line)
    if match is None:
        return None, None
    step = _safe_int(match.group("step"))
    total_steps = _safe_int(match.groupdict().get("total"))
    return step, total_steps


def _float_match(pattern: re.Pattern[str], line: str, group_name: str) -> float | None:
    match = pattern.search(line)
    if match is None:
        return None
    value = float(match.group(group_name))
    if not math.isfinite(value):
        return None
    return value


def _int_match(pattern: re.Pattern[str], line: str, group_name: str) -> int | None:
    match = pattern.search(line)
    if match is None:
        return None
    return _safe_int(match.group(group_name))


def _safe_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    parsed = int(value)
    return parsed if parsed >= 0 else None


def _seconds_match(pattern: re.Pattern[str], line: str, group_name: str) -> float | None:
    match = pattern.search(line)
    if match is None:
        return None
    return _duration_seconds(match.group(group_name))


def _milliseconds_match(pattern: re.Pattern[str], line: str, group_name: str) -> float | None:
    seconds = _seconds_match(pattern, line, group_name)
    return None if seconds is None else seconds * 1000.0


def _duration_seconds(value: str) -> float | None:
    text = value.strip().lower()
    if not text:
        return None
    if ":" in text:
        parts = [float(part) for part in text.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return None
    match = re.match(r"(?P<value>[0-9]+(?:\.\d+)?)\s*(?P<unit>[a-z]+)", text)
    if match is None:
        return None
    amount = float(match.group("value"))
    unit = match.group("unit")
    if unit == "ms":
        return amount / 1000.0
    if unit in {"s", "sec", "secs", "second", "seconds"}:
        return amount
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return amount * 60
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return amount * 3600
    return None


def _operator_message_for(event_type: str) -> str:
    return {
        "progress": "Training progress updated.",
        "loss": "Training loss updated.",
        "validation_loss": "Validation loss updated.",
        "final_summary": "Training completed and emitted a final summary.",
    }.get(event_type, "Training event parsed.")


def _redacted_line(line: str) -> str:
    redacted = re.sub(r"(?i)(token|secret|password|api[_-]?key)=\S+", r"\1=<redacted>", line)
    redacted = re.sub(r"(?i)(https?://[^/\s]+)[^\s]*", r"\1/<redacted>", redacted)
    redacted = re.sub(r"(?<![\w.-])/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+", "<path:redacted>", redacted)
    return redacted[:512]
