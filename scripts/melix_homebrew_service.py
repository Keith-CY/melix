#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIGURED_REPO_ROOT = Path(__file__).resolve().parents[1]
if "MELIX_REPO_ROOT" in os.environ:
    CONFIGURED_REPO_ROOT = Path(os.environ["MELIX_REPO_ROOT"]).expanduser().resolve()

sys.path.insert(0, str(CONFIGURED_REPO_ROOT))
sys.path.insert(0, str(CONFIGURED_REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.homebrew_service import (  # noqa: E402
    DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME,
    build_homebrew_service_manifest,
    build_homebrew_service_specs,
    ensure_runtime_directories,
    run_homebrew_service_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["manifest", "run"])
    parser.add_argument("--repo-root", default=os.environ.get("MELIX_REPO_ROOT", str(REPO_ROOT)))
    parser.add_argument("--bin-dir", default=os.environ.get("MELIX_HOMEBREW_BIN_DIR", str(Path(sys.argv[0]).resolve().parent)))
    parser.add_argument("--home-dir", default=str(Path.home()))
    parser.add_argument("--http-port", type=int, default=11434)
    parser.add_argument("--service-instance-name", default=DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME)
    parser.add_argument("--swift-backend-mode", default="swift")
    parser.add_argument("--python-backend-mode", default="auto")
    parser.add_argument("--dev-text-model-path", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    layout, specs = build_homebrew_service_specs(
        repo_root=args.repo_root,
        bin_dir=args.bin_dir,
        home_dir=args.home_dir,
        http_port=args.http_port,
        service_instance_name=args.service_instance_name,
        swift_backend_mode=args.swift_backend_mode,
        python_backend_mode=args.python_backend_mode,
        dev_text_model_path=args.dev_text_model_path,
    )
    ensure_runtime_directories(layout)
    manifest = build_homebrew_service_manifest(layout, specs)

    if args.command == "manifest":
        if args.json:
            print(json.dumps(manifest, indent=2, sort_keys=True))
        else:
            print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    return run_homebrew_service_bundle(specs)


if __name__ == "__main__":
    raise SystemExit(main())
