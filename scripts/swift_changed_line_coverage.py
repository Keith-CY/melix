#!/usr/bin/env python3

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
LLVM_COV_LINE_RE = re.compile(r"^\s*(\d+)\|\s*([^|]*)\|")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute changed-line coverage for Swift files using llvm-cov show output."
    )
    parser.add_argument("--binary", required=True, help="Path to the covered test binary")
    parser.add_argument("--profdata", required=True, help="Path to the llvm profdata file")
    parser.add_argument(
        "--diff-from",
        default="HEAD",
        help="Git revision to diff from. Defaults to HEAD.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Swift source files to measure, relative to the repository root or absolute paths.",
    )
    return parser.parse_args()


def run(command: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True)


def repo_root() -> Path:
    return Path(run(["git", "rev-parse", "--show-toplevel"]).strip())


def normalize_file(root: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def changed_lines(root: Path, diff_from: str, files: list[Path]) -> dict[Path, set[int]]:
    command = ["git", "diff", "--unified=0", diff_from, "--", *[str(file) for file in files]]
    diff_text = run(command, cwd=root)
    changed: dict[Path, set[int]] = defaultdict(set)
    current_file: Path | None = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = (root / line.removeprefix("+++ b/")).resolve()
            continue
        match = HUNK_RE.match(line)
        if current_file is None or match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        for line_number in range(start, start + count):
            changed[current_file].add(line_number)

    return changed


def line_counts(binary: Path, profdata: Path, file: Path) -> dict[int, int | None]:
    output = run(
        [
            "xcrun",
            "llvm-cov",
            "show",
            str(binary),
            f"-instr-profile={profdata}",
            str(file),
        ]
    )
    results: dict[int, int | None] = {}

    for raw_line in output.splitlines():
        match = LLVM_COV_LINE_RE.match(raw_line)
        if match is None:
            continue
        line_number = int(match.group(1))
        count_field = match.group(2).strip()
        if not count_field:
            results[line_number] = None
            continue
        if count_field == "#####":
            results[line_number] = 0
            continue
        try:
            results[line_number] = int(count_field.replace(",", ""))
        except ValueError:
            results[line_number] = None

    return results


def main() -> int:
    args = parse_args()
    root = repo_root()
    binary = Path(args.binary).resolve()
    profdata = Path(args.profdata).resolve()
    files = [normalize_file(root, raw) for raw in args.files]
    changed = changed_lines(root, args.diff_from, files)

    total_measurable = 0
    total_covered = 0

    for file in files:
        modified = sorted(changed.get(file, set()))
        counts = line_counts(binary, profdata, file)
        measurable = 0
        covered = 0
        uncovered_lines: list[int] = []
        skipped_lines: list[int] = []

        for line_number in modified:
            count = counts.get(line_number)
            if count is None:
                skipped_lines.append(line_number)
                continue
            measurable += 1
            if count > 0:
                covered += 1
            else:
                uncovered_lines.append(line_number)

        total_measurable += measurable
        total_covered += covered

        percent = (covered / measurable * 100) if measurable else 100.0
        display = file.relative_to(root)
        print(f"{display}\t{percent:.2f}%\t{covered}/{measurable}")
        if uncovered_lines:
            print(f"  uncovered: {','.join(str(line) for line in uncovered_lines)}")
        if skipped_lines:
            print(f"  skipped-non-executable: {','.join(str(line) for line in skipped_lines)}")

    total_percent = (total_covered / total_measurable * 100) if total_measurable else 100.0
    print(f"TOTAL\t{total_percent:.2f}%\t{total_covered}/{total_measurable}")
    return 0 if total_measurable else 1


if __name__ == "__main__":
    raise SystemExit(main())
