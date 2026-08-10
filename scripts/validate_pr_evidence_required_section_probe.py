from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import statistics
import time
import tracemalloc
from typing import Callable

REPO_ROOT = Path(os.environ.get("MELIX_VALIDATE_PR_EVIDENCE_REPO_ROOT") or Path(__file__).resolve().parents[1])
MODULE_PATH = REPO_ROOT / "scripts" / "validate_pr_evidence.py"
MODULE_SPEC = importlib.util.spec_from_file_location("validate_pr_evidence", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
validate_pr_evidence = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(validate_pr_evidence)


def _large_pr_body(filler_line_count: int) -> str:
    summary_lines = "\n".join(
        f"- Summary filler row {index:05d}: generated release-note context."
        for index in range(filler_line_count)
    )
    checklist_lines = "\n".join(
        f"- [x] Evidence checklist filler {index:05d}: retained by reviewers."
        for index in range(filler_line_count)
    )
    return f"""
## Summary
{summary_lines}

## Plan or Spec
- docs/plans/2026-08-10-pr-evidence-required-section-scan.md

## Commands Run
```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_validate_pr_evidence.py
```

## Coverage and Metrics
- changed-scope coverage: 100 percent.

## Known Gaps
- None.

## Evidence Checklist
{checklist_lines}
""".strip()


def _baseline_extract_sections(body_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None
    for line in body_text.splitlines():
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections.setdefault(current_section, [])
            continue
        if current_section is not None:
            sections[current_section].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _timed_samples(
    extractor: Callable[[str], dict[str, str]],
    body: str,
    *,
    iterations: int,
    sample_count: int,
) -> tuple[list[float], list[float], float]:
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    checksum = 0.0
    required = validate_pr_evidence.REQUIRED_SECTIONS
    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            sections = extractor(body)
            checksum += sum(len(sections[name]) for name in required)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak))
    return elapsed_samples, peak_samples, checksum


def main() -> int:
    filler_line_count = int(os.environ.get("MELIX_VALIDATE_PR_EVIDENCE_FILLER_LINES", "2500"))
    iterations = int(os.environ.get("MELIX_VALIDATE_PR_EVIDENCE_ITERATIONS", "120"))
    sample_count = int(os.environ.get("MELIX_VALIDATE_PR_EVIDENCE_SAMPLES", "5"))
    body = _large_pr_body(filler_line_count)

    baseline_elapsed, baseline_peaks, baseline_checksum = _timed_samples(
        _baseline_extract_sections,
        body,
        iterations=iterations,
        sample_count=sample_count,
    )
    current_elapsed, current_peaks, current_checksum = _timed_samples(
        validate_pr_evidence._extract_sections,
        body,
        iterations=iterations,
        sample_count=sample_count,
    )

    if baseline_checksum != current_checksum:
        raise SystemExit(f"section checksum mismatch: {current_checksum} != {baseline_checksum}")

    baseline_mean = statistics.fmean(baseline_elapsed)
    current_mean = statistics.fmean(current_elapsed)
    metrics = {
        "elapsed_ms_mean": current_mean,
        "baseline_elapsed_ms_mean": baseline_mean,
        "delta_ms_mean": current_mean - baseline_mean,
        "speedup_ratio": baseline_mean / current_mean if current_mean else 0.0,
        "peak_bytes_mean": statistics.fmean(current_peaks),
        "baseline_peak_bytes_mean": statistics.fmean(baseline_peaks),
        "irrelevant_section_line_count": float(filler_line_count * 2),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
        "section_checksum": current_checksum,
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
