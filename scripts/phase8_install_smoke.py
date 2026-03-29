#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.install_assets import build_local_product_layout, write_local_product_artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="melix-phase8-install-") as home_dir:
        layout = build_local_product_layout(
            repo_root=args.repo_root,
            home_dir=home_dir,
            launch_agents_dir=Path(home_dir) / "Library/LaunchAgents",
        )
        manifest = write_local_product_artifacts(layout)

        asset_paths = [Path(path) for path in manifest["plists"].values()]
        checks = {
            "manifest_exists": layout.install_manifest_path.exists(),
            "environment_script_exists": layout.environment_script_path.exists(),
            "all_plists_exist": all(path.exists() for path in asset_paths),
            "bootstrap_command_count": len(manifest["bootstrap_commands"]),
        }

    duration_ms = (time.perf_counter() - started_at) * 1_000
    result = {
        "install_render_ms": round(duration_ms, 2),
        "generated_asset_count": 5,
        "checks": checks,
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
