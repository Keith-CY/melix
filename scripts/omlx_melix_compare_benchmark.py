#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import melix_metrics_snapshot


DEFAULT_PROMPT_TOKEN_TARGETS = [1024]
DEFAULT_CONCURRENCY = [1]
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 128
DEFAULT_REPEATS = 3
DEFAULT_WARMUP_MAX_TOKENS = 8
DEFAULT_WARMUP_PROMPT_TOKEN_TARGET = 128
DEFAULT_PREFLIGHT_WAIT_SECONDS = 0.0
DEFAULT_PREFLIGHT_RETRY_INTERVAL_SECONDS = 2.0
DEFAULT_TOP_P = 1.0
DEFAULT_TOP_K = 0
PROMPT_STYLES = ("concise", "saturating")
MEASUREMENT_PROFILES = ("auto", "cold", "warm", "mixed")
COMPARISON_SCOPES = ("peer", "debug-only")
REPORT_SCHEMA_VERSION = 3
DEFAULT_TOTAL_LATENCY_THRESHOLD_RATIO = 0.25
DEFAULT_DECODE_THROUGHPUT_THRESHOLD_RATIO = 0.25
MELIX_VLM_BATCHING_BLOCKED_REASON_CODES = {
    1: "multimodal route does not expose a streaming continuous batching path",
    2: "python VLM request is not eligible for cooperative text-only token-step batching",
}
REQUIRED_MELIX_PEER_BINARY_NAMES = ("text_worker", "control_plane")


@dataclass(frozen=True)
class EndpointConfig:
    name: str
    base_url: str
    model: str
    headers: dict[str, str]


@dataclass(frozen=True)
class BenchmarkScenario:
    scenario_id: str
    prompt_token_target: int
    max_tokens: int
    concurrency: int
    cache_profile: str
    repeat_index: int
    prompt_style: str = "concise"


@dataclass
class RequestObservation:
    endpoint: str
    model: str
    scenario_id: str
    group_id: str
    prompt_token_target: int
    prompt_token_source: str
    max_tokens: int
    concurrency: int
    cache_profile: str
    repeat_index: int
    request_index: int
    status: str
    http_status: int
    error: str
    ttft_ms: float | None
    total_ms: float
    decode_ms: float | None
    completion_tokens: float
    completion_token_source: str
    prompt_tokens: float
    streamed_chunks: int
    completion_chars: int
    decode_tokens_per_second: float | None
    group_elapsed_ms: float
    prompt_style: str = "concise"


@dataclass
class ScenarioSummary:
    endpoint: str
    model: str
    prompt_token_target: int
    max_tokens: int
    concurrency: int
    cache_profile: str
    request_count: int
    success_count: int
    error_count: int
    error_rate: float
    median_ttft_ms: float | None
    p95_ttft_ms: float | None
    median_total_ms: float | None
    p95_total_ms: float | None
    median_decode_tokens_per_second: float | None
    median_aggregate_output_tokens_per_second: float | None
    median_completion_tokens: float | None
    prompt_style: str = "concise"
    prompt_token_sources: str = "unknown"
    completion_token_sources: str = "unknown"


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def endpoint_url(base_url: str, path: str) -> str:
    return f"{normalize_base_url(base_url)}/{path.lstrip('/')}"


