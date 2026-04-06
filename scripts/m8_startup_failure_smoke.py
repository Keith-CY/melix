#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import socket
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.install_assets import build_local_product_layout, write_local_product_artifacts
from worker.productization.startup_signals import check_for_updates, classify_startup_failure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="melix-m8-startup-") as home_dir:
        home_path = Path(home_dir)
        occupied_port = _reserve_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", occupied_port))
            listener.listen(1)

            update_channel_path = home_path / "stable.json"
            update_channel_path.write_text(
                json.dumps(
                    {
                        "schema_version": "melix.update_channel.v1",
                        "channel": "stable",
                        "latest_version": "0.2.0",
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            layout = build_local_product_layout(
                repo_root=args.repo_root,
                home_dir=home_path,
                launch_agents_dir=home_path / "Library/LaunchAgents",
                http_port=occupied_port,
                prefer_available_http_port=True,
                update_channel_path=update_channel_path,
            )
            manifest = write_local_product_artifacts(layout)
            Path(manifest["control_plane_stderr_path"]).write_text(
                "bind() failed: Address already in use\n",
                encoding="utf-8",
            )

        update_result = check_for_updates(manifest["product_version"], manifest["update_channel_path"])
        startup_failure = classify_startup_failure(manifest, error_text="handshake failed")

        checks = {
            "update_available": update_result.update_available,
            "startup_failure_classified": startup_failure.classification == "host_port_conflict",
            "http_port_auto_selected": bool(manifest["http_port_auto_selected"]),
            "ready_probe_uses_selected_port": manifest["ready_probe_url"].endswith(f":{layout.http_port}/v1/models"),
        }
        payload = {
            "checks": checks,
            "installed_version": manifest["product_version"],
            "latest_version": update_result.latest_version,
            "requested_http_port": occupied_port,
            "selected_http_port": layout.http_port,
            "startup_failure": startup_failure.to_dict(),
            "startup_failure_smoke_ms": round((time.perf_counter() - started_at) * 1_000, 2),
        }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        handle.listen(1)
        return int(handle.getsockname()[1])


if __name__ == "__main__":
    raise SystemExit(main())
