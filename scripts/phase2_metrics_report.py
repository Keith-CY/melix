#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import grpc

from packages.protocol.python.worker.v1 import (
    common_pb2,
    inference_pb2,
    inference_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)


DEFAULT_HTTP_PROMPT = "Measure the Melix phase two text path."
DEFAULT_QUEUE_PROMPT = "\n".join(
    [
        "phase-two-queue-pressure",
        "{",
        '  "task": "queue-pressure",',
        '  "repeat": ["alpha", "beta", "gamma", "delta"],',
        '  "shape": {"kind": "structured", "lane": "interactive"}',
        "}",
    ]
)
DEFAULT_ABORT_PROMPT = " ".join(f"decode-abort-{index}" for index in range(200))


@dataclass
class StackConfiguration:
    runtime_dir: Path
    swift_socket_path: Path
    python_socket_path: Path
    http_port: int
    swift_backend_mode: str
    python_backend_mode: str
    control_plane_metrics_path: Path
    swift_worker_metrics_path: Path


@dataclass
class StreamMetrics:
    label: str
    transport: str
    ttft_ms: float | None
    total_ms: float | None
    tokens_per_second: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    finish_reason: str | None
    request_id: str | None
    assistant_preview: str | None

    def json_dict(self) -> dict[str, Any]:
        return asdict(self)


