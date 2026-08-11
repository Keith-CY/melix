#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Mapping, Sequence


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_LLVM_COV_LINE_RE = re.compile(r"^\s*(\d+)\|\s*([^|]*)\|")
_COVERAGE_PATHS_ENV = "MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON"
_BASE_REPO_ENV = "MELIX_CHANGED_SCOPE_BASE_REPO"


@dataclass(frozen=True)
class PackageCoverage:
    package_path: str
    changed_file_count: int
    measurable: int
    covered: int
    missed: int
    unlinked_files: tuple[str, ...] = ()

    @property
    def percent(self) -> float:
        return coverage_percent(self.measurable, self.covered)


def coverage_percent(measurable: int, covered: int) -> float:
    return 100.0 if measurable == 0 else covered / measurable * 100.0


def format_total(measurable: int, missed: int) -> str:
    covered = measurable - missed
    percent = coverage_percent(measurable, covered)
    # The PR-scoped performance parser intentionally accepts an integer TOTAL
    # percentage. Floor it so the rendered gate never overstates coverage.
    return f"TOTAL {measurable} {missed} {math.floor(percent)}%"


def meets_minimum(measurable: int, covered: int, minimum: float) -> bool:
    return measurable > 0 and coverage_percent(measurable, covered) >= minimum


def parse_changed_line_numbers(diff_text: str) -> set[int]:
    changed: set[int] = set()
    for line in diff_text.splitlines():
        match = _HUNK_RE.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        changed.update(range(start, start + count))
    return changed


def parse_coverage_paths(raw: str) -> frozenset[str] | None:
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid {_COVERAGE_PATHS_ENV}: {error}") from error
    if isinstance(payload, str):
        return frozenset([payload] if payload else [])
    if not isinstance(payload, list):
        raise ValueError(f"{_COVERAGE_PATHS_ENV} must be a JSON list")
    return frozenset(str(path) for path in payload if str(path))


def parse_exclusions(raw_exclusions: Sequence[str]) -> dict[str, str]:
    exclusions: dict[str, str] = {}
    for raw in raw_exclusions:
        path, separator, reason = raw.partition("=")
        path = path.strip()
        reason = reason.strip()
        if not separator or not path or not reason:
            raise ValueError(
                "--exclude-nonmeasurable requires PATH=REASON with both "
                "fields non-empty"
            )
        exclusions[path] = reason
    return exclusions


def parse_additional_profdata_specs(
    raw_specs: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    specs: dict[str, list[str]] = {}
    for raw in raw_specs:
        package_path, separator, pattern = raw.partition("=")
        package_path = package_path.strip()
        pattern = pattern.strip()
        if not separator or not package_path or not pattern:
            raise ValueError(
                "--additional-profdata requires PACKAGE=GLOB with both "
                "fields non-empty"
            )
        specs.setdefault(package_path, []).append(pattern)
    return {
        package_path: tuple(dict.fromkeys(patterns))
        for package_path, patterns in specs.items()
    }


def resolve_additional_profdata(
    *,
    root: Path,
    package_paths: Sequence[str],
    raw_specs: Sequence[str],
) -> dict[str, tuple[Path, ...]]:
    parsed = parse_additional_profdata_specs(raw_specs)
    unknown_packages = sorted(set(parsed) - set(package_paths))
    if unknown_packages:
        raise ValueError(
            "additional profdata references unselected package(s): "
            + ", ".join(unknown_packages)
        )

    resolved: dict[str, tuple[Path, ...]] = {}
    for package_path, patterns in parsed.items():
        matches: list[Path] = []
        for pattern in patterns:
            pattern_path = Path(pattern)
            if pattern_path.is_absolute() or ".." in pattern_path.parts:
                raise ValueError(
                    "additional profdata glob must stay within the repository: "
                    f"{pattern}"
                )
            pattern_matches = sorted(
                path.resolve()
                for path in root.glob(pattern)
                if path.is_file()
            )
            if not pattern_matches:
                raise FileNotFoundError(
                    f"additional profdata glob matched no files: {pattern}"
                )
            for path in pattern_matches:
                try:
                    path.relative_to(root)
                except ValueError as error:
                    raise ValueError(
                        "additional profdata path is outside the repository: "
                        f"{path}"
                    ) from error
            matches.extend(pattern_matches)
        resolved[package_path] = tuple(dict.fromkeys(matches))
    return resolved


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _repo_root() -> Path:
    completed = _run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
    )
    return Path(completed.stdout.strip()).resolve()


def _normalized_package_paths(
    root: Path,
    raw_packages: Sequence[str],
) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in raw_packages:
        package = (root / raw).resolve()
        try:
            relative = package.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(f"package is outside the repository: {raw}") from error
        if not (package / "Package.swift").is_file():
            raise ValueError(f"Swift package is missing Package.swift: {relative}")
        normalized.append(relative)
    return tuple(dict.fromkeys(normalized))


