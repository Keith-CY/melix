from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from packages.protocol.python.worker.v1 import common_pb2
from worker.runtime import multimodal_preprocessing
from worker.runtime.multimodal_preprocessing import prepare_vision_request


def _build_messages(image_paths: list[Path]) -> list[common_pb2.ChatMessage]:
    parts = [common_pb2.MessagePart(text="Describe these images.")]
    for index, image_path in enumerate(image_paths):
        reference = image_path.as_uri() if index % 2 else str(image_path)
        parts.append(
            common_pb2.MessagePart(
                image_uri=reference,
                media=common_pb2.MediaMetadata(
                    media_type=common_pb2.MEDIA_TYPE_IMAGE,
                    source_kind=common_pb2.MEDIA_SOURCE_URI,
                ),
            )
        )
    return [common_pb2.ChatMessage(role="user", parts=parts)]


def main() -> int:
    image_count = 640
    sample_count = 5
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    urlparse_calls: list[int] = []
    unquote_calls: list[int] = []
    original_urlparse = multimodal_preprocessing.urlparse
    original_unquote = multimodal_preprocessing.unquote

    with tempfile.TemporaryDirectory(prefix="melix-image-uri-parse-probe-") as tmpdir:
        root = Path(tmpdir)
        image_paths = []
        for index in range(image_count):
            image_path = root / f"image-{index:04d}.txt"
            image_path.write_text(f"synthetic image payload {index}\n")
            image_paths.append(image_path)
        messages = _build_messages(image_paths)

        for _ in range(sample_count):
            call_count = 0
            unquote_call_count = 0

            def counting_urlparse(uri: str):
                nonlocal call_count
                call_count += 1
                return original_urlparse(uri)

            def counting_unquote(path: str) -> str:  # pragma: no cover - exercised by base-repo probe
                nonlocal unquote_call_count
                unquote_call_count += 1
                return original_unquote(path)

            multimodal_preprocessing.urlparse = counting_urlparse
            multimodal_preprocessing.unquote = counting_unquote
            try:
                tracemalloc.start()
                started = time.perf_counter()
                request = prepare_vision_request(messages)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                _, peak_bytes = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            finally:
                multimodal_preprocessing.urlparse = original_urlparse
                multimodal_preprocessing.unquote = original_unquote

            if len(request.images) != image_count:
                raise SystemExit(f"unexpected prepared image count: {len(request.images)}")
            if request.preprocess_input_bytes <= 0:
                raise SystemExit("expected non-empty image payload accounting")
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak_bytes))
            urlparse_calls.append(call_count)
            unquote_calls.append(unquote_call_count)

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "urlparse_calls_mean": statistics.fmean(urlparse_calls),
                "unquote_calls_mean": statistics.fmean(unquote_calls),
                "prepared_image_count": float(image_count),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
