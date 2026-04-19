#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import grpc

try:
    from scripts.real_model_support import resolve_real_small_text_model_source
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/...` execution fallback.
    from real_model_support import resolve_real_small_text_model_source  # type: ignore[no-redef]

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
TURBOQUANT_FUSED_MAX_WORKER_TPS_OVERHEAD_PCT = 15.0
TURBOQUANT_FUSED_CAPABILITY_EVIDENCE = {
    "status": "smoke_proven",
    "runtime_path": "not_connected",
    "dispatch": "single_custom_metal_dispatch",
    "quantization": "mse_q4",
    "operations": ["key_score", "stable_softmax", "value_accumulate"],
    "smoke_tests": [
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsCustomIdentityKernel",
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4ValueDecodeKernel",
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionKernel",
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState",
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRejectsUnsupportedQuantizedKVCacheStateInputs",
        "WorkerScaffoldTests.testTurboQuantCandidateDispatchReadsQuantizedKVCacheState",
        "WorkerScaffoldTests.testTurboQuantRuntimeRouteStaysBlockedUntilAttentionHookIsAvailable",
    ],
}
TURBOQUANT_FUSED_RUNTIME_REQUIREMENTS = [
    "active_kv_kernel_path != fallback",
    "active_kv_fallback_count == 0",
    "active_kv_decode_quantize_total_us == 0",
    "active_kv_estimated_memory_savings_pct >= 67",
    "worker_tps_overhead_pct <= 15",
    "--require-fused-turboquant exits 0",
]


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


@dataclass(frozen=True)
class Phase2ModelConfiguration:
    model_id: str
    model_path: str
    revision: str
    source_resolution_mode: str
    warnings: tuple[str, ...] = ()


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
    parser.add_argument("--decode-repeats", type=int, default=1)
    parser.add_argument("--active-kv-profiles", default="q4")
    parser.add_argument("--model-id", default="", help="Model id sent to HTTP and worker probes.")
    parser.add_argument("--model-path", default="", help="Model path or Hub id used by direct worker probes.")
    parser.add_argument("--model-revision", default="", help="Model revision used by direct worker probes.")
    parser.add_argument(
        "--real-small-model",
        action="store_true",
        help="Use the shared Phase 8 real small text model for the Phase 2 probe run.",
    )
    parser.add_argument(
        "--skip-abort",
        action="store_true",
        help="Skip the decode abort subprobe while still collecting prefill/decode metrics.",
    )
    parser.add_argument("--output", default="", help="Optional path to write the rendered report.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--input-json",
        default="",
        help="Read an existing Phase 2 report JSON, backfill derived gates, and emit it without probing a live stack.",
    )
    parser.add_argument(
        "--require-fused-turboquant",
        action="store_true",
        help="Exit non-zero unless the turboquant-q4 probe reports a non-fallback fused decode kernel.",
    )
    args = parser.parse_args()

    if args.input_json:
        report = load_report_json(Path(args.input_json))
        ensure_active_kv_release_gates(report)
        rendered = emit_report(
            report,
            json_output=bool(args.json),
            output_path=Path(args.output) if args.output else None,
        )
        print(rendered)
        if args.require_fused_turboquant:
            failures = fused_turboquant_gate_failures(report)
            if failures:
                raise SystemExit(f"Phase 2 fused TurboQuant gate failed: {'; '.join(failures)}")
        return

    stack = resolve_stack_configuration(Path(args.runtime_dir))
    model = resolve_model_configuration(
        real_small_model=bool(args.real_small_model),
        model_id=str(args.model_id or ""),
        model_path=str(args.model_path or ""),
        model_revision=str(args.model_revision or ""),
        environment=os.environ,
    )
    baseline_http = measure_http_stream(
        stack.http_port,
        args.http_prompt,
        label="http_baseline",
        model_id=model.model_id,
    )
    queue_pressure = measure_queue_pressure(stack, args.queue_prompt, model_id=model.model_id)

    direct_worker = collect_direct_phase_two_metrics(
        stack=stack,
        prompt=args.http_prompt,
        queue_prompt=args.queue_prompt,
        abort_prompt=args.abort_prompt,
        decode_repeats=max(1, args.decode_repeats),
        active_kv_profiles=parse_active_kv_profiles(args.active_kv_profiles),
        model=model,
        skip_abort=bool(args.skip_abort),
    )

    report = {
        "generated_at_unix_ms": int(time.time() * 1000),
        "runtime_dir": os.fspath(stack.runtime_dir),
        "swift_backend_mode": stack.swift_backend_mode,
        "python_backend_mode": stack.python_backend_mode,
        "model_id": model.model_id,
        "model_path": model.model_path,
        "model_revision": model.revision,
        "model_source_resolution_mode": model.source_resolution_mode,
        "model_warnings": list(model.warnings),
        "http_baseline": baseline_http,
        "queue_pressure": queue_pressure,
        **direct_worker,
        "control_plane_metrics": read_metrics_export(stack.control_plane_metrics_path),
        "swift_worker_metrics": read_metrics_export(stack.swift_worker_metrics_path),
    }

    ensure_active_kv_release_gates(report)
    rendered = emit_report(report, json_output=bool(args.json), output_path=Path(args.output) if args.output else None)
    print(rendered)
    if args.require_fused_turboquant:
        failures = fused_turboquant_gate_failures(report)
        if failures:
            raise SystemExit(f"Phase 2 fused TurboQuant gate failed: {'; '.join(failures)}")


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


def load_report_json(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise RuntimeError(f"Phase 2 input report must be a JSON object: {path}")
    return report


def resolve_model_configuration(
    *,
    real_small_model: bool,
    model_id: str,
    model_path: str,
    model_revision: str,
    environment: dict[str, str] | None = None,
) -> Phase2ModelConfiguration:
    env = dict(os.environ if environment is None else environment)
    resolved_model_id = model_id.strip() or "melix-dev-text"

    if real_small_model:
        source = resolve_real_small_text_model_source(
            local_model_path=model_path,
            environment=env,
            allow_managed_root=True,
            allow_hf_cache=True,
        )
        return Phase2ModelConfiguration(
            model_id=resolved_model_id,
            model_path=source.model_path_for_runtime,
            revision=model_revision.strip() or "main",
            source_resolution_mode=source.source_resolution_mode,
            warnings=source.warnings,
        )

    env_model_path = env.get("MELIX_DEV_TEXT_MODEL_PATH", "").strip()
    env_model_revision = env.get("MELIX_DEV_TEXT_MODEL_REVISION", "").strip()
    resolved_model_path = model_path.strip() or env_model_path or "models/melix-dev-text"
    source_resolution_mode = "explicit_model_path" if model_path.strip() else (
        "env_model_path" if env_model_path else "dev_text_default"
    )
    return Phase2ModelConfiguration(
        model_id=resolved_model_id,
        model_path=resolved_model_path,
        revision=model_revision.strip() or env_model_revision or "dev",
        source_resolution_mode=source_resolution_mode,
    )


def collect_direct_phase_two_metrics(
    *,
    stack: StackConfiguration,
    prompt: str,
    queue_prompt: str,
    abort_prompt: str,
    decode_repeats: int = 1,
    active_kv_profiles: list[str] | None = None,
    model: Phase2ModelConfiguration | None = None,
    skip_abort: bool = False,
) -> dict[str, Any]:
    active_kv_profiles = active_kv_profiles or ["q4"]
    model = model or resolve_model_configuration(
        real_small_model=False,
        model_id="",
        model_path="",
        model_revision="",
    )
    with grpc.insecure_channel(f"unix://{stack.swift_socket_path}") as channel:
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)
        wait_for_worker_handshake(runtime_stub, worker_id="phase2-metrics", control_plane_id="phase2-metrics")

        load_started_at = time.perf_counter()
        load_response = runtime_stub.LoadModel(
            runtime_pb2.LoadModelRequest(
                model=dev_text_model_spec(model),
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
        prefill_sparse = measure_prefill_probe(
            inference_stub,
            stack.swift_worker_metrics_path,
            model_handle=model_handle,
            prompt=queue_prompt,
            label="prefill_sparse",
            policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_SPARSE_PREFILL,
                profile_id="structured-user",
                allow_baseline_fallback=True,
            ),
        )
        decode_rows: list[dict[str, Any]] = []
        for _ in range(max(1, decode_repeats)):
            decode_rows.append(
                measure_decode_probe(
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
            )
            for profile in active_kv_profiles:
                decode_rows.append(
                    measure_decode_probe(
                        inference_stub,
                        stack.swift_worker_metrics_path,
                        model_handle=model_handle,
                        prompt=prompt,
                        label=active_kv_decode_label(profile),
                        policy=common_pb2.AccelerationPolicy(
                            mode=common_pb2.ACCELERATION_MODE_ACTIVE_KV_QUANTIZED,
                            profile_id=f"{profile}-active-kv",
                            active_kv_quant_profile=profile,
                            allow_baseline_fallback=True,
                        ),
                    )
                )

        decode_rows.append(
            measure_decode_probe(
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
        )
        comparisons = build_decode_comparisons(decode_rows)
        if skip_abort:
            abort_probe = {
                "label": "decode_abort",
                "skipped": True,
                "reason": "disabled_by_cli",
            }
        else:
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

    active_kv_release_gates = build_active_kv_release_gates(decode_rows, comparisons)
    active_kv_fused_candidate_probes = build_active_kv_fused_candidate_probes(active_kv_release_gates)
    return {
        "swift_worker_direct": {
            "load_model_ms": load_model_ms,
            "resident_bytes": int(max(load_response.estimated_resident_bytes, stats.stats.resident_bytes)),
            "prefill": [prefill_baseline, prefill_accelerated, prefill_sparse],
            "decode": decode_rows,
            "comparisons": comparisons,
            "active_kv_release_gates": active_kv_release_gates,
            "active_kv_fused_candidate_probes": active_kv_fused_candidate_probes,
            "abort": abort_probe,
        }
    }


def measure_http_stream(http_port: int, prompt: str, *, label: str, model_id: str = "melix-dev-text") -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{http_port}/v1/chat/completions",
        data=json.dumps(
            {
                "model": model_id,
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


def measure_queue_pressure(stack: StackConfiguration, prompt: str, *, model_id: str = "melix-dev-text") -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}

    def run(label: str) -> None:
        results[label] = measure_http_stream(stack.http_port, prompt, label=label, model_id=model_id)

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
        "sparse_prefill_accepted_skip_count": exported.get("swift_text.sparse_prefill_accepted_skip_count"),
        "sparse_prefill_rejected_opportunity_count": exported.get("swift_text.sparse_prefill_rejected_opportunity_count"),
        "sparse_prefill_protected_region_count": exported.get("swift_text.sparse_prefill_protected_region_count"),
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
    active_kv_metrics = decode_active_kv_metrics(exported, policy)

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
        **active_kv_metrics,
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


def dev_text_model_spec(model: Phase2ModelConfiguration | None = None) -> common_pb2.ModelSpec:
    model = model or resolve_model_configuration(
        real_small_model=False,
        model_id="",
        model_path="",
        model_revision="",
    )
    return common_pb2.ModelSpec(
        model_id=model.model_id,
        model_path=model.model_path,
        model_kind="text",
        revision=model.revision,
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


def parse_active_kv_profiles(raw_profiles: str) -> list[str]:
    profiles = [profile.strip() for profile in raw_profiles.split(",") if profile.strip()]
    return profiles or ["q4"]


def active_kv_decode_label(profile: str) -> str:
    normalized = profile.lower().replace("-", "_").replace(".", "")
    if normalized.startswith("turboquant"):
        return f"decode_{normalized}"
    if normalized in {"q4", "q8"}:
        return f"decode_affine_{normalized}"
    return f"decode_active_kv_{normalized}"


def active_kv_comparison_name(label: str) -> str:
    prefix = "decode_"
    normalized = label.removeprefix(prefix) if label.startswith(prefix) else label
    return f"{normalized}_vs_baseline"


def decode_active_kv_metrics(
    exported: dict[str, Any],
    policy: common_pb2.AccelerationPolicy,
) -> dict[str, Any]:
    if policy.mode != common_pb2.ACCELERATION_MODE_ACTIVE_KV_QUANTIZED:
        return {
            "active_kv_quantization_ratio": 0,
            "active_kv_backend_code": 0,
            "active_kv_backend": None,
            "active_kv_kernel_path_code": 0,
            "active_kv_kernel_path": None,
            "active_kv_runtime_route_code": 0,
            "active_kv_runtime_route": None,
            "active_kv_runtime_block_reason_code": 0,
            "active_kv_runtime_block_reason": None,
            "active_kv_prefill_quantize_us": 0,
            "active_kv_decode_model_total_us": 0,
            "active_kv_decode_model_call_count": 0,
            "active_kv_decode_model_avg_us": 0,
            "active_kv_decode_token_eval_total_us": 0,
            "active_kv_decode_token_eval_call_count": 0,
            "active_kv_decode_token_eval_avg_us": 0,
            "active_kv_decode_quantize_total_us": 0,
            "active_kv_decode_quantize_avg_us": 0,
            "active_kv_decode_loop_total_us": 0,
            "active_kv_decode_token_count": 0,
            "active_kv_estimated_fp16_bytes": 0,
            "active_kv_estimated_quantized_bytes": 0,
            "active_kv_estimated_memory_savings_pct": 0,
            "active_kv_fallback_count": 0,
            "active_kv_candidate_dispatch_code": 0,
            "active_kv_candidate_eligibility_check_count": 0,
        }

    return {
        "active_kv_quantization_ratio": exported.get("swift_text.active_kv_quantization_ratio"),
        "active_kv_backend_code": exported.get("swift_text.active_kv_backend_code"),
        "active_kv_backend": active_kv_backend_name(exported.get("swift_text.active_kv_backend_code")),
        "active_kv_kernel_path_code": exported.get("swift_text.active_kv_kernel_path_code"),
        "active_kv_kernel_path": active_kv_kernel_path_name(exported.get("swift_text.active_kv_kernel_path_code")),
        "active_kv_runtime_route_code": exported.get("swift_text.active_kv_runtime_route_code"),
        "active_kv_runtime_route": active_kv_runtime_route_name(
            exported.get("swift_text.active_kv_runtime_route_code")
        ),
        "active_kv_runtime_block_reason_code": exported.get(
            "swift_text.active_kv_runtime_block_reason_code"
        ),
        "active_kv_runtime_block_reason": active_kv_runtime_block_reason_name(
            exported.get("swift_text.active_kv_runtime_block_reason_code")
        ),
        "active_kv_prefill_quantize_us": exported.get("swift_text.active_kv_prefill_quantize_us"),
        "active_kv_decode_model_total_us": exported.get("swift_text.active_kv_decode_model_total_us"),
        "active_kv_decode_model_call_count": exported.get(
            "swift_text.active_kv_decode_model_call_count", 0
        ),
        "active_kv_decode_model_avg_us": exported.get("swift_text.active_kv_decode_model_avg_us"),
        "active_kv_decode_token_eval_total_us": exported.get(
            "swift_text.active_kv_decode_token_eval_total_us", 0
        ),
        "active_kv_decode_token_eval_call_count": exported.get(
            "swift_text.active_kv_decode_token_eval_call_count", 0
        ),
        "active_kv_decode_token_eval_avg_us": exported.get(
            "swift_text.active_kv_decode_token_eval_avg_us", 0
        ),
        "active_kv_decode_quantize_total_us": exported.get("swift_text.active_kv_decode_quantize_total_us"),
        "active_kv_decode_quantize_avg_us": exported.get("swift_text.active_kv_decode_quantize_avg_us"),
        "active_kv_decode_loop_total_us": exported.get(
            "swift_text.active_kv_decode_loop_total_us", 0
        ),
        "active_kv_decode_token_count": exported.get("swift_text.active_kv_decode_token_count"),
        "active_kv_estimated_fp16_bytes": exported.get("swift_text.active_kv_estimated_fp16_bytes"),
        "active_kv_estimated_quantized_bytes": exported.get("swift_text.active_kv_estimated_quantized_bytes"),
        "active_kv_estimated_memory_savings_pct": exported.get(
            "swift_text.active_kv_estimated_memory_savings_pct"
        ),
        "active_kv_fallback_count": exported.get("swift_text.active_kv_fallback_count"),
        "active_kv_candidate_dispatch_code": exported.get(
            "swift_text.active_kv_candidate_dispatch_code", 0
        ),
        "active_kv_candidate_eligibility_check_count": exported.get(
            "swift_text.active_kv_candidate_eligibility_check_count", 0
        ),
    }


def active_kv_backend_name(raw_code: Any) -> str | None:
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        return None
    return {
        0: None,
        1: "affine",
        2: "turboquant",
    }.get(code, f"unknown_{code}")


def active_kv_kernel_path_name(raw_code: Any) -> str | None:
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        return None
    return {
        0: None,
        10: "affine_quantized_sdpa",
        20: "tq_mse_single",
        21: "tq_mse_2pass",
        30: "tq_prod_fully_fused",
        31: "tq_prod_tiled",
        90: "fallback",
    }.get(code, f"unknown_{code}")


def active_kv_runtime_route_name(raw_code: Any) -> str | None:
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        return None
    return {
        0: None,
        1: "blocked",
        2: "routed",
    }.get(code, f"unknown_{code}")


def active_kv_runtime_block_reason_name(raw_code: Any) -> str | None:
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        return None
    return {
        0: None,
        1: "unsupported_cache_state",
        2: "attention_hook_unavailable",
    }.get(code, f"unknown_{code}")


def build_decode_comparisons(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    baseline_rows = [row for row in rows if row.get("label") == "decode_baseline"]
    baseline_worker_tps = median_numeric(baseline_rows, "worker_decode_tokens_per_second")
    baseline_wall_tps = median_numeric(baseline_rows, "tokens_per_second")
    baseline_ttft = median_numeric(baseline_rows, "ttft_ms")
    baseline_total = median_numeric(baseline_rows, "total_ms")
    if baseline_worker_tps is None and baseline_wall_tps is None:
        return {}

    comparisons: dict[str, dict[str, Any]] = {}
    active_labels = sorted({
        str(row.get("label"))
        for row in rows
        if str(row.get("label", "")).startswith("decode_")
        and row.get("label") not in {"decode_baseline", "decode_speculative"}
    })
    for label in active_labels:
        active_rows = [row for row in rows if row.get("label") == label]
        worker_tps = median_numeric(active_rows, "worker_decode_tokens_per_second")
        wall_tps = median_numeric(active_rows, "tokens_per_second")
        ttft = median_numeric(active_rows, "ttft_ms")
        total = median_numeric(active_rows, "total_ms")
        model_avg = median_numeric(active_rows, "active_kv_decode_model_avg_us")
        token_eval_avg = median_numeric(active_rows, "active_kv_decode_token_eval_avg_us")
        quantize_avg = median_numeric(active_rows, "active_kv_decode_quantize_avg_us")
        comparisons[active_kv_comparison_name(label)] = {
            "baseline_worker_decode_tokens_per_second": baseline_worker_tps,
            "active_worker_decode_tokens_per_second": worker_tps,
            "worker_tps_overhead_pct": overhead_percent(baseline_worker_tps, worker_tps),
            "baseline_tokens_per_second": baseline_wall_tps,
            "active_tokens_per_second": wall_tps,
            "wall_tps_overhead_pct": overhead_percent(baseline_wall_tps, wall_tps),
            "ttft_delta_ms": delta(ttft, baseline_ttft),
            "total_ms_delta": delta(total, baseline_total),
            "active_kv_backend": first_non_empty(active_rows, "active_kv_backend"),
            "active_kv_kernel_path": first_non_empty(active_rows, "active_kv_kernel_path"),
            "active_kv_decode_model_avg_us": model_avg,
            "active_kv_decode_token_eval_avg_us": token_eval_avg,
            "active_kv_decode_loop_total_us": median_numeric(active_rows, "active_kv_decode_loop_total_us"),
            "active_kv_decode_quantize_avg_us": quantize_avg,
            "active_kv_decode_quantize_share_pct": quantize_share_percent(model_avg, quantize_avg),
            "active_kv_estimated_memory_savings_pct": median_numeric(
                active_rows,
                "active_kv_estimated_memory_savings_pct",
            ),
        }
    return comparisons


def ensure_active_kv_release_gates(report: dict[str, Any]) -> None:
    direct = report.get("swift_worker_direct")
    if not isinstance(direct, dict):
        return
    decode_rows = direct.get("decode", [])
    comparisons = direct.get("comparisons", {})
    has_release_gates = "active_kv_release_gates" in direct
    if (
        "decode" in direct
        and "comparisons" in direct
        and isinstance(decode_rows, list)
        and isinstance(comparisons, dict)
        and (not has_release_gates or bool(decode_rows) or bool(comparisons))
    ):
        direct["active_kv_release_gates"] = build_active_kv_release_gates(decode_rows, comparisons)
    gates = direct.get("active_kv_release_gates")
    if isinstance(gates, dict):
        direct["active_kv_fused_candidate_probes"] = build_active_kv_fused_candidate_probes(gates)


def build_active_kv_release_gates(
    rows: list[dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    turbo_rows = [row for row in rows if row.get("label") == "decode_turboquant_q4"]
    comparison = comparisons.get("turboquant_q4_vs_baseline", {})
    if not turbo_rows:
        return {
            "turboquant_fused_decode": {
                "status": "not_requested",
                "profile_label": "decode_turboquant_q4",
                "observed_kernel_paths": [],
                "observed_runtime_routes": [],
                "observed_runtime_block_reasons": [],
                "fallback_count": 0,
                "candidate_dispatch_count": 0,
                "decode_quantize_total_us": 0,
                "decode_token_eval_total_us": 0,
                "decode_loop_total_us": 0,
                "estimated_memory_savings_pct": None,
                "worker_tps_overhead_pct": comparison.get("worker_tps_overhead_pct"),
                "failures": ["decode_turboquant_q4=missing"],
            }
        }

    observed_kernel_paths = sorted({
        str(row["active_kv_kernel_path"])
        for row in turbo_rows
        if row.get("active_kv_kernel_path") not in (None, "")
    })
    observed_runtime_routes = sorted({
        str(row["active_kv_runtime_route"])
        for row in turbo_rows
        if row.get("active_kv_runtime_route") not in (None, "")
    })
    observed_runtime_block_reasons = sorted({
        str(row["active_kv_runtime_block_reason"])
        for row in turbo_rows
        if row.get("active_kv_runtime_block_reason") not in (None, "")
    })
    fallback_count = sum(int_value(row.get("active_kv_fallback_count")) for row in turbo_rows)
    candidate_dispatch_count = sum(
        int_value(row.get("active_kv_candidate_dispatch_code")) for row in turbo_rows
    )
    candidate_eligibility_check_count = sum(
        int_value(row.get("active_kv_candidate_eligibility_check_count")) for row in turbo_rows
    )
    decode_model_call_count = sum(
        int_value(row.get("active_kv_decode_model_call_count")) for row in turbo_rows
    )
    decode_token_eval_total_us = sum(
        int_value(row.get("active_kv_decode_token_eval_total_us")) for row in turbo_rows
    )
    decode_loop_total_us = sum(
        int_value(row.get("active_kv_decode_loop_total_us")) for row in turbo_rows
    )
    decode_quantize_total_us = sum(int_value(row.get("active_kv_decode_quantize_total_us")) for row in turbo_rows)
    memory_savings = median_numeric(turbo_rows, "active_kv_estimated_memory_savings_pct")
    worker_tps_overhead = numeric_value(comparison.get("worker_tps_overhead_pct"))
    failures: list[str] = []

    if not observed_kernel_paths:
        failures.append("active_kv_kernel_path=missing")
    if "fallback" in observed_kernel_paths:
        failures.append("active_kv_kernel_path=fallback")
    if any(path.startswith("unknown_") for path in observed_kernel_paths):
        failures.append(f"active_kv_kernel_path={','.join(observed_kernel_paths)}")
    if "blocked" in observed_runtime_routes:
        failures.append("active_kv_runtime_route=blocked")
    if any(route.startswith("unknown_") for route in observed_runtime_routes):
        failures.append(f"active_kv_runtime_route={','.join(observed_runtime_routes)}")
    if observed_runtime_block_reasons:
        failures.append(f"active_kv_runtime_block_reason={','.join(observed_runtime_block_reasons)}")
    if fallback_count > 0:
        failures.append(f"active_kv_fallback_count={fallback_count}")
    if decode_quantize_total_us > 0:
        failures.append(f"active_kv_decode_quantize_total_us={decode_quantize_total_us}")
    if memory_savings is None or memory_savings < 67:
        failures.append(f"active_kv_estimated_memory_savings_pct={stringify_gate_value(memory_savings)}")
    if worker_tps_overhead is None or worker_tps_overhead > TURBOQUANT_FUSED_MAX_WORKER_TPS_OVERHEAD_PCT:
        failures.append(f"worker_tps_overhead_pct={stringify_gate_value(worker_tps_overhead)}")

    return {
        "turboquant_fused_decode": {
            "status": "fail" if failures else "pass",
            "profile_label": "decode_turboquant_q4",
            "observed_kernel_paths": observed_kernel_paths,
            "observed_runtime_routes": observed_runtime_routes,
            "observed_runtime_block_reasons": observed_runtime_block_reasons,
            "fallback_count": fallback_count,
            "candidate_dispatch_count": candidate_dispatch_count,
            "candidate_eligibility_check_count": candidate_eligibility_check_count,
            "decode_model_call_count": decode_model_call_count,
            "decode_token_eval_total_us": decode_token_eval_total_us,
            "decode_loop_total_us": decode_loop_total_us,
            "decode_quantize_total_us": decode_quantize_total_us,
            "estimated_memory_savings_pct": memory_savings,
            "worker_tps_overhead_pct": worker_tps_overhead,
            "failures": failures,
        }
    }


def build_active_kv_fused_candidate_probes(
    release_gates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    gate = release_gates.get("turboquant_fused_decode", {})
    gate_status = str(gate.get("status", "missing"))
    if gate_status == "pass":
        status = "runtime_candidate_pass"
        next_required_evidence: list[str] = []
    elif gate_status == "not_requested":
        status = "not_requested"
        next_required_evidence = ["decode_turboquant_q4 profile requested"]
    else:
        status = "runtime_blocked"
        next_required_evidence = list(TURBOQUANT_FUSED_RUNTIME_REQUIREMENTS)
    observed_kernel_paths = gate.get("observed_kernel_paths", [])
    observed_runtime_routes = gate.get("observed_runtime_routes", [])
    observed_runtime_block_reasons = gate.get("observed_runtime_block_reasons", [])
    capability_evidence = dict(TURBOQUANT_FUSED_CAPABILITY_EVIDENCE)
    if int_value(gate.get("candidate_dispatch_count")) > 0:
        capability_evidence["runtime_path"] = "candidate_dispatch_connected"

    return {
        "turboquant_q4": {
            "status": status,
            "profile_label": "decode_turboquant_q4",
            "capability_evidence": capability_evidence,
            "runtime_evidence": {
                "release_gate_status": gate_status,
                "observed_kernel_paths": observed_kernel_paths,
                "observed_runtime_routes": observed_runtime_routes,
                "observed_runtime_block_reasons": observed_runtime_block_reasons,
                "fallback_count": gate.get("fallback_count"),
                "candidate_dispatch_count": gate.get("candidate_dispatch_count"),
                "candidate_eligibility_check_count": gate.get(
                    "candidate_eligibility_check_count"
                ),
                "decode_model_call_count": gate.get("decode_model_call_count"),
                "decode_token_eval_total_us": gate.get("decode_token_eval_total_us"),
                "decode_loop_total_us": gate.get("decode_loop_total_us"),
                "decode_quantize_total_us": gate.get("decode_quantize_total_us"),
                "estimated_memory_savings_pct": gate.get("estimated_memory_savings_pct"),
                "worker_tps_overhead_pct": gate.get("worker_tps_overhead_pct"),
                "failures": gate.get("failures", []),
            },
            "next_required_evidence": next_required_evidence,
        }
    }


def fused_turboquant_gate_failures(report: dict[str, Any]) -> list[str]:
    ensure_active_kv_release_gates(report)
    direct = report.get("swift_worker_direct")
    if not isinstance(direct, dict):
        return ["swift_worker_direct=missing"]
    gates = direct.get("active_kv_release_gates")
    if not isinstance(gates, dict):
        return ["active_kv_release_gates=missing"]
    gate = gates.get("turboquant_fused_decode")
    if not isinstance(gate, dict):
        return ["turboquant_fused_decode=missing"]
    if gate.get("status") == "pass":
        return []
    failures = gate.get("failures")
    if isinstance(failures, list) and failures:
        return [str(failure) for failure in failures]
    return [f"turboquant_fused_decode={gate.get('status', 'unknown')}"]


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def stringify_gate_value(value: Any) -> str:
    return "missing" if value is None else str(value)


def numeric_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def median_numeric(rows: list[dict[str, Any]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    return round(float(statistics.median(values)), 2)


def overhead_percent(baseline: float | None, active: float | None) -> float | None:
    if baseline is None or active is None or baseline <= 0:
        return None
    return round(((baseline - active) / baseline) * 100.0, 2)


def delta(active: float | None, baseline: float | None) -> float | None:
    if active is None or baseline is None:
        return None
    return round(active - baseline, 2)


def quantize_share_percent(model_avg_us: float | None, quantize_avg_us: float | None) -> float | None:
    if model_avg_us is None or quantize_avg_us is None:
        return None
    total = model_avg_us + quantize_avg_us
    if total <= 0:
        return None
    return round((quantize_avg_us / total) * 100.0, 2)


def first_non_empty(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        value = row.get(key)
        if value not in (None, "", 0):
            return value
    return None


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
        f"model_id: {report.get('model_id', 'melix-dev-text')}",
        f"model_path: {report.get('model_path', 'models/melix-dev-text')}",
        f"model_revision: {report.get('model_revision', 'dev')}",
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
            [
                "label",
                "mode",
                "total_ms",
                "worker_prefill_ms",
                "prompt_tokens",
                "accelerated_prefill_gain_pct",
                "active_kv_quantization_ratio",
                "sparse_prefill_accepted_skip_count",
                "sparse_prefill_rejected_opportunity_count",
                "sparse_prefill_protected_region_count",
            ],
        ),
        "",
        "Swift Worker Decode",
        format_table(
            report["swift_worker_direct"]["decode"],
            [
                "label",
                "mode",
                "ttft_ms",
                "total_ms",
                "tokens_per_second",
                "worker_decode_tokens_per_second",
                "speculative_acceptance_rate",
                "speculative_rollback_rate",
                "active_kv_quantization_ratio",
                "active_kv_backend",
                "active_kv_kernel_path",
                "active_kv_runtime_route",
                "active_kv_runtime_block_reason",
                "active_kv_candidate_dispatch_code",
                "active_kv_candidate_eligibility_check_count",
                "active_kv_decode_model_call_count",
                "active_kv_decode_model_avg_us",
                "active_kv_decode_token_eval_call_count",
                "active_kv_decode_token_eval_avg_us",
                "active_kv_decode_loop_total_us",
                "active_kv_decode_quantize_avg_us",
                "active_kv_estimated_memory_savings_pct",
            ],
        ),
        "",
        "Swift Worker Decode Comparisons",
        format_table(
            [
                {"comparison": name, **values}
                for name, values in report["swift_worker_direct"].get("comparisons", {}).items()
            ],
            [
                "comparison",
                "worker_tps_overhead_pct",
                "wall_tps_overhead_pct",
                "ttft_delta_ms",
                "total_ms_delta",
                "active_kv_backend",
                "active_kv_kernel_path",
                "active_kv_decode_model_avg_us",
                "active_kv_decode_token_eval_avg_us",
                "active_kv_decode_loop_total_us",
                "active_kv_decode_quantize_share_pct",
                "active_kv_estimated_memory_savings_pct",
            ],
        ),
        "",
        "Active-KV Release Gates",
        format_table(
            [
                {"gate": name, **values}
                for name, values in report["swift_worker_direct"].get("active_kv_release_gates", {}).items()
            ],
            [
                "gate",
                "status",
                "profile_label",
                "observed_kernel_paths",
                "observed_runtime_routes",
                "observed_runtime_block_reasons",
                "fallback_count",
                "candidate_dispatch_count",
                "decode_model_call_count",
                "decode_token_eval_total_us",
                "decode_loop_total_us",
                "decode_quantize_total_us",
                "estimated_memory_savings_pct",
                "worker_tps_overhead_pct",
                "failures",
            ],
        ),
        "",
        "Active-KV Fused Candidate Probes",
        format_table(
            [
                {
                    "candidate": name,
                    "capability_status": values.get("capability_evidence", {}).get("status"),
                    "runtime_path": values.get("capability_evidence", {}).get("runtime_path"),
                    "release_gate_status": values.get("runtime_evidence", {}).get("release_gate_status"),
                    "observed_kernel_paths": values.get("runtime_evidence", {}).get("observed_kernel_paths"),
                    "observed_runtime_routes": values.get("runtime_evidence", {}).get("observed_runtime_routes"),
                    "observed_runtime_block_reasons": values.get("runtime_evidence", {}).get(
                        "observed_runtime_block_reasons"
                    ),
                    "candidate_dispatch_count": values.get("runtime_evidence", {}).get("candidate_dispatch_count"),
                    "next_required_evidence": values.get("next_required_evidence"),
                    **values,
                }
                for name, values in report["swift_worker_direct"]
                .get("active_kv_fused_candidate_probes", {})
                .items()
            ],
            [
                "candidate",
                "status",
                "profile_label",
                "capability_status",
                "runtime_path",
                "release_gate_status",
                "observed_kernel_paths",
                "observed_runtime_routes",
                "observed_runtime_block_reasons",
                "candidate_dispatch_count",
                "next_required_evidence",
            ],
        ),
        "",
        "Abort",
        format_table(
            [report["swift_worker_direct"]["abort"]],
            ["label", "skipped", "reason", "abort_ms", "finish_reason"],
        ),
        "",
        "JSON",
        json.dumps(report, indent=2, sort_keys=True),
    ]
    return "\n".join(lines)


def emit_report(
    report: dict[str, Any],
    *,
    json_output: bool,
    output_path: Path | None = None,
) -> str:
    rendered = json.dumps(report, indent=2, sort_keys=True) if json_output else render_report(report)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{rendered}\n", encoding="utf-8")
    return rendered


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
