#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.benchmark_evaluation_report import (  # noqa: E402
    build_benchmark_evaluation_report,
    build_sticky_comment_body,
    load_report_input,
    render_markdown_report,
    render_terminal_report,
    write_report_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--format",
        choices=("terminal", "markdown", "json"),
        default="terminal",
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--sticky-comment", action="store_true")
    args = parser.parse_args()

    try:
        report = build_benchmark_evaluation_report(
            baseline=load_report_input(args.baseline),
            candidate=load_report_input(args.candidate),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.output_dir:
        write_report_outputs(report=report, output_dir=args.output_dir)

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.format == "markdown":
        markdown = render_markdown_report(report)
        if args.sticky_comment:
            markdown = build_sticky_comment_body(markdown)
        print(markdown, end="" if markdown.endswith("\n") else "\n")
    else:
        print(render_terminal_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
