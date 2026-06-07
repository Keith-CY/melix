from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.stream_assembler import (
    RequestStreamAssembler,
    StreamFragment,
    _whitespace_token_count,
)


def _measure_delta_token_count(sample_count: int) -> dict[str, float]:
    token_texts = tuple(
        " ".join(f"token{(index + offset) % 257}" for offset in range(128))
        for index in range(4096)
    )
    old_elapsed: list[float] = []
    new_elapsed: list[float] = []
    checksum = 0

    for _ in range(sample_count):
        started = time.perf_counter()
        old_counts = [len(text.split()) for text in token_texts]
        old_elapsed.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        new_counts = [_whitespace_token_count(text) for text in token_texts]
        new_elapsed.append((time.perf_counter() - started) * 1000.0)
        if new_counts != old_counts:
            raise SystemExit("delta token count fast path diverged from split() semantics")
        checksum += sum(new_counts)

    old_mean = statistics.fmean(old_elapsed)
    new_mean = statistics.fmean(new_elapsed)
    return {
        "delta_token_count_old_ms_mean": old_mean,
        "delta_token_count_new_ms_mean": new_mean,
        "delta_token_count_delta_ms": new_mean - old_mean,
        "delta_token_count_speedup": old_mean / new_mean if new_mean else 0.0,
        "delta_token_count_text_count": float(len(token_texts)),
        "delta_token_count_checksum": float(checksum),
    }


def _measure(sample_count: int | None = None, token_event_count: int | None = None) -> dict[str, float]:
    if sample_count is None:
        sample_count = int(os.environ.get("MELIX_STREAM_ASSEMBLER_TOKEN_BYTES_SAMPLES", "5"))
    if token_event_count is None:
        token_event_count = int(os.environ.get("MELIX_STREAM_ASSEMBLER_TOKEN_BYTES_EVENTS", "80000"))

    token_payloads = tuple(
        f"token-{index % 97} ".encode("utf-8")
        for index in range(token_event_count)
    )
    expected_text = b"".join(token_payloads).decode("utf-8")
    elapsed: list[float] = []
    peaks: list[float] = []
    generated_tokens: list[float] = []
    checksum = 0

    for _ in range(sample_count):
        assembler = RequestStreamAssembler("token-bytes-probe", False, "", "")
        tracemalloc.start()
        started = time.perf_counter()
        emitted_chars = 0
        for payload in token_payloads:
            for delta in assembler.accept(StreamFragment(token_bytes=payload)):
                emitted_chars += len(delta.content_text)
        completed = assembler.completed()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if completed.assistant_text != expected_text:
            raise SystemExit("assembled token-byte text did not match expected text")
        if emitted_chars != len(expected_text):
            raise SystemExit("unexpected emitted character count")
        if completed.metrics["byte_fallback_decode_error_count"] != 0:
            raise SystemExit("unexpected decode errors for ASCII token bytes")
        elapsed.append(elapsed_ms)
        peaks.append(float(peak))
        generated_tokens.append(float(completed.metrics["generated_token_count"]))
        checksum += len(completed.assistant_text)

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed),
        "peak_bytes_mean": statistics.fmean(peaks),
        "generated_token_count_mean": statistics.fmean(generated_tokens),
        "token_event_count": float(token_event_count),
        "checksum": float(checksum),
        "sample_count": float(sample_count),
    }
    metrics.update(_measure_delta_token_count(sample_count))
    return metrics


if __name__ == "__main__":
    print(json.dumps(_measure(), sort_keys=True))