def _is_package_swift_path(path: str, package_path: str) -> bool:
    normalized_package = package_path.rstrip("/")
    if normalized_package in {"", "."}:
        # The repository-root package owns only its direct SwiftPM source and
        # test roots. Nested packages have their own coverage artifacts and
        # must not be attributed to the root test bundle.
        belongs_to_package = path.startswith(("Sources/", "Tests/", "tests/"))
    else:
        belongs_to_package = path.startswith(f"{normalized_package}/")
    return (
        belongs_to_package
        and path.endswith(".swift")
        and "/.build/" not in path
        and not path.endswith("/Package.swift")
    )


def _candidate_paths_from_worktree(
    root: Path,
    package_paths: Sequence[str],
    diff_from: str | None,
) -> set[str]:
    command = ["git", "diff", "--name-only"]
    if diff_from:
        command.append(diff_from)
    command.extend(["--", *package_paths])
    completed = _run(command, cwd=root)
    paths = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    if diff_from is None:
        cached = _run(
            ["git", "diff", "--cached", "--name-only", "--", *package_paths],
            cwd=root,
        )
        paths.update(
            line.strip()
            for line in cached.stdout.splitlines()
            if line.strip()
        )
    untracked = _run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            *package_paths,
        ],
        cwd=root,
    )
    paths.update(
        line.strip()
        for line in untracked.stdout.splitlines()
        if line.strip()
    )
    return paths


def _candidate_paths_from_base(
    root: Path,
    base_root: Path,
    package_paths: Sequence[str],
) -> set[str]:
    paths: set[str] = set()
    for package_path in package_paths:
        completed = _run(
            [
                "git",
                "diff",
                "--no-index",
                "--name-only",
                "--",
                str(base_root / package_path),
                str(root / package_path),
            ],
            cwd=root,
            check=False,
        )
        if completed.returncode not in {0, 1}:
            raise RuntimeError(completed.stderr.strip() or "git diff failed")
        root_prefix = f"{root.as_posix()}/"
        for raw in completed.stdout.splitlines():
            candidate = raw.strip().strip('"')
            if candidate.startswith(root_prefix):
                paths.add(candidate.removeprefix(root_prefix))
    return paths


def discover_candidate_paths(
    *,
    root: Path,
    base_root: Path | None,
    package_paths: Sequence[str],
    diff_from: str | None,
    coverage_paths: frozenset[str] | None,
) -> tuple[str, ...]:
    candidates = (
        set(coverage_paths)
        if coverage_paths is not None
        else (
            _candidate_paths_from_base(root, base_root, package_paths)
            if base_root is not None
            else _candidate_paths_from_worktree(root, package_paths, diff_from)
        )
    )
    return tuple(
        sorted(
            path
            for path in candidates
            if any(
                _is_package_swift_path(path, package_path)
                for package_path in package_paths
            )
            and (root / path).is_file()
        )
    )


def _changed_lines_for_path(
    *,
    root: Path,
    base_root: Path | None,
    diff_from: str | None,
    rel_path: str,
) -> set[int]:
    target = root / rel_path
    if base_root is not None:
        base_file = base_root / rel_path
        before = str(base_file) if base_file.is_file() else "/dev/null"
        completed = _run(
            [
                "git",
                "diff",
                "--no-index",
                "--unified=0",
                "--",
                before,
                str(target),
            ],
            cwd=root,
            check=False,
        )
        if completed.returncode not in {0, 1}:
            raise RuntimeError(completed.stderr.strip() or "git diff failed")
        return parse_changed_line_numbers(completed.stdout)

    command = ["git", "diff", "--unified=0", diff_from or "HEAD"]
    command.extend(["--", rel_path])
    completed = _run(command, cwd=root)
    changed = parse_changed_line_numbers(completed.stdout)
    if not changed:
        tracked = _run(
            ["git", "ls-files", "--error-unmatch", "--", rel_path],
            cwd=root,
            check=False,
        )
        if tracked.returncode != 0:
            changed.update(range(1, len(target.read_text().splitlines()) + 1))
    return changed


