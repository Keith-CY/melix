#!/usr/bin/env python3

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: swift_coverage_summary.py <codecov-json> <filename-substring>", file=sys.stderr)
        return 2

    report_path = Path(sys.argv[1])
    include_substring = sys.argv[2]
    payload = json.loads(report_path.read_text())

    covered = 0
    count = 0
    for file_report in payload["data"][0]["files"]:
        filename = file_report["filename"]
        if include_substring not in filename:
            continue
        summary = file_report["summary"]["lines"]
        covered += summary["covered"]
        count += summary["count"]
        print(f"{summary['percent']:.2f}\t{filename}")

    percent = (covered / count * 100) if count else 0.0
    print(f"TOTAL\t{percent:.2f}%\t{covered}/{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