def main() -> None:
    parser = argparse.ArgumentParser()
    default_runtime_dir = Path(
        os.environ.get("MELIX_RUNTIME_DIR", Path(__file__).resolve().parents[1] / ".runtime/phase2")
    )
    parser.add_argument("--runtime-dir", default=os.fspath(default_runtime_dir))
    parser.add_argument("--http-prompt", default=DEFAULT_HTTP_PROMPT)
    parser.add_argument("--queue-prompt", default=DEFAULT_QUEUE_PROMPT)
    parser.add_argument("--abort-prompt", default=DEFAULT_ABORT_PROMPT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    stack = resolve_stack_configuration(Path(args.runtime_dir))
    baseline_http = measure_http_stream(stack.http_port, args.http_prompt, label="http_baseline")
    queue_pressure = measure_queue_pressure(stack, args.queue_prompt)

    direct_worker = collect_direct_phase_two_metrics(
        stack=stack,
        prompt=args.http_prompt,
        queue_prompt=args.queue_prompt,
        abort_prompt=args.abort_prompt,
    )

    report = {
        "generated_at_unix_ms": int(time.time() * 1000),
        "runtime_dir": os.fspath(stack.runtime_dir),
        "swift_backend_mode": stack.swift_backend_mode,
        "python_backend_mode": stack.python_backend_mode,
        "model_id": "melix-dev-text",
        "http_baseline": baseline_http,
        "queue_pressure": queue_pressure,
        **direct_worker,
        "control_plane_metrics": read_metrics_export(stack.control_plane_metrics_path),
        "swift_worker_metrics": read_metrics_export(stack.swift_worker_metrics_path),
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_report(report))


def resolve_stack_configuration(runtime_dir: Path) -> StackConfiguration:
    values = dict(parse_env_file(runtime_dir / "env.sh"))
    values.update({key: value for key, value in os.environ.items() if key.startswith("MELIX_")})

    swift_socket = values.get("MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH")
    python_socket = values.get("MELIX_WORKER_SOCKET_PATH")
    http_port_raw = values.get("MELIX_HTTP_PORT")
    control_plane_metrics = values.get("MELIX_CONTROL_PLANE_METRICS_PATH")
    swift_worker_metrics = values.get("MELIX_SWIFT_TEXT_WORKER_METRICS_PATH")

    if not swift_socket or not python_socket or not http_port_raw:
        raise RuntimeError("Phase 2 metrics report requires a running stack. Start it with `bash scripts/dev_up.sh` first.")
    if not control_plane_metrics or not swift_worker_metrics:
        raise RuntimeError("Phase 2 metrics report requires metrics export paths from the running stack.")

    stack = StackConfiguration(
        runtime_dir=runtime_dir,
        swift_socket_path=Path(swift_socket).resolve(),
        python_socket_path=Path(python_socket).resolve(),
        http_port=int(http_port_raw),
        swift_backend_mode=values.get("MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE", "unknown"),
        python_backend_mode=values.get("MELIX_BACKEND_MODE", "unknown"),
        control_plane_metrics_path=Path(control_plane_metrics),
        swift_worker_metrics_path=Path(swift_worker_metrics),
    )

    if not stack.swift_socket_path.exists():
        raise RuntimeError(f"Swift text worker socket does not exist: {stack.swift_socket_path}")
    if not stack.python_socket_path.exists():
        raise RuntimeError(f"Python compatibility worker socket does not exist: {stack.python_socket_path}")

    return stack


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("export "):
            continue
        key, _, raw_value = line.removeprefix("export ").partition("=")
        values[key] = raw_value.strip().strip('"')
    return values


def collect_direct_phase_two_metrics(
    *,
    stack: StackConfiguration,
    prompt: str,
    queue_prompt: str,
    abort_prompt: str,
) -> dict[str, Any]:
    with grpc.insecure_channel(f"unix://{stack.swift_socket_path}") as channel:
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)
        wait_for_worker_handshake(runtime_stub, worker_id="phase2-metrics", control_plane_id="phase2-metrics")

        load_started_at = time.perf_counter()
        load_response = runtime_stub.LoadModel(
            runtime_pb2.LoadModelRequest(
                model=dev_text_model_spec(),
                memory_budget_bytes=0,
                pin_on_load=False,
                warmup_after_load=False,
            ),
            timeout=120,
        )
        load_model_ms = elapsed_ms(load_started_at)
        if not load_response.ok:
            raise RuntimeError(f"LoadModel failed for phase 2 metrics: {load_response.error}")

        stats = runtime_stub.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), timeout=10)
        model_handle = load_response.model_handle

        prefill_baseline = measure_prefill_probe(
            inference_stub,
            stack.swift_worker_metrics_path,
            model_handle=model_handle,
            prompt=queue_prompt,
            label="prefill_baseline",
            policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_BASELINE,
                allow_baseline_fallback=True,
            ),
        )
        prefill_accelerated = measure_prefill_probe(
            inference_stub,
            stack.swift_worker_metrics_path,
            model_handle=model_handle,
            prompt=queue_prompt,
            label="prefill_accelerated",
            policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_ACCELERATED_PREFILL,
                profile_id="lookup-v1",
                prefill_hint="lookup-schema",
                allow_baseline_fallback=True,
            ),
        )
        decode_baseline = measure_decode_probe(
            inference_stub,
            stack.swift_worker_metrics_path,
            model_handle=model_handle,
            prompt=prompt,
            label="decode_baseline",
            policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_BASELINE,
                allow_baseline_fallback=True,
            ),
        )
        decode_speculative = measure_decode_probe(
            inference_stub,
            stack.swift_worker_metrics_path,
            model_handle=model_handle,
            prompt=prompt,
            label="decode_speculative",
            policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
                profile_id="draft-q4",
                draft_model_id="melix-dev-text-draft",
                allow_baseline_fallback=True,
            ),
        )
        decode_active_kv = measure_decode_probe(
            inference_stub,
            stack.swift_worker_metrics_path,
            model_handle=model_handle,
            prompt=prompt,
            label="decode_active_kv_quantized",
            policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_ACTIVE_KV_QUANTIZED,
                profile_id="q4-active-kv",
                active_kv_quant_profile="q4",
                allow_baseline_fallback=True,
            ),
        )
        abort_probe = measure_decode_abort(
            inference_stub,
            model_handle=model_handle,
            prompt=abort_prompt,
        )

        unload = runtime_stub.UnloadModel(
            runtime_pb2.UnloadModelRequest(model_handle=model_handle),
            timeout=30,
        )
        if not unload.ok:
            raise RuntimeError(f"UnloadModel failed for phase 2 metrics: {unload.error}")

    return {
        "swift_worker_direct": {
            "load_model_ms": load_model_ms,
            "resident_bytes": int(max(load_response.estimated_resident_bytes, stats.stats.resident_bytes)),
            "prefill": [prefill_baseline, prefill_accelerated],
            "decode": [decode_baseline, decode_speculative, decode_active_kv],
            "abort": abort_probe,
        }
    }