def _coverage_artifacts(
    root: Path,
    package_path: str,
    *,
    additional_profdata: Sequence[Path] = (),
    merge_root: Path | None = None,
) -> tuple[Path, Path]:
    build_root = root / package_path / ".build"
    standard_debug = build_root / "debug"
    report_root = (
        standard_debug.resolve() / "codecov"
        if standard_debug.exists()
        else None
    )
    reports = (
        sorted(
            report_root.glob("*.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        if report_root is not None
        else sorted(
            build_root.glob("*/debug/codecov/*.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
    )
    if not reports:
        raise FileNotFoundError(
            f"missing Swift code coverage report for {package_path}; "
            "run swift test --enable-code-coverage first"
        )
    codecov_dir = reports[0].parent
    profdata = codecov_dir / "default.profdata"
    binaries = sorted(
        codecov_dir.parent.glob(
            "*PackageTests.xctest/Contents/MacOS/*PackageTests"
        )
    )
    if not profdata.is_file():
        raise FileNotFoundError(f"missing profdata for {package_path}")
    if len(binaries) != 1:
        raise FileNotFoundError(
            f"expected one covered test binary for {package_path}, "
            f"found {len(binaries)}"
        )
    if additional_profdata:
        if merge_root is None:
            raise ValueError(
                "coverage merge root is required with additional profdata"
            )
        merge_root.mkdir(parents=True, exist_ok=True)
        safe_package_name = re.sub(
            r"[^A-Za-z0-9._-]+",
            "-",
            package_path,
        ).strip("-") or "root"
        merged_profdata = merge_root / f"{safe_package_name}.profdata"
        completed = _run(
            [
                "xcrun",
                "llvm-profdata",
                "merge",
                "-sparse",
                str(profdata),
                *(str(path) for path in additional_profdata),
                "-o",
                str(merged_profdata),
            ],
            cwd=root,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                completed.stderr.strip()
                or f"failed to merge coverage profiles for {package_path}"
            )
        if not merged_profdata.is_file():
            raise FileNotFoundError(
                f"coverage profile merge produced no output for {package_path}"
            )
        profdata = merged_profdata
    return binaries[0], profdata


def _line_counts(
    *,
    root: Path,
    binary: Path,
    profdata: Path,
    source: Path,
) -> dict[int, int | None]:
    completed = _run(
        [
            "xcrun",
            "llvm-cov",
            "show",
            str(binary),
            f"-instr-profile={profdata}",
            str(source),
        ],
        cwd=root,
    )
    counts: dict[int, int | None] = {}
    for raw_line in completed.stdout.splitlines():
        match = _LLVM_COV_LINE_RE.match(raw_line)
        if match is None:
            continue
        line_number = int(match.group(1))
        count_field = match.group(2).strip()
        if not count_field:
            counts[line_number] = None
        elif count_field == "#####":
            counts[line_number] = 0
        else:
            try:
                counts[line_number] = int(count_field.replace(",", ""))
            except ValueError:
                counts[line_number] = None
    return counts


def measure_package(
    *,
    root: Path,
    base_root: Path | None,
    package_path: str,
    diff_from: str | None,
    candidate_paths: Sequence[str],
    additional_profdata: Sequence[Path] = (),
    coverage_merge_root: Path | None = None,
) -> PackageCoverage:
    paths = [
        path
        for path in candidate_paths
        if _is_package_swift_path(path, package_path)
    ]
    if not paths:
        return PackageCoverage(package_path, 0, 0, 0, 0)
    if additional_profdata:
        binary, profdata = _coverage_artifacts(
            root,
            package_path,
            additional_profdata=additional_profdata,
            merge_root=coverage_merge_root,
        )
    else:
        binary, profdata = _coverage_artifacts(root, package_path)
    measurable = 0
    covered = 0
    changed_file_count = 0
    unlinked_files: list[str] = []
    for rel_path in paths:
        changed = _changed_lines_for_path(
            root=root,
            base_root=base_root,
            diff_from=diff_from,
            rel_path=rel_path,
        )
        if not changed:
            continue
        changed_file_count += 1
        counts = _line_counts(
            root=root,
            binary=binary,
            profdata=profdata,
            source=root / rel_path,
        )
        if not counts:
            unlinked_files.append(rel_path)
        file_measurable = [
            line_number
            for line_number in sorted(changed)
            if counts.get(line_number) is not None
        ]
        file_covered = [
            line_number
            for line_number in file_measurable
            if (counts.get(line_number) or 0) > 0
        ]
        file_missed = sorted(set(file_measurable) - set(file_covered))
        measurable += len(file_measurable)
        covered += len(file_covered)
        print(rel_path)
        print(f"measurable_changed_lines={file_measurable}")
        print(f"covered_changed_lines={file_covered}")
        print(f"missed_changed_lines={file_missed}")
        if not counts:
            print("coverage_linkage=missing")
        print(
            "changed_line_coverage="
            f"{coverage_percent(len(file_measurable), len(file_covered)):.2f}%"
        )
        print()
    return PackageCoverage(
        package_path=package_path,
        changed_file_count=changed_file_count,
        measurable=measurable,
        covered=covered,
        missed=measurable - covered,
        unlinked_files=tuple(unlinked_files),
    )


def _automatic_base_root(
    root: Path,
    explicit: str | None,
    env: Mapping[str, str],
) -> Path | None:
    raw = explicit or env.get(_BASE_REPO_ENV, "")
    if not raw and env.get("GITHUB_WORKSPACE"):
        candidate = Path(env["GITHUB_WORKSPACE"]) / "base"
        raw = str(candidate) if candidate.is_dir() else ""
    if not raw:
        return None
    base_root = Path(raw).resolve()
    if base_root == root:
        return None
    if not base_root.is_dir():
        raise ValueError(f"base repository does not exist: {base_root}")
    return base_root


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate changed-line coverage across one or more Swift packages."
        )
    )
    parser.add_argument(
        "--package",
        action="append",
        required=True,
        help="Swift package path relative to the repository root; repeatable.",
    )
    parser.add_argument("--base-repo")
    parser.add_argument("--diff-from")
    parser.add_argument(
        "--exclude-nonmeasurable",
        action="append",
        default=[],
        metavar="PATH=REASON",
        help=(
            "Explicitly report a selected Swift path as N/A when its target "
            "cannot be linked into the package test binary; repeatable."
        ),
    )
    parser.add_argument(
        "--additional-profdata",
        action="append",
        default=[],
        metavar="PACKAGE=GLOB",
        help=(
            "Merge one or more repository-local coverage profiles into the "
            "selected package profile before measuring; repeatable."
        ),
    )
    parser.add_argument("--minimum", type=float, default=95.0)
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    args = parse_args(argv)
    effective_env = os.environ if env is None else env
    if not 0.0 <= args.minimum <= 100.0:
        print("minimum must be between 0 and 100", file=sys.stderr)
        return 2
    try:
        root = _repo_root()
        package_paths = _normalized_package_paths(root, args.package)
        base_root = _automatic_base_root(root, args.base_repo, effective_env)
        if base_root is not None and args.diff_from:
            raise ValueError("--base-repo and --diff-from are mutually exclusive")
        coverage_paths = parse_coverage_paths(
            effective_env.get(_COVERAGE_PATHS_ENV, "")
        )
        exclusions = parse_exclusions(args.exclude_nonmeasurable)
        additional_profdata = resolve_additional_profdata(
            root=root,
            package_paths=package_paths,
            raw_specs=args.additional_profdata,
        )
        candidates = discover_candidate_paths(
            root=root,
            base_root=base_root,
            package_paths=package_paths,
            diff_from=args.diff_from,
            coverage_paths=coverage_paths,
        )
        selected_exclusions = {
            path: reason
            for path, reason in exclusions.items()
            if path in candidates
        }
        measured_candidates = tuple(
            path for path in candidates if path not in selected_exclusions
        )
        with tempfile.TemporaryDirectory(
            prefix="melix-swift-coverage-merge-"
        ) as merge_directory:
            merge_root = Path(merge_directory)
            measurements = [
                measure_package(
                    root=root,
                    base_root=base_root,
                    package_path=package_path,
                    diff_from=args.diff_from,
                    candidate_paths=measured_candidates,
                    additional_profdata=additional_profdata.get(
                        package_path,
                        (),
                    ),
                    coverage_merge_root=merge_root,
                )
                for package_path in package_paths
            ]
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    total_measurable = sum(item.measurable for item in measurements)
    total_covered = sum(item.covered for item in measurements)
    total_missed = total_measurable - total_covered
    unlinked_files = sorted({
        path
        for item in measurements
        for path in item.unlinked_files
    })
    for path, reason in sorted(selected_exclusions.items()):
        print(f"N/A {path}: {reason}")
    for item in measurements:
        print(
            f"PACKAGE {item.package_path} {item.measurable} "
            f"{item.missed} {math.floor(item.percent)}%"
        )
    print(format_total(total_measurable, total_missed))

    measured_source_count = sum(item.changed_file_count for item in measurements)
    if measured_source_count == 0:
        return 0
    if unlinked_files:
        print(
            "changed Swift files were not linked into coverage; add a "
            "process-level coverage profile or an explicit "
            "--exclude-nonmeasurable PATH=REASON: "
            + ", ".join(unlinked_files),
            file=sys.stderr,
        )
        return 1
    if total_measurable == 0:
        print(
            "changed Swift source files were selected but no executable lines "
            "were measurable",
            file=sys.stderr,
        )
        return 1
    package_failures = [
        item.package_path
        for item in measurements
        if item.changed_file_count > 0
        and not meets_minimum(item.measurable, item.covered, args.minimum)
    ]
    if package_failures or not meets_minimum(
        total_measurable,
        total_covered,
        args.minimum,
    ):
        if package_failures:
            print(
                "Swift changed-line coverage below threshold for: "
                + ", ".join(package_failures),
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
