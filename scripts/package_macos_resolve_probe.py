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
    cli_elapsed_samples: list[float] = []
    tail_debug_elapsed_samples: list[float] = []
    cli_tail_debug_elapsed_samples: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-package-resolve-") as temp_dir:
        synthetic_repo = Path(temp_dir) / "repo"
        menubar_build_root = synthetic_repo / "apps/macos-menubar/.build"
        cli_build_root = synthetic_repo / ".build"
        expected = menubar_build_root / "arch-0000" / "release" / "melix-menubar"
        expected_cli = cli_build_root / "arch-0000" / "release" / "melix"
        for build_root, product_name in (
            (menubar_build_root, "melix-menubar"),
            (cli_build_root, "melix"),
        ):
            for index in range(triple_count):
                product_dir = build_root / f"arch-{index:04d}" / "release"
                product_dir.mkdir(parents=True, exist_ok=True)
                name = product_name if index == 0 else "other-product"
                (product_dir / name).write_text("x", encoding="utf-8")

        tail_repo = Path(temp_dir) / "tail-repo"
        tail_menubar_build_root = tail_repo / "apps/macos-menubar/.build"
        tail_cli_build_root = tail_repo / ".build"
        expected_tail = tail_menubar_build_root / "arch-1499" / "debug" / "melix-menubar"
        expected_cli_tail = tail_cli_build_root / "arch-1499" / "debug" / "melix"
        for build_root, product_name in (
            (tail_menubar_build_root, "melix-menubar"),
            (tail_cli_build_root, "melix"),
        ):
            for index in range(triple_count):
                product_dir = build_root / f"arch-{index:04d}" / "debug"
                product_dir.mkdir(parents=True, exist_ok=True)
                name = product_name if index == triple_count - 1 else "other-product"
                (product_dir / name).write_text("x", encoding="utf-8")

        resolved = expected
        resolved_cli = expected_cli
        resolved_tail = expected_tail
        resolved_cli_tail = expected_cli_tail
        for _ in range(sample_count):
            started = time.perf_counter()
            resolved = module.resolve_built_binary(synthetic_repo)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            started = time.perf_counter()
            resolved_cli = module.resolve_built_cli_binary(synthetic_repo)
            cli_elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            started = time.perf_counter()
            resolved_tail = module.resolve_built_binary(tail_repo)
            tail_debug_elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            started = time.perf_counter()
            resolved_cli_tail = module.resolve_built_cli_binary(tail_repo)
            cli_tail_debug_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    if resolved != expected:
        raise AssertionError(f"expected {expected}, got {resolved}")
    if resolved_cli != expected_cli:
        raise AssertionError(f"expected {expected_cli}, got {resolved_cli}")  # pragma: no cover
    if resolved_tail != expected_tail:
        raise AssertionError(f"expected {expected_tail}, got {resolved_tail}")  # pragma: no cover
    if resolved_cli_tail != expected_cli_tail:
        raise AssertionError(f"expected {expected_cli_tail}, got {resolved_cli_tail}")  # pragma: no cover
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "cli_elapsed_ms_mean": round(statistics.fmean(cli_elapsed_samples), 6),
                "cli_elapsed_ms_min": round(min(cli_elapsed_samples), 6),
                "tail_debug_elapsed_ms_mean": round(statistics.fmean(tail_debug_elapsed_samples), 6),
                "tail_debug_elapsed_ms_min": round(min(tail_debug_elapsed_samples), 6),
                "cli_tail_debug_elapsed_ms_mean": round(statistics.fmean(cli_tail_debug_elapsed_samples), 6),
                "cli_tail_debug_elapsed_ms_min": round(min(cli_tail_debug_elapsed_samples), 6),
                "sample_count": float(sample_count),
                "triple_count": float(triple_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
