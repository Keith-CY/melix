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
    env["HOME"] = str(repo_root / ".swift-home" / "macos-menubar")
    env["CLANG_MODULE_CACHE_PATH"] = str(
        repo_root / ".build" / "ModuleCache.noindex" / "macos-menubar"
    )
    command = [
        "xcrun",
        "swift",
        "test",
        "--package-path",
        str(repo_root / "apps" / "macos-menubar"),
        "--filter",
        "AgentIntegrationExportSmokeTests",
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
            if line.startswith("M9_AGENT_EXPORT_METRICS="):
                return json.loads(line.split("=", 1)[1])

    raise RuntimeError("Swift smoke completed without emitting M9_AGENT_EXPORT_METRICS.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M9.2 agent integration export smoke."
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
        "metrics": {
            "integration.export_generation_ms": runtime_metrics[
                "integration.export_generation_ms"
            ],
            "integration.setup_success_rate": 1.0,
            "integration.export_target_count": runtime_metrics[
                "integration.export_target_count"
            ],
        },
        "targets": [
            "OpenAI-Compatible",
            "OpenClaw",
            "Hermes Agent",
            "OpenCode",
            "Codex",
        ],
    }

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("M9.2 agent integration smoke passed.")
        print(json.dumps(payload["metrics"], indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
