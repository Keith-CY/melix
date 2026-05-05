#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import statistics
import time


def _load_changed_scope_module(repo_root: Path):
    module_path = repo_root / "scripts" / "changed_scope_coverage.py"
    spec = importlib.util.spec_from_file_location("changed_scope_coverage_probe_target", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_synthetic_diff(file_count: int = 240, hunks_per_file: int = 8, additions_per_hunk: int = 4) -> str:
    lines: list[str] = []
    for file_index in range(file_count):
        path = f"pkg/module_{file_index:04d}.py"
        lines.extend(
            [
                f"diff --git a/{path} b/{path}",
                f"--- a/{path}",
                f"+++ b/{path}",
            ]
        )
        for hunk_index in range(hunks_per_file):
            start = hunk_index * 10 + 1
            lines.append(f"@@ -{start},3 +{start},6 @@")
            lines.append(" context")
            lines.append("-old_value")
            for addition_index in range(additions_per_hunk):
                lines.append(f"+new_value_{file_index}_{hunk_index}_{addition_index}")
            lines.append(" context_tail")
    return "\n".join(lines)


def run_probe(repo_root: Path) -> dict[str, float]:
    module = _load_changed_scope_module(repo_root)
    diff_text = _build_synthetic_diff()
    expected_changed = 240 * 8 * 4
    samples: list[float] = []
    observed_changed = 0
    observed_files = 0
    for _ in range(12):
        start = time.perf_counter()
        parsed = module._parse_changed_lines(diff_text)
        samples.append((time.perf_counter() - start) * 1000.0)
        observed_files = len(parsed)
        observed_changed = sum(len(lines) for lines in parsed.values())
        if observed_files != 240 or observed_changed != expected_changed:
            raise RuntimeError(
                f"unexpected parser output: files={observed_files} changed={observed_changed}"
            )
    return {
        "elapsed_ms_mean": statistics.fmean(samples),
        "elapsed_ms_min": min(samples),
        "line_count": float(diff_text.count("\n") + 1),
        "file_count": float(observed_files),
        "changed_line_count": float(observed_changed),
    }


def main() -> int:
    repo_root = Path.cwd()
    print(json.dumps(run_probe(repo_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
