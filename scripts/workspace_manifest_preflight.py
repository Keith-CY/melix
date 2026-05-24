#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from worker.productization.workspace_manifest import preflight_workspace


DEFAULT_FIXTURE = (
    ROOT
    / "services/mlx-worker-python/fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json"
)


def build_receipt(
    manifest_path: Path,
    *,
    output_path: Path | None = None,
) -> dict[str, object]:
    return preflight_workspace(manifest_path, receipt_output_path=output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight a Melix workspace manifest.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    receipt = build_receipt(args.manifest, output_path=args.output)
    encoded = json.dumps(receipt, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if receipt.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
