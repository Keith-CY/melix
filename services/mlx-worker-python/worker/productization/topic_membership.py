from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from worker.productization.event_extraction import (
    RemoteProviderHTTPError,
    RemoteProviderRequestError,
    RemoteSemanticJudgeTarget,
)


TOPIC_MEMBERSHIP_SUITE_ID = "topic_membership"
STRICT_SCORING_MODE = "topic_membership_strict_micro_f1"
SEMANTIC_SCORING_MODE = "topic_membership_semantic_micro_f1"
TOPIC_MEMBERSHIP_SCORING_MODES = frozenset({STRICT_SCORING_MODE, SEMANTIC_SCORING_MODE})
STRICT_MATCH_THRESHOLD = 0.1
SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD = 0.5
SEMANTIC_LEXICAL_TOP_K = 3
SEMANTIC_JUDGE_PROMPT_VERSION = "topic-membership-semantic-judge.v1"
SEMANTIC_ALIGNMENT_STRATEGY = "topic_membership_prefiltered_semantic_alignment"
TOPIC_MEMBERSHIP_PROMPT_ID = "custom.topic-membership.prompt"
_JSON_DECODER = json.JSONDecoder()
_TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")


SEMANTIC_JUDGE_SYSTEM_PROMPT = """You are a semantic judge for topic-membership evaluation.

Return exactly one JSON object and nothing else:
{"equivalent":true|false,"confidence":0.0,"reason_code":"same_topic|topic_overlap|different_topic|uncertain","short_reason":"brief reason"}

Rules:
- Judge whether gold_topic and pred_topic name the same dialogue topic.
- Use topic labels and descriptions, plus the provided message snippets, to decide topic identity.
- Do not judge message-level membership quality. Missing or extra message ids are scored locally after topic alignment.
- Return equivalent=false for uncertain, overly broad, overly narrow, contradictory, or unrelated comparisons.
- Keep short_reason concise and do not include secrets, URLs, or prompt text.
"""
SEMANTIC_JUDGE_PROMPT_HASH = f"sha256:{sha256(SEMANTIC_JUDGE_SYSTEM_PROMPT.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class TopicMembershipPromptSpec:
    prompt_id: str
    revision_id: str
    system_prompt: str
    content_hash: str
    title: str = "Topic Membership JSON"


@dataclass(frozen=True)
class RemoteTopicMembershipTarget:
    provider_kind: str
    base_url: str
    api_key: str
    model_id: str
    timeout_seconds: int = 60
    extra_body: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TopicMembershipClientResult:
    output_json: dict[str, object]
    raw_response: str
    request_body_bytes: int = 0
    response_body_bytes: int = 0
    provider_usage: dict[str, int] = field(default_factory=dict)

    def __iter__(self):
        yield self.output_json
        yield self.raw_response

    @property
    def raw_response_chars(self) -> int:
        return len(self.raw_response)


