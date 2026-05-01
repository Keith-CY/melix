#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def _changed_lines(repo_root: Path, rel_path: str) -> set[int]:
    proc = subprocess.run(
        ["git", "diff", "--unified=0", "--", rel_path],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    changed: set[int] = set()
    new_line: int | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match is None:
                continue
            new_line = int(match.group(1))
            continue
        if new_line is None or line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            changed.add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        else:
            new_line += 1
    return changed


def _measurable_changed_lines(repo_root: Path, coverage_payload: dict[str, object], rel_path: str) -> tuple[list[int], list[int], list[int]]:
    entry = coverage_payload["files"][rel_path]
    executed = set(entry["executed_lines"])
    missing = set(entry["missing_lines"])
    measured = executed | missing
    source_lines = (repo_root / rel_path).read_text(encoding="utf-8").splitlines()
    changed = _changed_lines(repo_root, rel_path)
    measurable = [
        line_no
        for line_no in sorted(changed)
        if line_no in measured
        and source_lines[line_no - 1].strip()
        and not source_lines[line_no - 1].strip().startswith("#")
    ]
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

    total_measurable = 0
    total_covered = 0
    total_missed = 0
    for rel_path in args.paths:
        measurable, covered, missed = _measurable_changed_lines(repo_root, coverage_payload, rel_path)
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
