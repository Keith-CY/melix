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


DEFAULT_PROMPT = "Measure the Melix phase one text path."
DEFAULT_ABORT_PROMPT = " ".join(f"abort-token-{index}" for index in range(160))


@dataclass
class StackConfiguration:
    runtime_dir: Path
    swift_socket_path: Path
    python_socket_path: Path
    http_port: int
    swift_backend_mode: str
    python_backend_mode: str


@dataclass
class PathMetrics:
    path: str
    transport: str
    backend_mode: str
    load_model_ms: float | None
    ttft_ms: float | None
    total_ms: float | None
    tokens_per_second: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    abort_ms: float | None
    resident_bytes: int | None
    finish_reason: str | None
    assistant_preview: str | None

    def json_dict(self) -> dict[str, Any]:
        return asdict(self)


def main() -> None:
    parser = argparse.ArgumentParser()
    default_runtime_dir = Path(os.environ.get("MELIX_RUNTIME_DIR", Path(__file__).resolve().parents[1] / ".runtime/phase1"))
    parser.add_argument("--runtime-dir", default=os.fspath(default_runtime_dir))
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--abort-prompt", default=DEFAULT_ABORT_PROMPT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    stack = resolve_stack_configuration(Path(args.runtime_dir))

    report = {
        "generated_at_unix_ms": int(time.time() * 1000),
        "runtime_dir": os.fspath(stack.runtime_dir),
        "swift_backend_mode": stack.swift_backend_mode,
        "python_backend_mode": stack.python_backend_mode,
        "model_id": "melix-dev-text",
        "prompt": args.prompt,
        "paths": [
            collect_direct_worker_metrics(
                socket_path=stack.swift_socket_path,
                backend_mode=stack.swift_backend_mode,
                prompt=args.prompt,
                abort_prompt=args.abort_prompt,
                path_label="swift_worker_direct",
            ).json_dict(),
            collect_direct_worker_metrics(
                socket_path=stack.python_socket_path,
                backend_mode=stack.python_backend_mode,
                prompt=args.prompt,
                abort_prompt=args.abort_prompt,
                path_label="python_worker_direct",
            ).json_dict(),
            measure_http_path(
                http_port=stack.http_port,
                backend_mode=stack.swift_backend_mode,
                prompt=args.prompt,
            ).json_dict(),
        ],
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

    if not swift_socket or not python_socket or not http_port_raw:
        raise RuntimeError(
            "Phase 1 metrics report requires a running stack. Start it with `bash scripts/dev_up.sh` first."
        )

    stack = StackConfiguration(
        runtime_dir=runtime_dir,
        swift_socket_path=Path(swift_socket).resolve(),
        python_socket_path=Path(python_socket).resolve(),
        http_port=int(http_port_raw),
        swift_backend_mode=values.get("MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE", "unknown"),
        python_backend_mode=values.get("MELIX_BACKEND_MODE", "unknown"),
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


def measure_http_path(
    *,
    http_port: int,
    backend_mode: str,
    prompt: str,
) -> PathMetrics:
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

    return PathMetrics(
        path="control_plane_http",
        transport="http-sse",
        backend_mode=backend_mode,
        load_model_ms=None,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        tokens_per_second=tokens_per_second,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        abort_ms=None,
        resident_bytes=None,
        finish_reason=finish_reason,
        assistant_preview="".join(assistant_chunks)[:80],
    )


def collect_direct_worker_metrics(
    *,
    socket_path: Path,
    backend_mode: str,
    prompt: str,
    abort_prompt: str,
    path_label: str,
) -> PathMetrics:
    with grpc.insecure_channel(f"unix://{socket_path}") as channel:
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)

        wait_for_worker_handshake(runtime_stub)

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
            raise RuntimeError(f"LoadModel failed for {path_label}: {load_response.error}")

        stats = runtime_stub.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), timeout=10)
        resident_bytes = int(max(load_response.estimated_resident_bytes, stats.stats.resident_bytes))
        model_handle = load_response.model_handle

        request_id = f"{path_label}-{uuid.uuid4().hex[:8]}"
        started_at = time.perf_counter()
        ttft_ms: float | None = None
        assistant_chunks: list[str] = []
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        finish_reason: str | None = None

        request = inference_pb2.GenerateRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=request_id),
                model_handle=model_handle,
            ),
            messages=[chat_message(prompt)],
            sampling=common_pb2.SamplingConfig(max_output_tokens=64, temperature=0.0),
            stream=True,
            return_usage=True,
        )

        for event in inference_stub.Generate(request, timeout=120):
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
                raise RuntimeError(f"Generate failed for {path_label}: {event.error.error}")

        total_ms = elapsed_ms(started_at)
        completion_tokens = completion_tokens or len(assistant_chunks)
        tokens_per_second = compute_tokens_per_second(completion_tokens, ttft_ms, total_ms)
        abort_ms = measure_abort_latency(inference_stub, model_handle, path_label, abort_prompt)

        unload_response = runtime_stub.UnloadModel(
            runtime_pb2.UnloadModelRequest(model_handle=model_handle),
            timeout=30,
        )
        if not unload_response.ok:
            raise RuntimeError(f"UnloadModel failed for {path_label}: {unload_response.error}")

        return PathMetrics(
            path=path_label,
            transport="grpc-uds",
            backend_mode=backend_mode,
            load_model_ms=load_model_ms,
            ttft_ms=ttft_ms,
            total_ms=total_ms,
            tokens_per_second=tokens_per_second,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            abort_ms=abort_ms,
            resident_bytes=resident_bytes,
            finish_reason=finish_reason,
            assistant_preview="".join(assistant_chunks)[:80],
        )


