from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path


def _prepare_imports() -> None:
    repo_root = Path.cwd()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))


def _build_request():
    from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest

    image = PreparedImageInput(
        bytes_data=b"synthetic-image-payload",
        source_kind="inline",
        reference="inline:sample.jpg",
        mime_type="image/jpeg",
        format="jpg",
        filename="sample.jpg",
        sha256_hex="f" * 64,
    )
    return PreparedVisionRequest(
        prompt_text="Describe the image in detail.",
        images=[image],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=1.0,
        preprocess_input_bytes=image.byte_length,
        preprocess_peak_memory_bytes=image.byte_length,
        prompt_hash_hex="p" * 64,
        multimodal_hash_hex="m" * 64,
    )


def _build_loaded_model() -> dict[str, object]:
    return {
        "model_id": "melix-dev-vlm",
        "revision": "main",
        "tokenizer_hash": "tok-abcdef",
        "quant_profile_id": "q8",
        "metadata": {
            "melix.vlm.execution_mode": "multimodal",
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "vision_tokenization_mode": "interleaved",
            "vision_max_images_per_prompt": "8",
            "melix.multimodal_adapter_hash": "adapter-a",
        },
    }


def main() -> int:
    _prepare_imports()
    from worker.runtime.multimodal_fast_paths import fast_path_probe_signature

    loaded_model = _build_loaded_model()
    request = _build_request()
    expected_signature = fast_path_probe_signature(loaded_model, request)

    iterations = int(os.environ.get("MELIX_MULTIMODAL_SIGNATURE_PROBE_ITERATIONS", "120000"))
    sample_count = int(os.environ.get("MELIX_MULTIMODAL_SIGNATURE_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    signature_count = 0

    for _ in range(sample_count):
        tracemalloc.start()
        start = time.perf_counter()
        for _index in range(iterations):
            signature = fast_path_probe_signature(loaded_model, request)
            if signature != expected_signature:
                raise AssertionError("fast-path probe signature changed during probe")
            signature_count += 1
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "sample_count": float(sample_count),
                "iterations_per_sample": float(iterations),
                "signature_count": float(signature_count),
                "top_level_item_count": float(expected_signature[1].count("(")) - 1.0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
