from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from threading import Event

REPO_ROOT = Path(os.environ.get("MELIX_DETERMINISTIC_VLM_COMPLETION_REPO_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import deterministic_vlm_runtime as deterministic_vlm_runtime_module  # noqa: E402
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime  # noqa: E402
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest  # noqa: E402


class SplitTrackingText(str):
    split_calls = 0

    def split(self, *args: object, **kwargs: object) -> list[str]:
        type(self).split_calls += 1
        return super().split(*args, **kwargs)


def _prepared_request() -> PreparedVisionRequest:
    return PreparedVisionRequest(
        prompt_text="Describe the synthetic image.",
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
        prompt_hash_hex="p" * 64,
        multimodal_hash_hex="m" * 64,
    )


def _response_payload(word_count: int) -> str:
    # Include mixed whitespace so the scan path preserves str.split(None) semantics.
    return ("alpha beta\tgamma\n" * max(1, word_count // 3)).strip()


def _run_once(*, iterations: int, word_count: int) -> tuple[float, int, float, int, int]:
    request = _prepared_request()
    payload = _response_payload(word_count)
    expected_completion_tokens = len(payload.split())
    runtime = DeterministicVLMRuntime()
    original_response_text = DeterministicVLMRuntime._response_text
    original_token_count = deterministic_vlm_runtime_module._whitespace_token_count
    token_count_calls = 0

    def counting_token_count(text: str) -> int:
        nonlocal token_count_calls
        token_count_calls += 1
        return original_token_count(text)

    try:
        DeterministicVLMRuntime._response_text = staticmethod(lambda prepared_request: SplitTrackingText(payload))  # type: ignore[method-assign]
        deterministic_vlm_runtime_module._whitespace_token_count = counting_token_count
        SplitTrackingText.split_calls = 0
        tracemalloc.start()
        start = time.perf_counter()
        completion_total = 0
        for _ in range(iterations):
            events = list(runtime.generate_tokens({}, request, sampling=None, cancel_event=Event()))
            completion_total += sum(event.completion_tokens for event in events if event.text)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        DeterministicVLMRuntime._response_text = staticmethod(original_response_text)  # type: ignore[method-assign]
        deterministic_vlm_runtime_module._whitespace_token_count = original_token_count
    expected_total = expected_completion_tokens * iterations
    if completion_total != expected_total:
        raise SystemExit(f"unexpected completion token total: {completion_total} != {expected_total}")
    return elapsed_ms, SplitTrackingText.split_calls, float(peak_bytes), expected_completion_tokens, token_count_calls


def main() -> int:
    iterations = int(os.environ.get("MELIX_DETERMINISTIC_VLM_COMPLETION_PROBE_ITERATIONS", "400"))
    samples = int(os.environ.get("MELIX_DETERMINISTIC_VLM_COMPLETION_PROBE_SAMPLES", "5"))
    word_count = int(os.environ.get("MELIX_DETERMINISTIC_VLM_COMPLETION_PROBE_WORDS", "6000"))
    elapsed: list[float] = []
    split_calls: list[int] = []
    peaks: list[float] = []
    token_counts: list[int] = []
    token_count_calls: list[int] = []
    for _ in range(samples):
        elapsed_ms, split_call_count, peak_bytes, token_count, token_count_call_count = _run_once(
            iterations=iterations,
            word_count=word_count,
        )
        elapsed.append(elapsed_ms)
        split_calls.append(split_call_count)
        peaks.append(peak_bytes)
        token_counts.append(token_count)
        token_count_calls.append(token_count_call_count)
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed),
                "split_calls_mean": statistics.fmean(split_calls),
                "peak_bytes_mean": statistics.fmean(peaks),
                "completion_tokens": token_counts[-1],
                "token_count_calls_mean": statistics.fmean(token_count_calls),
                "iterations": iterations,
                "samples": samples,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
