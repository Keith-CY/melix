from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


FIELD_NAMES = ("actor", "time", "location", "action")
FIELD_WEIGHTS = {
    "actor": 0.30,
    "time": 0.25,
    "location": 0.10,
    "action": 0.35,
}
EVENT_ALIGNMENT_STRATEGY = "optimal_soft_event_alignment"
EVENT_ALIGNMENT_SCORE_THRESHOLD = 0.30
EVENT_ALIGNMENT_ACTION_THRESHOLD = 0.20
_SIMILARITY_IGNORED_CHARS = set(
    " \t\r\n"
    "，。！？、；：,.!?;:"
    "（）()【】[]{}《》<>"
    "“”\"'`"
    "-_—"
)
EVENT_EXTRACTION_PROMPT_ID = "builtin.event-extraction.baseline"
EVENT_EXTRACTION_PROMPT_REVISION_ID = "baseline.v2"

EVENT_EXTRACTION_LEGACY_SYSTEM_PROMPT = """Extract established events and future plans from a dialogue.

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

EVENT_EXTRACTION_SYSTEM_PROMPT = """# Segment Metadata Candidates

Produce candidate metadata for one segment as a single JSON object that matches the stage-1 schema. This is a candidate-generation step; downstream normalization applies stricter filtering.

Input payload:
- `segment`: segment identifiers and segmentation metadata
- `participant_set`: optional dialogue-level participant roster
- `conversation`: ordered list of `{message_id, sender, participant_id?, timestamp, text}`

Extraction stance:
- Prioritize recall for concrete, already arranged or actionable events.
- Extract an event when dialogue-level evidence combines action + time/place/acceptance/condition, even if no single turn contains all parts.
- Preserve uncertainty in `detail` or `time`; do not discard only because time/place is relative or condition-dependent.
- Output no event only when the dialogue lacks a concrete action or lacks any commitment/schedule signal.
- Never invent missing facts; keep unsupported details out.

Return exactly one JSON object with this shape:

```json
{
  "boundary_decision": {
    "starts_new_dialogue": false,
    "new_dialogue_start_message_id": null,
    "boundary_confidence": 0.0,
    "boundary_reason": "no_restart"
  },
  "entity_mentions": [
    {
      "value": "string",
      "aliases": ["string"],
      "entity_kind": "person",
      "normalized": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "time_mentions": [
    {
      "value": "string",
      "normalized": "string or null",
      "aliases": ["string"],
      "entity_kind": "time",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "location_mentions": [
    {
      "value": "string",
      "aliases": ["string"],
      "entity_kind": "location",
      "normalized": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "topic_candidates": [
    {
      "value": "string",
      "aliases": ["string"],
      "entity_kind": "topic",
      "normalized": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "digest_candidates": [
    {
      "text": "string",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "event_candidates": [
    {
      "participants": ["string"],
      "time": ["string"],
      "location": ["string"],
      "action": "string",
      "status": "planned",
      "detail": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "issues": []
}
```

Hard requirements:
- `boundary_decision` must always be present as a single object.
- `boundary_reason` must be one of `restart_after_long_pause`, `explicit_reopening`, `topic_reset_with_reinit`, `context_discontinuity`, or `no_restart`; use `no_restart` with `new_dialogue_start_message_id:null` when no split is proposed.
- If `starts_new_dialogue=true`, `new_dialogue_start_message_id` must be a current `message_id` and `boundary_reason` must not be `no_restart`.
- Candidate fields and `aliases` must always be arrays.
- Every extracted item must include `confidence` and non-empty `evidence` from the input conversation.
- Keep the top-level shape unchanged and do not wrap the JSON in markdown fences.

