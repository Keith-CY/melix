#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.build_metadata import (
    compute_build_metadata,
    infer_git_ref_name,
    infer_git_sha,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--ref-type", default="branch")
    parser.add_argument("--ref-name", default="")
    parser.add_argument("--sha", default="")
    parser.add_argument("--base-version", default="0.1.0")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    ref_name = args.ref_name or infer_git_ref_name(repo_root)
    sha = args.sha or infer_git_sha(repo_root)
    metadata = compute_build_metadata(
        ref_type=args.ref_type,
        ref_name=ref_name,
        sha=sha,
        base_version=args.base_version,
    )
    payload = {
        "version": metadata.version,
        "artifact_name": metadata.artifact_name,
        "ref_name": ref_name,
        "sha": sha,
    }

    if args.github_output:
        output_path = Path(args.github_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(f"version={metadata.version}\n")
            handle.write(f"artifact_name={metadata.artifact_name}\n")

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
