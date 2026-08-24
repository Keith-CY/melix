#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time


def _load_changed_scope_coverage(repo_root: Path):
    module_path = repo_root / "scripts" / "changed_scope_coverage.py"
    spec = importlib.util.spec_from_file_location("changed_scope_coverage_probe_target", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_probe(repo_root: Path, *, path_count: int = 300, samples: int = 7) -> dict[str, float]:
    module = _load_changed_scope_coverage(repo_root)
    elapsed_samples: list[float] = []
    read_samples: list[float] = []
    main_elapsed_samples: list[float] = []
    main_coverage_read_samples: list[float] = []
    allowlist_parse_samples: list[float] = []
    allowlist_raw = json.dumps([f"pkg/module_{index}.py" for index in range(path_count * 120)])
    expected_allowlist_size = path_count * 120

    with tempfile.TemporaryDirectory(prefix="melix-changed-scope-probe-") as tmp:
        root = Path(tmp)
        rel_paths = [f"pkg/module_{index}.py" for index in range(path_count)]
        for rel_path in rel_paths:
            source_path = root / rel_path
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("covered = 1\nmissed = 2\n", encoding="utf-8")

        coverage_payload = {
            "files": {
                rel_path: {"executed_lines": [1], "missing_lines": [2]}
                for rel_path in rel_paths
            }
        }

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
                        {3, 4},
                    )
                    if measurable or covered or missed:
                        raise RuntimeError("empty changed sets must not produce measurable lines")
                elapsed_samples.append((time.perf_counter() - start) * 1000.0)
                read_samples.append(float(read_calls))
        finally:
            module.Path.read_text = original_read_text

        if hasattr(module, "main"):
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(coverage_payload), encoding="utf-8")
            original_argv = sys.argv
            original_cwd = module.Path.cwd
            original_environ = os.environ.copy()
            original_read_text = module.Path.read_text
            try:
                module.Path.cwd = staticmethod(lambda: root)
                os.environ["MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON"] = "[]"
                for _ in range(samples):
                    coverage_read_calls = 0

                    def counted_main_read_text(self: Path, *args: object, **kwargs: object) -> str:
                        nonlocal coverage_read_calls
                        if self == coverage_path:  # pragma: no cover - regression signal on old target
                            coverage_read_calls += 1
                        return original_read_text(self, *args, **kwargs)  # pragma: no cover

                    module.Path.read_text = counted_main_read_text
                    sys.argv = [
                        "changed_scope_coverage.py",
                        "--coverage-json",
                        str(coverage_path),
                        *rel_paths,
                    ]
                    start = time.perf_counter()
                    with contextlib.redirect_stdout(io.StringIO()):
                        main_exit_code = module.main()
                    if main_exit_code != 0:  # pragma: no cover - defensive probe failure path
                        raise RuntimeError("empty filtered path run should pass")
                    main_elapsed_samples.append((time.perf_counter() - start) * 1000.0)
                    main_coverage_read_samples.append(float(coverage_read_calls))
            finally:
                module.Path.cwd = original_cwd
                module.Path.read_text = original_read_text
                sys.argv = original_argv
                os.environ.clear()
                os.environ.update(original_environ)
        else:
            main_elapsed_samples.append(0.0)
            main_coverage_read_samples.append(0.0)

        allowlist_parser = getattr(module, "_coverage_path_allowlist_from_raw", None)
        if allowlist_parser is None:
            allowlist_parse_samples.append(0.0)
        else:
            for _ in range(samples):
                allowlist_parser.cache_clear()
                start = time.perf_counter()
                allowlist = allowlist_parser(allowlist_raw)
                allowlist_parse_samples.append((time.perf_counter() - start) * 1000.0)
                if allowlist is None or len(allowlist) != expected_allowlist_size:
                    raise RuntimeError(  # pragma: no cover - defensive probe failure path
                        "large JSON allowlist parsed to an unexpected size"
                    )

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "allowlist_parse_elapsed_ms_mean": statistics.fmean(allowlist_parse_samples),
        "main_empty_allowlist_elapsed_ms_mean": statistics.fmean(main_elapsed_samples),
        "main_empty_allowlist_coverage_read_calls_mean": statistics.fmean(
            main_coverage_read_samples
        ),
        "source_read_calls_mean": statistics.fmean(read_samples),
        "allowlist_path_count": float(expected_allowlist_size),
        "path_count": float(path_count),
        "sample_count": float(samples),
    }


def main() -> int:
    print(json.dumps(run_probe(Path.cwd()), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
