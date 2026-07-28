#!/usr/bin/env python3

from __future__ import annotations

import argparse
from bisect import bisect_left
from collections.abc import Mapping, Set
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import sys


_DIFF_HEADER_PREFIX = "diff --git a/"
_DIFF_HEADER_SEPARATOR = " b/"
_DIFF_HEADER_PREFIX_BYTES = b"diff --git a/"
_DIFF_HEADER_SEPARATOR_BYTES = b" b/"
_ASCII_ZERO = ord("0")
_ASCII_NINE = ord("9")
_ASCII_COMMA = ord(",")
_ASCII_SPACE = ord(" ")
_ASCII_BACKSLASH = ord("\\")
_ASCII_PLUS = ord("+")
_ASCII_MINUS = ord("-")
_ASCII_AT = ord("@")
_ASCII_LOWER_D = ord("d")
_ASCII_COMMENT = ord("#")
_DIFF_PARSER_ACCEPTS_BYTES = True
_EMPTY_CHANGED_LINES: frozenset[int] = frozenset()
_DENSE_CHANGED_LINE_SCAN_THRESHOLD = 32
_SPARSE_SOURCE_LINE_SCAN_THRESHOLD = 8
_ALLOWLIST_CACHE_MISS = object()
_ALLOWLIST_LAST_RAW = ""
_ALLOWLIST_LAST_RESULT: frozenset[str] | None | object = _ALLOWLIST_CACHE_MISS


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


def _parse_hunk_new_start_from_digit_bytes(line: bytes, digit_index: int) -> int | None:
    value = 0
    index = digit_index
    line_length = len(line)
    while index < line_length:
        character_code = line[index]
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


def _parse_changed_lines(diff_text: str | bytes) -> dict[str, set[int]]:
    changed_by_path: dict[str, set[int]] = {}
    changed_by_path_setdefault = changed_by_path.setdefault
    header_prefix = _DIFF_HEADER_PREFIX_BYTES
    header_separator = _DIFF_HEADER_SEPARATOR_BYTES
    header_prefix_len = len(header_prefix)
    header_separator_len = len(header_separator)
    hunk_new_range_marker = b" +"
    parse_hunk_new_start_from_digit = _parse_hunk_new_start_from_digit_bytes
    bytes_find = bytes.find
    bytes_startswith = bytes.startswith
    ascii_backslash = _ASCII_BACKSLASH
    ascii_plus = _ASCII_PLUS
    ascii_minus = _ASCII_MINUS
    ascii_at = _ASCII_AT
    ascii_lower_d = _ASCII_LOWER_D
    add_changed_line = None
    new_line: int | None = None
    diff_bytes = diff_text if isinstance(diff_text, bytes) else diff_text.encode()
    for line in diff_bytes.split(b"\n"):
        if not line:
            if add_changed_line is not None and new_line is not None:
                new_line += 1
            continue
        first_char = line[0]
        if first_char == ascii_lower_d and bytes_startswith(line, header_prefix):
            separator_index = bytes_find(line, header_separator, header_prefix_len)
            add_changed_line = None
            if separator_index >= 0:
                current_path = line[separator_index + header_separator_len :].decode()
                add_changed_line = changed_by_path_setdefault(current_path, set()).add
            new_line = None
            continue
        if first_char == ascii_at and len(line) > 1 and line[1] == ascii_at:
            new_range_index = bytes_find(line, hunk_new_range_marker)
            if new_range_index < 0:
                new_line = None
                continue
            new_line = parse_hunk_new_start_from_digit(line, new_range_index + 2)
            continue
        if add_changed_line is None or new_line is None:
            continue
        if first_char == ascii_backslash:
            continue
        if first_char == ascii_plus:
            add_changed_line(new_line)
            new_line += 1
        elif first_char == ascii_minus:
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
        capture_output=True,
        check=True,
    )
    changed_by_path = _parse_changed_lines(proc.stdout)
    return {rel_path: changed_by_path.get(rel_path, set()) for rel_path in rel_paths}


