from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path.cwd().resolve()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.evaluation_final_result import (  # noqa: E402
    _GENERIC_FENCE_PATTERN,
    _TEXT_ANSWER_PATTERN,
    _last_stripped_pattern_match,
    extract_final_result,
)


def _legacy_extract_text_heuristic(raw_response: str) -> str:
    answer_prefix_count = 0
    answer_prefix_candidate = ""
    for match in _TEXT_ANSWER_PATTERN.finditer(raw_response):
        candidate = match.group(1).strip()
        if not candidate:
            continue
        answer_prefix_count += 1
        if answer_prefix_count > 1:
            return ""
        answer_prefix_candidate = candidate
    if answer_prefix_candidate:
        return answer_prefix_candidate

    candidate = _last_stripped_pattern_match(_GENERIC_FENCE_PATTERN, raw_response)
    if candidate:
        return candidate

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", raw_response) if paragraph.strip()]
    if not paragraphs:
        return ""
    lines = [line.strip() for line in paragraphs[-1].splitlines() if line.strip()]
    if lines:
        return lines[-1]
    return paragraphs[-1]


def _payload(*, paragraphs: int, lines_per_paragraph: int, line_width: int) -> str:
    chunks: list[str] = []
    body = "x" * max(1, line_width - 20)
    for paragraph_index in range(paragraphs):
        lines = [
            f"p{paragraph_index:05d}-line{line_index:03d}-{body}"
            for line_index in range(lines_per_paragraph)
        ]
        chunks.append("\n".join(lines))
    chunks.append("Terminal response line")
    return "\n\n".join(chunks) + "\n\n   \n"


def _run_once(raw_response: str, *, legacy: bool, iterations: int) -> tuple[float, int, int]:
    checksum = 0
    tracemalloc.start()
    started = time.perf_counter()
    for _ in range(iterations):
        if legacy:
            extracted = _legacy_extract_text_heuristic(raw_response)
        else:
            outcome = extract_final_result(
                raw_response=raw_response,
                result_kind="text",
                extraction_mode="heuristic_final",
            )
            extracted = outcome.extracted_result
        checksum += len(extracted)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed_ms, peak, checksum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paragraphs", type=int, default=2500)
    parser.add_argument("--lines-per-paragraph", type=int, default=3)
    parser.add_argument("--line-width", type=int, default=80)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()

    raw_response = _payload(
        paragraphs=args.paragraphs,
        lines_per_paragraph=args.lines_per_paragraph,
        line_width=args.line_width,
    )

    legacy_elapsed: list[float] = []
    legacy_peaks: list[float] = []
    new_elapsed: list[float] = []
    new_peaks: list[float] = []
    checksum = 0
    for _ in range(args.samples):
        elapsed, peak, checksum = _run_once(raw_response, legacy=True, iterations=args.iterations)
        legacy_elapsed.append(elapsed)
        legacy_peaks.append(float(peak))
        elapsed, peak, checksum = _run_once(raw_response, legacy=False, iterations=args.iterations)
        new_elapsed.append(elapsed)
        new_peaks.append(float(peak))

    legacy_elapsed_mean = statistics.fmean(legacy_elapsed)
    elapsed_mean = statistics.fmean(new_elapsed)
    legacy_peak_mean = statistics.fmean(legacy_peaks)
    peak_mean = statistics.fmean(new_peaks)
    print(
        json.dumps(
            {
                "checksum": float(checksum),
                "elapsed_ms_mean": elapsed_mean,
                "legacy_elapsed_ms_mean": legacy_elapsed_mean,
                "delta_ms_mean": elapsed_mean - legacy_elapsed_mean,
                "peak_bytes_mean": peak_mean,
                "legacy_peak_bytes_mean": legacy_peak_mean,
                "peak_bytes_delta_mean": peak_mean - legacy_peak_mean,
                "paragraph_count": float(args.paragraphs + 1),
                "iteration_count": float(args.iterations),
                "samples": float(args.samples),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
