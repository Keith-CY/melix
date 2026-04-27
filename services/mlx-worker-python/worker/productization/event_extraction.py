from __future__ import annotations

import json
from dataclasses import dataclass
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


FIELD_NAMES = ("actor", "time", "location", "action")
FIELD_WEIGHTS = {
    "actor": 0.30,
    "time": 0.25,
    "location": 0.10,
    "action": 0.35,
}

EVENT_EXTRACTION_SYSTEM_PROMPT = """Extract established events and future plans from a dialogue.

Return only one JSON object. Do not wrap it in markdown.

Required shape:
{"events":[{"actor":null|["..."],"time":null|["..."],"location":null|["..."],"action":null|["..."]}]}

Rules:
- Extract only events or plans stated in the dialogue.
- Split each event into actor, time, location, and action arrays.
- Use null when a field is absent.
- Keep original wording as much as possible.
- Do not include digest; Melix derives it locally.
"""


@dataclass(frozen=True)
class RemoteEventExtractionTarget:
    provider_kind: str
    base_url: str
    api_key: str
    model_id: str
    timeout_seconds: int = 60


def make_event_extraction_client(target: RemoteEventExtractionTarget):
    provider_kind = target.provider_kind.strip()
    if provider_kind == "openai-compatible":
        return OpenAICompatibleEventExtractionClient(target)
    if provider_kind == "gemini-generative-language":
        return GeminiGenerativeLanguageEventExtractionClient(target)
    raise ValueError(f"unsupported remote provider kind: {provider_kind}")


class OpenAICompatibleEventExtractionClient:
    def __init__(self, target: RemoteEventExtractionTarget) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "openai-compatible":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target

    def extract_events(self, dialogue: list[str]) -> tuple[list[dict[str, object]], str]:
        payload = {
            "model": self._target.model_id,
            "messages": [
                {"role": "system", "content": EVENT_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(dialogue)},
            ],
            "stream": False,
            "temperature": 0,
        }
        response = self._post_json(payload)
        content = _assistant_content(response)
        return extract_events_from_response_text(content), content

    def _post_json(self, payload: dict[str, object]) -> dict[str, object]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("remote provider base_url is empty")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._target.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OpenAI/Python 1.0.0 Melix/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._target.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"remote provider HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise ValueError(f"remote provider request failed: {exc.reason}") from exc

        parsed = json.loads(response_body)
        if not isinstance(parsed, dict):
            raise ValueError("remote provider response must be a JSON object")
        return parsed


