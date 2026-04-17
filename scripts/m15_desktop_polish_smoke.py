#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import swift_root_package


_SWIFTPM_LOCK_MARKER = "Another instance of SwiftPM"
_SWIFTPM_LOCK_RETRIES = 3
_SWIFTPM_LOCK_BACKOFF_SECONDS = 2.0


def run_swift_smoke(repo_root: Path) -> dict[str, object]:
    env = swift_root_package.swift_package_environment(
        repo_root,
        "macos-menubar",
        base_env=os.environ.copy(),
    )
    env.setdefault(
        "MELIX_HOME",
        str(repo_root / ".runtime" / "phase1" / "smoke-home"),
    )
    command = swift_root_package.swift_package_command(
        repo_root / "apps" / "macos-menubar",
        repo_root,
        "macos-menubar",
        "test",
        [
            "--disable-sandbox",
            "--filter",
            "DesktopPolishSmokeTests",
        ],
    )
    completed = None
    for attempt in range(_SWIFTPM_LOCK_RETRIES + 1):
        completed = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if completed.returncode == 0:
            break
        if (
            attempt < _SWIFTPM_LOCK_RETRIES
            and _SWIFTPM_LOCK_MARKER in "\n".join(
                part for part in [completed.stdout, completed.stderr] if part
            )
        ):
            time.sleep(_SWIFTPM_LOCK_BACKOFF_SECONDS * (attempt + 1))
            continue
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )

    for stream in (completed.stdout, completed.stderr):
        if not stream:
            continue
        for line in stream.splitlines():
            if line.startswith("M15_DESKTOP_POLISH_SMOKE="):
                return json.loads(line.split("=", 1)[1])

    raise RuntimeError("Swift smoke completed without emitting M15_DESKTOP_POLISH_SMOKE.")


def run_smoke(repo_root: Path) -> dict[str, object]:
    payload = run_swift_smoke(repo_root)
    chat = payload["chat"]
    signals = payload["signals"]
    persistence = payload["persistence"]
    navigation = payload["navigation"]

    return {
        "ok": True,
        "repo_root": str(repo_root),
        "chat": {
            "presentation_lag_ms": chat["presentation_lag_ms"],
            "presentation_flush_count": chat["presentation_flush_count"],
        },
        "signals": {
            "top_banner_title": signals["top_banner_title"],
            "download_recovery_visible": signals["download_recovery_visible"] == 1,
            "update_signal_visible": signals["update_signal_visible"] == 1,
            "update_signal_dismissible": signals["update_signal_dismissible"] == 1,
        },
        "persistence": {
            "operator_session_restore_ms": persistence["operator_session_restore_ms"],
            "operator_session_persist_write_ms": persistence["operator_session_persist_write_ms"],
            "persisted_download_queue_count": persistence["persisted_download_queue_count"],
            "restored_download_queue_count": persistence["restored_download_queue_count"],
            "restored_selected_tool_section": persistence["restored_selected_tool_section"],
        },
        "navigation": {
            "grounded_surface_count": navigation["grounded_surface_count"],
            "grounded_tool_section_count": navigation["grounded_tool_section_count"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M15.4 desktop-polish smoke."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable payload.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Override the repository root for test execution.",
    )
    args = parser.parse_args()

    payload = run_smoke(args.repo_root)

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("M15.4 desktop-polish smoke passed.")
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
