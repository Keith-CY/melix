#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import subprocess
import sys


_DIFF_HEADER_PREFIX = "diff --git a/"
_DIFF_HEADER_SEPARATOR = " b/"
_ASCII_ZERO = ord("0")
_ASCII_NINE = ord("9")
_ASCII_COMMA = ord(",")
_ASCII_SPACE = ord(" ")


def _is_diff_file_marker(line: str) -> bool:
    return line.startswith(("+++ b/", "+++ /dev/null", "--- a/", "--- /dev/null"))


def _parse_diff_header_new_path(line: str) -> str | None:
    if not line.startswith(_DIFF_HEADER_PREFIX):
        return None
    separator_index = line.find(_DIFF_HEADER_SEPARATOR, len(_DIFF_HEADER_PREFIX))
    if separator_index < 0:
        return None
    return line[separator_index + len(_DIFF_HEADER_SEPARATOR) :]


def _parse_hunk_new_start_from_digit(line: str, digit_index: int) -> int | None:
    value = 0
    index = digit_index
    line_length = len(line)
    ord_char = ord
    while index < line_length:
        character_code = ord_char(line[index])
        if _ASCII_ZERO <= character_code <= _ASCII_NINE:
            value = value * 10 + (character_code - _ASCII_ZERO)
            index += 1
            continue
        if character_code == _ASCII_COMMA or character_code == _ASCII_SPACE:
            return value if index > digit_index else None
        return None
    return None


def _parse_hunk_new_start(line: str) -> int | None:
    new_range_index = line.find(" +")
    if new_range_index < 0:
        return None
    return _parse_hunk_new_start_from_digit(line, new_range_index + 2)


def _parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    changed_by_path: dict[str, set[int]] = {}
    changed_by_path_setdefault = changed_by_path.setdefault
    header_prefix = _DIFF_HEADER_PREFIX
    header_separator = _DIFF_HEADER_SEPARATOR
    header_prefix_len = len(header_prefix)
    header_separator_len = len(header_separator)
    parse_hunk_new_start_from_digit = _parse_hunk_new_start_from_digit
    add_changed_line = None
    new_line: int | None = None
    for line in diff_text.splitlines():
        if not line:
            if add_changed_line is not None and new_line is not None:
                new_line += 1
            continue
        first_char = line[0]
        if first_char == "d" and line.startswith(header_prefix):
            separator_index = line.find(header_separator, header_prefix_len)
            add_changed_line = None
            if separator_index >= 0:
                current_path = line[separator_index + header_separator_len :]
                add_changed_line = changed_by_path_setdefault(current_path, set()).add
            new_line = None
            continue
        if first_char == "@" and len(line) > 1 and line[1] == "@":
            new_range_index = line.find(" +")
            if new_range_index < 0:
                new_line = None
                continue
            new_line = parse_hunk_new_start_from_digit(line, new_range_index + 2)
            continue
        if add_changed_line is None or new_line is None:
            continue
        if first_char == "\\":
            continue
        if first_char == "+":
            add_changed_line(new_line)
            new_line += 1
        elif first_char == "-":
            continue
        else:
            new_line += 1
    return changed_by_path


def _changed_lines_by_path(repo_root: Path, rel_paths: list[str]) -> dict[str, set[int]]:
    if not rel_paths:
        return {}
    proc = subprocess.run(
        ["git", "diff", "--unified=0", "--", *rel_paths],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    changed_by_path = _parse_changed_lines(proc.stdout)
    return {rel_path: changed_by_path.get(rel_path, set()) for rel_path in rel_paths}


def _coverage_path_allowlist(env: Mapping[str, str]) -> frozenset[str] | None:
    raw_value = env.get("MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON", "").strip()
    if not raw_value:
        return None
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON: {exc}") from exc
    if isinstance(payload, str):
        return frozenset([payload] if payload else [])
    if not isinstance(payload, list):
        raise SystemExit("MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON must be a JSON list")
    return frozenset(str(path) for path in payload if str(path))


def _filter_coverage_paths(paths: list[str], allowlist: frozenset[str] | None) -> list[str]:
    if allowlist is None:
        return paths
    return [path for path in paths if path in allowlist]


def _line_ranges_may_overlap(
    changed: set[int],
    executed_lines: list[int],
    missing_lines: list[int],
) -> bool:
    if not changed:
        return False
    min_changed = min(changed)
    max_changed = max(changed)
    if executed_lines:
        first_line = executed_lines[0]
        last_line = executed_lines[-1]
        if first_line > last_line:
            first_line = min(executed_lines)
            last_line = max(executed_lines)
        if first_line <= max_changed and last_line >= min_changed:
            return True
    if missing_lines:
        first_line = missing_lines[0]
        last_line = missing_lines[-1]
        if first_line > last_line:
            first_line = min(missing_lines)
            last_line = max(missing_lines)
        if first_line <= max_changed and last_line >= min_changed:
            return True
    return False


def _measurable_changed_lines(
    repo_root: Path,
    coverage_payload: dict[str, object],
    rel_path: str,
    changed: set[int],
) -> tuple[list[int], list[int], list[int]]:
    if not changed:
        return [], [], []

    entry = coverage_payload["files"][rel_path]
    executed_lines = entry["executed_lines"]
    missing_lines = entry["missing_lines"]
    if len(executed_lines) == 1 and len(missing_lines) == 1:
        executed_line = executed_lines[0]
        missing_line = missing_lines[0]
        if executed_line not in changed and missing_line not in changed:
            return [], [], []
        measured_changed = [
            line_no
            for line_no in changed
            if line_no == executed_line or line_no == missing_line
        ]
        executed_lookup = (executed_line,)
        missing_lookup = (missing_line,)
    else:
        if not _line_ranges_may_overlap(changed, executed_lines, missing_lines):
            return [], [], []
        executed = set(executed_lines)
        missing = set(missing_lines)
        measured_changed = [
            line_no for line_no in changed if line_no in executed or line_no in missing
        ]
        executed_lookup = executed
        missing_lookup = missing
    if not measured_changed:
        return [], [], []

    source_lines = (repo_root / rel_path).read_text(encoding="utf-8").splitlines()
    measurable: list[int] = []
    for line_no in sorted(measured_changed):
        stripped = source_lines[line_no - 1].strip()
        if stripped and not stripped.startswith("#"):
            measurable.append(line_no)
    covered = [line_no for line_no in measurable if line_no in executed_lookup]
    missed = [line_no for line_no in measurable if line_no in missing_lookup]
    return measurable, covered, missed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    repo_root = Path.cwd()
    coverage_payload = json.loads(Path(args.coverage_json).read_text(encoding="utf-8"))
    paths = _filter_coverage_paths(args.paths, _coverage_path_allowlist(os.environ))
    changed_lines_by_path = _changed_lines_by_path(repo_root, paths)

    total_measurable = 0
    total_covered = 0
    total_missed = 0
    for rel_path in paths:
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
