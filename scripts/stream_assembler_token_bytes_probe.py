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

from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


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

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed),
        "peak_bytes_mean": statistics.fmean(peaks),
        "generated_token_count_mean": statistics.fmean(generated_tokens),
        "token_event_count": float(token_event_count),
        "checksum": float(checksum),
        "sample_count": float(sample_count),
    }


if __name__ == "__main__":
    print(json.dumps(_measure(), sort_keys=True))