@lru_cache(maxsize=16)
def _coverage_path_allowlist_from_raw(raw_value: str) -> frozenset[str] | None:
    if not raw_value:
        return None
    if raw_value == "[]":
        return frozenset()
    if (
        len(raw_value) >= 2
        and raw_value[0] == '"'
        and raw_value[-1] == '"'
        and "\\" not in raw_value
        and '"' not in raw_value[1:-1]
    ):
        return frozenset([raw_value[1:-1]] if raw_value[1:-1] else [])
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON: {exc}") from exc
    if isinstance(payload, str):
        return frozenset([payload] if payload else [])
    if not isinstance(payload, list):
        raise SystemExit("MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON must be a JSON list")
    return frozenset(str(path) for path in payload if str(path))


def _coverage_path_allowlist(env: Mapping[str, str]) -> frozenset[str] | None:
    global _ALLOWLIST_LAST_RAW, _ALLOWLIST_LAST_RESULT

    raw_value = env.get("MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON", "")
    if raw_value == _ALLOWLIST_LAST_RAW and _ALLOWLIST_LAST_RESULT is not _ALLOWLIST_CACHE_MISS:
        return _ALLOWLIST_LAST_RESULT  # type: ignore[return-value]
    raw_value = raw_value.strip()
    if raw_value == _ALLOWLIST_LAST_RAW and _ALLOWLIST_LAST_RESULT is not _ALLOWLIST_CACHE_MISS:
        return _ALLOWLIST_LAST_RESULT  # type: ignore[return-value]
    allowlist = _coverage_path_allowlist_from_raw(raw_value)
    _ALLOWLIST_LAST_RAW = raw_value
    _ALLOWLIST_LAST_RESULT = allowlist
    return allowlist


def _filter_coverage_paths(paths: list[str], allowlist: frozenset[str] | None) -> list[str]:
    if allowlist is None:
        return paths
    if not allowlist:
        return []
    return [path for path in paths if path in allowlist]


def _line_ranges_may_overlap(
    changed: Set[int],
    executed_lines: list[int],
    missing_lines: list[int],
) -> bool:
    if not changed:
        return False
    if len(changed) == 1:
        changed_line = next(iter(changed))
        if executed_lines and missing_lines:
            executed_first = executed_lines[0]
            executed_last = executed_lines[-1]
            missing_first = missing_lines[0]
            missing_last = missing_lines[-1]
            if executed_first <= executed_last and missing_first <= missing_last:
                first_line = executed_first if executed_first < missing_first else missing_first
                last_line = executed_last if executed_last > missing_last else missing_last
                return first_line <= changed_line <= last_line
        if executed_lines:
            first_line = executed_lines[0]
            last_line = executed_lines[-1]
            if first_line <= last_line:
                if first_line <= changed_line <= last_line:
                    return True
            elif min(executed_lines) <= changed_line <= max(executed_lines):
                return True
        if missing_lines:
            first_line = missing_lines[0]
            last_line = missing_lines[-1]
            if first_line <= last_line:
                if first_line <= changed_line <= last_line:
                    return True
            elif min(missing_lines) <= changed_line <= max(missing_lines):
                return True
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


def _sorted_line_list_contains(lines: list[int], line_no: int) -> bool:
    index = bisect_left(lines, line_no)
    return index < len(lines) and lines[index] == line_no


def _ascii_bytes_measurable_non_comment_lines(
    source_path: Path,
    line_numbers: list[int],
) -> list[int] | None:
    source_bytes = source_path.read_bytes()
    if not source_bytes.isascii():
        return None

    source_lines = source_bytes.splitlines()
    source_line_count = len(source_lines)
    measurable: list[int] = []
    append_measurable = measurable.append
    ascii_comment = _ASCII_COMMENT
    ascii_space = _ASCII_SPACE
    for line_no in line_numbers:
        if 1 <= line_no <= source_line_count:
            line = source_lines[line_no - 1]
            if not line:
                continue
            first_byte = line[0]
            if first_byte != ascii_comment and first_byte > ascii_space:
                append_measurable(line_no)
                continue
            stripped = line.strip()
            if stripped and not stripped.startswith(b"#"):
                append_measurable(line_no)
    return measurable


