from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable


OUTPUT_KEYS = (
    "proto_should_run",
    "swift_should_run",
    "python_should_run",
    "integration_should_run",
)

FORCE_ALL_PATTERNS = (
    ".github/workflows/ci-pr.yml",
    ".github/workflows/ci-full-scheduled.yml",
    "Makefile",
    "Package.swift",
    "Package.resolved",
    "pyproject.toml",
    "uv.lock",
    "buf.yaml",
    "buf.gen.yaml",
    "scripts/ci_progress.sh",
    "scripts/ci_scope.py",
)

PROTO_PATTERNS = (
    "buf.yaml",
    "buf.gen.yaml",
    "packages/protocol/schema/**",
    "packages/protocol/descriptors/**",
    "packages/protocol/python/**",
    "packages/protocol/swift/**",
)

SWIFT_PATTERNS = (
    "Package.swift",
    "Package.resolved",
    "packages/protocol/swift/**",
    "services/control-plane-swift/**",
    "services/mlx-text-worker-swift/**",
    "apps/macos-menubar/**",
)

PYTHON_PATTERNS = (
    "pyproject.toml",
    "uv.lock",
    "infra/perf/**",
    "scripts/**",
    "services/mlx-worker-python/**",
)

INTEGRATION_PATTERNS = (
    "Package.swift",
    "Package.resolved",
    "pyproject.toml",
    "uv.lock",
    "buf.yaml",
    "buf.gen.yaml",
    "packages/protocol/**",
    "scripts/dev_app_up.py",
    "scripts/dev_up.py",
    "scripts/dev_up.sh",
    "scripts/dev_down.sh",
    "services/control-plane-swift/**",
    "services/mlx-text-worker-swift/**",
    "services/mlx-worker-python/worker/control_plane_bridge.py",
    "services/mlx-worker-python/worker/runtime/**",
    "tests/integration/**",
)


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(f"{prefix}/")
    return path == pattern


def _any_match(path: str, patterns: Iterable[str]) -> bool:
    return any(_matches(path, pattern) for pattern in patterns)


def classify_paths(paths: Iterable[str]) -> dict[str, bool]:
    normalized_paths = [
        normalized
        for path in paths
        if (normalized := _normalize_path(path))
    ]

    result = {key: False for key in OUTPUT_KEYS}
    if any(_any_match(path, FORCE_ALL_PATTERNS) for path in normalized_paths):
        return {key: True for key in OUTPUT_KEYS}

    for path in normalized_paths:
        if _any_match(path, PROTO_PATTERNS):
            result["proto_should_run"] = True
            result["swift_should_run"] = True
            result["python_should_run"] = True
            result["integration_should_run"] = True
            continue
        if _any_match(path, SWIFT_PATTERNS):
            result["swift_should_run"] = True
            result["integration_should_run"] = True
        if _any_match(path, PYTHON_PATTERNS):
            result["python_should_run"] = True
        if _any_match(path, INTEGRATION_PATTERNS):
            result["integration_should_run"] = True
    return result


def _read_changed_files(args: argparse.Namespace) -> list[str]:
    paths: list[str] = []
    if args.changed_files_file:
        paths.extend(Path(args.changed_files_file).read_text(encoding="utf-8").splitlines())
    paths.extend(args.paths)
    return paths


def _write_github_output(values: dict[str, bool], output_path: str) -> None:
    with Path(output_path).open("a", encoding="utf-8") as output_file:
        for key in OUTPUT_KEYS:
            output_file.write(f"{key}={str(values[key]).lower()}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify changed paths for Melix PR CI scope.")
    parser.add_argument("paths", nargs="*", help="Changed paths to classify.")
    parser.add_argument(
        "--changed-files-file",
        help="Newline-delimited file containing changed paths.",
    )
    parser.add_argument(
        "--github-output",
        default=os.environ.get("GITHUB_OUTPUT"),
        help="GitHub Actions output file to append key=value results to.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of GitHub output lines.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    values = classify_paths(_read_changed_files(args))
    if args.json:
        print(json.dumps(values, sort_keys=True))
    else:
        for key in OUTPUT_KEYS:
            print(f"{key}={str(values[key]).lower()}")
    if args.github_output:
        _write_github_output(values, args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