def parse_header_values(values: Iterable[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        if ":" not in value:
            raise ValueError(f"Header must use 'Name: value' format: {value}")
        name, header_value = value.split(":", 1)
        name = name.strip()
        header_value = header_value.strip()
        if not name:
            raise ValueError(f"Header name is empty: {value}")
        headers[name] = header_value
    return headers


def estimate_tokens_from_text(text: str) -> float:
    if not text:
        return 0.0
    return max(1.0, len(text) / 4.0)


def build_prompt(
    prompt_token_target: int,
    *,
    cache_profile: str,
    request_key: str,
    prompt_style: str = "concise",
) -> str:
    if prompt_token_target <= 0:
        raise ValueError("prompt_token_target must be positive")
    if cache_profile not in {"cold_unique", "repeated"}:
        raise ValueError(f"Unsupported cache profile: {cache_profile}")
    if prompt_style not in PROMPT_STYLES:
        raise ValueError(f"Unsupported prompt style: {prompt_style}")

    prefix = "MELIX-OMLX-BENCH-REPEATED" if cache_profile == "repeated" else f"MELIX-OMLX-BENCH-{request_key}"
    if prompt_style == "saturating":
        sentence = (
            "Measure local inference serving behavior with a deterministic synthetic prompt. "
            "Continue generating numbered observations until the server stops the response. "
        )
        instruction = (
            "Return a long numbered list of concrete observations. "
            "Do not conclude, summarize, or stop early; continue with the next numbered item until interrupted."
        )
    else:
        sentence = (
            "Measure local inference serving behavior with a deterministic synthetic prompt. "
            "Keep the answer concise and continue the numbered observations. "
        )
        instruction = "Return a numbered list of concrete observations."
    target_chars = max(128, prompt_token_target * 4)
    body = (sentence * ((target_chars // len(sentence)) + 2))[:target_chars]
    return f"{prefix}\n\n{body}\n\n{instruction}"


def request_key_for_scenario(
    scenario: BenchmarkScenario,
    *,
    request_index: int,
    run_key: str = "",
) -> str:
    parts = []
    if scenario.cache_profile == "cold_unique" and run_key:
        parts.append(run_key)
    parts.append(scenario.scenario_id)
    parts.append(f"req{request_index}")
    return "-".join(parts)


def parse_sse_data_lines(lines: Iterable[bytes]) -> tuple[str, int, dict[str, Any] | None, bool]:
    content_parts: list[str] = []
    chunk_count = 0
    usage: dict[str, Any] | None = None
    saw_done = False

    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if payload == "[DONE]":
            saw_done = True
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        delta_text = extract_openai_delta_text(event)
        if delta_text:
            content_parts.append(delta_text)
            chunk_count += 1
    return "".join(content_parts), chunk_count, usage, saw_done


def extract_openai_delta_text(event: dict[str, Any]) -> str:
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    for container_key in ("delta", "message"):
        container = choice.get(container_key)
        if isinstance(container, dict):
            text = _text_from_openai_content(container.get("content"))
            if text:
                return text
            for key in ("reasoning_content", "text"):
                value = container.get(key)
                if isinstance(value, str) and value:
                    return value
    value = choice.get("text")
    return value if isinstance(value, str) else ""


def _text_from_openai_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def request_json(url: str, *, headers: dict[str, str], timeout_seconds: float) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return int(exc.code), _decode_json_body(exc.read())
    except Exception as exc:  # pragma: no cover - exercised by live preflight
        return 0, {"error": {"message": str(exc), "type": type(exc).__name__}}


def _decode_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {"raw_body": body.decode("utf-8", errors="replace")}
    return payload if isinstance(payload, dict) else {"payload": payload}


def preflight_endpoint(endpoint: EndpointConfig, *, timeout_seconds: float) -> dict[str, Any]:
    status, payload = request_json(
        endpoint_url(endpoint.base_url, "/models"),
        headers=endpoint.headers,
        timeout_seconds=timeout_seconds,
    )
    model_ids = extract_model_ids(payload)
    return {
        "endpoint": endpoint.name,
        "base_url": endpoint.base_url,
        "status_code": status,
        "ok": status == 200 and endpoint.model in model_ids,
        "model": endpoint.model,
        "model_listed": endpoint.model in model_ids if status == 200 else None,
        "model_count": len(model_ids),
        "models": model_ids[:25],
        "error": payload.get("error") if isinstance(payload.get("error"), dict) else None,
    }


def preflight_endpoints(
    endpoints: list[EndpointConfig],
    *,
    timeout_seconds: float,
    wait_seconds: float,
    retry_interval_seconds: float,
) -> list[dict[str, Any]]:
    started_at = time.monotonic()
    attempt_count = 0
    while True:
        attempt_count += 1
        preflight = [
            preflight_endpoint(endpoint, timeout_seconds=timeout_seconds)
            for endpoint in endpoints
        ]
        elapsed_seconds = time.monotonic() - started_at
        for item in preflight:
            item["attempt_count"] = attempt_count
            item["elapsed_seconds"] = round(elapsed_seconds, 3)
        if all(item["ok"] is True for item in preflight) or wait_seconds <= 0:
            return preflight

        remaining_seconds = wait_seconds - elapsed_seconds
        if remaining_seconds <= 0:
            return preflight
        time.sleep(min(retry_interval_seconds, remaining_seconds))


def extract_model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    ids: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


def stream_chat_completion(
    endpoint: EndpointConfig,
    scenario: BenchmarkScenario,
    *,
    request_index: int,
    request_key: str,
    include_usage: bool,
    temperature: float,
    top_p: float,
    top_k: int,
    timeout_seconds: float,
    group_id: str,
    group_elapsed_ms: float,
) -> RequestObservation:
    prompt = build_prompt(
        scenario.prompt_token_target,
        cache_profile=scenario.cache_profile,
        request_key=request_key,
        prompt_style=scenario.prompt_style,
    )
    payload: dict[str, Any] = {
        "model": endpoint.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "max_tokens": scenario.max_tokens,
        "stream": True,
    }
    if include_usage:
        payload["stream_options"] = {"include_usage": True}

    started_at = time.perf_counter()
    first_delta_at: float | None = None
    completion_parts: list[str] = []
    streamed_chunks = 0
    usage: dict[str, Any] | None = None
    http_status = 0
    error = ""

    request = urllib.request.Request(
        endpoint_url(endpoint.base_url, "/chat/completions"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", **endpoint.headers},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            http_status = int(response.status)
            while True:
                raw_line = response.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(event.get("usage"), dict):
                    usage = event["usage"]
                delta_text = extract_openai_delta_text(event)
                if delta_text:
                    if first_delta_at is None:
                        first_delta_at = time.perf_counter()
                    completion_parts.append(delta_text)
                    streamed_chunks += 1
    except urllib.error.HTTPError as exc:
        http_status = int(exc.code)
        error = json.dumps(_decode_json_body(exc.read()), sort_keys=True)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    ended_at = time.perf_counter()
    completion_text = "".join(completion_parts)
    usage_prompt_tokens = _numeric_usage_value(usage, "prompt_tokens")
    usage_completion_tokens = _numeric_usage_value(usage, "completion_tokens")
    prompt_tokens = usage_prompt_tokens if usage_prompt_tokens is not None else estimate_tokens_from_text(prompt)
    completion_tokens = (
        usage_completion_tokens
        if usage_completion_tokens is not None
        else estimate_tokens_from_text(completion_text)
    )
    completion_token_source = "usage" if usage_completion_tokens is not None else "estimated_chars"
    prompt_token_source = "usage" if usage_prompt_tokens is not None else "estimated_chars"

    ttft_ms = (first_delta_at - started_at) * 1000.0 if first_delta_at is not None else None
    total_ms = (ended_at - started_at) * 1000.0
    decode_ms = total_ms - ttft_ms if ttft_ms is not None else None
    decode_tokens_per_second = (
        completion_tokens / max(decode_ms / 1000.0, 1e-9)
        if decode_ms is not None and completion_tokens > 0
        else None
    )
    status = "ok" if http_status == 200 and not error and completion_text else "error"
    if status == "error" and not error and http_status == 200:
        error = "stream completed without text deltas"

    return RequestObservation(
        endpoint=endpoint.name,
        model=endpoint.model,
        scenario_id=scenario.scenario_id,
        group_id=group_id,
        prompt_token_target=scenario.prompt_token_target,
        prompt_token_source=prompt_token_source,
        max_tokens=scenario.max_tokens,
        concurrency=scenario.concurrency,
        cache_profile=scenario.cache_profile,
        repeat_index=scenario.repeat_index,
        request_index=request_index,
        status=status,
        http_status=http_status,
        error=error,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        decode_ms=decode_ms,
        completion_tokens=completion_tokens,
        completion_token_source=completion_token_source,
        prompt_tokens=prompt_tokens,
        streamed_chunks=streamed_chunks,
        completion_chars=len(completion_text),
        decode_tokens_per_second=decode_tokens_per_second,
        group_elapsed_ms=group_elapsed_ms,
        prompt_style=scenario.prompt_style,
    )


def _numeric_usage_value(usage: dict[str, Any] | None, key: str) -> float | None:
    if not usage:
        return None
    value = usage.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def run_group(
    endpoint: EndpointConfig,
    scenario: BenchmarkScenario,
    *,
    include_usage: bool,
    temperature: float,
    top_p: float,
    top_k: int,
    timeout_seconds: float,
    run_key: str = "",
) -> list[RequestObservation]:
    group_id = f"{endpoint.name}-{scenario.scenario_id}-{uuid.uuid4().hex[:8]}"
    started_at = time.perf_counter()
    observations: list[RequestObservation] = []

    def run_one(request_index: int) -> RequestObservation:
        return stream_chat_completion(
            endpoint,
            scenario,
            request_index=request_index,
            request_key=request_key_for_scenario(
                scenario,
                request_index=request_index,
                run_key=run_key,
            ),
            include_usage=include_usage,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            timeout_seconds=timeout_seconds,
            group_id=group_id,
            group_elapsed_ms=0.0,
        )

    if scenario.concurrency == 1:
        observations.append(run_one(0))
    else:
        with ThreadPoolExecutor(max_workers=scenario.concurrency) as executor:
            futures = [executor.submit(run_one, index) for index in range(scenario.concurrency)]
            for future in as_completed(futures):
                observations.append(future.result())

    group_elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    for observation in observations:
        observation.group_elapsed_ms = group_elapsed_ms
    return sorted(observations, key=lambda item: item.request_index)


def build_scenarios(
    *,
    prompt_token_targets: list[int],
    max_tokens: int,
    concurrency_values: list[int],
    cache_profile: str,
    prompt_style: str,
    repeats: int,
) -> list[BenchmarkScenario]:
    scenarios: list[BenchmarkScenario] = []
    for prompt_token_target in prompt_token_targets:
        for concurrency in concurrency_values:
            for repeat_index in range(repeats):
                scenarios.append(
                    BenchmarkScenario(
                        scenario_id=f"pt{prompt_token_target}-out{max_tokens}-c{concurrency}-r{repeat_index}",
                        prompt_token_target=prompt_token_target,
                        max_tokens=max_tokens,
                        concurrency=concurrency,
                        cache_profile=cache_profile,
                        repeat_index=repeat_index,
                        prompt_style=prompt_style,
                    )
                )
    return scenarios


def endpoints_for_scenario(
    endpoints: list[EndpointConfig],
    scenario: BenchmarkScenario,
    *,
    endpoint_order: str,
) -> list[EndpointConfig]:
    if endpoint_order == "alternate" and scenario.repeat_index % 2 == 1:
        return list(reversed(endpoints))
    return list(endpoints)


def summarize_observations(observations: list[RequestObservation]) -> list[ScenarioSummary]:
    grouped: dict[tuple[str, str, int, int, int, str, str], list[RequestObservation]] = {}
    for observation in observations:
        key = (
            observation.endpoint,
            observation.model,
            observation.prompt_token_target,
            observation.max_tokens,
            observation.concurrency,
            observation.cache_profile,
            observation.prompt_style,
        )
        grouped.setdefault(key, []).append(observation)

    summaries: list[ScenarioSummary] = []
    for key, rows in sorted(grouped.items()):
        endpoint, model, prompt_token_target, max_tokens, concurrency, cache_profile, prompt_style = key
        successes = [row for row in rows if row.status == "ok"]
        source_rows = successes if successes else rows
        group_tps = aggregate_output_tps_by_group(successes)
        summaries.append(
            ScenarioSummary(
                endpoint=endpoint,
                model=model,
                prompt_token_target=prompt_token_target,
                max_tokens=max_tokens,
                concurrency=concurrency,
                cache_profile=cache_profile,
                request_count=len(rows),
                success_count=len(successes),
                error_count=len(rows) - len(successes),
                error_rate=(len(rows) - len(successes)) / max(len(rows), 1),
                median_ttft_ms=median([row.ttft_ms for row in successes]),
                p95_ttft_ms=percentile([row.ttft_ms for row in successes], 95),
                median_total_ms=median([row.total_ms for row in successes]),
                p95_total_ms=percentile([row.total_ms for row in successes], 95),
                median_decode_tokens_per_second=median(
                    [row.decode_tokens_per_second for row in successes]
                ),
                median_aggregate_output_tokens_per_second=median(group_tps),
                median_completion_tokens=median([row.completion_tokens for row in successes]),
                prompt_style=prompt_style,
                prompt_token_sources=_source_summary(row.prompt_token_source for row in source_rows),
                completion_token_sources=_source_summary(
                    row.completion_token_source for row in source_rows
                ),
            )
        )
    return summaries


def _source_summary(values: Iterable[str]) -> str:
    sources = sorted({value for value in values if value})
    return ",".join(sources) if sources else "unknown"


def aggregate_output_tps_by_group(rows: list[RequestObservation]) -> list[float]:
    grouped: dict[str, list[RequestObservation]] = {}
    for row in rows:
        grouped.setdefault(row.group_id, []).append(row)
    values: list[float] = []
    for group_rows in grouped.values():
        elapsed_ms = max(row.group_elapsed_ms for row in group_rows)
        tokens = sum(row.completion_tokens for row in group_rows)
        if elapsed_ms > 0 and tokens > 0:
            values.append(tokens / (elapsed_ms / 1000.0))
    return values


def median(values: Iterable[float | None]) -> float | None:
    clean = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2.0


def percentile(values: Iterable[float | None], pct: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    rank = (len(clean) - 1) * (pct / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return clean[int(rank)]
    lower_value = clean[lower] * (upper - rank)
    upper_value = clean[upper] * (rank - lower)
    return lower_value + upper_value


def comparison_hints(summaries: list[ScenarioSummary]) -> list[dict[str, Any]]:
    by_key: dict[tuple[int, int, int, str, str], dict[str, ScenarioSummary]] = {}
    for summary in summaries:
        key = (
            summary.prompt_token_target,
            summary.max_tokens,
            summary.concurrency,
            summary.cache_profile,
            summary.prompt_style,
        )
        by_key.setdefault(key, {})[summary.endpoint] = summary

    hints: list[dict[str, Any]] = []
    for key, endpoint_summaries in sorted(by_key.items()):
        melix = endpoint_summaries.get("melix")
        omlx = endpoint_summaries.get("omlx")
        if melix is None or omlx is None:
            continue
        prompt_token_target, max_tokens, concurrency, cache_profile, prompt_style = key
        scenario = {
            "prompt_token_target": prompt_token_target,
            "max_tokens": max_tokens,
            "concurrency": concurrency,
            "cache_profile": cache_profile,
            "prompt_style": prompt_style,
        }
        if melix.error_rate > omlx.error_rate:
            hints.append({
                "scenario": scenario,
                "area": "reliability",
                "severity": "high",
                "message": "Melix has a higher request error rate than OMLX for the same scenario.",
                "melix_error_rate": melix.error_rate,
                "omlx_error_rate": omlx.error_rate,
            })
        if _is_regressed_latency(melix.median_ttft_ms, omlx.median_ttft_ms):
            hints.append({
                "scenario": scenario,
                "area": "ttft",
                "severity": "medium",
                "message": "Melix median TTFT is slower; inspect gateway overhead, queue wait, runtime preparation, and prefill probes.",
                "melix_median_ttft_ms": melix.median_ttft_ms,
                "omlx_median_ttft_ms": omlx.median_ttft_ms,
            })
        if _is_regressed_latency(melix.median_total_ms, omlx.median_total_ms):
            hints.append({
                "scenario": scenario,
                "area": "end_to_end_latency",
                "severity": "medium",
                "message": "Melix median end-to-end latency is slower; inspect stream assembly and request lifecycle overhead.",
                "melix_median_total_ms": melix.median_total_ms,
                "omlx_median_total_ms": omlx.median_total_ms,
            })
        if _is_regressed_throughput(
            melix.median_decode_tokens_per_second,
            omlx.median_decode_tokens_per_second,
        ):
            hints.append({
                "scenario": scenario,
                "area": "decode_throughput",
                "severity": "medium",
                "message": "Melix decode throughput is lower; inspect worker decode loop, MLX runtime settings, and token streaming cadence.",
                "melix_median_decode_tps": melix.median_decode_tokens_per_second,
                "omlx_median_decode_tps": omlx.median_decode_tokens_per_second,
            })
        if concurrency > 1 and _is_regressed_throughput(
            melix.median_aggregate_output_tokens_per_second,
            omlx.median_aggregate_output_tokens_per_second,
        ):
            hints.append({
                "scenario": scenario,
                "area": "continuous_batching",
                "severity": "medium",
                "message": "Melix aggregate output throughput is lower under concurrency; inspect scheduler admission, batching, and backpressure.",
                "melix_median_aggregate_tps": melix.median_aggregate_output_tokens_per_second,
                "omlx_median_aggregate_tps": omlx.median_aggregate_output_tokens_per_second,
            })
    return hints


def build_request_phase_rows(observations: list[RequestObservation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for observation in observations:
        rows.append({
            "endpoint": observation.endpoint,
            "model": observation.model,
            "scenario_id": observation.scenario_id,
            "group_id": observation.group_id,
            "prompt_token_target": observation.prompt_token_target,
            "max_tokens": observation.max_tokens,
            "concurrency": observation.concurrency,
            "cache_profile": observation.cache_profile,
            "prompt_style": observation.prompt_style,
            "repeat_index": observation.repeat_index,
            "request_index": observation.request_index,
            "status": observation.status,
            "http_status": observation.http_status,
            "error": observation.error,
            "prompt_tokens": observation.prompt_tokens,
            "prompt_token_source": observation.prompt_token_source,
            "output_tokens": observation.completion_tokens,
            "output_token_source": observation.completion_token_source,
            "queue_ms": None,
            "prefill_ms": None,
            "first_http_sse_event_ms": observation.ttft_ms,
            "decode_ms": observation.decode_ms,
            "worker_stream_ms": None,
            "total_ms": observation.total_ms,
            "streamed_chunks": observation.streamed_chunks,
            "completion_chars": observation.completion_chars,
            "decode_tokens_per_second": observation.decode_tokens_per_second,
            "group_elapsed_ms": observation.group_elapsed_ms,
            "phase_sources": {
                "queue_ms": "unavailable",
                "prefill_ms": "unavailable",
                "first_http_sse_event_ms": "client_stream_first_delta",
                "decode_ms": "client_total_minus_first_delta",
                "worker_stream_ms": "unavailable",
                "total_ms": "client_elapsed",
            },
        })
    return rows


def build_peer_delta_rows(
    summaries: list[ScenarioSummary],
    *,
    target_endpoint: str = "melix",
    total_latency_threshold_ratio: float = DEFAULT_TOTAL_LATENCY_THRESHOLD_RATIO,
    decode_throughput_threshold_ratio: float = DEFAULT_DECODE_THROUGHPUT_THRESHOLD_RATIO,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int, int, str, str], list[ScenarioSummary]] = {}
    for summary in summaries:
        grouped.setdefault(_scenario_key(summary), []).append(summary)

    rows: list[dict[str, Any]] = []
    for key, scenario_rows in sorted(grouped.items()):
        target = next((row for row in scenario_rows if row.endpoint == target_endpoint), None)
        if target is None:
            continue
        best_total_peer = _best_peer_summary(
            scenario_rows,
            target_endpoint,
            "median_total_ms",
            lower_is_better=True,
        )
        best_decode_peer = _best_peer_summary(
            scenario_rows,
            target_endpoint,
            "median_decode_tokens_per_second",
            lower_is_better=False,
        )
        total_status = _latency_threshold_status(
            target.median_total_ms,
            best_total_peer.median_total_ms if best_total_peer else None,
            total_latency_threshold_ratio,
        )
        decode_status = _throughput_threshold_status(
            target.median_decode_tokens_per_second,
            best_decode_peer.median_decode_tokens_per_second if best_decode_peer else None,
            decode_throughput_threshold_ratio,
        )
        row_status = (
            "threshold_failed"
            if total_status == "failed" or decode_status == "failed"
            else "ok"
            if total_status == "ok" and decode_status == "ok"
            else "insufficient_data"
        )
        rows.append({
            "scenario": _scenario_dict_from_key(key),
            "target_endpoint": target_endpoint,
            "status": row_status,
            "total_latency": {
                "status": total_status,
                "threshold_ratio": total_latency_threshold_ratio,
                "threshold_pct": total_latency_threshold_ratio * 100.0,
                "target_median_ms": target.median_total_ms,
                "best_peer": best_total_peer.endpoint if best_total_peer else None,
                "best_peer_median_ms": best_total_peer.median_total_ms if best_total_peer else None,
                "delta_ms": _delta(target.median_total_ms, best_total_peer.median_total_ms if best_total_peer else None),
                "delta_pct": _percent_delta(
                    target.median_total_ms,
                    best_total_peer.median_total_ms if best_total_peer else None,
                ),
            },
            "decode_throughput": {
                "status": decode_status,
                "threshold_ratio": decode_throughput_threshold_ratio,
                "threshold_pct": decode_throughput_threshold_ratio * 100.0,
                "target_median_tokens_per_second": target.median_decode_tokens_per_second,
                "best_peer": best_decode_peer.endpoint if best_decode_peer else None,
                "best_peer_median_tokens_per_second": (
                    best_decode_peer.median_decode_tokens_per_second if best_decode_peer else None
                ),
                "delta_tokens_per_second": _delta(
                    target.median_decode_tokens_per_second,
                    best_decode_peer.median_decode_tokens_per_second if best_decode_peer else None,
                ),
                "delta_pct": _percent_delta(
                    target.median_decode_tokens_per_second,
                    best_decode_peer.median_decode_tokens_per_second if best_decode_peer else None,
                ),
            },
        })
    return rows


def build_threshold_status(
    peer_delta_rows: list[dict[str, Any]],
    *,
    total_latency_threshold_ratio: float = DEFAULT_TOTAL_LATENCY_THRESHOLD_RATIO,
    decode_throughput_threshold_ratio: float = DEFAULT_DECODE_THROUGHPUT_THRESHOLD_RATIO,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    has_insufficient = False
    for row in peer_delta_rows:
        scenario = row.get("scenario", {})
        for area in ("total_latency", "decode_throughput"):
            area_payload = row.get(area, {})
            status = area_payload.get("status") if isinstance(area_payload, dict) else None
            if status == "failed":
                failures.append({
                    "scenario": scenario,
                    "area": area,
                    "target_endpoint": row.get("target_endpoint"),
                    "best_peer": area_payload.get("best_peer"),
                    "delta_pct": area_payload.get("delta_pct"),
                    "threshold_pct": area_payload.get("threshold_pct"),
                })
            elif status != "ok":
                has_insufficient = True
    if not peer_delta_rows:
        status = "no_data"
    elif failures:
        status = "threshold_failed"
    elif has_insufficient:
        status = "insufficient_data"
    else:
        status = "ok"
    return {
        "status": status,
        "row_count": len(peer_delta_rows),
        "failure_count": len(failures),
        "failures": failures,
        "total_latency_threshold_pct": total_latency_threshold_ratio * 100.0,
        "decode_throughput_threshold_pct": decode_throughput_threshold_ratio * 100.0,
    }


def _scenario_key(summary: ScenarioSummary) -> tuple[int, int, int, str, str]:
    return (
        summary.prompt_token_target,
        summary.max_tokens,
        summary.concurrency,
        summary.cache_profile,
        summary.prompt_style,
    )


def _scenario_dict_from_key(key: tuple[int, int, int, str, str]) -> dict[str, Any]:
    prompt_token_target, max_tokens, concurrency, cache_profile, prompt_style = key
    return {
        "prompt_token_target": prompt_token_target,
        "max_tokens": max_tokens,
        "concurrency": concurrency,
        "cache_profile": cache_profile,
        "prompt_style": prompt_style,
    }


def _best_peer_summary(
    rows: list[ScenarioSummary],
    target_endpoint: str,
    metric: str,
    *,
    lower_is_better: bool,
) -> ScenarioSummary | None:
    clean = [
        row
        for row in rows
        if row.endpoint != target_endpoint
        and row.error_count == 0
        and getattr(row, metric) is not None
    ]
    if not clean:
        return None
    return (
        min(clean, key=lambda row: getattr(row, metric))
        if lower_is_better
        else max(clean, key=lambda row: getattr(row, metric))
    )


def _latency_threshold_status(
    target_value: float | None,
    peer_value: float | None,
    threshold_ratio: float,
) -> str:
    if target_value is None or peer_value is None:
        return "missing"
    return "failed" if target_value > peer_value * (1.0 + threshold_ratio) else "ok"


def _throughput_threshold_status(
    target_value: float | None,
    peer_value: float | None,
    threshold_ratio: float,
) -> str:
    if target_value is None or peer_value is None or peer_value <= 0:
        return "missing"
    return "failed" if target_value < peer_value * (1.0 - threshold_ratio) else "ok"


def _delta(target_value: float | None, peer_value: float | None) -> float | None:
    if target_value is None or peer_value is None:
        return None
    return target_value - peer_value


def _percent_delta(target_value: float | None, peer_value: float | None) -> float | None:
    if target_value is None or peer_value is None or peer_value == 0:
        return None
    return ((target_value - peer_value) / peer_value) * 100.0


def _is_regressed_latency(melix_value: float | None, omlx_value: float | None) -> bool:
    if melix_value is None or omlx_value is None:
        return False
    return melix_value > omlx_value * 1.15 and (melix_value - omlx_value) > 25.0


def _is_regressed_throughput(melix_value: float | None, omlx_value: float | None) -> bool:
    if melix_value is None or omlx_value is None or omlx_value <= 0:
        return False
    return melix_value < omlx_value * 0.90


def load_metrics_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        return {"path": str(path), "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    except json.JSONDecodeError as exc:
        return {"path": str(path), "ok": False, "error": f"JSONDecodeError: {exc}"}
    if not isinstance(payload, dict):
        return {"path": str(path), "ok": False, "error": "metrics snapshot must be a JSON object"}
    values = payload.get("values")
    if not isinstance(values, dict):
        return {"path": str(path), "ok": False, "error": "metrics snapshot is missing a values object"}
    return {
        "path": str(path.expanduser()),
        "ok": True,
        "updated_at_unix_ms": payload.get("updated_at_unix_ms"),
        "values": values,
    }


def load_melix_metrics_snapshot(
    *,
    control_plane_path: Path | None,
    swift_text_worker_path: Path | None,
    python_worker_path: Path | None = None,
    runtime_dir: Path | None = None,
    stale_after_seconds: float = melix_metrics_snapshot.DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any] | None:
    if (
        control_plane_path is None
        and swift_text_worker_path is None
        and python_worker_path is None
        and runtime_dir is None
    ):
        return None

    snapshot = melix_metrics_snapshot.build_snapshot_from_paths(
        control_plane_metrics=control_plane_path,
        swift_text_worker_metrics=swift_text_worker_path,
        python_worker_metrics=python_worker_path,
        runtime_dir=runtime_dir,
        stale_after_seconds=stale_after_seconds,
    )
    return snapshot


def enrich_hints_with_metrics(
    hints: list[dict[str, Any]],
    metrics_snapshot: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not metrics_snapshot or metrics_snapshot.get("ok") is not True:
        return hints
    values = metrics_snapshot.get("values")
    if not isinstance(values, dict):
        return hints

    enabled = _numeric_metric(values, "scheduler.multimodal_continuous_batch_enabled")
    blocked_count = _numeric_metric(values, "scheduler.multimodal_continuous_batch_blocked_count")
    requested_capacity = _numeric_metric(
        values,
        "scheduler.multimodal_continuous_batch_requested_capacity",
    )
    effective_capacity = _numeric_metric(
        values,
        "scheduler.multimodal_continuous_batch_effective_capacity",
    )
    reason_code = _numeric_metric(
        values,
        "scheduler.multimodal_continuous_batch_blocked_reason_code",
    )
    if enabled == 0 and (blocked_count or 0) > 0:
        code = int(reason_code or 0)
        hints.append({
            "scenario": {"source": "melix_control_plane_metrics"},
            "area": "continuous_batching",
            "severity": "high",
            "message": "Melix reported that multimodal continuous batching was disabled during the run.",
            "melix_requested_batch_capacity": requested_capacity,
            "melix_effective_batch_capacity": effective_capacity,
            "melix_blocked_count": blocked_count,
            "melix_blocked_reason_code": code,
            "melix_blocked_reason": MELIX_VLM_BATCHING_BLOCKED_REASON_CODES.get(
                code,
                "unknown",
            ),
        })
    admission_cohort_size = _numeric_metric(values, "scheduler.admission_cohort_size")
    if admission_cohort_size is None:
        admission_cohort_size = _numeric_metric(values, "scheduler.continuous_batch_size")
    worker_decode_batch_size = _numeric_metric(values, "swift_text.decode_batch_size")
    model_eval_batch_size = _numeric_metric(values, "swift_text.model_eval_batch_size")
    per_batch_output_tokens_per_second = _numeric_metric(
        values,
        "swift_text.per_batch_output_tokens_per_second",
    )
    worker_execution_batch_size = max(
        value
        for value in (
            worker_decode_batch_size,
            model_eval_batch_size,
            0.0,
        )
        if value is not None
    )
    if (
        admission_cohort_size is not None
        and admission_cohort_size > 1
        and worker_execution_batch_size <= 1
    ):
        hints.append({
            "scenario": {"source": "melix_metrics_snapshot"},
            "area": "continuous_batching",
            "severity": "medium",
            "message": (
                "Melix admitted a multi-request cohort, but worker/model batch "
                "metrics still show singleton execution."
            ),
            "melix_admission_cohort_size": admission_cohort_size,
            "melix_worker_decode_batch_size": worker_decode_batch_size,
            "melix_model_eval_batch_size": model_eval_batch_size,
            "melix_per_batch_output_tokens_per_second": per_batch_output_tokens_per_second,
        })
    return hints


def metrics_manifest_entries(metrics_snapshot: dict[str, Any] | None, *, artifact_name: str) -> dict[str, Any]:
    if metrics_snapshot is None:
        return {}
    entry = {
        "ok": metrics_snapshot.get("ok"),
        "path": metrics_snapshot.get("path"),
        "sources": metrics_snapshot.get("sources"),
        "updated_at_unix_ms": metrics_snapshot.get("updated_at_unix_ms"),
        "artifact": artifact_name,
    }
    entries: dict[str, Any] = {"melix": entry}
    sources = metrics_snapshot.get("sources")
    if isinstance(sources, dict):
        for source_name in ("control_plane", "swift_text_worker", "python_worker"):
            source = sources.get(source_name)
            if not isinstance(source, dict):
                continue
            entries[f"melix_{source_name}"] = {
                "ok": source.get("ok"),
                "path": source.get("path"),
                "updated_at_unix_ms": source.get("updated_at_unix_ms"),
                "freshness": source.get("freshness"),
                "artifact": artifact_name,
            }
    return entries


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def detect_swift_build_mode(path: Path) -> str:
    parts = path.expanduser().parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] != ".build":
            continue
        tail = parts[index + 1 :]
        if "debug" in tail:
            return "debug"
        if "release" in tail:
            return "release"
    return "unknown"


def binary_metadata(path: Path | None, *, build_mode_detector=detect_swift_build_mode) -> dict[str, Any]:
    if path is None:
        return {
            "provided": False,
            "path": None,
            "exists": False,
            "sha256": None,
            "build_mode": "unknown",
        }
    expanded = path.expanduser().resolve(strict=False)
    exists = expanded.is_file()
    sha256 = None
    read_error = None
    if exists:
        try:
            sha256 = file_sha256(expanded)
        except OSError as exc:
            read_error = f"{type(exc).__name__}: {exc}"
    entry = {
        "provided": True,
        "path": str(expanded),
        "exists": exists and read_error is None,
        "sha256": sha256,
        "build_mode": build_mode_detector(expanded),
    }
    if not exists:
        entry["error"] = "binary path does not exist or is not a file"
    elif read_error is not None:
        entry["error"] = f"binary path is not readable: {read_error}"
    return entry


def runtime_metadata_from_args(
    args: argparse.Namespace,
    *,
    endpoints: list[EndpointConfig],
) -> dict[str, Any]:
    endpoint_by_name = {endpoint.name: endpoint for endpoint in endpoints}
    melix = endpoint_by_name.get("melix")
    omlx = endpoint_by_name.get("omlx")
    metadata: dict[str, Any] = {
        "melix": {
            "base_url": melix.base_url if melix is not None else None,
            "model": melix.model if melix is not None else None,
            "revision": args.melix_revision or None,
            "version": args.melix_version or None,
            "binaries": {
                "text_worker": binary_metadata(args.melix_text_worker_binary),
                "control_plane": binary_metadata(args.melix_control_plane_binary),
            },
        },
        "omlx": {
            "base_url": omlx.base_url if omlx is not None else None,
            "model": omlx.model if omlx is not None else None,
            "revision": args.omlx_revision or None,
            "version": args.omlx_version or None,
        },
        "model_snapshot": {
            "path": str(args.model_snapshot_path.expanduser()) if args.model_snapshot_path else None,
        },
    }
    if args.swiftlm_revision or args.swiftlm_version or args.swiftlm_binary is not None:
        metadata["swiftlm"] = {
            "revision": args.swiftlm_revision or None,
            "version": args.swiftlm_version or None,
            "binaries": {
                "server": binary_metadata(args.swiftlm_binary),
            },
        }
    return metadata


def comparison_validity_metadata(
    runtime_metadata: dict[str, Any],
    *,
    comparison_scope: str,
    token_accounting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    melix = runtime_metadata.get("melix")
    melix_binaries = melix.get("binaries", {}) if isinstance(melix, dict) else {}
    binary_names = sorted({
        *REQUIRED_MELIX_PEER_BINARY_NAMES,
        *(melix_binaries.keys() if isinstance(melix_binaries, dict) else ()),
    })
    for name in binary_names:
        entry = melix_binaries.get(name) if isinstance(melix_binaries, dict) else None
        if not isinstance(entry, dict) or entry.get("provided") is not True:
            reasons.append(f"Melix {name} binary metadata was not provided.")
            continue
        if entry.get("exists") is not True:
            reasons.append(
                f"Melix {name} binary error: "
                f"{entry.get('error') or 'binary path is not readable'} "
                f"(path: {entry.get('path')})"
            )
            continue
        if entry.get("build_mode") == "debug":
            reasons.append(
                f"Melix {name} binary uses a debug build path: {entry.get('path')}"
            )
        elif entry.get("build_mode") != "release":
            reasons.append(
                f"Melix {name} binary is not a release build: build_mode={entry.get('build_mode')}"
            )
    if token_accounting is not None:
        if (
            token_accounting.get("mixed_prompt_token_sources") is True
            and token_accounting.get("allow_mixed_token_accounting") is not True
        ):
            reasons.append(
                "Prompt token accounting used mixed sources without --allow-mixed-token-accounting."
            )
        if (
            token_accounting.get("mixed_completion_token_sources") is True
            and token_accounting.get("allow_mixed_token_accounting") is not True
        ):
            reasons.append(
                "Completion token accounting used mixed sources without --allow-mixed-token-accounting."
            )
        if (
            token_accounting.get("allow_mixed_token_accounting") is True
            and (
                token_accounting.get("mixed_prompt_token_sources") is True
                or token_accounting.get("mixed_completion_token_sources") is True
            )
        ):
            warnings.append("Mixed token accounting was explicitly allowed for this run.")

    if comparison_scope == "debug-only":
        return {
            "status": "debug_only",
            "peer_comparison_valid": False,
            "comparison_scope": comparison_scope,
            "reasons": [
                "Run was explicitly declared debug-only; do not use it as a fair peer performance comparison.",
                *reasons,
            ],
            "warnings": warnings,
        }
    if reasons:
        return {
            "status": "invalid",
            "peer_comparison_valid": False,
            "comparison_scope": comparison_scope,
            "reasons": reasons,
            "warnings": warnings,
        }
    return {
        "status": "valid",
        "peer_comparison_valid": True,
        "comparison_scope": comparison_scope,
        "reasons": [],
        "warnings": warnings,
    }


def scenario_matrix_metadata(scenarios: list[BenchmarkScenario]) -> dict[str, Any]:
    repeat_indexes = [scenario.repeat_index for scenario in scenarios]
    prompt_styles = sorted({scenario.prompt_style for scenario in scenarios})
    return {
        "prompt_style": prompt_styles[0] if len(prompt_styles) == 1 else None,
        "prompt_token_targets": sorted({scenario.prompt_token_target for scenario in scenarios}),
        "max_tokens": sorted({scenario.max_tokens for scenario in scenarios}),
        "concurrency": sorted({scenario.concurrency for scenario in scenarios}),
        "cache_profiles": sorted({scenario.cache_profile for scenario in scenarios}),
        "prompt_styles": prompt_styles,
        "repeat_count": (max(repeat_indexes) + 1) if repeat_indexes else 0,
    }


def token_accounting_metadata(
    summaries: list[ScenarioSummary],
    *,
    include_usage_requested: bool,
    allow_mixed_token_accounting: bool,
) -> dict[str, Any]:
    prompt_sources = _split_source_summary(
        summary.prompt_token_sources for summary in summaries
    )
    completion_sources = _split_source_summary(
        summary.completion_token_sources for summary in summaries
    )
    return {
        "include_usage_requested": include_usage_requested,
        "allow_mixed_token_accounting": allow_mixed_token_accounting,
        "observed_prompt_token_sources": prompt_sources,
        "observed_completion_token_sources": completion_sources,
        "mixed_prompt_token_sources": len(prompt_sources) > 1,
        "mixed_completion_token_sources": len(completion_sources) > 1,
    }


def _split_source_summary(values: Iterable[Any]) -> list[str]:
    sources: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        for source in value.split(","):
            source = source.strip()
            if source and source != "unknown":
                sources.add(source)
    return sorted(sources)


def _numeric_metric(values: dict[str, Any], key: str) -> float | None:
    value = values.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def write_artifacts(
    *,
    staging_dir: Path,
    endpoints: list[EndpointConfig],
    scenarios: list[BenchmarkScenario],
    preflight: list[dict[str, Any]],
    warmups: list[RequestObservation],
    warmup_settings: dict[str, Any],
    metrics_snapshot: dict[str, Any] | None,
    observations: list[RequestObservation],
    summaries: list[ScenarioSummary],
    request_phase_rows: list[dict[str, Any]],
    peer_delta_rows: list[dict[str, Any]],
    threshold_status: dict[str, Any],
    hints: list[dict[str, Any]],
    dry_run: bool,
    measurement_profile: dict[str, Any],
    runtime_metadata: dict[str, Any],
    comparison_validity: dict[str, Any],
    token_accounting: dict[str, Any],
) -> dict[str, str]:
    staging_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    paths = {
        "manifest": staging_dir / "manifest.json",
        "observations": staging_dir / "observations.jsonl",
        "summary_json": staging_dir / "summary.json",
        "summary_csv": staging_dir / "summary.csv",
        "summary_markdown": staging_dir / "summary.md",
        "request_phase_rows": staging_dir / "request-phase-rows.json",
        "peer_delta_rows": staging_dir / "peer-delta-rows.json",
        "threshold_status": staging_dir / "threshold-status.json",
    }
    if warmups:
        paths["warmups"] = staging_dir / "warmups.jsonl"
    if metrics_snapshot is not None:
        paths["melix_metrics"] = staging_dir / "melix-metrics.json"
    manifest = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "dry_run": dry_run,
        "measurement_profile": measurement_profile,
        "endpoints": [
            {
                "name": endpoint.name,
                "base_url": endpoint.base_url,
                "model": endpoint.model,
                "header_names": sorted(endpoint.headers.keys()),
            }
            for endpoint in endpoints
        ],
        "scenario_count": len(scenarios),
        "scenario_settings": scenario_matrix_metadata(scenarios),
        "warmup_count": len(warmups),
        "warmup_settings": warmup_settings,
        "runtime_metadata": runtime_metadata,
        "comparison_validity": comparison_validity,
        "token_accounting": token_accounting,
        "observation_count": len(observations),
        "request_phase_row_count": len(request_phase_rows),
        "peer_delta_row_count": len(peer_delta_rows),
        "threshold_status": threshold_status,
        "preflight": preflight,
        "metrics": metrics_manifest_entries(
            metrics_snapshot,
            artifact_name=paths["melix_metrics"].name,
        ) if metrics_snapshot is not None else {},
        "artifacts": {key: path.name for key, path in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if metrics_snapshot is not None:
        paths["melix_metrics"].write_text(
            json.dumps(metrics_snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if warmups:
        with paths["warmups"].open("w", encoding="utf-8") as handle:
            for observation in warmups:
                handle.write(json.dumps(asdict(observation), sort_keys=True) + "\n")
    with paths["observations"].open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(asdict(observation), sort_keys=True) + "\n")
    paths["request_phase_rows"].write_text(
        json.dumps(request_phase_rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["peer_delta_rows"].write_text(
        json.dumps(peer_delta_rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["threshold_status"].write_text(
        json.dumps(threshold_status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "measurement_profile": measurement_profile,
        "runtime_metadata": runtime_metadata,
        "comparison_validity": comparison_validity,
        "token_accounting": token_accounting,
        "melix_metrics_snapshot": metrics_snapshot,
        "warmups": [asdict(observation) for observation in warmups],
        "summaries": [asdict(summary) for summary in summaries],
        "request_phase_rows": request_phase_rows,
        "peer_delta_rows": peer_delta_rows,
        "threshold_status": threshold_status,
        "optimization_hints": hints,
    }
    paths["summary_json"].write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_summary_csv(paths["summary_csv"], summaries)
    paths["summary_markdown"].write_text(
        render_markdown_summary(
            summaries,
            hints,
            preflight=preflight,
            warmups=warmups,
            metrics_snapshot=metrics_snapshot,
            request_phase_rows=request_phase_rows,
            peer_delta_rows=peer_delta_rows,
            threshold_status=threshold_status,
            dry_run=dry_run,
            measurement_profile=measurement_profile,
            runtime_metadata=runtime_metadata,
            comparison_validity=comparison_validity,
        ),
        encoding="utf-8",
    )
    return {key: str(path) for key, path in paths.items()}


def write_summary_csv(path: Path, summaries: list[ScenarioSummary]) -> None:
    fieldnames = list(asdict(summaries[0]).keys()) if summaries else list(ScenarioSummary.__annotations__.keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(asdict(summary))


def runtime_metadata_markdown_rows(runtime_metadata: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for runtime_name in ("melix", "omlx", "swiftlm"):
        runtime = runtime_metadata.get(runtime_name)
        if not isinstance(runtime, dict):
            continue
        model = runtime.get("model") or ""
        revision = runtime.get("revision") or ""
        version = runtime.get("version") or ""
        binaries = runtime.get("binaries")
        if isinstance(binaries, dict) and binaries:
            for binary_name, binary in sorted(binaries.items()):
                if not isinstance(binary, dict):
                    continue
                rows.append(
                    "| {runtime}:{binary_name} | `{model}` | `{revision}` | `{version}` | `{build_mode}` | `{sha256}` |".format(
                        runtime=runtime_name,
                        binary_name=binary_name,
                        model=model,
                        revision=revision,
                        version=version,
                        build_mode=binary.get("build_mode") or "unknown",
                        sha256=binary.get("sha256") or "",
                    )
                )
        else:
            rows.append(
                f"| {runtime_name} | `{model}` | `{revision}` | `{version}` | n/a | n/a |"
            )
    snapshot = runtime_metadata.get("model_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("path"):
        rows.append(f"| model_snapshot | `{snapshot.get('path')}` |  |  | n/a | n/a |")
    return rows


def append_peer_delta_markdown(
    lines: list[str],
    peer_delta_rows: list[dict[str, Any]],
    threshold_status: dict[str, Any] | None,
) -> None:
    lines.append("")
    lines.append("## Peer Delta Rows")
    lines.append("")
    if threshold_status is not None:
        lines.append(
            "- Status: `{status}`; failures: `{failures}`".format(
                status=threshold_status.get("status", "unknown"),
                failures=threshold_status.get("failure_count", 0),
            )
        )
        lines.append("")
    if not peer_delta_rows:
        lines.append("No peer delta rows were generated.")
        return
    lines.append(
        "| Scenario | Total Status | Total Best Peer | Total Target ms | Total Best ms | "
        "Total Delta % | Decode Status | Decode Best Peer | Decode Target tok/s | "
        "Decode Best tok/s | Decode Delta % |"
    )
    lines.append("|---|---|---|---:|---:|---:|---|---|---:|---:|---:|")
    for row in peer_delta_rows:
        scenario = row.get("scenario", {})
        total = row.get("total_latency", {})
        decode = row.get("decode_throughput", {})
        lines.append(
            "| pt={prompt} out={out} c={concurrency} | {total_status} | {total_peer} | {total_target} | {total_best} | {total_delta} | {decode_status} | {decode_peer} | {decode_target} | {decode_best} | {decode_delta} |".format(
                prompt=scenario.get("prompt_token_target", "n/a"),
                out=scenario.get("max_tokens", "n/a"),
                concurrency=scenario.get("concurrency", "n/a"),
                total_status=total.get("status", "missing") if isinstance(total, dict) else "missing",
                total_peer=total.get("best_peer") or "n/a" if isinstance(total, dict) else "n/a",
                total_target=_fmt(total.get("target_median_ms") if isinstance(total, dict) else None),
                total_best=_fmt(total.get("best_peer_median_ms") if isinstance(total, dict) else None),
                total_delta=_fmt(total.get("delta_pct") if isinstance(total, dict) else None),
                decode_status=decode.get("status", "missing") if isinstance(decode, dict) else "missing",
                decode_peer=decode.get("best_peer") or "n/a" if isinstance(decode, dict) else "n/a",
                decode_target=_fmt(
                    decode.get("target_median_tokens_per_second") if isinstance(decode, dict) else None
                ),
                decode_best=_fmt(
                    decode.get("best_peer_median_tokens_per_second") if isinstance(decode, dict) else None
                ),
                decode_delta=_fmt(decode.get("delta_pct") if isinstance(decode, dict) else None),
            )
        )


def append_request_phase_markdown(lines: list[str], request_phase_rows: list[dict[str, Any]]) -> None:
    lines.append("")
    lines.append("## Request Phase Rows")
    lines.append("")
    if not request_phase_rows:
        lines.append("No request phase rows were generated.")
        return
    lines.append(
        "| Endpoint | Scenario | Repeat | Request | Status | Queue ms | Prefill ms | "
        "First HTTP/SSE Event ms | Decode ms | Worker Stream ms | Total ms | Output Tokens | Decode tok/s |"
    )
    lines.append("|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in request_phase_rows:
        lines.append(
            "| {endpoint} | {scenario} | {repeat} | {request} | {status} | {queue} | {prefill} | {first_event} | {decode_ms} | {worker_stream} | {total} | {output_tokens} | {decode_tps} |".format(
                endpoint=row.get("endpoint", ""),
                scenario=row.get("scenario_id", ""),
                repeat=row.get("repeat_index", ""),
                request=row.get("request_index", ""),
                status=row.get("status", ""),
                queue=_fmt(row.get("queue_ms")),
                prefill=_fmt(row.get("prefill_ms")),
                first_event=_fmt(row.get("first_http_sse_event_ms")),
                decode_ms=_fmt(row.get("decode_ms")),
                worker_stream=_fmt(row.get("worker_stream_ms")),
                total=_fmt(row.get("total_ms")),
                output_tokens=_fmt(row.get("output_tokens")),
                decode_tps=_fmt(row.get("decode_tokens_per_second")),
            )
        )


def render_markdown_summary(
    summaries: list[ScenarioSummary],
    hints: list[dict[str, Any]],
    *,
    preflight: list[dict[str, Any]],
    warmups: list[RequestObservation],
    metrics_snapshot: dict[str, Any] | None,
    request_phase_rows: list[dict[str, Any]] | None = None,
    peer_delta_rows: list[dict[str, Any]] | None = None,
    threshold_status: dict[str, Any] | None = None,
    dry_run: bool,
    measurement_profile: dict[str, Any],
    runtime_metadata: dict[str, Any] | None = None,
    comparison_validity: dict[str, Any] | None = None,
) -> str:
    lines = ["# OMLX And Melix Serving Benchmark Summary", ""]
    lines.append(f"- Dry run: `{str(dry_run).lower()}`")
    lines.append(f"- Measurement profile: `{measurement_profile.get('profile', 'unknown')}`")
    if comparison_validity is not None:
        lines.append(f"- Peer comparison status: `{comparison_validity.get('status', 'unknown')}`")
        for reason in comparison_validity.get("reasons") or []:
            lines.append(f"- Peer comparison warning: {reason}")
    if measurement_profile.get("operator_note"):
        lines.append(f"- Measurement note: {measurement_profile['operator_note']}")
    if threshold_status is not None:
        lines.append(f"- Threshold status: `{threshold_status.get('status', 'unknown')}`")
    if runtime_metadata:
        lines.append("")
        lines.append("## Reproducibility")
        lines.append("")
        lines.append("| Runtime | Model | Revision | Version | Binary Build | Binary SHA256 |")
        lines.append("|---|---|---|---|---|---|")
        lines.extend(runtime_metadata_markdown_rows(runtime_metadata))
    lines.append("")
    lines.append("## Preflight")
    lines.append("")
    lines.append("| Endpoint | Status | Model | Model Listed | Model Count |")
    lines.append("|---|---:|---|---:|---:|")
    for item in preflight:
        lines.append(
            "| {endpoint} | {status_code} | `{model}` | {model_listed} | {model_count} |".format(
                endpoint=item.get("endpoint", ""),
                status_code=item.get("status_code", "n/a"),
                model=item.get("model", ""),
                model_listed=item.get("model_listed", "n/a"),
                model_count=item.get("model_count", 0),
            )
        )
    lines.append("")
    lines.append("## Warmup")
    lines.append("")
    if warmups:
        lines.append("| Endpoint | Requests | Errors | Median TTFT ms | Median Total ms |")
        lines.append("|---|---:|---:|---:|---:|")
        for endpoint, rows in sorted(_group_warmups_by_endpoint(warmups).items()):
            successes = [row for row in rows if row.status == "ok"]
            lines.append(
                "| {endpoint} | {requests} | {errors} | {ttft} | {total} |".format(
                    endpoint=endpoint,
                    requests=len(rows),
                    errors=len(rows) - len(successes),
                    ttft=_fmt(median([row.ttft_ms for row in successes])),
                    total=_fmt(median([row.total_ms for row in successes])),
                )
            )
    else:
        lines.append("No warmup requests were run.")
    lines.append("")
    lines.append("## Scenario Summary")
    lines.append("")
    lines.append(
        "| Endpoint | Prompt Target | Prompt Style | Prompt Token Source | Completion Token Source | "
        "Max Tokens | Concurrency | Errors | Median TTFT ms | Median Total ms | "
        "Median Decode tok/s | Median Aggregate tok/s |"
    )
    lines.append("|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for summary in summaries:
        lines.append(
            "| {endpoint} | {prompt} | {prompt_style} | {prompt_token_sources} | {completion_token_sources} | {max_tokens} | {concurrency} | {errors} | {ttft} | {total} | {decode} | {aggregate} |".format(
                endpoint=summary.endpoint,
                prompt=summary.prompt_token_target,
                prompt_style=summary.prompt_style,
                prompt_token_sources=summary.prompt_token_sources,
                completion_token_sources=summary.completion_token_sources,
                max_tokens=summary.max_tokens,
                concurrency=summary.concurrency,
                errors=summary.error_count,
                ttft=_fmt(summary.median_ttft_ms),
                total=_fmt(summary.median_total_ms),
                decode=_fmt(summary.median_decode_tokens_per_second),
                aggregate=_fmt(summary.median_aggregate_output_tokens_per_second),
            )
        )
    append_peer_delta_markdown(lines, peer_delta_rows or [], threshold_status)
    append_request_phase_markdown(lines, request_phase_rows or [])
    if metrics_snapshot is not None:
        lines.append("")
        lines.append("## Melix Metrics Snapshot")
        lines.append("")
        if metrics_snapshot.get("ok") is True:
            values = metrics_snapshot.get("values", {})
            lines.append("| Metric | Value |")
            lines.append("|---|---:|")
            for key in (
                "scheduler.admission_cohort_size",
                "scheduler.admission_active_cohorts",
                "scheduler.multimodal_continuous_batch_enabled",
                "scheduler.multimodal_continuous_batch_requested_capacity",
                "scheduler.multimodal_continuous_batch_effective_capacity",
                "scheduler.multimodal_continuous_batch_blocked_count",
                "scheduler.multimodal_continuous_batch_blocked_reason_code",
                "scheduler.continuous_batch_size",
                "scheduler.continuous_batch_active_cohorts",
                "control_plane.text_first_load_ms",
                "control_plane.text_first_load_estimated_resident_bytes",
                "control_plane.text_first_load_resident_bytes",
                "swift_text.decode_batch_size",
                "swift_text.model_eval_batch_size",
                "swift_text.per_batch_output_token_count",
                "swift_text.per_batch_output_tokens_per_second",
                "swift_text.decode_batch_observation_count",
                "swift_text.prefill_ms",
                "swift_text.prefill_prompt_tokens",
                "swift_text.decode_ttft_ms",
                "swift_text.decode_ms",
                "swift_text.decode_tokens_per_second",
                "scheduler.multimodal_queue_delay_ms",
                "vision.vlm_first_token_ms",
                "vision.multimodal_decode_mode_code",
                "vision.multimodal_fallback_reason_code",
                "vision.multimodal_decode_sync_mode_code",
                "vision.text_batch_generator.submitted_request_count",
                "vision.text_batch_generator.completed_request_count",
                "vision.text_batch_generator.step_count",
                "vision.text_batch_generator.generated_token_count",
                "vision.text_batch_generator.prepare_ms_total",
                "vision.text_batch_generator.first_response_ms_total",
                "vision.text_batch_generator.first_visible_ms_total",
                "vision.text_batch_generator.first_visible_token_index_total",
                "vision.text_batch_generator.first_empty_segment_count",
                "vision.text_batch_generator.peak_active_batch_size",
                "vision.text_batch_generator.queue_wait_ms_total",
                "vision.text_batch_generator.insert_ms_total",
                "vision.text_batch_generator.executor_step_ms_total",
                "vision.text_batch_generator.next_ms_total",
                "vision.text_batch_generator.emit_ms_total",
                "vision.text_batch_generator.speculative_cycle_count_total",
                "vision.text_batch_generator.speculative_accepted_count_total",
                "vision.text_batch_generator.speculative_rejected_count_total",
                "vision.text_batch_generator.speculative_backbone_ms_total",
                "vision.text_batch_generator.speculative_mtp_head_ms_total",
                "vision.text_batch_generator.speculative_sample_ms_total",
                "vision.text_batch_generator.speculative_cache_ops_ms_total",
                "http.parser.text_batch_generator_speculative_cycle_count_total",
                "http.parser.text_batch_generator_speculative_accepted_count_total",
                "http.parser.text_batch_generator_speculative_rejected_count_total",
                "http.parser.text_batch_generator_speculative_backbone_ms_total",
                "http.parser.text_batch_generator_speculative_mtp_head_ms_total",
                "http.parser.text_batch_generator_speculative_sample_ms_total",
                "http.parser.text_batch_generator_speculative_cache_ops_ms_total",
                "http.parser.text_batch_generator_prepare_ms",
                "http.parser.text_batch_generator_prompt_encode_ms",
                "http.parser.text_batch_generator_prefill_ms",
                "http.parser.text_batch_generator_batch_insert_ms",
                "http.parser.text_batch_generator_insert_ms",
                "http.parser.text_batch_generator_first_response_ms",
                "http.parser.text_batch_generator_first_visible_ms",
                "http.stream_first_event_ms",
                "http.text_batch_generator_first_visible_to_stream_first_event_ms",
                "vision.text_batch_generator.active_batch_size",
                "vision.text_batch_generator.generated_response_count",
                "vision.text_batch_generator.failed_request_count",
                "http.ttfd_ms",
            ):
                value = values.get(key) if isinstance(values, dict) else None
                if (
                    key == "http.text_batch_generator_first_visible_to_stream_first_event_ms"
                    and value is None
                    and isinstance(values, dict)
                ):
                    stream_first = _numeric_metric(values, "http.stream_first_event_ms")
                    first_visible = _numeric_metric(
                        values,
                        "http.parser.text_batch_generator_first_visible_ms",
                    )
                    if stream_first is not None and first_visible is not None:
                        value = stream_first - first_visible
                lines.append(f"| `{key}` | {_fmt_metric(value)} |")
        else:
            lines.append(f"Metrics snapshot unavailable: `{metrics_snapshot.get('error', 'unknown')}`")
    lines.append("")
    lines.append("## Optimization Hints")
    lines.append("")
    if not hints:
        lines.append("No Melix regression hints were generated from the collected summaries.")
    else:
        for hint in hints:
            scenario = hint.get("scenario", {})
            lines.append(
                "- `{area}` {message} scenario={scenario}".format(
                    area=hint.get("area", "unknown"),
                    message=hint.get("message", ""),
                    scenario=json.dumps(scenario, sort_keys=True),
                )
            )
    lines.append("")
    return "\n".join(lines)


def _group_warmups_by_endpoint(warmups: list[RequestObservation]) -> dict[str, list[RequestObservation]]:
    grouped: dict[str, list[RequestObservation]] = {}
    for observation in warmups:
        grouped.setdefault(observation.endpoint, []).append(observation)
    return grouped


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _fmt_metric(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.2f}"
    if value is None:
        return "n/a"
    return str(value)


def measurement_profile_metadata(
    *,
    requested_profile: str,
    warmup_requests: int,
    operator_note: str = "",
) -> dict[str, Any]:
    if requested_profile == "auto":
        profile = "warm" if warmup_requests > 0 else "cold"
    else:
        profile = requested_profile
    return {
        "profile": profile,
        "warmup_requests_per_endpoint": warmup_requests,
        "operator_note": operator_note,
    }


def export_bundle(staging_dir: Path, export_dir: Path | None) -> Path | None:
    if export_dir is None:
        return None
    export_dir = export_dir.expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)
    destination = export_dir / staging_dir.name
    if destination.exists():
        suffix = datetime.now(timezone.utc).strftime("%H%M%S")
        destination = export_dir / f"{staging_dir.name}-{suffix}"
    shutil.copytree(staging_dir, destination)
    return destination


def run_warmups(
    endpoints: list[EndpointConfig],
    *,
    request_count: int,
    prompt_token_target: int,
    max_tokens: int,
    prompt_style: str,
    include_usage: bool,
    temperature: float,
    top_p: float,
    top_k: int,
    timeout_seconds: float,
) -> list[RequestObservation]:
    observations: list[RequestObservation] = []
    if request_count <= 0:
        return observations
    for endpoint in endpoints:
        for request_index in range(request_count):
            scenario = BenchmarkScenario(
                scenario_id=f"warmup-pt{prompt_token_target}-out{max_tokens}-r{request_index}",
                prompt_token_target=prompt_token_target,
                max_tokens=max_tokens,
                concurrency=1,
                cache_profile="repeated",
                repeat_index=request_index,
                prompt_style=prompt_style,
            )
            observations.extend(
                run_group(
                    endpoint,
                    scenario,
                    include_usage=include_usage,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    timeout_seconds=timeout_seconds,
                    run_key="warmup",
                )
            )
    return observations


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    endpoints = [
        EndpointConfig(
            name="melix",
            base_url=normalize_base_url(args.melix_base_url),
            model=args.melix_model or args.model,
            headers=parse_header_values(args.melix_header),
        ),
        EndpointConfig(
            name="omlx",
            base_url=normalize_base_url(args.omlx_base_url),
            model=args.omlx_model or args.model,
            headers=parse_header_values(args.omlx_header),
        ),
    ]
    if any(not endpoint.model for endpoint in endpoints):
        raise ValueError("Pass --model, or pass both --melix-model and --omlx-model.")

    scenarios = build_scenarios(
        prompt_token_targets=args.prompt_token_targets,
        max_tokens=args.max_tokens,
        concurrency_values=args.concurrency,
        cache_profile=args.cache_profile,
        prompt_style=args.prompt_style,
        repeats=args.repeats,
    )
    run_id = args.run_id or datetime.now(timezone.utc).strftime("omlx-melix-benchmark-%Y%m%d-%H%M%S")
    staging_dir = args.staging_root.expanduser() / run_id
    measurement_profile = measurement_profile_metadata(
        requested_profile=args.measurement_profile,
        warmup_requests=args.warmup_requests,
        operator_note=args.measurement_profile_note,
    )

    if args.dry_run:
        preflight = [
            {
                "endpoint": endpoint.name,
                "base_url": endpoint.base_url,
                "status_code": "dry-run",
                "ok": None,
                "model": endpoint.model,
                "model_listed": None,
                "model_count": 0,
                "models": [],
                "error": None,
                "attempt_count": 0,
                "elapsed_seconds": 0.0,
            }
            for endpoint in endpoints
        ]
        warmups: list[RequestObservation] = []
        observations: list[RequestObservation] = []
    else:
        preflight = preflight_endpoints(
            endpoints,
            timeout_seconds=args.preflight_timeout_seconds,
            wait_seconds=args.preflight_wait_seconds,
            retry_interval_seconds=args.preflight_retry_interval_seconds,
        )
        if args.preflight_only:
            warmups = []
            observations = []
        else:
            failed = [item for item in preflight if item["ok"] is not True]
            if failed and not args.allow_failed_preflight:
                raise RuntimeError(
                    "Endpoint preflight failed; rerun with --allow-failed-preflight to collect failure observations. "
                    + json.dumps(failed, sort_keys=True)
                )
            warmups = run_warmups(
                endpoints,
                request_count=args.warmup_requests,
                prompt_token_target=args.warmup_prompt_token_target,
                max_tokens=args.warmup_max_tokens,
                prompt_style=args.prompt_style,
                include_usage=args.include_usage,
                temperature=args.temperature,
                top_p=args.top_p,
                top_k=args.top_k,
                timeout_seconds=args.timeout_seconds,
            )
            observations = []
            for scenario in scenarios:
                for endpoint in endpoints_for_scenario(
                    endpoints,
                    scenario,
                    endpoint_order=args.endpoint_order,
                ):
                    observations.extend(
                        run_group(
                            endpoint,
                            scenario,
                            include_usage=args.include_usage,
                            temperature=args.temperature,
                            top_p=args.top_p,
                            top_k=args.top_k,
                            timeout_seconds=args.timeout_seconds,
                            run_key=run_id,
                        )
                    )

    metrics_snapshot = load_melix_metrics_snapshot(
        control_plane_path=args.melix_control_plane_metrics,
        swift_text_worker_path=args.melix_swift_text_worker_metrics,
        python_worker_path=args.melix_python_worker_metrics,
        runtime_dir=args.melix_metrics_runtime_dir,
        stale_after_seconds=args.melix_metrics_stale_after_seconds,
    )
    summaries = summarize_observations(observations)
    runtime_metadata = runtime_metadata_from_args(args, endpoints=endpoints)
    token_accounting = token_accounting_metadata(
        summaries,
        include_usage_requested=args.include_usage,
        allow_mixed_token_accounting=args.allow_mixed_token_accounting,
    )
    comparison_validity = comparison_validity_metadata(
        runtime_metadata,
        comparison_scope=args.comparison_scope,
        token_accounting=token_accounting,
    )
    hints = enrich_hints_with_metrics(comparison_hints(summaries), metrics_snapshot)
    request_phase_rows = build_request_phase_rows(observations)
    peer_delta_rows = build_peer_delta_rows(
        summaries,
        target_endpoint="melix",
        total_latency_threshold_ratio=args.total_latency_threshold_ratio,
        decode_throughput_threshold_ratio=args.decode_throughput_threshold_ratio,
    )
    threshold_status = build_threshold_status(
        peer_delta_rows,
        total_latency_threshold_ratio=args.total_latency_threshold_ratio,
        decode_throughput_threshold_ratio=args.decode_throughput_threshold_ratio,
    )
    warmup_settings = {
        "request_count_per_endpoint": args.warmup_requests,
        "prompt_token_target": args.warmup_prompt_token_target,
        "max_tokens": args.warmup_max_tokens,
        "prompt_style": args.prompt_style,
    }
    artifact_paths = write_artifacts(
        staging_dir=staging_dir,
        endpoints=endpoints,
        scenarios=scenarios,
        preflight=preflight,
        warmups=warmups,
        warmup_settings=warmup_settings,
        metrics_snapshot=metrics_snapshot,
        observations=observations,
        summaries=summaries,
        request_phase_rows=request_phase_rows,
        peer_delta_rows=peer_delta_rows,
        threshold_status=threshold_status,
        hints=hints,
        dry_run=args.dry_run,
        measurement_profile=measurement_profile,
        runtime_metadata=runtime_metadata,
        comparison_validity=comparison_validity,
        token_accounting=token_accounting,
    )
    exported_to = None if args.no_export else export_bundle(staging_dir, args.export_dir)
    return {
        "run_id": run_id,
        "staging_dir": str(staging_dir),
        "exported_to": str(exported_to) if exported_to else None,
        "preflight": preflight,
        "scenario_count": len(scenarios),
        "warmup_count": len(warmups),
        "measurement_profile": measurement_profile["profile"],
        "comparison_validity": comparison_validity,
        "observation_count": len(observations),
        "summary_count": len(summaries),
        "request_phase_row_count": len(request_phase_rows),
        "peer_delta_row_count": len(peer_delta_rows),
        "threshold_status": threshold_status,
        "optimization_hint_count": len(hints),
        "melix_metrics_snapshot": {
            "ok": metrics_snapshot.get("ok"),
            "path": metrics_snapshot.get("path"),
        } if metrics_snapshot is not None else None,
        "artifacts": artifact_paths,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare OMLX and Melix OpenAI-compatible streaming serving performance.",
    )
    parser.add_argument("--melix-base-url", default="http://127.0.0.1:12434/v1")
    parser.add_argument("--omlx-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="", help="Model id to use for both endpoints.")
    parser.add_argument("--melix-model", default="", help="Melix model id; overrides --model.")
    parser.add_argument("--omlx-model", default="", help="OMLX model id; overrides --model.")
    parser.add_argument("--melix-revision", default="", help="Melix git revision used for this run.")
    parser.add_argument("--omlx-revision", default="", help="OMLX git revision used for this run.")
    parser.add_argument("--swiftlm-revision", default="", help="Optional SwiftLM git revision used for an external peer run.")
    parser.add_argument("--melix-version", default="", help="Melix build or CLI version used for this run.")
    parser.add_argument("--omlx-version", default="", help="OMLX package/server version used for this run.")
    parser.add_argument("--swiftlm-version", default="", help="Optional SwiftLM build or server version used for an external peer run.")
    parser.add_argument(
        "--melix-text-worker-binary",
        type=Path,
        default=None,
        help="Melix Swift text-worker binary path; peer reports are invalid when this resolves to a debug build.",
    )
    parser.add_argument(
        "--melix-control-plane-binary",
        type=Path,
        default=None,
        help="Melix Swift control-plane binary path; peer reports are invalid when this resolves to a debug build.",
    )
    parser.add_argument(
        "--swiftlm-binary",
        type=Path,
        default=None,
        help="Optional SwiftLM binary path to hash into the reproducibility manifest.",
    )
    parser.add_argument(
        "--model-snapshot-path",
        type=Path,
        default=None,
        help="Optional local model snapshot path used by the compared servers.",
    )
    parser.add_argument(
        "--comparison-scope",
        choices=COMPARISON_SCOPES,
        default="peer",
        help="Use debug-only to explicitly mark artifacts as unsuitable for peer performance comparison.",
    )
    parser.add_argument("--melix-header", action="append", default=[], help="Extra Melix header, 'Name: value'.")
    parser.add_argument("--omlx-header", action="append", default=[], help="Extra OMLX header, 'Name: value'.")
    parser.add_argument(
        "--prompt-token-targets",
        type=int,
        nargs="+",
        default=DEFAULT_PROMPT_TOKEN_TARGETS,
        help="Synthetic prompt token targets. Endpoint usage is recorded when available.",
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument(
        "--warmup-requests",
        type=int,
        default=0,
        help="Number of warmup streaming requests to run per endpoint after preflight and before measured scenarios.",
    )
    parser.add_argument(
        "--warmup-prompt-token-target",
        type=int,
        default=DEFAULT_WARMUP_PROMPT_TOKEN_TARGET,
    )
    parser.add_argument("--warmup-max-tokens", type=int, default=DEFAULT_WARMUP_MAX_TOKENS)
    parser.add_argument("--concurrency", type=int, nargs="+", default=DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--cache-profile",
        choices=["cold_unique", "repeated"],
        default="cold_unique",
    )
    parser.add_argument(
        "--prompt-style",
        choices=PROMPT_STYLES,
        default="concise",
        help="Use 'saturating' when measuring long decode throughput and avoiding early natural stops.",
    )
    parser.add_argument(
        "--endpoint-order",
        choices=["fixed", "alternate"],
        default="fixed",
        help="Use 'alternate' to reverse Melix/OMLX order on odd repeats and reduce time-drift bias.",
    )
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--top-p", type=float, default=DEFAULT_TOP_P)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--include-usage", action="store_true", help="Request streaming usage chunks.")
    parser.add_argument(
        "--allow-mixed-token-accounting",
        action="store_true",
        help="Keep peer report artifacts when prompt/completion token counts come from mixed usage and estimate sources.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--total-latency-threshold-ratio",
        type=float,
        default=DEFAULT_TOTAL_LATENCY_THRESHOLD_RATIO,
        help="Scenario status fails when target total latency is more than this ratio above the best peer.",
    )
    parser.add_argument(
        "--decode-throughput-threshold-ratio",
        type=float,
        default=DEFAULT_DECODE_THROUGHPUT_THRESHOLD_RATIO,
        help="Scenario status fails when target decode tok/s is more than this ratio below the best peer.",
    )
    parser.add_argument("--preflight-timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--preflight-wait-seconds",
        type=float,
        default=DEFAULT_PREFLIGHT_WAIT_SECONDS,
        help="Wait up to this many seconds for every target model to appear in /v1/models before running requests.",
    )
    parser.add_argument(
        "--preflight-retry-interval-seconds",
        type=float,
        default=DEFAULT_PREFLIGHT_RETRY_INTERVAL_SECONDS,
        help="Seconds between repeated /v1/models checks while --preflight-wait-seconds is active.",
    )
    parser.add_argument(
        "--melix-control-plane-metrics",
        type=Path,
        default=None,
        help="Optional Melix control-plane metrics JSON to snapshot into the report.",
    )
    parser.add_argument(
        "--melix-swift-text-worker-metrics",
        type=Path,
        default=None,
        help="Optional Melix Swift text worker metrics JSON to merge into the report.",
    )
    parser.add_argument(
        "--melix-python-worker-metrics",
        type=Path,
        default=None,
        help="Optional Melix Python worker metrics JSON to merge into the report.",
    )
    parser.add_argument(
        "--melix-metrics-runtime-dir",
        type=Path,
        default=None,
        help="Optional Melix runtime directory used to discover the newest metrics exports.",
    )
    parser.add_argument(
        "--melix-metrics-stale-after-seconds",
        type=float,
        default=melix_metrics_snapshot.DEFAULT_STALE_AFTER_SECONDS,
        help="Freshness threshold recorded for Melix metrics sources.",
    )
    parser.add_argument(
        "--measurement-profile",
        choices=MEASUREMENT_PROFILES,
        default="auto",
        help="Label measured scenarios as cold, warm, or mixed. 'auto' uses warm when warmups are run, otherwise cold.",
    )
    parser.add_argument(
        "--measurement-profile-note",
        default="",
        help="Optional note describing how endpoint residency was prepared before measurement.",
    )
    parser.add_argument("--allow-failed-preflight", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--staging-root",
        type=Path,
        default=Path(".runtime/omlx-melix-benchmark"),
        help="Worktree-local temporary artifact root.",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=Path("~/Downloads"),
        help="Directory that receives the completed artifact bundle.",
    )
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable run metadata.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.repeats < 1:
        raise ValueError("--repeats must be at least 1")
    if args.max_tokens < 1:
        raise ValueError("--max-tokens must be at least 1")
    if args.warmup_requests < 0:
        raise ValueError("--warmup-requests must be at least 0")
    if args.warmup_prompt_token_target < 1:
        raise ValueError("--warmup-prompt-token-target must be positive")
    if args.warmup_max_tokens < 1:
        raise ValueError("--warmup-max-tokens must be at least 1")
    if any(value < 1 for value in args.prompt_token_targets):
        raise ValueError("--prompt-token-targets values must be positive")
    if any(value < 1 for value in args.concurrency):
        raise ValueError("--concurrency values must be positive")
    if args.timeout_seconds <= 0 or args.preflight_timeout_seconds <= 0:
        raise ValueError("Timeout values must be positive")
    if args.total_latency_threshold_ratio < 0:
        raise ValueError("--total-latency-threshold-ratio must be at least 0")
    if not 0.0 <= args.decode_throughput_threshold_ratio <= 1.0:
        raise ValueError("--decode-throughput-threshold-ratio must be between 0.0 and 1.0")
    if args.preflight_wait_seconds < 0:
        raise ValueError("--preflight-wait-seconds must be at least 0")
    if args.preflight_retry_interval_seconds <= 0:
        raise ValueError("--preflight-retry-interval-seconds must be positive")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        result = run_benchmark(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"Run id: {result['run_id']}")
        print(f"Staging dir: {result['staging_dir']}")
        if result["exported_to"]:
            print(f"Exported to: {result['exported_to']}")
        print(f"Scenarios: {result['scenario_count']}")
        print(f"Observations: {result['observation_count']}")
        print(f"Optimization hints: {result['optimization_hint_count']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