def wait_for_worker_handshake(
    runtime_stub: runtime_pb2_grpc.RuntimeServiceStub,
    *,
    timeout_seconds: float = 30,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            response = runtime_stub.Handshake(
                runtime_pb2.HandshakeRequest(
                    protocol_version="melix.worker.v1",
                    worker_id="phase1-metrics",
                    controlplane_instance_id="phase1-metrics",
                ),
                timeout=2,
            )
            if response.protocol_version == "melix.worker.v1":
                return
        except grpc.RpcError as exc:
            last_error = exc
        time.sleep(0.2)

    raise RuntimeError(f"Worker handshake did not complete within {timeout_seconds:.1f}s: {last_error}")


def measure_abort_latency(
    inference_stub: inference_pb2_grpc.InferenceServiceStub,
    model_handle: str,
    path_label: str,
    abort_prompt: str,
) -> float:
    request_id = f"{path_label}-abort-{uuid.uuid4().hex[:8]}"
    first_token_seen = threading.Event()
    outcome: dict[str, Any] = {}

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=request_id),
            model_handle=model_handle,
        ),
        messages=[chat_message(abort_prompt)],
        sampling=common_pb2.SamplingConfig(max_output_tokens=160, temperature=0.0),
        stream=True,
        return_usage=False,
    )

    def consume() -> None:
        try:
            for event in inference_stub.Generate(request, timeout=120):
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
        raise RuntimeError(f"Abort probe never emitted a token for {path_label}.")

    abort_started_at = time.perf_counter()
    abort_response = inference_stub.Abort(
        inference_pb2.AbortRequest(request_id=request_id),
        timeout=30,
    )
    abort_ms = elapsed_ms(abort_started_at)

    thread.join(timeout=30)
    if thread.is_alive():
        raise RuntimeError(f"Abort probe did not finish cleanly for {path_label}.")
    if not abort_response.ok or not abort_response.found:
        raise RuntimeError(f"Abort RPC did not acknowledge request {request_id}.")
    if outcome.get("exception"):
        raise RuntimeError(f"Abort probe raised unexpectedly for {path_label}: {outcome['exception']}")
    if outcome.get("error"):
        raise RuntimeError(f"Abort probe returned an error for {path_label}: {outcome['error']}")
    if outcome.get("finish_reason") != "cancelled":
        raise RuntimeError(
            f"Abort probe finished with unexpected reason for {path_label}: {outcome.get('finish_reason')}"
        )
    return abort_ms


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
        "Melix Phase 1 Metrics Report",
        f"runtime_dir: {report['runtime_dir']}",
        f"swift_backend_mode: {report['swift_backend_mode']}",
        f"python_backend_mode: {report['python_backend_mode']}",
        f"model_id: {report['model_id']}",
        "",
        format_table(report["paths"]),
        "",
        "JSON",
        json.dumps(report, indent=2, sort_keys=True),
    ]
    return "\n".join(lines)


def format_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "path",
        "backend_mode",
        "transport",
        "load_model_ms",
        "ttft_ms",
        "total_ms",
        "tokens_per_second",
        "completion_tokens",
        "abort_ms",
        "finish_reason",
    ]

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
