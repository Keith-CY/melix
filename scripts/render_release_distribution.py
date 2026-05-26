#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.release_distribution import (  # noqa: E402
    DEFAULT_RELEASE_REPOSITORY,
    write_distribution_files,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag-name", required=True)
    parser.add_argument("--repository", default=DEFAULT_RELEASE_REPOSITORY)
    parser.add_argument("--archive-path", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = write_distribution_files(
        tag_name=args.tag_name,
        repository=args.repository,
        archive_path=args.archive_path,
        output_root=args.output_root,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
