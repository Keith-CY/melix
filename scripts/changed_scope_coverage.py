#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


_DIFF_HEADER_PREFIX = "diff --git a/"
_DIFF_HEADER_SEPARATOR = " b/"


def _is_diff_file_marker(line: str) -> bool:
    return line.startswith(("+++ b/", "+++ /dev/null", "--- a/", "--- /dev/null"))


def _parse_diff_header_new_path(line: str) -> str | None:
    if not line.startswith(_DIFF_HEADER_PREFIX):
        return None
    separator_index = line.find(_DIFF_HEADER_SEPARATOR, len(_DIFF_HEADER_PREFIX))
    if separator_index < 0:
        return None
    return line[separator_index + len(_DIFF_HEADER_SEPARATOR) :]


def _parse_hunk_new_start(line: str) -> int | None:
    new_range_index = line.find(" +")
    if new_range_index < 0:
        return None
    digit_index = new_range_index + 2
    end_index = digit_index
    line_length = len(line)
    while end_index < line_length and line[end_index].isdigit():
        end_index += 1
    if end_index == digit_index:
        return None
    return int(line[digit_index:end_index])


def _parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    changed_by_path: dict[str, set[int]] = {}
    current_changed_lines: set[int] | None = None
    new_line: int | None = None
    for line in diff_text.splitlines():
        first_char = line[:1]
        if first_char == "d" and line.startswith(_DIFF_HEADER_PREFIX):
            current_path = _parse_diff_header_new_path(line)
            current_changed_lines = (
                None if current_path is None else changed_by_path.setdefault(current_path, set())
            )
            new_line = None
            continue
        if first_char == "@" and line.startswith("@@"):
            new_line = _parse_hunk_new_start(line)
            continue
        if current_changed_lines is None or new_line is None:
            continue
        if first_char == "\\" and line.startswith("\\ "):
            continue
        if first_char == "+":
            current_changed_lines.add(new_line)
            new_line += 1
        elif first_char == "-":
            continue
        else:
            new_line += 1
    return changed_by_path


def _changed_lines_by_path(repo_root: Path, rel_paths: list[str]) -> dict[str, set[int]]:
    proc = subprocess.run(
        ["git", "diff", "--unified=0", "--", *rel_paths],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    changed_by_path = _parse_changed_lines(proc.stdout)
    return {rel_path: changed_by_path.get(rel_path, set()) for rel_path in rel_paths}


def _measurable_changed_lines(
    repo_root: Path,
    coverage_payload: dict[str, object],
    rel_path: str,
    changed: set[int],
) -> tuple[list[int], list[int], list[int]]:
    if not changed:
        return [], [], []

    entry = coverage_payload["files"][rel_path]
    executed = set(entry["executed_lines"])
    missing = set(entry["missing_lines"])
    measured = executed | missing
    measured_changed = changed & measured
    if not measured_changed:
        return [], [], []

    source_lines = (repo_root / rel_path).read_text(encoding="utf-8").splitlines()
    measurable: list[int] = []
    for line_no in sorted(measured_changed):
        stripped = source_lines[line_no - 1].strip()
        if stripped and not stripped.startswith("#"):
            measurable.append(line_no)
    covered = [line_no for line_no in measurable if line_no in executed]
    missed = [line_no for line_no in measurable if line_no in missing]
    return measurable, covered, missed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    repo_root = Path.cwd()
    coverage_payload = json.loads(Path(args.coverage_json).read_text(encoding="utf-8"))
    changed_lines_by_path = _changed_lines_by_path(repo_root, args.paths)

    total_measurable = 0
    total_covered = 0
    total_missed = 0
    for rel_path in args.paths:
        measurable, covered, missed = _measurable_changed_lines(
            repo_root,
            coverage_payload,
            rel_path,
            changed_lines_by_path.get(rel_path, set()),
        )
        total_measurable += len(measurable)
        total_covered += len(covered)
        total_missed += len(missed)
        print(rel_path)
        print(f"measurable_changed_lines={measurable}")
        print(f"covered_changed_lines={covered}")
        print(f"missed_changed_lines={missed}")
        file_pct = 100.0 if not measurable else len(covered) / len(measurable) * 100.0
        print(f"changed_line_coverage={file_pct:.2f}%")
        print()

    overall_pct = 100.0 if total_measurable == 0 else total_covered / total_measurable * 100.0
    print(f"aggregate_measurable_changed_lines={total_measurable}")
    print(f"aggregate_covered_changed_lines={total_covered}")
    print(f"aggregate_missed_changed_lines={total_missed}")
    print(f"TOTAL {total_measurable} {total_missed} {overall_pct:.0f}%")
    return 0 if overall_pct >= 95.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
