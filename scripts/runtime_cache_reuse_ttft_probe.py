#!/usr/bin/env python3
"""Baseline TTFT probe for prefix cache reuse.

Measures p50/p95 TTFT for repeated requests with a shared system prompt and
varied final-user turns, comparing cache-cold vs cache-warm runs.

Run after completing a full model load so hardware warm-up effects are excluded.
Results are written to the runtime evidence bundle.

Requires: MLX hardware (Apple Silicon), mlx-lm, a loaded model via MELIX_MODEL_HANDLE.

Usage:
    MELIX_MODEL_HANDLE=<handle> MELIX_SOCKET=<socket> python scripts/runtime_cache_reuse_ttft_probe.py
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer concisely and accurately. "
    "Do not add unnecessary preamble."
)

_USER_TURNS = [
    "What is 2 + 2?",
    "What is the capital of France?",
    "Name three programming languages.",
    "What color is the sky?",
    "How many days are in a week?",
    "What is 10 divided by 2?",
    "Name the first planet from the Sun.",
    "What is water made of?",
]

_SAMPLE_COUNT = int(os.environ.get("MELIX_CACHE_PROBE_SAMPLES", "3"))
_WARMUP_TURNS = 2


def _measure_ttft_via_runtime(
    model_handle: str,
    socket_path: str,
    session_id: str,
    messages: list[dict[str, str]],
) -> float | None:
    """Measure TTFT by timing the first token from a generate request.

    Returns elapsed milliseconds, or None if the runtime is unavailable.
    """
    try:
        import grpc
        from packages.protocol.python.worker.v1 import inference_pb2, common_pb2, inference_pb2_grpc
    except ImportError:
        return None

    channel = grpc.insecure_channel(f"unix://{socket_path}")
    stub = inference_pb2_grpc.InferenceServiceStub(channel)

    proto_messages = [
        inference_pb2.ChatMessage(
            role=m["role"],
            parts=[inference_pb2.MessagePart(text=m["content"])],
        )
        for m in messages
    ]

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(
                request_id=f"probe-{session_id}-{time.monotonic_ns()}",
                session_id=session_id,
            ),
            model_handle=model_handle,
        ),
        messages=proto_messages,
        sampling=common_pb2.SamplingConfig(max_output_tokens=4),
        stream=True,
        return_usage=False,
    )

    started = time.perf_counter()
    first_token_ms: float | None = None
    try:
        for event in stub.Generate(request, timeout=30):
            if event.HasField("token_delta") and first_token_ms is None:
                first_token_ms = (time.perf_counter() - started) * 1000.0
                break
    except Exception:
        pass
    channel.close()
    return first_token_ms


def main() -> None:
    model_handle = os.environ.get("MELIX_MODEL_HANDLE", "")
    socket_path = os.environ.get("MELIX_SOCKET", ".runtime/worker.sock")

    cold_samples: list[float] = []
    warm_samples: list[float] = []

    session_id = f"cache-probe-{time.monotonic_ns()}"

    for turn_idx, user_turn in enumerate(_USER_TURNS):
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_turn},
        ]

        for sample_idx in range(_SAMPLE_COUNT):
            ttft = _measure_ttft_via_runtime(model_handle, socket_path, session_id, messages)
            if ttft is None:
                continue
            if turn_idx < _WARMUP_TURNS:
                continue  # skip warm-up turns from stats
            if sample_idx == 0:
                cold_samples.append(ttft)
            else:
                warm_samples.append(ttft)

    def _p95(samples: list[float]) -> float | None:
        # Nearest-rank p95 with a zero-based index: ceil(0.95 * N) - 1, clamped.
        # The previous int(N * 0.95) collapsed to the last element (the max) for
        # small N (e.g. N=20 -> index 19), making the metric meaningless.
        if len(samples) < 4:
            return None
        ordered = sorted(samples)
        rank = math.ceil(0.95 * len(ordered)) - 1
        rank = min(max(rank, 0), len(ordered) - 1)
        return round(ordered[rank], 3)

    result: dict[str, object] = {
        "probe": "runtime_cache_reuse_ttft",
        "cold_samples": cold_samples,
        "warm_samples": warm_samples,
        "cold_p50_ms": round(statistics.median(cold_samples), 3) if cold_samples else None,
        "cold_p95_ms": _p95(cold_samples),
        "warm_p50_ms": round(statistics.median(warm_samples), 3) if warm_samples else None,
        "warm_p95_ms": _p95(warm_samples),
        "sample_count": len(cold_samples),
    }

    if result["cold_p50_ms"] is not None and result["warm_p50_ms"] is not None:
        cold_p50 = float(result["cold_p50_ms"])
        warm_p50 = float(result["warm_p50_ms"])
        if cold_p50 > 0:
            result["p50_improvement_pct"] = round((cold_p50 - warm_p50) / cold_p50 * 100, 1)

    cold_p95 = result["cold_p95_ms"]
    warm_p95 = result["warm_p95_ms"]
    if cold_p95 is not None and warm_p95 is not None and float(cold_p95) > 0:
        result["p95_improvement_pct"] = round(
            (float(cold_p95) - float(warm_p95)) / float(cold_p95) * 100, 1
        )

    print(json.dumps(result, sort_keys=True))

    target_p50_improvement = 25.0
    target_p95_improvement = 20.0
    p50_improvement = result.get("p50_improvement_pct")
    if p50_improvement is not None and float(p50_improvement) < target_p50_improvement:
        print(
            f"WARNING: p50 improvement {p50_improvement}% below target {target_p50_improvement}%",
            file=sys.stderr,
        )
    p95_improvement = result.get("p95_improvement_pct")
    if p95_improvement is not None and float(p95_improvement) < target_p95_improvement:
        print(
            f"WARNING: p95 improvement {p95_improvement}% below target {target_p95_improvement}%",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
