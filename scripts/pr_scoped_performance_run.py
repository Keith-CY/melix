#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.pr_scoped_performance import run_probe_job  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--base-repo", required=True)
    parser.add_argument("--head-repo", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result, success = run_probe_job(
        registry_path=args.registry,
        probe_id=args.probe_id,
        base_repo=args.base_repo,
        head_repo=args.head_repo,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
