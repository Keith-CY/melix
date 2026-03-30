#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute changed-line coverage for Python files using coverage.py JSON output."
    )
    parser.add_argument(
        "--coverage-json",
        required=True,
        help="Path to the coverage.py JSON report.",
    )
    parser.add_argument(
        "--diff-from",
        default="HEAD",
        help="Git revision to diff from. Defaults to HEAD.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Python source files to measure, relative to the repository root or absolute paths.",
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


def load_coverage(root: Path, coverage_json: Path) -> dict[Path, tuple[set[int], set[int]]]:
    payload = json.loads(coverage_json.read_text())
    results: dict[Path, tuple[set[int], set[int]]] = {}

    for raw_path, metadata in payload.get("files", {}).items():
        file_path = Path(raw_path)
        if not file_path.is_absolute():
            file_path = (root / file_path).resolve()
        executed = {int(line) for line in metadata.get("executed_lines", [])}
        missing = {int(line) for line in metadata.get("missing_lines", [])}
        results[file_path] = (executed, missing)

    return results


def main() -> int:
    args = parse_args()
    root = repo_root()
    coverage_json = Path(args.coverage_json).resolve()
    files = [normalize_file(root, raw) for raw in args.files]
    changed = changed_lines(root, args.diff_from, files)
    coverage = load_coverage(root, coverage_json)

    total_measurable = 0
    total_covered = 0

    for file in files:
        modified = sorted(changed.get(file, set()))
        executed, missing = coverage.get(file, (set(), set()))
        measurable = 0
        covered = 0
        uncovered_lines: list[int] = []
        skipped_lines: list[int] = []

        for line_number in modified:
            if line_number in executed:
                measurable += 1
                covered += 1
                continue
            if line_number in missing:
                measurable += 1
                uncovered_lines.append(line_number)
                continue
            skipped_lines.append(line_number)

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
