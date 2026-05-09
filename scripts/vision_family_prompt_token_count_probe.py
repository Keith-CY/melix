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

from worker.runtime.multimodal_preprocessing import PreparedVisionRequest  # noqa: E402
from worker.runtime.vision_family_adapters import resolve_vision_family_config  # noqa: E402


class SplitTrackingPrompt(str):
    split_calls = 0

    def split(self, *args: object, **kwargs: object) -> list[str]:
        type(self).split_calls += 1
        return super().split(*args, **kwargs)


def _build_request(prompt_text: str) -> PreparedVisionRequest:
    return PreparedVisionRequest(
        prompt_text=prompt_text,
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
    )


def main() -> None:
    family_config = resolve_vision_family_config({"vision_family_id": "paligemma-v1"})
    prompt = SplitTrackingPrompt(("alpha beta gamma delta\n" * 4096).strip())
    request = _build_request(prompt)
    expected_count = len(str(prompt).split()) + family_config.prompt_token_bias
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
