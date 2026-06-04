#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import statistics
import tempfile
import time
from pathlib import Path


def _load_packaging_module(repo_root: Path):
    module_path = repo_root / "scripts" / "package_macos_menubar_app.py"
    spec = importlib.util.spec_from_file_location("melix_package_macos_app_probe", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    repo_root = Path.cwd()
    module = _load_packaging_module(repo_root)
    triple_count = 1500
    sample_count = 9
    elapsed_samples: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-package-resolve-") as temp_dir:
        synthetic_repo = Path(temp_dir) / "repo"
        build_root = synthetic_repo / "apps/macos-menubar/.build"
        expected = build_root / "arch-0000" / "release" / "melix-menubar"
        for index in range(triple_count):
            product_dir = build_root / f"arch-{index:04d}" / "release"
            product_dir.mkdir(parents=True, exist_ok=True)
            product_name = "melix-menubar" if index == 0 else "other-product"
            (product_dir / product_name).write_text("x", encoding="utf-8")

        resolved = expected
        for _ in range(sample_count):
            started = time.perf_counter()
            resolved = module.resolve_built_binary(synthetic_repo)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    if resolved != expected:
        raise AssertionError(f"expected {expected}, got {resolved}")
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "sample_count": float(sample_count),
                "triple_count": float(triple_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