def measure_http_stream(http_port: int, prompt: str, *, label: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{http_port}/v1/chat/completions",
        data=json.dumps(
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )

    started_at = time.perf_counter()
    ttft_ms: float | None = None
    current_event = "message"
    assistant_chunks: list[str] = []
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    request_id: str | None = None

    with urllib.request.urlopen(request, timeout=120) as response:
        while True:
            line = response.readline()
            if not line:
                break
            decoded = line.decode("utf-8").strip()
            if not decoded:
                continue
            if decoded.startswith("event: "):
                current_event = decoded.removeprefix("event: ").strip()
                continue
            if not decoded.startswith("data: "):
                continue

            payload_text = decoded.removeprefix("data: ").strip()
            if payload_text == "[DONE]":
                break

            payload = json.loads(payload_text)
            if current_event == "error":
                raise RuntimeError(f"HTTP path returned an error payload: {payload}")
            if current_event == "usage":
                usage = payload.get("usage", {})
                prompt_tokens = int(usage.get("prompt_tokens", 0))
                completion_tokens = int(usage.get("completion_tokens", 0))
                continue

            if current_event != "message":
                continue

            request_id = request_id or payload.get("id") or payload.get("request_id")
            choices = payload.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta", {})
            content = delta.get("content", "")
            if content:
                if ttft_ms is None:
                    ttft_ms = elapsed_ms(started_at)
                assistant_chunks.append(content)
            if choice.get("finish_reason"):
                finish_reason = str(choice["finish_reason"])

    total_ms = elapsed_ms(started_at)
    completion_tokens = completion_tokens or len(assistant_chunks)
    tokens_per_second = compute_tokens_per_second(completion_tokens, ttft_ms, total_ms)

    return StreamMetrics(
        label=label,
        transport="http-sse",
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        tokens_per_second=tokens_per_second,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        finish_reason=finish_reason,
        request_id=str(request_id) if request_id else None,
        assistant_preview="".join(assistant_chunks)[:80],
    ).json_dict()


def measure_queue_pressure(stack: StackConfiguration, prompt: str) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}

    def run(label: str) -> None:
        results[label] = measure_http_stream(stack.http_port, prompt, label=label)

    leader = threading.Thread(target=run, args=("queue_leader",), daemon=True)
    follower = threading.Thread(target=run, args=("queue_follower",), daemon=True)
    leader.start()
    time.sleep(0.05)
    follower.start()
    leader.join(timeout=120)
    follower.join(timeout=120)
    if leader.is_alive() or follower.is_alive():
        raise RuntimeError("Queue-pressure benchmark did not finish within the timeout.")

    metrics = read_metrics_export(stack.control_plane_metrics_path)
    scheduler = metrics.get("values", {})
    baseline_ttft = results["queue_leader"].get("ttft_ms")
    follower_ttft = results["queue_follower"].get("ttft_ms")
    observed_queue_delay = None
    if isinstance(baseline_ttft, (int, float)) and isinstance(follower_ttft, (int, float)):
        observed_queue_delay = round(max(float(follower_ttft) - float(baseline_ttft), 0.0), 2)

    return {
        "leader": results["queue_leader"],
        "follower": results["queue_follower"],
        "observed_queue_delay_ms": observed_queue_delay,
        "scheduler": {
            "admission_latency_ms": scheduler.get("scheduler.admission_latency_ms"),
            "queue_delay_ms": scheduler.get("scheduler.queue_delay_ms"),
            "queued_requests": scheduler.get("scheduler.queued_requests"),
            "active_requests": scheduler.get("scheduler.active_requests"),
            "active_lane_depth": scheduler.get("scheduler.active_lane_depth"),
            "backpressure": scheduler.get("scheduler.backpressure"),
        },
    }


