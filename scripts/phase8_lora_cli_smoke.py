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
    env["CLANG_MODULE_CACHE_PATH"] = str(repo_root / ".build" / "ModuleCache.noindex")
    command = [
        "xcrun",
        "swift",
        "test",
        "--disable-sandbox",
        "--filter",
        "Phase8LoRACLISmokeTests",
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
            if line.startswith("PHASE8_LORA_CLI_SMOKE="):
                return json.loads(line.split("=", 1)[1])

    raise RuntimeError("Swift smoke completed without emitting PHASE8_LORA_CLI_SMOKE.")


def run_smoke(repo_root: Path) -> dict[str, object]:
    payload = run_swift_smoke(repo_root)
    return {
        "ok": True,
        "repo_root": str(repo_root),
        "model_id": payload["model_id"],
        "positive": payload["positive"],
        "negative": payload["negative"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic Phase 8 LoRA CLI smoke."
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable payload.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Override the repository root for smoke execution.",
    )
    args = parser.parse_args()

    payload = run_smoke(args.repo_root)

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("Phase 8 LoRA CLI smoke passed.")
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
