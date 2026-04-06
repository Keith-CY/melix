#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_swift_smoke(repo_root: Path) -> dict[str, object]:
    env = os.environ.copy()
    env["HOME"] = str(repo_root / ".swift-home")
    env["CLANG_MODULE_CACHE_PATH"] = str(
        repo_root / ".build" / "ModuleCache.noindex"
    )
    env.setdefault(
        "MELIX_HOME",
        str(repo_root / ".runtime" / "phase1" / "smoke-home"),
    )
    command = [
        "swift",
        "test",
        "--disable-sandbox",
        "--package-path",
        str(repo_root / "apps" / "macos-menubar"),
        "--filter",
        "DesktopPolishSmokeTests",
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