def measure_prefill_probe(
    inference_stub: inference_pb2_grpc.InferenceServiceStub,
    metrics_path: Path,
    *,
    model_handle: str,
    prompt: str,
    label: str,
    policy: common_pb2.AccelerationPolicy,
) -> dict[str, Any]:
    request_id = f"{label}-{uuid.uuid4().hex[:8]}"
    request = inference_pb2.PrefillRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=request_id),
            model_handle=model_handle,
            acceleration=policy,
        ),
        messages=[chat_message(prompt)],
        prefill_step_size=16,
        return_decode_handle=True,
        resume_hint=label,
    )

    started_at = time.perf_counter()
    response = inference_stub.Prefill(request, timeout=120)
    total_ms = elapsed_ms(started_at)
    if not response.ok:
        raise RuntimeError(f"Prefill failed for {label}: {response.error}")

    exported = read_metrics_export(metrics_path).get("values", {})
    return {
        "label": label,
        "mode": acceleration_mode_name(response.applied_acceleration.mode),
        "profile_id": response.applied_acceleration.profile_id or None,
        "prompt_tokens": int(response.prompt_tokens),
        "total_ms": total_ms,
        "decode_handle": response.decode_handle or None,
        "accelerated_prefill_gain_pct": exported.get("swift_text.accelerated_prefill_gain_pct"),
        "active_kv_quantization_ratio": exported.get("swift_text.active_kv_quantization_ratio"),
        "worker_prefill_ms": exported.get("swift_text.prefill_ms"),
    }


def measure_decode_probe(
    inference_stub: inference_pb2_grpc.InferenceServiceStub,
    metrics_path: Path,
    *,
    model_handle: str,
    prompt: str,
    label: str,
    policy: common_pb2.AccelerationPolicy,
) -> dict[str, Any]:
    prefill = inference_stub.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=f"{label}-prefill-{uuid.uuid4().hex[:8]}"),
                model_handle=model_handle,
                acceleration=policy,
            ),
            messages=[chat_message(prompt)],
            prefill_step_size=16,
            return_decode_handle=True,
            resume_hint=label,
        ),
        timeout=120,
    )
    if not prefill.ok:
        raise RuntimeError(f"Prefill failed for {label}: {prefill.error}")

    decode_request = inference_pb2.DecodeRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=f"{label}-decode-{uuid.uuid4().hex[:8]}"),
            model_handle=model_handle,
            acceleration=policy,
        ),
        decode_handle=prefill.decode_handle,
        sampling=common_pb2.SamplingConfig(max_output_tokens=64, temperature=0.0),
        max_output_tokens=64,
        return_usage=True,
        decode_step_size=4,
        prefill_token="phase2",
    )

    started_at = time.perf_counter()
    ttft_ms: float | None = None
    assistant_chunks: list[str] = []
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None

    for event in inference_stub.Decode(decode_request, timeout=120):
        if event.HasField("token_delta"):
            if ttft_ms is None:
                ttft_ms = elapsed_ms(started_at)
            assistant_chunks.append(event.token_delta.text)
        elif event.HasField("usage_delta"):
            prompt_tokens = int(event.usage_delta.prompt_tokens)
            completion_tokens = int(event.usage_delta.completion_tokens)
        elif event.HasField("completed"):
            finish_reason = event.completed.finish_reason
        elif event.HasField("error"):
            raise RuntimeError(f"Decode failed for {label}: {event.error.error}")

    total_ms = elapsed_ms(started_at)
    completion_tokens = completion_tokens or len(assistant_chunks)
    exported = read_metrics_export(metrics_path).get("values", {})

    return {
        "label": label,
        "mode": acceleration_mode_name(policy.mode),
        "profile_id": policy.profile_id or None,
        "draft_model_id": policy.draft_model_id or None,
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "tokens_per_second": compute_tokens_per_second(completion_tokens, ttft_ms, total_ms),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "finish_reason": finish_reason,
        "assistant_preview": "".join(assistant_chunks)[:80],
        "worker_decode_ttft_ms": exported.get("swift_text.decode_ttft_ms"),
        "worker_decode_tokens_per_second": exported.get("swift_text.decode_tokens_per_second"),
        "speculative_acceptance_rate": exported.get("swift_text.speculative_acceptance_rate"),
        "speculative_rollback_rate": exported.get("swift_text.speculative_rollback_rate"),
        "active_kv_quantization_ratio": exported.get("swift_text.active_kv_quantization_ratio"),
    }


