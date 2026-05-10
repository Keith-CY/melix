from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(globals().get("__file__", Path.cwd())).resolve()
if REPO_ROOT.is_file():
    REPO_ROOT = REPO_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.multimodal_preprocessing import (  # noqa: E402
    PreparedImageInput,
    PreparedVideoFramePolicy,
    PreparedVisionRequest,
)
from worker.runtime.vision_family_adapters import resolve_vision_family_config  # noqa: E402


class SplitTrackingPrompt(str):
    split_calls = 0

    def split(self, *args: object, **kwargs: object) -> list[str]:
        type(self).split_calls += 1
        return super().split(*args, **kwargs)


def _build_request(prompt_text: str) -> PreparedVisionRequest:
    images = [
        PreparedImageInput(
            bytes_data=b"x" * (index + 1),
            source_kind="inline",
            reference=f"inline:image-{index}",
            mime_type="image/jpeg",
            format="jpg",
            filename=f"image-{index}.jpg",
            sha256_hex=f"{index:064x}"[-64:],
        )
        for index in range(64)
    ]
    video_frame_policies = [
        PreparedVideoFramePolicy(
            reference=f"video-{index}",
            sampling_strategy="uniform",
            requested_frame_budget=index % 8,
            effective_frame_count=index % 8,
            clip_start_ms=0,
            clip_end_ms=(index % 8) * 1000,
            clip_duration_ms=(index % 8) * 1000,
        )
        for index in range(64)
    ]
    return PreparedVisionRequest(
        prompt_text=prompt_text,
        images=images,
        videos=[],
        video_frame_policies=video_frame_policies,
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=sum(image.byte_length for image in images),
        preprocess_peak_memory_bytes=0,
    )


def _expected_media_tokens(family_config) -> int:
    image_divisor = max(1, family_config.image_token_divisor)
    image_tokens = sum(max(1, byte_length // image_divisor) for byte_length in range(1, 65))
    frame_cost = max(1, family_config.video_frame_token_cost)
    video_tokens = sum(max(1, (index % 8) * frame_cost) for index in range(64))
    return image_tokens + video_tokens


def main() -> None:
    family_config = resolve_vision_family_config({"vision_family_id": "paligemma-v1"})
    prompt = SplitTrackingPrompt(("alpha beta gamma delta\n" * 128).strip())
    request = _build_request(prompt)
    expected_count = len(str(prompt).split()) + family_config.prompt_token_bias + _expected_media_tokens(
        family_config
    )
    samples = []
    split_call_samples = []
    peak_samples = []
    token_count = 0

    for _ in range(7):
        SplitTrackingPrompt.split_calls = 0
        tracemalloc.start()
        started = time.perf_counter()
        for _inner in range(400):
            token_count = family_config.prompt_token_count(request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if token_count != expected_count:
            raise SystemExit(f"unexpected token count: {token_count} != {expected_count}")
        samples.append(elapsed_ms)
        split_call_samples.append(float(SplitTrackingPrompt.split_calls))
        peak_samples.append(float(peak_bytes))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(samples),
                "split_calls_mean": statistics.fmean(split_call_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "token_count": float(token_count),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
