#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.install_assets import build_local_product_layout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--home-dir", default=str(Path.home()))
    parser.add_argument("--launch-agents-dir", default="")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    layout = build_local_product_layout(
        repo_root=args.repo_root,
        home_dir=args.home_dir,
        launch_agents_dir=args.launch_agents_dir or None,
    )
    manifest_path = layout.install_manifest_path
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {
            "plists": {
                "io.melix.swift-text-worker": str(layout.launch_agents_dir / "io.melix.swift-text-worker.plist"),
                "io.melix.python-worker": str(layout.launch_agents_dir / "io.melix.python-worker.plist"),
                "io.melix.control-plane": str(layout.launch_agents_dir / "io.melix.control-plane.plist"),
            },
            "bootout_commands": [
                f'launchctl bootout gui/$(id -u) "{layout.launch_agents_dir / "io.melix.swift-text-worker.plist"}"',
                f'launchctl bootout gui/$(id -u) "{layout.launch_agents_dir / "io.melix.python-worker.plist"}"',
                f'launchctl bootout gui/$(id -u) "{layout.launch_agents_dir / "io.melix.control-plane.plist"}"',
            ],
        }

    for plist_path in manifest["plists"].values():
        Path(plist_path).unlink(missing_ok=True)

    layout.environment_script_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)

    if args.prune:
        shutil.rmtree(layout.runtime_dir, ignore_errors=True)
        shutil.rmtree(layout.logs_dir, ignore_errors=True)

    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    print("Melix local product assets removed.")
    print("Bootout commands:")
    for command in manifest["bootout_commands"]:
        print(f"- {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