Guidance:
- Use the smallest complete set of candidates supported by direct dialogue evidence.
- Prefer grounded real-world names. If the dialogue uses canonical slots such as `user1` / `user2`, keep a single slot-id system; when `participant_set` is present, treat it as the canonical slot-to-person mapping. Direct address inside a message often names the addressee, not the speaker.
- `time_mentions` should contain explicit or anchorable times only. Prefer a clean anchored span such as `周六晚上`; avoid weak markers such as `平时`, `最近`, or `有次`.
- `location_mentions` should be real places or venues; put projects, competitions, and themes into `topic_candidates`.
- `topic_candidates` should be abstract themes, not keyword piles, copied fragments, time-specific labels, or one-off events. Keep surface wording in `aliases`; prefer 1-2 broad topics such as `约饭安排`, `见面安排`, `旅行协调`, `产检讨论`, or `穿搭讨论`.
- Put concrete scheduled actions in `event_candidates`; keep topics abstract or omit them.
- `event_candidates` should describe concrete event instances only. A valid event needs a concrete action plus a commitment or schedule signal: agreement, fixed time, departure/return date, bought/reserved tickets, confirmed venue/activity, or confirmed meeting plan.
- Reject goals, vague proposals, habitual activities, current-conversation discussion acts, questions, and unconfirmed proposals. Reject weak future contact such as `有空再联系`, `以后再约`, `总有机会碰头`, or `想约一下` unless later turns clearly confirm it.
- Extract explicit time-anchored invitations such as `周五一起吃饭吧` as concrete lower-confidence events; the time plus action makes them actionable even before an acceptance.
- Extract ticket/date/slot evidence such as `我买的是周三的票`, `周二周日两场`, or `买好票就去`; treat these as strong event evidence and keep separate supported slots as separate events.
- Do not let ticket-seeking openings or third-party/public future appearance comments create extra events unless a dialogue participant clearly plans to attend/use them; still extract explicitly owned tickets/slots.
- Extract response-confirmed plans when proposal + time/availability/condition/acceptance makes the action actionable, such as `要看比赛不` + `星期三` + `买票我就去`, `求约` + `明天放假`, or `按早上说的地方见`; place/group-targeted meetup requests plus near-term availability can support a lower-confidence `见面` or `约见`.
- Preserve useful uncertainty in `detail`; do not drop events only because they depend on buying tickets, confirming a place, or another concrete action.
- Extract asserted visits/travel when action plus place/time are stated, such as `我姐姐来澳门玩`, `后天晚上就走`, `23号就走`, or `9月16号走`.
- Do not merge distinct supported event slots unless one event explicitly spans multiple times.
- Do not extract bare travel desire (`我想回去`) or modal travel (`可能过完年回去`) unless another turn fixes the plan.
- Use `hypothetical` only when the hypothetical event itself is important and clearly grounded; otherwise omit it. Apply the same conservative standard to `event_candidates.time` that you use for `time_mentions`.
- `digest_candidates` should summarize purpose or outcome in one concise sentence, not replay every field or turn.
- `event_candidates.detail` is optional and must not replace structured fields or invent unsupported specifics.
- Use the dominant language of the input dialogue for natural-language or free-text fields. If genuinely mixed-language, preserve that. Keep schema/control fields in schema-compliant English tokens.
"""


@dataclass(frozen=True)
class EventExtractionPromptSpec:
    prompt_id: str
    revision_id: str
    system_prompt: str
    content_hash: str
    title: str = "Built-in Segment Metadata Candidates"
    examples: tuple[dict[str, object], ...] = ()


def default_event_extraction_prompt_spec() -> EventExtractionPromptSpec:
    return EventExtractionPromptSpec(
        prompt_id=EVENT_EXTRACTION_PROMPT_ID,
        revision_id=EVENT_EXTRACTION_PROMPT_REVISION_ID,
        system_prompt=EVENT_EXTRACTION_SYSTEM_PROMPT,
        content_hash=event_prompt_content_hash(EVENT_EXTRACTION_SYSTEM_PROMPT, []),
    )


def event_prompt_content_hash(system_prompt: str, examples: Sequence[dict[str, object]]) -> str:
    payload = {
        "examples": list(examples),
        "scoring_mode": "event_extraction_weighted_f1",
        "system_prompt": system_prompt,
        "task_kind": "event_extraction",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True)
class RemoteEventExtractionTarget:
    provider_kind: str
    base_url: str
    api_key: str
    model_id: str
    timeout_seconds: int = 60


@dataclass(frozen=True)
class EventExtractionClientResult:
    events: list[dict[str, object]]
    raw_response: str
    request_body_bytes: int = 0
    response_body_bytes: int = 0
    provider_usage: dict[str, int] = field(default_factory=dict)

    def __iter__(self):
        yield self.events
        yield self.raw_response

    @property
    def raw_response_chars(self) -> int:
        return len(self.raw_response)


class RemoteProviderHTTPError(ValueError):
    def __init__(self, *, status_code: int, response_body: str) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"remote provider HTTP {status_code}: {response_body}")

    @property
    def code(self) -> str:
        if self.status_code == 429:
            return "remote_provider_rate_limited"
        if self.status_code in {401, 403}:
            return "remote_provider_auth_failed"
        if self.status_code == 404:
            return "remote_provider_not_found"
        if self.status_code >= 500:
            return "remote_provider_unavailable"
        return "remote_provider_http_error"


class RemoteProviderRequestError(ValueError):
    def __init__(self, *, reason: object) -> None:
        self.reason = str(reason)
        super().__init__(f"remote provider request failed: {self.reason}")

    @property
    def code(self) -> str:
        return "remote_provider_request_failed"


def make_event_extraction_client(
    target: RemoteEventExtractionTarget,
    prompt_spec: EventExtractionPromptSpec | None = None,
):
    resolved_prompt = prompt_spec or default_event_extraction_prompt_spec()
    provider_kind = target.provider_kind.strip()
    if provider_kind == "openai-compatible":
        return OpenAICompatibleEventExtractionClient(target, resolved_prompt)
    if provider_kind == "gemini-generative-language":
        return GeminiGenerativeLanguageEventExtractionClient(target, resolved_prompt)
    raise ValueError(f"unsupported remote provider kind: {provider_kind}")


class OpenAICompatibleEventExtractionClient:
    def __init__(
        self,
        target: RemoteEventExtractionTarget,
        prompt_spec: EventExtractionPromptSpec | None = None,
    ) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "openai-compatible":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target
        self._prompt = prompt_spec or default_event_extraction_prompt_spec()

    def extract_events(
        self,
        dialogue: list[str],
        dialogue_id: str = "",
    ) -> EventExtractionClientResult:
        messages = [{"role": "system", "content": self._prompt.system_prompt}]
        use_stage1_schema = _prompt_uses_stage1_schema(self._prompt)
        messages.extend(_openai_example_messages(self._prompt.examples, use_stage1_schema))
        messages.append({"role": "user", "content": _dialogue_user_content(dialogue, dialogue_id, use_stage1_schema)})
        payload = {
            "model": self._target.model_id,
            "messages": messages,
            "stream": False,
            "temperature": 0,
        }
        response, request_body_bytes, response_body_bytes = self._post_json(payload)
        content = _assistant_content(response)
        return EventExtractionClientResult(
            events=extract_events_from_response_text(content),
            raw_response=content,
            request_body_bytes=request_body_bytes,
            response_body_bytes=response_body_bytes,
            provider_usage=_openai_provider_usage(response),
        )

    def _post_json(self, payload: dict[str, object]) -> tuple[dict[str, object], int, int]:
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
                response_bytes = response.read()
                response_body = response_bytes.decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RemoteProviderHTTPError(status_code=exc.code, response_body=error_body) from exc
        except URLError as exc:
            raise RemoteProviderRequestError(reason=exc.reason) from exc

        parsed = json.loads(response_body)
        if not isinstance(parsed, dict):
            raise ValueError("remote provider response must be a JSON object")
        return parsed, len(body), len(response_bytes)


class GeminiGenerativeLanguageEventExtractionClient:
    def __init__(
        self,
        target: RemoteEventExtractionTarget,
        prompt_spec: EventExtractionPromptSpec | None = None,
    ) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "gemini-generative-language":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target
        self._prompt = prompt_spec or default_event_extraction_prompt_spec()

    def extract_events(
        self,
        dialogue: list[str],
        dialogue_id: str = "",
    ) -> EventExtractionClientResult:
        use_stage1_schema = _prompt_uses_stage1_schema(self._prompt)
        contents = _gemini_example_contents(self._prompt.examples, use_stage1_schema)
        contents.append(
            {
                "role": "user",
                "parts": [{"text": _dialogue_user_content(dialogue, dialogue_id, use_stage1_schema)}],
            }
        )
        payload = {
            "systemInstruction": {
                "parts": [{"text": self._prompt.system_prompt}],
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0,
            },
        }
        response, request_body_bytes, response_body_bytes = self._post_json(payload)
        content = _gemini_content(response)
        return EventExtractionClientResult(
            events=extract_events_from_response_text(content),
            raw_response=content,
            request_body_bytes=request_body_bytes,
            response_body_bytes=response_body_bytes,
            provider_usage=_gemini_provider_usage(response),
        )

    def _post_json(self, payload: dict[str, object]) -> tuple[dict[str, object], int, int]:
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
                response_bytes = response.read()
                response_body = response_bytes.decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RemoteProviderHTTPError(status_code=exc.code, response_body=error_body) from exc
        except URLError as exc:
            raise RemoteProviderRequestError(reason=exc.reason) from exc

        parsed = json.loads(response_body)
        if not isinstance(parsed, dict):
            raise ValueError("remote provider response must be a JSON object")
        return parsed, len(body), len(response_bytes)


def extract_events_from_response_text(response_text: str) -> list[dict[str, object]]:
    payload = _parse_response_json(response_text)
    events = payload.get("events") if isinstance(payload, dict) else None
    if isinstance(events, list):
        parsed_events: list[dict[str, object]] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("each event must be a JSON object")
            parsed_events.append(event)
        return parsed_events

    event_candidates = payload.get("event_candidates")
    if not isinstance(event_candidates, list):
        raise ValueError("LLM response must include an events or event_candidates array")
    parsed_candidates: list[dict[str, object]] = []
    for candidate in event_candidates:
        if not isinstance(candidate, dict):
            raise ValueError("each event candidate must be a JSON object")
        parsed_candidates.append(_event_from_candidate(candidate))
    return parsed_candidates


def prompt_snapshot_payload(prompt_spec: EventExtractionPromptSpec) -> dict[str, object]:
    return {
        "prompt_id": prompt_spec.prompt_id,
        "prompt_revision_id": prompt_spec.revision_id,
        "prompt_content_hash": prompt_spec.content_hash,
        "title": prompt_spec.title,
        "task_kind": "event_extraction",
        "scoring_mode": "event_extraction_weighted_f1",
        "system_prompt": prompt_spec.system_prompt,
        "examples": list(prompt_spec.examples),
        "prompt_example_dialogue_ids": prompt_example_dialogue_ids(prompt_spec),
    }


def prompt_example_dialogue_ids(prompt_spec: EventExtractionPromptSpec) -> list[str]:
    ids: list[str] = []
    for example in prompt_spec.examples:
        dialogue_id = str(example.get("dialogue_id") or "").strip()
        if dialogue_id:
            ids.append(dialogue_id)
    return ids


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
    row_audit_output: Path | None = None,
) -> dict[str, object]:
    gold_dialogues = _read_dialogue_jsonl(gold_jsonl)
    pred_dialogues = _read_dialogue_jsonl(pred_jsonl)

    details: list[dict[str, object]] = []
    row_audits: list[dict[str, object]] = []
    field_totals = {field_name: {"tp": 0, "fp": 0, "fn": 0} for field_name in FIELD_NAMES}
    matched_event_scores: list[float] = []
    matched_events = 0
    unmatched_gold = 0
    unmatched_pred = 0
    alignment_scores: list[float] = []

    for dialogue_id in sorted(set(gold_dialogues) | set(pred_dialogues)):
        gold_events = gold_dialogues.get(dialogue_id, [])
        pred_events = pred_dialogues.get(dialogue_id, [])
        alignment = _align_dialogue_events(gold_events, pred_events)
        matched_by_gold = {gold_index: pred_index for gold_index, pred_index, _score in alignment["matches"]}
        matched_pred_indices = {pred_index for _gold_index, pred_index, _score in alignment["matches"]}
        alignment_by_pair = {
            (gold_index, pred_index): _event_alignment(gold_events[gold_index], pred_events[pred_index])
            for gold_index, pred_index, _score in alignment["matches"]
        }
        row_audits.append(
            _build_row_alignment_audit(
                dialogue_id=dialogue_id,
                gold_events=gold_events,
                pred_events=pred_events,
                alignment=alignment,
            )
        )

        for gold_index, gold_event in enumerate(gold_events):
            pred_index = matched_by_gold.get(gold_index)
            if pred_index is None:
                unmatched_gold += 1
                field_details = _build_unmatched_fields(gold_event, None)
                _add_field_scores(field_totals, field_details)
                details.append(
                    {
                        "dialogue_id": dialogue_id,
                        "event_index": gold_index,
                        "gold_event_index": gold_index,
                        "pred_event_index": None,
                        "match_status": "unmatched_gold",
                        "weighted_f1": 0.0,
                        "active_weight": 0.0,
                        "alignment_score": 0.0,
                        "alignment_fields": {},
                        "fields": field_details,
                    }
                )
                continue
            pred_event = pred_events[pred_index]
            pair_alignment = alignment_by_pair[(gold_index, pred_index)]
            matched_events += 1
            alignment_scores.append(float(pair_alignment["score"]))
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
                    "event_index": gold_index,
                    "gold_event_index": gold_index,
                    "pred_event_index": pred_index,
                    "match_status": "matched",
                    "weighted_f1": weighted_f1,
                    "active_weight": _round_metric(active_weight),
                    "alignment_score": _round_metric(float(pair_alignment["score"])),
                    "alignment_fields": pair_alignment["fields"],
                    "fields": field_details,
                }
            )

        for pred_index, pred_event in enumerate(pred_events):
            if pred_index in matched_pred_indices:
                continue
            unmatched_pred += 1
            field_details = _build_unmatched_fields(None, pred_event)
            _add_field_scores(field_totals, field_details)
            details.append(
                {
                    "dialogue_id": dialogue_id,
                    "event_index": pred_index,
                    "gold_event_index": None,
                    "pred_event_index": pred_index,
                    "match_status": "unmatched_pred",
                    "weighted_f1": 0.0,
                    "active_weight": 0.0,
                    "alignment_score": 0.0,
                    "alignment_fields": {},
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
        alignment_scores=alignment_scores,
    )
    _write_json(summary_output, summary)
    _write_jsonl(details_output, details)
    if row_audit_output is not None:
        _write_jsonl(row_audit_output, row_audits)
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


def _align_dialogue_events(
    gold_events: list[dict[str, object]],
    pred_events: list[dict[str, object]],
) -> dict[str, object]:
    scores: list[list[float]] = []
    accepted: list[list[bool]] = []
    candidate_scores: list[dict[str, object]] = []
    for gold_index, gold_event in enumerate(gold_events):
        score_row: list[float] = []
        accepted_row: list[bool] = []
        for pred_index, pred_event in enumerate(pred_events):
            alignment = _event_alignment(gold_event, pred_event)
            score = float(alignment["score"])
            is_accepted = bool(alignment["accepted"])
            score_row.append(score)
            accepted_row.append(is_accepted)
            candidate_scores.append(
                {
                    "gold_event_index": gold_index,
                    "pred_event_index": pred_index,
                    "alignment_score": _round_metric(score),
                    "accepted": is_accepted,
                }
            )
        scores.append(score_row)
        accepted.append(accepted_row)

    matches = _maximum_weight_event_matching(scores, accepted)
    return {
        "matches": matches,
        "candidate_scores": candidate_scores,
    }


def _event_alignment(gold_event: dict[str, object], pred_event: dict[str, object]) -> dict[str, object]:
    field_scores: dict[str, float] = {}
    active_weight = 0.0
    weighted_score = 0.0
    for field_name in FIELD_NAMES:
        gold_values = _normalize_event_field(gold_event.get(field_name))
        pred_values = _normalize_event_field(pred_event.get(field_name))
        field_score = _soft_field_f1(gold_values, pred_values)
        field_scores[field_name] = _round_metric(field_score)
        if gold_values or pred_values:
            weight = FIELD_WEIGHTS[field_name]
            active_weight += weight
            weighted_score += weight * field_score
    score = weighted_score / active_weight if active_weight else 0.0
    gold_actions = _normalize_event_field(gold_event.get("action"))
    pred_actions = _normalize_event_field(pred_event.get("action"))
    action_score = field_scores["action"]
    accepted = score >= EVENT_ALIGNMENT_SCORE_THRESHOLD
    if gold_actions and pred_actions and action_score < EVENT_ALIGNMENT_ACTION_THRESHOLD:
        accepted = False
    return {
        "score": _round_metric(score),
        "accepted": accepted,
        "fields": field_scores,
    }


def _soft_field_f1(gold_values: list[str], pred_values: list[str]) -> float:
    if not gold_values and not pred_values:
        return 0.0
    if not gold_values or not pred_values:
        return 0.0
    scores: list[list[float]] = [
        [_string_similarity(gold_value, pred_value) for pred_value in pred_values]
        for gold_value in gold_values
    ]
    accepted = [[score > 0.0 for score in row] for row in scores]
    matches = _maximum_weight_event_matching(scores, accepted)
    soft_tp = sum(score for _gold_index, _pred_index, score in matches)
    return _safe_divide(2.0 * soft_tp, len(gold_values) + len(pred_values))


def _string_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_similarity_text(left)
    normalized_right = _normalize_similarity_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    containment_score = 0.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        containment_score = 1.0
    return max(containment_score, _bigram_dice(normalized_left, normalized_right))


def _normalize_similarity_text(value: str) -> str:
    return "".join(char for char in value.strip().lower() if char not in _SIMILARITY_IGNORED_CHARS)


def _bigram_dice(left: str, right: str) -> float:
    left_units = _character_bigrams(left)
    right_units = _character_bigrams(right)
    if not left_units or not right_units:
        return 0.0
    overlap = 0
    remaining = dict(right_units)
    for unit, count in left_units.items():
        matched = min(count, remaining.get(unit, 0))
        overlap += matched
        if matched:
            remaining[unit] = remaining.get(unit, 0) - matched
    return _safe_divide(2.0 * overlap, sum(left_units.values()) + sum(right_units.values()))


def _character_bigrams(value: str) -> dict[str, int]:
    if len(value) <= 1:
        return {value: 1} if value else {}
    counts: dict[str, int] = {}
    for index in range(len(value) - 1):
        unit = value[index : index + 2]
        counts[unit] = counts.get(unit, 0) + 1
    return counts


def _maximum_weight_event_matching(
    scores: list[list[float]],
    accepted: list[list[bool]],
) -> list[tuple[int, int, float]]:
    gold_count = len(scores)
    pred_count = max((len(row) for row in scores), default=0)
    memo: dict[tuple[int, int], tuple[float, tuple[tuple[int, int, float], ...]]] = {}

    def better(
        candidate: tuple[float, tuple[tuple[int, int, float], ...]],
        current: tuple[float, tuple[tuple[int, int, float], ...]],
    ) -> bool:
        if candidate[0] > current[0] + 1e-12:
            return True
        if abs(candidate[0] - current[0]) <= 1e-12:
            return candidate[1] < current[1]
        return False

    def solve(gold_index: int, used_pred_mask: int) -> tuple[float, tuple[tuple[int, int, float], ...]]:
        key = (gold_index, used_pred_mask)
        if key in memo:
            return memo[key]
        if gold_index >= gold_count:
            return (0.0, ())

        best = solve(gold_index + 1, used_pred_mask)
        for pred_index in range(pred_count):
            if used_pred_mask & (1 << pred_index):
                continue
            if pred_index >= len(scores[gold_index]) or not accepted[gold_index][pred_index]:
                continue
            next_score, next_pairs = solve(gold_index + 1, used_pred_mask | (1 << pred_index))
            score = float(scores[gold_index][pred_index])
            pair = (gold_index, pred_index, _round_metric(score))
            candidate = (score + next_score, (pair,) + next_pairs)
            if better(candidate, best):
                best = candidate
        memo[key] = best
        return best

    return list(solve(0, 0)[1])


def _build_row_alignment_audit(
    *,
    dialogue_id: str,
    gold_events: list[dict[str, object]],
    pred_events: list[dict[str, object]],
    alignment: dict[str, object],
) -> dict[str, object]:
    matches = alignment["matches"] if isinstance(alignment.get("matches"), list) else []
    matched_gold = {gold_index for gold_index, _pred_index, _score in matches}
    matched_pred = {pred_index for _gold_index, pred_index, _score in matches}
    return {
        "dialogue_id": dialogue_id,
        "alignment_strategy": EVENT_ALIGNMENT_STRATEGY,
        "gold_event_count": len(gold_events),
        "pred_event_count": len(pred_events),
        "matched_pairs": [
            {
                "gold_event_index": gold_index,
                "pred_event_index": pred_index,
                "alignment_score": _round_metric(score),
            }
            for gold_index, pred_index, score in matches
        ],
        "unmatched_gold_indices": [
            gold_index for gold_index in range(len(gold_events)) if gold_index not in matched_gold
        ],
        "unmatched_pred_indices": [
            pred_index for pred_index in range(len(pred_events)) if pred_index not in matched_pred
        ],
        "candidate_scores": alignment.get("candidate_scores", []),
    }


def _build_summary(
    *,
    field_totals: dict[str, dict[str, int]],
    matched_event_scores: Sequence[float],
    events_evaluated: int,
    matched_events: int,
    unmatched_gold: int,
    unmatched_pred: int,
    alignment_scores: Sequence[float],
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
    alignment_summary = {
        "matched_pairs": matched_events,
        "unmatched_gold": unmatched_gold,
        "unmatched_pred": unmatched_pred,
        "mean_alignment_score": _round_metric(_safe_divide(sum(alignment_scores), len(alignment_scores))),
        "min_alignment_score": _round_metric(min(alignment_scores)) if alignment_scores else 0.0,
        "alignment_score_threshold": EVENT_ALIGNMENT_SCORE_THRESHOLD,
        "action_score_threshold": EVENT_ALIGNMENT_ACTION_THRESHOLD,
    }
    return {
        **event_summary,
        "alignment_strategy": EVENT_ALIGNMENT_STRATEGY,
        "summary": event_summary,
        "event_alignment": alignment_summary,
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


def _openai_provider_usage(response: dict[str, object]) -> dict[str, int]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}
    return _provider_usage_from_keys(
        usage,
        (
            ("prompt_tokens", "prompt_tokens"),
            ("completion_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
        ),
    )


def _gemini_provider_usage(response: dict[str, object]) -> dict[str, int]:
    usage = response.get("usageMetadata")
    if not isinstance(usage, dict):
        return {}
    return _provider_usage_from_keys(
        usage,
        (
            ("promptTokenCount", "prompt_tokens"),
            ("candidatesTokenCount", "completion_tokens"),
            ("totalTokenCount", "total_tokens"),
        ),
    )


def _provider_usage_from_keys(usage: dict[object, object], key_map: Sequence[tuple[str, str]]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for source_key, target_key in key_map:
        value = usage.get(source_key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            normalized[target_key] = value
        elif isinstance(value, float) and value.is_integer():
            normalized[target_key] = int(value)
    return normalized


def _gemini_model_path(model_id: str) -> str:
    trimmed = model_id.strip()
    path = trimmed if trimmed.startswith("models/") else f"models/{trimmed}"
    return "/".join(quote(part, safe="") for part in path.split("/"))


def _openai_example_messages(
    examples: Sequence[dict[str, object]],
    use_stage1_schema: bool = False,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for example in examples:
        messages.append({"role": "user", "content": _example_dialogue_text(example, use_stage1_schema)})
        messages.append({"role": "assistant", "content": _example_response_text(example, use_stage1_schema)})
    return messages


def _gemini_example_contents(
    examples: Sequence[dict[str, object]],
    use_stage1_schema: bool = False,
) -> list[dict[str, object]]:
    contents: list[dict[str, object]] = []
    for example in examples:
        contents.append(
            {
                "role": "user",
                "parts": [{"text": _example_dialogue_text(example, use_stage1_schema)}],
            }
        )
        contents.append(
            {
                "role": "model",
                "parts": [{"text": _example_response_text(example, use_stage1_schema)}],
            }
        )
    return contents


def _example_dialogue_text(example: dict[str, object], use_stage1_schema: bool = False) -> str:
    return _dialogue_user_content(
        _normalize_dialogue_lines(example.get("dialogue")),
        str(example.get("dialogue_id") or "").strip(),
        use_stage1_schema,
    )


def _example_response_text(example: dict[str, object], use_stage1_schema: bool = False) -> str:
    events = example.get("events")
    normalized_events: list[dict[str, object]] = []
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                normalized_events.append({field_name: event.get(field_name) for field_name in FIELD_NAMES})
    if use_stage1_schema:
        return json.dumps(
            _stage1_response_payload_from_events(normalized_events),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return json.dumps({"events": normalized_events}, ensure_ascii=False, separators=(",", ":"))


def _prompt_uses_stage1_schema(prompt_spec: EventExtractionPromptSpec) -> bool:
    prompt = prompt_spec.system_prompt
    return "event_candidates" in prompt and "conversation" in prompt and "stage-1" in prompt


def _dialogue_user_content(
    dialogue: Sequence[str],
    dialogue_id: str = "",
    use_stage1_schema: bool = False,
) -> str:
    if not use_stage1_schema:
        return "\n".join(_normalize_dialogue_lines(list(dialogue)))
    return json.dumps(
        _dialogue_segment_payload(dialogue, dialogue_id),
        ensure_ascii=False,
        indent=2,
    )


def _dialogue_segment_payload(dialogue: Sequence[str], dialogue_id: str = "") -> dict[str, object]:
    normalized_dialogue = _normalize_dialogue_lines(list(dialogue))
    conversation: list[dict[str, object]] = []
    participant_set: list[dict[str, str]] = []
    seen_participants: set[str] = set()

    for index, line in enumerate(normalized_dialogue, start=1):
        sender, text = _split_dialogue_line(line)
        participant_id = sender or f"speaker_{index}"
        if participant_id not in seen_participants:
            participant_set.append(
                {
                    "participant_id": participant_id,
                    "display_name": participant_id,
                }
            )
            seen_participants.add(participant_id)
        conversation.append(
            {
                "message_id": f"m{index}",
                "sender": sender or participant_id,
                "participant_id": participant_id,
                "timestamp": None,
                "text": text,
            }
        )

    segment_id = dialogue_id.strip() or "segment-1"
    return {
        "segment": {
            "segment_id": segment_id,
            "dialogue_id": dialogue_id.strip() or None,
            "message_count": len(conversation),
        },
        "participant_set": participant_set,
        "conversation": conversation,
    }


def _split_dialogue_line(line: str) -> tuple[str, str]:
    for delimiter in (":", "："):
        if delimiter in line:
            prefix, text = line.split(delimiter, 1)
            sender = prefix.strip()
            if sender:
                return sender, text.strip()
    return "", line.strip()


def _stage1_response_payload_from_events(events: Sequence[dict[str, object]]) -> dict[str, object]:
    event_candidates = []
    for event in events:
        event_candidates.append(
            {
                "participants": _coerce_string_list(event.get("actor")),
                "time": _coerce_string_list(event.get("time")),
                "location": _coerce_string_list(event.get("location")),
                "action": ", ".join(_coerce_string_list(event.get("action"))),
                "status": "planned",
                "detail": None,
                "confidence": 1.0,
                "evidence": ["m1"],
            }
        )
    return {
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
        "event_candidates": event_candidates,
        "issues": [],
    }


def _event_from_candidate(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "actor": _coerce_string_list(candidate.get("participants", candidate.get("actor"))),
        "time": _coerce_string_list(candidate.get("time")),
        "location": _coerce_string_list(candidate.get("location")),
        "action": _coerce_action(candidate.get("action")),
    }


def _coerce_action(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else None
    return _coerce_string_list(value)


def _coerce_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


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