def _measurable_non_comment_lines(
    source_path: Path,
    line_numbers: list[int],
) -> list[int]:
    measurable: list[int] = []
    append_measurable = measurable.append
    if len(line_numbers) <= _SPARSE_SOURCE_LINE_SCAN_THRESHOLD:
        remaining = set(line_numbers)
        with source_path.open("r", encoding="utf-8") as source_file:
            for index, line in enumerate(source_file, 1):
                if index in remaining:
                    first_char = line[0] if line else ""
                    if first_char and first_char != "#" and not first_char.isspace():
                        append_measurable(index)
                    else:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            append_measurable(index)
                    remaining.remove(index)
                    if not remaining:
                        break
        return measurable

    ascii_measurable = _ascii_bytes_measurable_non_comment_lines(source_path, line_numbers)
    if ascii_measurable is not None:
        return ascii_measurable

    source_lines = source_path.read_text(encoding="utf-8").splitlines()
    source_line_count = len(source_lines)
    for line_no in line_numbers:
        if 1 <= line_no <= source_line_count:
            line = source_lines[line_no - 1]
            first_char = line[0] if line else ""
            if first_char and first_char != "#" and not first_char.isspace():
                append_measurable(line_no)
            else:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    append_measurable(line_no)
    return measurable


def _measurable_changed_lines(
    repo_root: Path,
    coverage_payload: dict[str, object],
    rel_path: str,
    changed: Set[int],
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
        executed_lookup = executed_lines
        missing_lookup = missing_lines
        changed_count = len(changed)
        measured_changed = None
        dense_sorted_measured = False
        if changed_count == 1:
            changed_line = 0
            for changed_line in changed:
                break
            singleton_may_overlap = False
            singleton_combined_sorted = False
            if (
                executed_lines
                and missing_lines
                and executed_lines[0] <= executed_lines[-1]
                and missing_lines[0] <= missing_lines[-1]
            ):
                singleton_combined_sorted = True
                first_line = executed_lines[0] if executed_lines[0] < missing_lines[0] else missing_lines[0]
                last_line = executed_lines[-1] if executed_lines[-1] > missing_lines[-1] else missing_lines[-1]
                singleton_may_overlap = first_line <= changed_line <= last_line
            else:
                if executed_lines:
                    first_line = executed_lines[0]
                    last_line = executed_lines[-1]
                    if first_line > last_line:
                        first_line = min(executed_lines)
                        last_line = max(executed_lines)
                    singleton_may_overlap = first_line <= changed_line <= last_line
                if not singleton_may_overlap and missing_lines:
                    first_line = missing_lines[0]
                    last_line = missing_lines[-1]
                    if first_line > last_line:
                        first_line = min(missing_lines)
                        last_line = max(missing_lines)
                    singleton_may_overlap = first_line <= changed_line <= last_line
            if not singleton_may_overlap:
                return [], [], []
            if singleton_combined_sorted or (
                executed_lines and executed_lines[0] <= executed_lines[-1]
            ):
                covered_singleton = _sorted_line_list_contains(executed_lines, changed_line)
            else:
                covered_singleton = changed_line in executed_lines
            if singleton_combined_sorted or (
                missing_lines and missing_lines[0] <= missing_lines[-1]
            ):
                missed_singleton = _sorted_line_list_contains(missing_lines, changed_line)
            else:
                missed_singleton = changed_line in missing_lines
            if not covered_singleton and not missed_singleton:
                return [], [], []
            measured_changed = [changed_line]
            executed_lookup = (changed_line,) if covered_singleton else ()
            missing_lookup = (changed_line,) if missed_singleton else ()
        else:
            dense_sorted_measured = (
                changed_count >= _DENSE_CHANGED_LINE_SCAN_THRESHOLD
                and executed_lines
                and missing_lines
                and executed_lines[0] <= executed_lines[-1]
                and missing_lines[0] <= missing_lines[-1]
            )
        measured_line_count = len(executed_lines) + len(missing_lines) if dense_sorted_measured else 0
        if (
            dense_sorted_measured
            and measured_line_count
            and changed_count * 4 >= measured_line_count
            and isinstance(changed, (set, frozenset))
        ):
            executed_lookup = changed.intersection(executed_lines)
            missing_lookup = changed.intersection(missing_lines)
            measured_changed = list(executed_lookup)
            measured_changed.extend(missing_lookup)
        elif changed_count != 1:
            if not _line_ranges_may_overlap(changed, executed_lines, missing_lines):
                return [], [], []
            measured_changed = None
        if executed_lines and executed_lines[0] > executed_lines[-1]:
            executed_lookup = set(executed_lines)
        else:
            if measured_changed is None:
                executed_lookup = executed_lines
        if missing_lines and missing_lines[0] > missing_lines[-1]:
            missing_lookup = set(missing_lines)
        else:
            if measured_changed is None:
                missing_lookup = missing_lines
        if measured_changed is not None:
            pass
        elif isinstance(executed_lookup, list) and isinstance(missing_lookup, list):
            measured_line_count = len(executed_lookup) + len(missing_lookup)
            sorted_line_list_contains = _sorted_line_list_contains
            if (
                measured_line_count
                and changed_count >= _DENSE_CHANGED_LINE_SCAN_THRESHOLD
                and changed_count * 4 >= measured_line_count
            ):
                if isinstance(changed, (set, frozenset)):
                    executed_lookup = changed.intersection(executed_lines)
                    missing_lookup = changed.intersection(missing_lines)
                else:
                    executed_lookup = {line_no for line_no in executed_lines if line_no in changed}
                    missing_lookup = {line_no for line_no in missing_lines if line_no in changed}
                measured_changed = list(executed_lookup)
                measured_changed.extend(missing_lookup)
            else:
                measured_changed = [
                    line_no
                    for line_no in changed
                    if sorted_line_list_contains(executed_lookup, line_no)
                    or sorted_line_list_contains(missing_lookup, line_no)
                ]
        else:
            measured_changed = [
                line_no
                for line_no in changed
                if line_no in executed_lookup or line_no in missing_lookup
            ]
    if not measured_changed:
        return [], [], []

    sorted_measured_changed = sorted(measured_changed)
    measurable = _measurable_non_comment_lines(
        repo_root / rel_path, sorted_measured_changed
    )
    if isinstance(executed_lookup, list) and isinstance(missing_lookup, list):
        covered = [
            line_no
            for line_no in measurable
            if _sorted_line_list_contains(executed_lookup, line_no)
        ]
        missed = [
            line_no
            for line_no in measurable
            if _sorted_line_list_contains(missing_lookup, line_no)
        ]
    else:
        covered = []
        missed = []
        covered_append = covered.append
        missed_append = missed.append
        for line_no in measurable:
            if line_no in executed_lookup:
                covered_append(line_no)
            elif line_no in missing_lookup:
                missed_append(line_no)
    return measurable, covered, missed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    repo_root = Path.cwd()
    paths = _filter_coverage_paths(args.paths, _coverage_path_allowlist(os.environ))
    if not paths:
        sys.stdout.write(
            "aggregate_measurable_changed_lines=0\n"
            "aggregate_covered_changed_lines=0\n"
            "aggregate_missed_changed_lines=0\n"
            "TOTAL 0 0 100%\n"
        )
        return 0

    coverage_payload = json.loads(Path(args.coverage_json).read_text(encoding="utf-8"))
    changed_lines_by_path = _changed_lines_by_path(repo_root, paths)

    total_measurable = 0
    total_covered = 0
    total_missed = 0
    for rel_path in paths:
        measurable, covered, missed = _measurable_changed_lines(
            repo_root,
            coverage_payload,
            rel_path,
            changed_lines_by_path.get(rel_path, _EMPTY_CHANGED_LINES),
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
