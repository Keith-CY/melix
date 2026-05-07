from __future__ import annotations

import builtins
import json
import statistics
import tempfile
import time
from pathlib import Path
from threading import Event

from packages.protocol.python.worker.v1 import inference_pb2
from worker.runtime import deterministic_image_generation_runtime as image_runtime
from worker.runtime.deterministic_image_generation_runtime import DeterministicImageGenerationRuntime


def _run_once(sample: int) -> dict[str, float]:
    runtime = DeterministicImageGenerationRuntime()
    loaded_model = {"model_id": "melix-dev-image"}
    output_byte_scan_calls = 0

    def counting_sum(iterable, *args):
        nonlocal output_byte_scan_calls
        output_byte_scan_calls += 1
        return builtins.sum(iterable, *args)

    had_module_sum = hasattr(image_runtime, "sum")
    original_module_sum = getattr(image_runtime, "sum", None)
    image_runtime.sum = counting_sum
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory() as raw_tmp:
            images_root = Path(raw_tmp)
            generate_result = runtime.generate_images(
                loaded_model,
                inference_pb2.ImageGenerateRequest(
                    prompt=f"probe generated image {sample}",
                    size="256x256",
                    response_format="png",
                    artifact_namespace="probe",
                    n=96,
                ),
                job_id=f"output-bytes-generate-{sample}",
                images_root=images_root,
                cancel_event=Event(),
            )
            generated_output_bytes = float(runtime.last_probe_snapshot().output_bytes)

            edit_result = runtime.edit_image(
                loaded_model,
                inference_pb2.ImageEditRequest(
                    prompt=f"probe image edit {sample}",
                    image=(b"SOURCE_IMAGE_BLOCK_%04d" % sample) * 256,
                    mask=(b"MASK_IMAGE_BLOCK_%04d" % sample) * 128,
                    size="256x256",
                    response_format="png",
                    n=96,
                ),
                job_id=f"output-bytes-edit-{sample}",
                images_root=images_root,
                cancel_event=Event(),
            )
            edit_output_bytes = float(runtime.last_probe_snapshot().output_bytes)
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if had_module_sum:
            image_runtime.sum = original_module_sum
        else:
            delattr(image_runtime, "sum")

    checksum = 0
    for payload in generate_result.images:
        checksum += payload[0]
    for payload in edit_result.images:
        checksum += payload[0]

    return {
        "elapsed_ms": elapsed_ms,
        "output_byte_scan_calls": float(output_byte_scan_calls),
        "generated_image_count": float(len(generate_result.images)),
        "edit_image_count": float(len(edit_result.images)),
        "generated_output_bytes": generated_output_bytes,
        "edit_output_bytes": edit_output_bytes,
        "payload_checksum": float(checksum),
    }


def main() -> None:
    samples = [_run_once(index) for index in range(5)]
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(sample["elapsed_ms"] for sample in samples),
                "output_byte_scan_calls_mean": statistics.fmean(
                    sample["output_byte_scan_calls"] for sample in samples
                ),
                "generated_image_count": samples[-1]["generated_image_count"],
                "edit_image_count": samples[-1]["edit_image_count"],
                "generated_output_bytes": samples[-1]["generated_output_bytes"],
                "edit_output_bytes": samples[-1]["edit_output_bytes"],
                "payload_checksum": samples[-1]["payload_checksum"],
                "sample_count": float(len(samples)),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
