#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_swift_smoke(repo_root: Path) -> dict[str, float]:
    env = os.environ.copy()
    env.setdefault("HOME", str(repo_root / ".swift-home"))
    env.setdefault(
        "CLANG_MODULE_CACHE_PATH",
        str(repo_root / "apps" / "macos-menubar" / ".build" / "ModuleCache.noindex"),
    )
    command = [
        "swift",
        "test",
        "--disable-sandbox",
        "--package-path",
        str(repo_root / "apps" / "macos-menubar"),
        "--filter",
        "OperatorSessionPersistenceSmokeTests",
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    for stream in (completed.stdout, completed.stderr):
        if not stream:
            continue
        for line in stream.splitlines():
            if line.startswith("M8_ADMIN_STATE_SMOKE="):
                return json.loads(line.split("=", 1)[1])

    raise RuntimeError("Swift smoke completed without emitting M8_ADMIN_STATE_SMOKE.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M8.6 admin-state persistence smoke."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable metrics payload.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    runtime_metrics = run_swift_smoke(repo_root)

    payload = {
        "ok": True,
        "metrics": runtime_metrics,
        "persistence": {
            "selected_tool_section": "Diagnostics",
            "restores_across_restart": runtime_metrics["operator.session_tool_section_restored"] == 1,
            "secure_permissions": runtime_metrics["operator.session_file_permissions_ok"] == 1,
        },
        "offline_assets": {
            "native_shell": True,
            "external_reference_count": runtime_metrics["operator.offline_asset_external_reference_count"],
        },
    }

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("M8.6 admin-state persistence smoke passed.")
        print(json.dumps(payload["metrics"], indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
