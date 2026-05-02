#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.pr_scoped_performance import (  # noqa: E402
    build_performance_report,
    build_sticky_comment_body,
    render_markdown_report,
    render_terminal_report,
    write_report_outputs,
)


def _load_results(results_dir: Path) -> list[dict[str, object]]:
    if not results_dir.exists():
        return []
    results: list[dict[str, object]] = []
    result_paths = sorted(
        entry.path
        for entry in os.scandir(results_dir)
        if entry.name.endswith(".json")
    )
    for path in result_paths:
        with open(path, "rb") as result_file:
            payload = json.loads(result_file.read())
        if isinstance(payload, dict):
            results.append(payload)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--format", choices=("terminal", "markdown", "json"), default="terminal")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--sticky-comment", action="store_true")
    args = parser.parse_args()

    scope = json.loads(Path(args.scope).read_text(encoding="utf-8"))
    if not isinstance(scope, dict):
        raise ValueError("scope payload must be a JSON object")
    report = build_performance_report(scope=scope, probe_results=_load_results(Path(args.results_dir)))
    markdown_report = ""
    if args.output_dir or args.format == "markdown" or args.sticky_comment:
        markdown_report = render_markdown_report(report)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        write_report_outputs(
            report,
            output_dir,
            markdown_report=markdown_report,
            sticky_comment=args.sticky_comment,
        )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.format == "markdown":
        markdown = build_sticky_comment_body(markdown_report) if args.sticky_comment else markdown_report
        print(markdown, end="" if markdown.endswith("\n") else "\n")
        return 0
    print(render_terminal_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
