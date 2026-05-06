#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2  # noqa: E402
from worker.runtime import multimodal_preprocessing  # noqa: E402
from worker.runtime.multimodal_preprocessing import prepare_vision_request  # noqa: E402


def _sample(iterations: int) -> tuple[float, int]:
    with TemporaryDirectory() as directory:
        image_path = Path(directory) / "probe-image.txt"
        image_path.write_bytes(b"synthetic local image bytes")
        image_uri = image_path.as_uri()
        message = common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Describe the image."),
                common_pb2.MessagePart(
                    image_uri=image_uri,
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_URI,
                    ),
                ),
            ],
        )
        original_urlparse = multimodal_preprocessing.urlparse
        urlparse_calls = 0

        def tracked_urlparse(uri: str):
            nonlocal urlparse_calls
            urlparse_calls += 1
            return original_urlparse(uri)

        multimodal_preprocessing.urlparse = tracked_urlparse
        try:
            started = time.perf_counter()
            for _ in range(iterations):
                request = prepare_vision_request([message])
                if request.images[0].bytes_data != b"synthetic local image bytes":
                    raise RuntimeError("unexpected image bytes")
            elapsed_ms = (time.perf_counter() - started) * 1000.0
        finally:
            multimodal_preprocessing.urlparse = original_urlparse
    return elapsed_ms, urlparse_calls


def main() -> None:
    iterations = int(os.environ.get("MELIX_PROBE_ITERATIONS", "5000"))
    sample_count = int(os.environ.get("MELIX_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    urlparse_call_samples: list[float] = []
    for _ in range(sample_count):
        elapsed_ms, urlparse_calls = _sample(iterations)
        elapsed_samples.append(elapsed_ms)
        urlparse_call_samples.append(float(urlparse_calls))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "elapsed_ms_min": min(elapsed_samples),
                "urlparse_calls_mean": statistics.fmean(urlparse_call_samples),
                "iteration_count": float(iterations),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
