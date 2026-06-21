from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path
from threading import Event

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2
from worker.runtime import deterministic_image_generation_runtime as image_runtime
from worker.runtime.deterministic_image_generation_runtime import DeterministicImageGenerationRuntime


def _run_once(sample: int) -> dict[str, float]:
    source_bytes = (b"SOURCE_IMAGE_BLOCK_%04d" % sample) * 220_000
    mask_bytes = (b"MASK_IMAGE_BLOCK_%04d" % sample) * 220_000
    original_sha256 = image_runtime.hashlib.sha256
    original_unquote = image_runtime.unquote
    tracked_inputs = {source_bytes, mask_bytes}
    digest_calls = 0
    unquote_calls = 0

    def counting_sha256(payload: bytes = b""):
        nonlocal digest_calls
        if payload in tracked_inputs:
            digest_calls += 1
        return original_sha256(payload)

    def counting_unquote(uri_path: str) -> str:  # pragma: no cover - expected only on origin/main comparison.
        nonlocal unquote_calls  # pragma: no cover - expected only on origin/main comparison.
        unquote_calls += 1
        return original_unquote(uri_path)

    runtime = DeterministicImageGenerationRuntime()
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp_path = Path(raw_tmp)
        source_path = tmp_path / f"source-{sample}.png"
        mask_path = tmp_path / f"mask-{sample}.png"
        source_path.write_bytes(source_bytes)
        mask_path.write_bytes(mask_bytes)
        request = inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id=f"digest-probe-{sample}"),
            prompt="add detail without changing composition",
            image_uri=source_path.as_uri(),
            mask_uri=mask_path.as_uri(),
            size="512x512",
            response_format="png",
            n=8,
        )
        image_runtime.hashlib.sha256 = counting_sha256
        image_runtime.unquote = counting_unquote
        started = time.perf_counter()
        try:
            result = runtime.edit_image(
                {"model_id": "melix-dev-image"},
                request,
                job_id=f"digest-probe-{sample}",
                images_root=tmp_path,
                cancel_event=Event(),
            )
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            image_runtime.hashlib.sha256 = original_sha256
            image_runtime.unquote = original_unquote

    payload_checksum = sum(sum(image) for image in result.images)
    return {
        "elapsed_ms": elapsed_ms,
        "digest_calls": float(digest_calls),
        "unquote_calls": float(unquote_calls),
        "image_count": float(len(result.images)),
        "payload_checksum": float(payload_checksum),
    }


def main() -> None:
    samples = [_run_once(index) for index in range(5)]
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(sample["elapsed_ms"] for sample in samples),
                "digest_calls_mean": statistics.fmean(sample["digest_calls"] for sample in samples),
                "unquote_calls_mean": statistics.fmean(sample["unquote_calls"] for sample in samples),
                "image_count": samples[-1]["image_count"],
                "payload_checksum": samples[-1]["payload_checksum"],
                "sample_count": float(len(samples)),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
