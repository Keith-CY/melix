#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.install_assets import build_local_product_layout, write_local_product_artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--home-dir", default=str(Path.home()))
    parser.add_argument("--launch-agents-dir", default="")
    parser.add_argument("--http-port", type=int, default=12436)
    parser.add_argument("--service-instance-name", default="")
    parser.add_argument("--prefer-available-http-port", action="store_true")
    parser.add_argument("--product-version", default="")
    parser.add_argument("--update-channel-path", default="")
    parser.add_argument("--swift-backend-mode", default="swift")
    parser.add_argument("--python-backend-mode", default="auto")
    parser.add_argument("--dev-text-model-path", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    layout = build_local_product_layout(
        repo_root=args.repo_root,
        home_dir=args.home_dir,
        launch_agents_dir=args.launch_agents_dir or None,
        http_port=args.http_port,
        service_instance_name=args.service_instance_name,
        prefer_available_http_port=args.prefer_available_http_port,
        product_version=args.product_version,
        update_channel_path=args.update_channel_path or None,
    )
    manifest = write_local_product_artifacts(
        layout,
        swift_backend_mode=args.swift_backend_mode,
        python_backend_mode=args.python_backend_mode,
        dev_text_model_path=args.dev_text_model_path,
    )

    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    print("Melix local product assets installed.")
    print(f"LaunchAgents: {layout.launch_agents_dir}")
    print(f"Manifest: {layout.install_manifest_path}")
    print(f"Environment: {layout.environment_script_path}")
    print("Bootstrap commands:")
    for command in manifest["bootstrap_commands"]:
        print(f"- {command}")
    print("Ready probe:")
    print(f"- {manifest['ready_probe_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