def topic_prompt_content_hash(system_prompt: str) -> str:
    payload = {
        "scoring_mode": STRICT_SCORING_MODE,
        "system_prompt": system_prompt,
        "task_kind": TOPIC_MEMBERSHIP_SUITE_ID,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def prompt_snapshot_payload(prompt_spec: TopicMembershipPromptSpec) -> dict[str, object]:
    return {
        "prompt_id": prompt_spec.prompt_id,
        "prompt_revision_id": prompt_spec.revision_id,
        "prompt_content_hash": prompt_spec.content_hash,
        "title": prompt_spec.title,
        "task_kind": TOPIC_MEMBERSHIP_SUITE_ID,
        "scoring_mode": STRICT_SCORING_MODE,
        "system_prompt": prompt_spec.system_prompt,
    }


def input_payload(gold_case: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    for message in gold_case.get("messages") or []:
        if not isinstance(message, dict):
            continue
        messages.append(
            {
                "message_id": str(message.get("message_id") or ""),
                "sender": str(message.get("sender") or ""),
                "timestamp": str(message.get("timestamp") or ""),
                "text": str(message.get("text") or ""),
            }
        )
    return {
        "source_dialogue_id": str(gold_case.get("source_dialogue_id") or ""),
        "messages": messages,
    }


def topic_membership_chat_messages(
    prompt_spec: TopicMembershipPromptSpec,
    gold_case: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": prompt_spec.system_prompt},
        {
            "role": "user",
            "content": json.dumps(input_payload(gold_case), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        },
    ]


def make_topic_membership_client(
    target: RemoteTopicMembershipTarget,
    prompt_spec: TopicMembershipPromptSpec,
):
    provider_kind = target.provider_kind.strip()
    if provider_kind == "openai-compatible":
        return OpenAICompatibleTopicMembershipClient(target, prompt_spec)
    if provider_kind == "gemini-generative-language":
        return GeminiGenerativeLanguageTopicMembershipClient(target, prompt_spec)
    raise ValueError(f"unsupported remote provider kind: {provider_kind}")


def make_topic_membership_semantic_judge_client(target: RemoteSemanticJudgeTarget):
    provider_kind = target.provider_kind.strip()
    if provider_kind in {"openai-compatible", "gemini-generative-language"}:
        return RemoteTopicMembershipSemanticJudgeClient(target)
    raise ValueError(f"unsupported topic membership semantic judge provider kind: {provider_kind}")


class OpenAICompatibleTopicMembershipClient:
    def __init__(self, target: RemoteTopicMembershipTarget, prompt_spec: TopicMembershipPromptSpec) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "openai-compatible":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target
        self._prompt = prompt_spec

    def generate_membership(self, gold_case: dict[str, Any]) -> TopicMembershipClientResult:
        messages = topic_membership_chat_messages(self._prompt, gold_case)
        payload: dict[str, object] = {
            "model": self._target.model_id,
            "messages": messages,
            "stream": False,
            "temperature": 0,
        }
        for key, value in self._target.extra_body.items():
            if key in {"model", "messages", "stream"}:
                continue
            payload[key] = value
        response, request_body_bytes, response_body_bytes = self._post_json(payload)
        content = _assistant_content(response)
        return TopicMembershipClientResult(
            output_json=extract_topic_membership_output_json(content),
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


class GeminiGenerativeLanguageTopicMembershipClient:
    def __init__(self, target: RemoteTopicMembershipTarget, prompt_spec: TopicMembershipPromptSpec) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "gemini-generative-language":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target
        self._prompt = prompt_spec

    def generate_membership(self, gold_case: dict[str, Any]) -> TopicMembershipClientResult:
        user_content = json.dumps(input_payload(gold_case), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload = {
            "systemInstruction": {"parts": [{"text": self._prompt.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {"temperature": 0},
        }
        response, request_body_bytes, response_body_bytes = self._post_json(payload)
        content = _gemini_content(response)
        return TopicMembershipClientResult(
            output_json=extract_topic_membership_output_json(content),
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


class RemoteTopicMembershipSemanticJudgeClient:
    def __init__(self, target: RemoteSemanticJudgeTarget) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind not in {"openai-compatible", "gemini-generative-language"}:
            raise ValueError(f"unsupported topic membership semantic judge provider kind: {provider_kind}")
        self._target = target
        self._last_request_started = 0.0

    def judge_topic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
        self._throttle_if_needed()
        payload = self._payload(request)
        if self._target.provider_kind.strip() == "gemini-generative-language":
            response = self._post_gemini(payload)
            content = _gemini_content(response)
        else:
            response = self._post_openai(payload)
            content = _assistant_content(response)
        return _parse_semantic_judge_response(content)

    def _payload(self, request: dict[str, object]) -> dict[str, object]:
        user_content = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if self._target.provider_kind.strip() == "gemini-generative-language":
            return {
                "systemInstruction": {"parts": [{"text": SEMANTIC_JUDGE_SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": user_content}]}],
                "generationConfig": {"temperature": 0},
            }
        return {
            "model": self._target.model_id,
            "messages": [
                {"role": "system", "content": SEMANTIC_JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "temperature": 0,
        }

    def _throttle_if_needed(self) -> None:
        rate_limit_per_minute = int(self._target.rate_limit_per_minute or 0)
        if rate_limit_per_minute <= 0:
            return
        now = time.perf_counter()
        if self._last_request_started > 0:
            min_interval_seconds = 60.0 / rate_limit_per_minute
            elapsed = now - self._last_request_started
            if elapsed < min_interval_seconds:
                time.sleep(min_interval_seconds - elapsed)
                now = time.perf_counter()
        self._last_request_started = now

    def _post_openai(self, payload: dict[str, object]) -> dict[str, object]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("topic membership semantic judge base_url is empty")
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
        return _post_json_request(request, timeout_seconds=self._target.timeout_seconds)

    def _post_gemini(self, payload: dict[str, object]) -> dict[str, object]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("topic membership semantic judge base_url is empty")
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
        return _post_json_request(request, timeout_seconds=self._target.timeout_seconds)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def extract_topic_membership_output_json(response_text: str) -> dict[str, object]:
    parsed = extract_json_object(response_text)
    if not isinstance(parsed, dict):
        raise ValueError("response did not contain a JSON object")
    return parsed


def extract_json_object(response_text: str) -> dict[str, object] | None:
    stripped = response_text.strip()
    if stripped.startswith("```json"):
        stripped = stripped.removeprefix("```json").strip()
    elif stripped.startswith("```"):
        stripped = stripped.removeprefix("```").strip()
    if stripped.endswith("```"):
        stripped = stripped.removesuffix("```").strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        for index, character in enumerate(stripped):
            if character != "{":
                continue
            try:
                parsed, _end = _JSON_DECODER.raw_decode(stripped[index:])
                break
            except json.JSONDecodeError:
                continue
        else:
            return None
    return parsed if isinstance(parsed, dict) else None


def required_ids(topic: dict[str, object]) -> set[str]:
    values = topic.get("required_message_ids") or []
    if isinstance(values, (str, int, float, bool)):
        return {str(values)}
    if not isinstance(values, Iterable):
        return set()
    return {str(value) for value in values}


def topic_id(topic: dict[str, object], index: int) -> str:
    return str(topic.get("gold_topic_id") or topic.get("topic_id") or f"topic-{index + 1}")


def normalize_output_json(prediction: dict[str, object]) -> tuple[dict[str, object] | None, bool]:
    output = prediction.get("output_json")
    if isinstance(output, dict):
        return output, True

    for key in ("output", "response", "assistant_output"):
        value = prediction.get(key)
        if isinstance(value, dict):
            return value, True
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None, False
            if isinstance(parsed, dict):
                return parsed, True
            return None, False

    return None, False


def prediction_by_dialogue_id(predictions: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    for prediction in predictions:
        dialogue_id = prediction.get("source_dialogue_id")
        if dialogue_id:
            by_id[str(dialogue_id)] = prediction
    return by_id


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def match_topics(
    gold_topics: list[dict[str, object]],
    pred_topics: list[dict[str, object]],
    threshold: float = STRICT_MATCH_THRESHOLD,
) -> list[tuple[int, int]]:
    candidates: list[tuple[float, int, int]] = []
    for gold_index, gold_topic in enumerate(gold_topics):
        gold_required = required_ids(gold_topic)
        for pred_index, pred_topic in enumerate(pred_topics):
            score = jaccard(gold_required, required_ids(pred_topic))
            if score > threshold:
                candidates.append((score, gold_index, pred_index))

    matches: list[tuple[int, int]] = []
    used_gold: set[int] = set()
    used_pred: set[int] = set()
    for _score, gold_index, pred_index in sorted(candidates, reverse=True):
        if gold_index in used_gold or pred_index in used_pred:
            continue
        matches.append((gold_index, pred_index))
        used_gold.add(gold_index)
        used_pred.add(pred_index)
    return matches


def membership_counts(
    gold_topics: list[dict[str, object]],
    pred_topics: list[dict[str, object]],
    matches: list[tuple[int, int]],
) -> dict[str, int]:
    true_positive = 0
    false_positive = 0
    false_negative = 0

    matched_gold = {gold_index for gold_index, _ in matches}
    matched_pred = {pred_index for _, pred_index in matches}

    for gold_index, pred_index in matches:
        gold_required = required_ids(gold_topics[gold_index])
        pred_required = required_ids(pred_topics[pred_index])
        true_positive += len(gold_required & pred_required)
        false_positive += len(pred_required - gold_required)
        false_negative += len(gold_required - pred_required)

    for pred_index, pred_topic in enumerate(pred_topics):
        if pred_index not in matched_pred:
            false_positive += len(required_ids(pred_topic))

    for gold_index, gold_topic in enumerate(gold_topics):
        if gold_index not in matched_gold:
            false_negative += len(required_ids(gold_topic))

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def safe_divide(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return numerator / denominator


def prf(counts: dict[str, int]) -> dict[str, float | int]:
    tp = counts["true_positive"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    if tp == 0 and (fp > 0 or fn > 0):
        f1 = 0.0
    else:
        f1 = safe_divide(2 * precision * recall, precision + recall)
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def in_expected_topic_count_range(predicted_count: int, gold_case: dict[str, object]) -> bool:
    expected = gold_case.get("expected_topic_count_range") or [
        len(gold_case.get("gold_topics") or []),
        len(gold_case.get("gold_topics") or []),
    ]
    if not isinstance(expected, list) or len(expected) != 2:
        return False
    return int(expected[0]) <= predicted_count <= int(expected[1])


def fallback_matches(gold_case: dict[str, object], pred_output: dict[str, object]) -> bool:
    gold_reasons = set(gold_case.get("allowed_fallback_reasons") or [])
    pred_reasons = set(pred_output.get("allowed_fallback_reasons") or [])
    if not gold_reasons and not pred_reasons:
        return True
    return bool(gold_reasons) == bool(pred_reasons) and pred_reasons <= gold_reasons


def bridge_messages(topics: list[dict[str, object]]) -> set[str]:
    counts: Counter[str] = Counter()
    for topic in topics:
        counts.update(required_ids(topic))
    return {message_id for message_id, count in counts.items() if count > 1}


def score_dataset(
    gold_cases: list[dict[str, object]],
    predictions: list[dict[str, object]],
    *,
    scoring_mode: str = STRICT_SCORING_MODE,
    judge: object | None = None,
    judge_remote_server_id: str = "",
    judge_model_id: str = "",
) -> dict[str, Any]:
    if scoring_mode not in TOPIC_MEMBERSHIP_SCORING_MODES:
        raise ValueError(f"unsupported topic membership scoring mode: {scoring_mode}")
    semantic_runtime = (
        _TopicSemanticJudgeRuntime(
            judge=judge,
            judge_remote_server_id=judge_remote_server_id,
            judge_model_id=judge_model_id,
        )
        if scoring_mode == SEMANTIC_SCORING_MODE
        else None
    )
    result = _score_dataset_core(gold_cases, predictions, semantic_runtime=semantic_runtime)
    if semantic_runtime is not None:
        result["semantic_judge"] = {
            "judge_remote_server_id": semantic_runtime.judge_remote_server_id,
            "judge_model_id": semantic_runtime.judge_model_id,
            "judge_prompt_version": SEMANTIC_JUDGE_PROMPT_VERSION,
            "judge_prompt_hash": SEMANTIC_JUDGE_PROMPT_HASH,
            "calls": semantic_runtime.calls,
            "cache_hits": semantic_runtime.cache_hits,
            "failures": semantic_runtime.failures,
        }
        result["semantic_alignment_strategy"] = SEMANTIC_ALIGNMENT_STRATEGY
    result["scoring_mode"] = scoring_mode
    return result


def _score_dataset_core(
    gold_cases: list[dict[str, object]],
    predictions: list[dict[str, object]],
    *,
    semantic_runtime: "_TopicSemanticJudgeRuntime | None",
) -> dict[str, Any]:
    predictions_by_id = prediction_by_dialogue_id(predictions)
    total_counts = {"true_positive": 0, "false_positive": 0, "false_negative": 0}
    semantic_total_counts = {"true_positive": 0, "false_positive": 0, "false_negative": 0}
    valid_outputs = 0
    topic_count_hits = 0
    fallback_hits = 0
    gold_fallback_cases = 0
    cases_scored = 0
    missing_predictions = 0
    gold_bridge_total = 0
    gold_bridge_recalled = 0
    per_case: list[dict[str, object]] = []
    row_audit: list[dict[str, object]] = []

    for gold_case in gold_cases:
        cases_scored += 1
        dialogue_id = str(gold_case.get("source_dialogue_id") or "")
        prediction = predictions_by_id.get(dialogue_id)
        if not prediction:
            missing_predictions += 1
            pred_output: dict[str, object] = {"gold_topics": []}
            valid = False
            parse_status = "missing_prediction"
        else:
            pred_output, valid = normalize_output_json(prediction)
            if pred_output is None:
                pred_output = {"gold_topics": []}
            parse_status = "ok" if valid else "parse_error"
        if valid:
            valid_outputs += 1

        raw_gold_topics = gold_case.get("gold_topics") or []
        gold_topics = raw_gold_topics if isinstance(raw_gold_topics, list) else []
        raw_pred_topics = pred_output.get("gold_topics") or []
        pred_topics = raw_pred_topics if isinstance(raw_pred_topics, list) else []
        normalized_gold_topics = [topic for topic in gold_topics if isinstance(topic, dict)]
        normalized_pred_topics = [topic for topic in pred_topics if isinstance(topic, dict)]

        strict_matches = match_topics(normalized_gold_topics, normalized_pred_topics)
        counts = membership_counts(normalized_gold_topics, normalized_pred_topics, strict_matches)
        for key in total_counts:
            total_counts[key] += counts[key]

        semantic_matches: list[tuple[int, int]] | None = None
        semantic_counts: dict[str, int] | None = None
        semantic_alignment: dict[str, object] | None = None
        if semantic_runtime is not None:
            semantic_alignment = semantic_match_topics(
                dialogue_id=dialogue_id,
                messages=gold_case.get("messages") if isinstance(gold_case.get("messages"), list) else [],
                gold_topics=normalized_gold_topics,
                pred_topics=normalized_pred_topics,
                strict_matches=strict_matches,
                judge_runtime=semantic_runtime,
            )
            semantic_matches = [
                (int(gold_index), int(pred_index))
                for gold_index, pred_index in semantic_alignment.get("matches", [])
                if isinstance(gold_index, int) and isinstance(pred_index, int)
            ]
            semantic_counts = membership_counts(normalized_gold_topics, normalized_pred_topics, semantic_matches)
            for key in semantic_total_counts:
                semantic_total_counts[key] += semantic_counts[key]

        if in_expected_topic_count_range(len(normalized_pred_topics), gold_case):
            topic_count_hits += 1

        if gold_case.get("allowed_fallback_reasons"):
            gold_fallback_cases += 1
            if fallback_matches(gold_case, pred_output):
                fallback_hits += 1

        gold_bridges = bridge_messages(normalized_gold_topics)
        pred_bridges = bridge_messages(normalized_pred_topics)
        gold_bridge_total += len(gold_bridges)
        gold_bridge_recalled += len(gold_bridges & pred_bridges)

        per_case_row: dict[str, object] = {
            "source_dialogue_id": dialogue_id,
            "matches": len(strict_matches),
            "gold_topics": len(normalized_gold_topics),
            "predicted_topics": len(normalized_pred_topics),
            "strict_membership": prf(counts),
            "json_valid": valid,
            "parse_status": parse_status,
        }
        if semantic_matches is not None and semantic_counts is not None:
            per_case_row["semantic_matches"] = len(semantic_matches)
            per_case_row["semantic_membership"] = prf(semantic_counts)
            if semantic_alignment is not None:
                per_case_row["semantic_alignment"] = {
                    "candidate_count": len(semantic_alignment.get("candidate_scores", [])),
                    "judge_candidate_count": len(
                        [
                            row
                            for row in semantic_alignment.get("candidate_scores", [])
                            if isinstance(row, dict) and row.get("source") == "judge"
                        ]
                    ),
                }
        per_case.append(per_case_row)
        row_audit.append(
            {
                "source_dialogue_id": dialogue_id,
                "status": "ok" if valid else parse_status,
                "gold_topic_count": len(normalized_gold_topics),
                "predicted_topic_count": len(normalized_pred_topics),
                "strict_matches": [
                    {
                        "gold_topic_index": gold_index,
                        "pred_topic_index": pred_index,
                        "gold_topic_id": topic_id(normalized_gold_topics[gold_index], gold_index),
                        "pred_topic_id": topic_id(normalized_pred_topics[pred_index], pred_index),
                    }
                    for gold_index, pred_index in strict_matches
                ],
                "strict_membership": prf(counts),
                **(
                    {
                        "semantic_matches": [
                            {
                                "gold_topic_index": gold_index,
                                "pred_topic_index": pred_index,
                                "gold_topic_id": topic_id(normalized_gold_topics[gold_index], gold_index),
                                "pred_topic_id": topic_id(normalized_pred_topics[pred_index], pred_index),
                            }
                            for gold_index, pred_index in (semantic_matches or [])
                        ],
                        "semantic_membership": prf(semantic_counts or {"true_positive": 0, "false_positive": 0, "false_negative": 0}),
                    }
                    if semantic_runtime is not None
                    else {}
                ),
            }
        )

    result: dict[str, Any] = {
        "cases": cases_scored,
        "missing_predictions": missing_predictions,
        "json_valid_rate": safe_divide(valid_outputs, cases_scored),
        "topic_count_range_accuracy": safe_divide(topic_count_hits, cases_scored),
        "fallback_accuracy": safe_divide(fallback_hits, gold_fallback_cases),
        "gold_fallback_cases": gold_fallback_cases,
        "strict_membership": prf(total_counts),
        "bridge_message_recall": {
            "gold_bridge_messages": gold_bridge_total,
            "recalled_bridge_messages": gold_bridge_recalled,
            "recall": safe_divide(gold_bridge_recalled, gold_bridge_total),
        },
        "per_case": per_case,
        "row_audit": row_audit,
    }
    if semantic_runtime is not None:
        result["semantic_membership"] = prf(semantic_total_counts)
    return result


def semantic_match_topics(
    *,
    dialogue_id: str,
    messages: list[object],
    gold_topics: list[dict[str, object]],
    pred_topics: list[dict[str, object]],
    strict_matches: list[tuple[int, int]],
    judge_runtime: "_TopicSemanticJudgeRuntime",
) -> dict[str, object]:
    strict_pair_set = set(strict_matches)
    candidate_scores: list[dict[str, object]] = []
    candidates: list[tuple[int, float, int, int]] = []
    for gold_index, pred_index in strict_matches:
        score = jaccard(required_ids(gold_topics[gold_index]), required_ids(pred_topics[pred_index]))
        candidates.append((1, score, gold_index, pred_index))
        candidate_scores.append(
            {
                "gold_topic_index": gold_index,
                "pred_topic_index": pred_index,
                "score": score,
                "accepted": True,
                "source": "strict",
                "reason_code": "strict_jaccard",
            }
        )

    lexical_candidates = _lexical_candidate_pairs(
        messages=messages,
        gold_topics=gold_topics,
        pred_topics=pred_topics,
        strict_pair_set=strict_pair_set,
    )
    for lexical_score, gold_index, pred_index in lexical_candidates:
        request = _semantic_topic_request(
            dialogue_id=dialogue_id,
            messages=messages,
            gold_topic_index=gold_index,
            pred_topic_index=pred_index,
            gold_topic=gold_topics[gold_index],
            pred_topic=pred_topics[pred_index],
            lexical_similarity=lexical_score,
        )
        decision = judge_runtime.decide(request)
        equivalent = bool(decision.get("equivalent", False))
        confidence = float(decision.get("confidence", 0.0) or 0.0)
        accepted = equivalent and confidence >= SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD
        if accepted:
            candidates.append((0, confidence, gold_index, pred_index))
        candidate_scores.append(
            {
                "gold_topic_index": gold_index,
                "pred_topic_index": pred_index,
                "score": confidence,
                "lexical_similarity": lexical_score,
                "accepted": accepted,
                "source": "judge",
                "reason_code": decision.get("reason_code", ""),
                "equivalent": equivalent,
                "short_reason": decision.get("short_reason", ""),
            }
        )

    matches: list[tuple[int, int]] = []
    used_gold: set[int] = set()
    used_pred: set[int] = set()
    for _rank, _score, gold_index, pred_index in sorted(candidates, reverse=True):
        if gold_index in used_gold or pred_index in used_pred:
            continue
        matches.append((gold_index, pred_index))
        used_gold.add(gold_index)
        used_pred.add(pred_index)
    return {
        "matches": matches,
        "candidate_scores": candidate_scores,
    }


def evaluate_topic_membership(
    *,
    gold_jsonl: Path,
    pred_jsonl: Path,
    summary_output: Path,
    details_output: Path,
    row_audit_output: Path | None = None,
    judge_audit_output: Path | None = None,
    scoring_mode: str = STRICT_SCORING_MODE,
    judge: object | None = None,
    judge_remote_server_id: str = "",
    judge_model_id: str = "",
) -> dict[str, object]:
    result = score_dataset(
        read_jsonl(gold_jsonl),
        read_jsonl(pred_jsonl),
        scoring_mode=scoring_mode,
        judge=judge,
        judge_remote_server_id=judge_remote_server_id,
        judge_model_id=judge_model_id,
    )
    details = result.get("per_case")
    if not isinstance(details, list):
        details = []
    row_audit = result.get("row_audit")
    if not isinstance(row_audit, list):
        row_audit = []
    summary = dict(result)
    summary.pop("per_case", None)
    summary.pop("row_audit", None)

    _write_json(summary_output, summary)
    _write_jsonl(details_output, details)
    if row_audit_output is not None:
        _write_jsonl(row_audit_output, row_audit)
    if judge_audit_output is not None:
        audit_rows: list[dict[str, object]] = []
        runtime = getattr(judge, "_topic_membership_runtime", None)
        if isinstance(runtime, _TopicSemanticJudgeRuntime):
            audit_rows = runtime.audit_rows
        _write_jsonl(judge_audit_output, audit_rows)
    return summary


class _TopicSemanticJudgeRuntime:
    def __init__(
        self,
        *,
        judge: object,
        judge_remote_server_id: str,
        judge_model_id: str,
    ) -> None:
        if judge is None:
            raise ValueError("topic_membership_semantic_micro_f1 requires a semantic judge")
        self.judge = judge
        self.judge_remote_server_id = judge_remote_server_id
        self.judge_model_id = judge_model_id
        self.calls = 0
        self.cache_hits = 0
        self.failures = 0
        self.cache: dict[str, dict[str, object]] = {}
        self.audit_rows: list[dict[str, object]] = []
        try:
            setattr(judge, "_topic_membership_runtime", self)
        except Exception:
            pass

    def decide(self, request: dict[str, object]) -> dict[str, object]:
        cache_key = _semantic_judge_cache_key(request)
        if cache_key in self.cache:
            self.cache_hits += 1
            decision = dict(self.cache[cache_key])
            self.audit_rows.append(
                _semantic_judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="cache",
                    status="ok",
                    error_code=None,
                    failure_reason=None,
                )
            )
            return decision

        self.calls += 1
        try:
            raw_decision = getattr(self.judge, "judge_topic_equivalence")(request)
            decision = _normalize_semantic_judge_decision(raw_decision)
            self.cache[cache_key] = decision
            self.audit_rows.append(
                _semantic_judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="judge",
                    status="ok",
                    error_code=None,
                    failure_reason=None,
                )
            )
            return decision
        except Exception as exc:
            self.failures += 1
            failure_reason = _semantic_judge_failure_reason(exc)
            decision = {
                "equivalent": False,
                "confidence": 0.0,
                "reason_code": getattr(exc, "code", "judge_error"),
                "short_reason": failure_reason,
            }
            self.audit_rows.append(
                _semantic_judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="judge",
                    status="failed",
                    error_code=str(getattr(exc, "code", "judge_error")),
                    failure_reason=failure_reason,
                )
            )
            return decision


def _lexical_candidate_pairs(
    *,
    messages: list[object],
    gold_topics: list[dict[str, object]],
    pred_topics: list[dict[str, object]],
    strict_pair_set: set[tuple[int, int]],
) -> list[tuple[float, int, int]]:
    pairs: list[tuple[float, int, int]] = []
    for gold_index, gold_topic in enumerate(gold_topics):
        scored: list[tuple[float, int]] = []
        gold_text = _topic_similarity_text(gold_topic, messages)
        for pred_index, pred_topic in enumerate(pred_topics):
            if (gold_index, pred_index) in strict_pair_set:
                continue
            score = _lexical_similarity(gold_text, _topic_similarity_text(pred_topic, messages))
            scored.append((score, pred_index))
        for score, pred_index in sorted(scored, reverse=True)[:SEMANTIC_LEXICAL_TOP_K]:
            if score <= 0.0:
                continue
            pairs.append((score, gold_index, pred_index))
    return pairs


def _topic_similarity_text(topic: dict[str, object], messages: list[object]) -> str:
    parts = [
        str(topic.get("label") or ""),
        str(topic.get("description") or ""),
        " ".join(sorted(required_ids(topic))),
    ]
    message_by_id = {
        str(message.get("message_id") or ""): str(message.get("text") or "")
        for message in messages
        if isinstance(message, dict)
    }
    for message_id in sorted(required_ids(topic)):
        text = message_by_id.get(message_id, "")
        if text:
            parts.append(text)
    return " ".join(part for part in parts if part)


def _lexical_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _token_set(text: str) -> set[str]:
    lowered = text.lower()
    tokens = {match.group(0) for match in _TOKEN_PATTERN.finditer(lowered)}
    for cjk_char in _CJK_PATTERN.findall(lowered):
        tokens.add(cjk_char)
    return {token for token in tokens if token}


def _semantic_topic_request(
    *,
    dialogue_id: str,
    messages: list[object],
    gold_topic_index: int,
    pred_topic_index: int,
    gold_topic: dict[str, object],
    pred_topic: dict[str, object],
    lexical_similarity: float,
) -> dict[str, object]:
    return {
        "kind": "topic",
        "dialogue_id": dialogue_id,
        "judge_prompt_version": SEMANTIC_JUDGE_PROMPT_VERSION,
        "judge_prompt_hash": SEMANTIC_JUDGE_PROMPT_HASH,
        "gold_topic_index": gold_topic_index,
        "pred_topic_index": pred_topic_index,
        "lexical_similarity": round(float(lexical_similarity), 6),
        "gold_topic": _semantic_topic_payload(gold_topic, messages),
        "pred_topic": _semantic_topic_payload(pred_topic, messages),
    }


def _semantic_topic_payload(topic: dict[str, object], messages: list[object]) -> dict[str, object]:
    message_by_id = {
        str(message.get("message_id") or ""): {
            "message_id": str(message.get("message_id") or ""),
            "sender": str(message.get("sender") or ""),
            "text": str(message.get("text") or ""),
        }
        for message in messages
        if isinstance(message, dict)
    }
    message_ids = sorted(required_ids(topic))
    return {
        "topic_id": str(topic.get("gold_topic_id") or topic.get("topic_id") or ""),
        "label": str(topic.get("label") or ""),
        "description": str(topic.get("description") or ""),
        "required_message_ids": message_ids,
        "message_snippets": [
            message_by_id[message_id]
            for message_id in message_ids
            if message_id in message_by_id
        ][:12],
    }


def _normalize_semantic_judge_decision(raw_decision: object) -> dict[str, object]:
    if not isinstance(raw_decision, dict):
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": "Judge response was not a JSON object.",
        }
    equivalent = raw_decision.get("equivalent")
    if not isinstance(equivalent, bool):
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": "Judge response did not contain a boolean equivalent field.",
        }
    confidence_value = raw_decision.get("confidence", 0.0)
    confidence = 0.0
    if not isinstance(confidence_value, bool) and isinstance(confidence_value, (int, float)):
        confidence = max(0.0, min(1.0, float(confidence_value)))
    reason_code = raw_decision.get("reason_code")
    short_reason = raw_decision.get("short_reason")
    if str(reason_code or "").strip() == "uncertain":
        equivalent = False
    return {
        "equivalent": equivalent,
        "confidence": round(confidence, 6),
        "reason_code": str(reason_code or ("same_topic" if equivalent else "uncertain")).strip(),
        "short_reason": str(short_reason or "").strip(),
    }


def _parse_semantic_judge_response(response_text: str) -> dict[str, object]:
    try:
        return _normalize_semantic_judge_decision(extract_topic_membership_output_json(response_text))
    except Exception as exc:
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": str(exc),
        }


def _semantic_judge_cache_key(request: dict[str, object]) -> str:
    payload = {
        "judge_prompt_hash": SEMANTIC_JUDGE_PROMPT_HASH,
        "kind": request.get("kind", ""),
        "gold_topic": request.get("gold_topic", {}),
        "pred_topic": request.get("pred_topic", {}),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _semantic_judge_failure_reason(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return f"remote provider HTTP {status_code}"
    if isinstance(exc, RemoteProviderRequestError):
        return "remote provider request failed"
    first_line = str(exc).splitlines()[0].strip()
    if not first_line:
        return exc.__class__.__name__
    return first_line[:240]


def _semantic_judge_audit_row(
    *,
    request: dict[str, object],
    decision: dict[str, object],
    cache_key: str,
    source: str,
    status: str,
    error_code: str | None,
    failure_reason: str | None,
) -> dict[str, object]:
    return {
        "dialogue_id": request.get("dialogue_id", ""),
        "kind": request.get("kind", ""),
        "judge_prompt_version": SEMANTIC_JUDGE_PROMPT_VERSION,
        "judge_prompt_hash": SEMANTIC_JUDGE_PROMPT_HASH,
        "cache_key": cache_key,
        "source": source,
        "status": status,
        "error_code": error_code,
        "failure_reason": failure_reason,
        "gold_topic_index": request.get("gold_topic_index"),
        "pred_topic_index": request.get("pred_topic_index"),
        "equivalent": bool(decision.get("equivalent", False)),
        "confidence": float(decision.get("confidence", 0.0) or 0.0),
        "reason_code": decision.get("reason_code", ""),
        "short_reason": decision.get("short_reason", ""),
    }


def _assistant_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("remote provider response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("remote provider choice must be a JSON object")
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    text = first.get("text")
    if isinstance(text, str):
        return text
    raise ValueError("remote provider choice did not include text content")


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


def _provider_usage_from_keys(
    usage: dict[object, object],
    key_map: Sequence[tuple[str, str]],
) -> dict[str, int]:
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
    stripped = model_id.strip()
    if not stripped:
        raise ValueError("remote provider model_id is empty")
    if stripped.startswith("models/"):
        return stripped
    return f"models/{stripped}"


def _post_json_request(request: Request, *, timeout_seconds: int) -> dict[str, object]:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RemoteProviderHTTPError(status_code=exc.code, response_body=error_body) from exc
    except URLError as exc:
        raise RemoteProviderRequestError(reason=exc.reason) from exc

    parsed = json.loads(response_body)
    if not isinstance(parsed, dict):
        raise ValueError("remote provider response must be a JSON object")
    return parsed


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path | None, rows: Iterable[dict[str, object]]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
