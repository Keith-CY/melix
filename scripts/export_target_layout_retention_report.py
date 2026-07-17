#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import tempfile
from typing import Literal


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))  # pragma: no cover - script bootstrap

from worker.productization.export_target_layout import build_layout_metrics_report


CleanupMode = Literal["none", "dry-run", "apply"]


DEFAULT_FIXTURE_ROOT = (
    ROOT
    / "services/mlx-worker-python/fixtures/runtime-export/target-manifests.dev.v1"
)


def _default_manifest_paths() -> list[Path]:
    return _manifest_paths_for_fixture_root(DEFAULT_FIXTURE_ROOT)


def _manifest_paths_for_fixture_root(root: Path) -> list[Path]:
    manifest_paths: list[str] = []
    manifest_paths_append = manifest_paths.append
    manifest_name = "export-target-manifest.json"
    root_path = os.fspath(root)
    try:
        with os.scandir(root_path) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:  # pragma: no cover - disappearing fixture race guard
                    continue
                manifest_path = os.path.join(entry.path, manifest_name)
                if os.path.isfile(manifest_path):
                    manifest_paths_append(manifest_path)
    except OSError:  # pragma: no cover - missing fixture root guard
        return []
    manifest_paths.sort()
    path_cls = Path
    return [path_cls(path) for path in manifest_paths]


def build_report(
    *,
    manifests: list[Path] | None = None,
    workspace_root: Path | None = None,
    cleanup: CleanupMode = "dry-run",
    create_placeholder_files: bool = True,
) -> dict[str, object]:
    paths = manifests or _default_manifest_paths()
    if workspace_root is not None:
        return build_layout_metrics_report(
            paths,
            workspace_root,
            cleanup=cleanup,
            create_placeholder_files=create_placeholder_files,
        )
    with tempfile.TemporaryDirectory(prefix="melix-export-layout-report-") as directory:
        return build_layout_metrics_report(
            paths,
            Path(directory),
            cleanup=cleanup,
            create_placeholder_files=create_placeholder_files,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize Melix export target layout reports.")
    parser.add_argument("--manifest", type=Path, action="append", dest="manifests")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--cleanup",
        choices=("none", "dry-run", "apply"),
        default="dry-run",
        help="Build no cleanup report, dry-run cleanup report, or apply cleanup.",
    )
    parser.add_argument(
        "--no-placeholder-files",
        action="store_true",
        help="Only write reports and directories; do not create small fixture placeholder files.",
    )
    args = parser.parse_args(argv)

    payload = build_report(
        manifests=args.manifests,
        workspace_root=args.workspace_root,
        cleanup=args.cleanup,
        create_placeholder_files=not args.no_placeholder_files,
    )
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if payload.get("ok") is True else 1


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
