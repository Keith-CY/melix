#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.closure_audit import build_closure_audit, render_closure_audit_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument(
        "--output",
        default=str(ROOT / ".runtime" / "m9-closure-audit" / "closure-audit.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_path = Path(args.output).resolve()
    report = build_closure_audit(repo_root)
    payload = render_closure_audit_json(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")

    if args.json:
        print(payload, end="")
    else:
        print(f"Wrote closure audit to {output_path}")

    blocker_count = report.metrics["closure_audit.blocker_count"]
    return 1 if blocker_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