def measure_decode_abort(
    inference_stub: inference_pb2_grpc.InferenceServiceStub,
    *,
    model_handle: str,
    prompt: str,
) -> dict[str, Any]:
    request_id = f"phase2-decode-abort-{uuid.uuid4().hex[:8]}"
    prefill = inference_stub.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=f"{request_id}-prefill"),
                model_handle=model_handle,
                acceleration=common_pb2.AccelerationPolicy(
                    mode=common_pb2.ACCELERATION_MODE_BASELINE,
                    allow_baseline_fallback=True,
                ),
            ),
            messages=[chat_message(prompt)],
            prefill_step_size=16,
            return_decode_handle=True,
            resume_hint="abort",
        ),
        timeout=120,
    )
    if not prefill.ok:
        raise RuntimeError(f"Abort prefill failed: {prefill.error}")

    first_token_seen = threading.Event()
    outcome: dict[str, Any] = {}

    decode_request = inference_pb2.DecodeRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=request_id),
            model_handle=model_handle,
            acceleration=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_BASELINE,
                allow_baseline_fallback=True,
            ),
        ),
        decode_handle=prefill.decode_handle,
        sampling=common_pb2.SamplingConfig(max_output_tokens=128, temperature=0.0),
        max_output_tokens=128,
        return_usage=False,
        decode_step_size=4,
    )

    def consume() -> None:
        try:
            for event in inference_stub.Decode(decode_request, timeout=120):
                if event.HasField("token_delta"):
                    first_token_seen.set()
                elif event.HasField("completed"):
                    outcome["finish_reason"] = event.completed.finish_reason
                elif event.HasField("error"):
                    outcome["error"] = {
                        "code": event.error.error.code,
                        "message": event.error.error.message,
                    }
        except Exception as exc:  # pragma: no cover - surfaced to caller
            outcome["exception"] = repr(exc)

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()

    if not first_token_seen.wait(timeout=10):
        raise RuntimeError("Decode abort probe never emitted a token.")

    abort_started_at = time.perf_counter()
    abort_response = inference_stub.Abort(
        inference_pb2.AbortRequest(request_id=request_id),
        timeout=30,
    )
    abort_ms = elapsed_ms(abort_started_at)

    thread.join(timeout=30)
    if thread.is_alive():
        raise RuntimeError("Decode abort probe did not finish cleanly.")
    if not abort_response.ok or not abort_response.found:
        raise RuntimeError(f"Abort RPC did not acknowledge request {request_id}.")
    if outcome.get("exception"):
        raise RuntimeError(f"Decode abort probe raised unexpectedly: {outcome['exception']}")
    if outcome.get("error"):
        raise RuntimeError(f"Decode abort probe returned an error: {outcome['error']}")
    if outcome.get("finish_reason") != "cancelled":
        raise RuntimeError(f"Decode abort finished with unexpected reason: {outcome.get('finish_reason')}")

    return {
        "label": "decode_abort",
        "abort_ms": abort_ms,
        "finish_reason": outcome.get("finish_reason"),
    }


