#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.homebrew_service import (
    DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME,
    ManagedServiceProcessGroup,
    build_homebrew_service_manifest,
    build_homebrew_service_specs,
    ensure_runtime_directories,
)
from worker.productization.install_assets import LaunchAgentSpec


def _fixture_spec(root: Path, label: str, marker_path: Path) -> LaunchAgentSpec:
    return LaunchAgentSpec(
        label=label,
        plist_path=root / f"{label}.plist",
        program_arguments=[
            sys.executable,
            "-c",
            (
                "import pathlib,time;"
                f"pathlib.Path(r'{marker_path}').write_text('started', encoding='utf-8');"
                "time.sleep(60)"
            ),
        ],
        environment={},
        working_directory=root,
        stdout_path=root / f"{label}.stdout.log",
        stderr_path=root / f"{label}.stderr.log",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started_at = time.perf_counter()
    repo_root = Path(args.repo_root).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="melix-homebrew-service-") as temp_dir:
        temp_root = Path(temp_dir)
        bin_dir = temp_root / "bin"
        bin_dir.mkdir()

        layout, specs = build_homebrew_service_specs(
            repo_root=repo_root,
            bin_dir=bin_dir,
            home_dir=temp_root / "home",
            http_port=19434,
            service_instance_name=DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME,
        )
        ensure_runtime_directories(layout)
        manifest = build_homebrew_service_manifest(layout, specs)

        markers = [temp_root / f"fixture-{index}.marker" for index in range(3)]
        fixture_specs = [
            _fixture_spec(temp_root, f"io.melix.fixture-{index}", marker)
            for index, marker in enumerate(markers, start=1)
        ]
        group = ManagedServiceProcessGroup(fixture_specs)
        group.start()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not all(marker.exists() for marker in markers):
            time.sleep(0.05)
        shutdown_results = group.shutdown()
        checks = {
            "manifest_service_count": len(manifest["services"]) == 3,
            "manifest_homebrew_labels": all(
                service["label"].startswith("io.melix.homebrew.") for service in manifest["services"]
            ),
            "all_fixture_processes_started": all(marker.exists() for marker in markers),
            "all_fixture_processes_shutdown": len(shutdown_results) == 3
            and all(code is not None for _, code in shutdown_results),
        }
        result = {
            "homebrew_service_smoke_ms": round((time.perf_counter() - started_at) * 1_000, 2),
            "fixture_process_count": len(shutdown_results),
            "checks": checks,
            "ready_probe_url": manifest["ready_probe_url"],
        }

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
