from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

from worker.runtime.deterministic_ocr_runtime import DeterministicOCRRuntime  # noqa: E402
from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest  # noqa: E402
from worker.runtime.token_counting import whitespace_token_count  # noqa: E402


_RAW_WHITESPACE_TOKEN_COUNT = getattr(whitespace_token_count, "__wrapped__", whitespace_token_count)


def _request(prompt_text: str, image_bytes: bytes) -> PreparedVisionRequest:
    image = PreparedImageInput(
        bytes_data=image_bytes,
        source_kind="inline",
        reference="inline:ocr-probe.txt",
        mime_type="text/plain",
        format="txt",
        filename="ocr-probe.txt",
        sha256_hex="a" * 64,
    )
    return PreparedVisionRequest(
        prompt_text=prompt_text,
        images=[image],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(image_bytes),
        preprocess_peak_memory_bytes=len(image_bytes),
        prompt_hash_hex="p" * 64,
        multimodal_hash_hex="m" * 64,
    )


def main() -> None:
    iterations = int(os.environ.get("MELIX_OCR_TOKEN_COUNT_ITERATIONS", "80000"))
    sample_count = int(os.environ.get("MELIX_OCR_TOKEN_COUNT_SAMPLES", "5"))
    prompt_text = "\tExtract   the receipt text and preserve\nline breaks  " * 8
    image_bytes = (b"Receipt Total 42\n" * 64) + b"end"
    request = _request(prompt_text, image_bytes)
    helper_texts = tuple(f"{prompt_text}sample-{index}" for index in range(1024))
    helper_expected = tuple(len(text.split()) for text in helper_texts)
    runtime = DeterministicOCRRuntime()
    expected = max(1, len(prompt_text.split()) + max(1, len(image_bytes) // 8))

    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    checksum = 0
    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            token_count = runtime.prompt_token_count(request)
            if token_count != expected:
                raise AssertionError(f"unexpected token count: {token_count} != {expected}")
            helper_index = _index % len(helper_texts)
            helper_token_count = _RAW_WHITESPACE_TOKEN_COUNT(helper_texts[helper_index])
            if helper_token_count != helper_expected[helper_index]:
                raise AssertionError("unexpected helper token count")
            checksum += token_count + helper_token_count
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        peak_samples.append(float(peak))
        tracemalloc.stop()

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 6),
                "sample_count": float(sample_count),
                "iterations": float(iterations),
                "token_count": float(expected),
                "checksum": float(checksum),
                "helper_token_count": float(helper_expected[-1]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
