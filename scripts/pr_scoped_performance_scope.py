#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.pr_scoped_performance import build_scope_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--changed-files-json", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    changed_files = json.loads(Path(args.changed_files_json).read_text(encoding="utf-8"))
    if not isinstance(changed_files, list):
        raise ValueError("changed files payload must be a JSON list")
    scope = build_scope_report(registry_path=args.registry, changed_files=[str(path) for path in changed_files])
    rendered = json.dumps(scope, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