def wait_for_worker_handshake(
    runtime_stub: runtime_pb2_grpc.RuntimeServiceStub,
    *,
    worker_id: str,
    control_plane_id: str,
    timeout_seconds: float = 30,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            response = runtime_stub.Handshake(
                runtime_pb2.HandshakeRequest(
                    protocol_version="melix.worker.v1",
                    worker_id=worker_id,
                    controlplane_instance_id=control_plane_id,
                ),
                timeout=2,
            )
            if response.protocol_version == "melix.worker.v1":
                return
        except grpc.RpcError as exc:
            last_error = exc
        time.sleep(0.2)

    raise RuntimeError(f"Worker handshake did not complete within {timeout_seconds:.1f}s: {last_error}")


def read_metrics_export(path: Path) -> dict[str, Any]:
    deadline = time.time() + 5
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            last_error = exc
        time.sleep(0.05)
    if last_error:
        raise RuntimeError(f"Unable to read metrics export from {path}: {last_error}")
    return {"values": {}}


def dev_text_model_spec() -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="melix-dev-text",
        model_path=os.environ.get("MELIX_DEV_TEXT_MODEL_PATH", "models/melix-dev-text"),
        model_kind="text",
        revision="dev",
        tokenizer_hash="tok-dev",
        quant_profile_id="q4",
        parser_mode="text",
        reasoning_mode="off",
        max_context=8192,
    )


def chat_message(text: str) -> common_pb2.ChatMessage:
    return common_pb2.ChatMessage(
        role="user",
        parts=[common_pb2.MessagePart(text=text)],
    )


def acceleration_mode_name(mode: int) -> str:
    try:
        return common_pb2.AccelerationMode.Name(mode)
    except ValueError:
        return str(mode)


def compute_tokens_per_second(
    completion_tokens: int | None,
    ttft_ms: float | None,
    total_ms: float | None,
) -> float | None:
    if completion_tokens is None or total_ms is None:
        return None
    completion_window_ms = max(total_ms - (ttft_ms or 0), 1.0)
    return round(completion_tokens / (completion_window_ms / 1000.0), 2)


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 2)


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "Melix Phase 2 Metrics Report",
        f"runtime_dir: {report['runtime_dir']}",
        f"swift_backend_mode: {report['swift_backend_mode']}",
        f"python_backend_mode: {report['python_backend_mode']}",
        "",
        "HTTP Baseline",
        format_table([report["http_baseline"]], ["label", "ttft_ms", "total_ms", "tokens_per_second", "completion_tokens", "finish_reason"]),
        "",
        "Queue Pressure",
        format_table(
            [report["queue_pressure"]["leader"], report["queue_pressure"]["follower"]],
            ["label", "ttft_ms", "total_ms", "tokens_per_second", "completion_tokens", "finish_reason"],
        ),
        format_table(
            [report["queue_pressure"]["scheduler"]],
            ["admission_latency_ms", "queue_delay_ms", "queued_requests", "active_requests", "active_lane_depth", "backpressure"],
        ),
        "",
        "Swift Worker Prefill",
        format_table(
            report["swift_worker_direct"]["prefill"],
            ["label", "mode", "total_ms", "worker_prefill_ms", "prompt_tokens", "accelerated_prefill_gain_pct", "active_kv_quantization_ratio"],
        ),
        "",
        "Swift Worker Decode",
        format_table(
            report["swift_worker_direct"]["decode"],
            ["label", "mode", "ttft_ms", "total_ms", "tokens_per_second", "worker_decode_tokens_per_second", "speculative_acceptance_rate", "speculative_rollback_rate", "active_kv_quantization_ratio"],
        ),
        "",
        "Abort",
        format_table([report["swift_worker_direct"]["abort"]], ["label", "abort_ms", "finish_reason"]),
        "",
        "JSON",
        json.dumps(report, indent=2, sort_keys=True),
    ]
    return "\n".join(lines)


def format_table(rows: list[dict[str, Any]], headers: list[str]) -> str:
    rendered_rows: list[list[str]] = []
    widths = [len(header) for header in headers]

    for row in rows:
        rendered = [stringify_cell(row.get(header)) for header in headers]
        rendered_rows.append(rendered)
        widths = [max(width, len(value)) for width, value in zip(widths, rendered)]

    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    header_row = "| " + " | ".join(header.ljust(width) for header, width in zip(headers, widths)) + " |"
    body_rows = [
        "| " + " | ".join(value.ljust(width) for value, width in zip(row, widths)) + " |"
        for row in rendered_rows
    ]

    return "\n".join([border, header_row, border, *body_rows, border])


def stringify_cell(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


if __name__ == "__main__":
    main()