class GeminiGenerativeLanguageEventExtractionClient:
    def __init__(self, target: RemoteEventExtractionTarget) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "gemini-generative-language":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target

    def extract_events(self, dialogue: list[str]) -> tuple[list[dict[str, object]], str]:
        payload = {
            "systemInstruction": {
                "parts": [{"text": EVENT_EXTRACTION_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "\n".join(dialogue)}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
            },
        }
        response = self._post_json(payload)
        content = _gemini_content(response)
        return extract_events_from_response_text(content), content

    def _post_json(self, payload: dict[str, object]) -> dict[str, object]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("remote provider base_url is empty")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        model_path = _gemini_model_path(self._target.model_id)
        request = Request(
            f"{base_url}/{model_path}:generateContent?key={quote(self._target.api_key, safe='')}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OpenAI/Python 1.0.0 Melix/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._target.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"remote provider HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise ValueError(f"remote provider request failed: {exc.reason}") from exc

        parsed = json.loads(response_body)
        if not isinstance(parsed, dict):
            raise ValueError("remote provider response must be a JSON object")
        return parsed


def extract_events_from_response_text(response_text: str) -> list[dict[str, object]]:
    payload = _parse_response_json(response_text)
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        raise ValueError("LLM response must include an events array")
    parsed_events: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each event must be a JSON object")
        parsed_events.append(event)
    return parsed_events


def normalize_event_fields(payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")

    normalized = {
        field_name: _normalize_optional_string_list(payload.get(field_name), field_name)
        for field_name in FIELD_NAMES
    }
    if not any(normalized.values()):
        raise ValueError("extracted event must contain at least one non-empty field")
    normalized["digest"] = build_event_digest(
        actor=normalized["actor"],
        time=normalized["time"],
        location=normalized["location"],
        action=normalized["action"],
    )
    return normalized


def build_event_digest(
    *,
    actor: list[str] | None,
    time: list[str] | None,
    location: list[str] | None,
    action: list[str] | None,
) -> str:
    parts: list[str] = []
    if actor:
        parts.append("和".join(actor))
    for field_values in (time, location, action):
        if field_values:
            parts.append(",".join(field_values))
    return "".join(parts)


def write_event_prediction_rows(
    *,
    rows: Iterable[dict[str, object]],
    output_path: Path,
    failure_path: Path,
) -> dict[str, int]:
    output_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    events_written = 0

    for line_number, row in enumerate(rows, start=1):
        dialogue_id = str(row.get("dialogue_id") or "")
        raw_events = row.get("events")
        events: list[dict[str, object]] = []
        if isinstance(raw_events, list):
            for event_index, raw_event in enumerate(raw_events):
                try:
                    if not isinstance(raw_event, dict):
                        raise ValueError("extracted event must be a JSON object")
                    event = normalize_event_fields(raw_event)
                except Exception as exc:
                    failures.append(
                        {
                            "dialogue_id": dialogue_id,
                            "line_number": line_number,
                            "event_index": event_index,
                            "reason": str(exc),
                        }
                    )
                    continue
                events.append(event)
                events_written += 1

        output_rows.append(
            {
                "dialogue_id": dialogue_id,
                "dialogue": _normalize_dialogue_lines(row.get("dialogue")),
                "events": events,
            }
        )

    _write_jsonl(output_path, output_rows)
    _write_jsonl(failure_path, failures)
    return {
        "dialogues_written": len(output_rows),
        "events_written": events_written,
        "events_failed": len(failures),
    }


def evaluate_event_extraction(
    *,
    gold_jsonl: Path,
    pred_jsonl: Path,
    summary_output: Path,
    details_output: Path,
) -> dict[str, object]:
    gold_dialogues = _read_dialogue_jsonl(gold_jsonl)
    pred_dialogues = _read_dialogue_jsonl(pred_jsonl)

    details: list[dict[str, object]] = []
    field_totals = {field_name: {"tp": 0, "fp": 0, "fn": 0} for field_name in FIELD_NAMES}
    matched_event_scores: list[float] = []
    matched_events = 0
    unmatched_gold = 0
    unmatched_pred = 0

    for dialogue_id in sorted(set(gold_dialogues) | set(pred_dialogues)):
        gold_events = gold_dialogues.get(dialogue_id, [])
        pred_events = pred_dialogues.get(dialogue_id, [])
        max_events = max(len(gold_events), len(pred_events))
        for event_index in range(max_events):
            gold_event = gold_events[event_index] if event_index < len(gold_events) else None
            pred_event = pred_events[event_index] if event_index < len(pred_events) else None

            if gold_event is None:
                unmatched_pred += 1
                field_details = _build_unmatched_fields(gold_event, pred_event)
                _add_field_scores(field_totals, field_details)
                details.append(
                    {
                        "dialogue_id": dialogue_id,
                        "event_index": event_index,
                        "match_status": "unmatched_pred",
                        "weighted_f1": 0.0,
                        "active_weight": 0.0,
                        "fields": field_details,
                    }
                )
                continue

            if pred_event is None:
                unmatched_gold += 1
                field_details = _build_unmatched_fields(gold_event, pred_event)
                _add_field_scores(field_totals, field_details)
                details.append(
                    {
                        "dialogue_id": dialogue_id,
                        "event_index": event_index,
                        "match_status": "unmatched_gold",
                        "weighted_f1": 0.0,
                        "active_weight": 0.0,
                        "fields": field_details,
                    }
                )
                continue

            matched_events += 1
            field_details: dict[str, dict[str, object]] = {}
            weighted_score_total = 0.0
            active_weight = 0.0
            for field_name in FIELD_NAMES:
                field_score = _score_field(
                    _normalize_event_field(gold_event.get(field_name)),
                    _normalize_event_field(pred_event.get(field_name)),
                )
                field_details[field_name] = field_score
                if field_score["gold"] or field_score["pred"]:
                    weight = FIELD_WEIGHTS[field_name]
                    active_weight += weight
                    weighted_score_total += weight * float(field_score["f1"])
            _add_field_scores(field_totals, field_details)

            weighted_f1 = _round_metric(weighted_score_total / active_weight) if active_weight else 0.0
            matched_event_scores.append(weighted_f1)
            details.append(
                {
                    "dialogue_id": dialogue_id,
                    "event_index": event_index,
                    "match_status": "matched",
                    "weighted_f1": weighted_f1,
                    "active_weight": _round_metric(active_weight),
                    "fields": field_details,
                }
            )

    events_evaluated = matched_events + unmatched_gold + unmatched_pred
    summary = _build_summary(
        field_totals=field_totals,
        matched_event_scores=matched_event_scores,
        events_evaluated=events_evaluated,
        matched_events=matched_events,
        unmatched_gold=unmatched_gold,
        unmatched_pred=unmatched_pred,
    )
    _write_json(summary_output, summary)
    _write_jsonl(details_output, details)
    return summary


def _normalize_optional_string_list(value: object, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be null or an array of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must be null or an array of strings")
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)
    return normalized or None


def _normalize_event_field(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("event field values must be null or a list of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("event field values must be null or a list of strings")
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def _score_field(gold_values: list[str], pred_values: list[str]) -> dict[str, object]:
    gold_set = set(gold_values)
    pred_set = set(pred_values)
    tp = len(gold_set & pred_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)
    return {
        "gold": gold_values,
        "pred": pred_values,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _round_metric(_safe_divide(tp, tp + fp)),
        "recall": _round_metric(_safe_divide(tp, tp + fn)),
        "f1": _round_metric(_safe_divide(2 * tp, 2 * tp + fp + fn)),
    }


def _build_summary(
    *,
    field_totals: dict[str, dict[str, int]],
    matched_event_scores: Sequence[float],
    events_evaluated: int,
    matched_events: int,
    unmatched_gold: int,
    unmatched_pred: int,
) -> dict[str, object]:
    field_metrics: dict[str, dict[str, object]] = {}
    hallucination_rates: dict[str, float] = {}
    missing_rates: dict[str, float] = {}

    for field_name in FIELD_NAMES:
        totals = field_totals[field_name]
        tp = totals["tp"]
        fp = totals["fp"]
        fn = totals["fn"]
        field_metrics[field_name] = {
            "weight": FIELD_WEIGHTS[field_name],
            "precision": _round_metric(_safe_divide(tp, tp + fp)),
            "recall": _round_metric(_safe_divide(tp, tp + fn)),
            "f1": _round_metric(_safe_divide(2 * tp, 2 * tp + fp + fn)),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
        hallucination_rates[field_name] = _round_metric(_safe_divide(fp, tp + fp))
        missing_rates[field_name] = _round_metric(_safe_divide(fn, tp + fn))

    event_summary = {
        "overall_weighted_f1": _round_metric(
            _safe_divide(sum(matched_event_scores), events_evaluated)
        ),
        "events_evaluated": events_evaluated,
        "events_matched": matched_events,
        "events_unmatched_gold": unmatched_gold,
        "events_unmatched_pred": unmatched_pred,
    }
    return {
        **event_summary,
        "summary": event_summary,
        "field_metrics": field_metrics,
        "rates": {
            "hallucination_rate_by_field": hallucination_rates,
            "missing_rate_by_field": missing_rates,
        },
        "weights": dict(FIELD_WEIGHTS),
    }


def _read_dialogue_jsonl(path: Path) -> dict[str, list[dict[str, object]]]:
    dialogues: dict[str, list[dict[str, object]]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            dialogue_id = row.get("dialogue_id")
            if not isinstance(dialogue_id, str) or not dialogue_id:
                raise ValueError(f"missing dialogue_id at {path}:{line_number}")
            events = row.get("events")
            if not isinstance(events, list):
                raise ValueError(f"events must be a list at {path}:{line_number}")
            dialogues[dialogue_id] = [event for event in events if isinstance(event, dict)]
    return dialogues


def _build_unmatched_fields(
    gold_event: dict[str, object] | None,
    pred_event: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    return {
        field_name: _score_field(
            _normalize_event_field(gold_event.get(field_name)) if gold_event is not None else [],
            _normalize_event_field(pred_event.get(field_name)) if pred_event is not None else [],
        )
        for field_name in FIELD_NAMES
    }


def _add_field_scores(
    field_totals: dict[str, dict[str, int]],
    field_details: dict[str, dict[str, object]],
) -> None:
    for field_name in FIELD_NAMES:
        field_score = field_details[field_name]
        field_totals[field_name]["tp"] += int(field_score["tp"])
        field_totals[field_name]["fp"] += int(field_score["fp"])
        field_totals[field_name]["fn"] += int(field_score["fn"])


def _normalize_dialogue_lines(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _assistant_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("remote provider response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("remote provider choice must be a JSON object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("remote provider choice did not include a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("remote provider message content must be a string")
    return content


def _gemini_content(response: dict[str, object]) -> str:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("remote provider response did not include candidates")
    first = candidates[0]
    if not isinstance(first, dict):
        raise ValueError("remote provider candidate must be a JSON object")
    content = first.get("content")
    if not isinstance(content, dict):
        raise ValueError("remote provider candidate did not include content")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise ValueError("remote provider candidate content did not include parts")
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    if not text_parts:
        raise ValueError("remote provider candidate parts did not include text")
    return "".join(text_parts)


def _gemini_model_path(model_id: str) -> str:
    trimmed = model_id.strip()
    path = trimmed if trimmed.startswith("models/") else f"models/{trimmed}"
    return "/".join(quote(part, safe="") for part in path.split("/"))


def _parse_response_json(response_text: str) -> dict[str, object]:
    stripped = response_text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _round_metric(value: float) -> float:
    return round(value, 6)
