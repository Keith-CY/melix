#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import statistics
import tempfile
import time


def _load_changed_scope_coverage(repo_root: Path):
    module_path = repo_root / "scripts" / "changed_scope_coverage.py"
    spec = importlib.util.spec_from_file_location("changed_scope_coverage_measured_probe_target", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_probe(
    repo_root: Path,
    *,
    path_count: int = 300,
    measured_lines_per_path: int = 500,
    allowlist_parse_count: int = 10000,
    samples: int = 7,
) -> dict[str, float]:
    module = _load_changed_scope_coverage(repo_root)
    elapsed_samples: list[float] = []
    allowlist_elapsed_samples: list[float] = []
    read_samples: list[float] = []
    allowlist_value = json.dumps("pkg/module_0.py")

    with tempfile.TemporaryDirectory(prefix="melix-changed-scope-measured-probe-") as tmp:
        root = Path(tmp)
        rel_paths = [f"pkg/module_{index}.py" for index in range(path_count)]
        for rel_path in rel_paths:
            source_path = root / rel_path
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("covered = 1\nmissed = 2\n", encoding="utf-8")

        coverage_payload = {
            "files": {
                rel_path: {
                    "executed_lines": list(range(1, measured_lines_per_path + 1, 2)),
                    "missing_lines": list(range(2, measured_lines_per_path + 1, 2)),
                }
                for rel_path in rel_paths
            }
        }
        changed_lines = {measured_lines_per_path + 1, measured_lines_per_path + 2}

        original_read_text = module.Path.read_text
        try:
            for _ in range(samples):
                read_calls = 0

                def counted_read_text(self: Path, *args: object, **kwargs: object) -> str:
                    nonlocal read_calls
                    read_calls += 1
                    return original_read_text(self, *args, **kwargs)

                module.Path.read_text = counted_read_text
                start = time.perf_counter()
                for rel_path in rel_paths:
                    measurable, covered, missed = module._measurable_changed_lines(
                        root,
                        coverage_payload,
                        rel_path,
                        changed_lines,
                    )
                    if measurable or covered or missed:
                        raise RuntimeError("empty changed sets must not produce measurable lines")
                elapsed_samples.append((time.perf_counter() - start) * 1000.0)
                read_samples.append(float(read_calls))

                start = time.perf_counter()
                for _ in range(allowlist_parse_count):
                    allowlist = module._coverage_path_allowlist(
                        {"MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON": allowlist_value}
                    )
                    if allowlist != frozenset({"pkg/module_0.py"}):
                        raise RuntimeError("single-string allowlist parse returned unexpected paths")
                allowlist_elapsed_samples.append((time.perf_counter() - start) * 1000.0)
        finally:
            module.Path.read_text = original_read_text

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "allowlist_parse_elapsed_ms_mean": statistics.fmean(allowlist_elapsed_samples),
        "allowlist_parse_count": float(allowlist_parse_count),
        "source_read_calls_mean": statistics.fmean(read_samples),
        "path_count": float(path_count),
        "measured_lines_per_path": float(measured_lines_per_path),
        "sample_count": float(samples),
    }


def main() -> int:
    print(json.dumps(run_probe(Path.cwd()), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
