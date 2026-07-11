#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))  # pragma: no cover - script bootstrap

from google.protobuf.json_format import MessageToDict

from worker.productization.export_target_manifest import validate_export_target_manifest_file


DEFAULT_FIXTURE_ROOT = (
    ROOT
    / "services/mlx-worker-python/fixtures/runtime-export/target-manifests.dev.v1"
)


def _default_manifest_paths() -> list[Path]:
    paths: list[Path] = []
    try:
        entries = os.scandir(DEFAULT_FIXTURE_ROOT)
    except FileNotFoundError:
        return paths
    with entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            manifest_path = Path(entry.path) / "export-target-manifest.json"
            if manifest_path.is_file():
                paths.append(manifest_path)
    paths.sort()
    return paths


def build_report(manifest_paths: list[Path] | None = None) -> dict[str, object]:
    paths = manifest_paths or _default_manifest_paths()
    reports = [
        MessageToDict(
            validate_export_target_manifest_file(path, fixture_count=len(paths)),
            always_print_fields_with_no_presence=True,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )
        for path in paths
    ]
    schema_error_count = sum(int(report.get("schema_error_count", 0)) for report in reports)
    return {
        "schema_version": "melix.export_target_manifest.metrics.v1",
        "ok": all(report.get("ok") is True for report in reports),
        "fixture_count": len(reports),
        "schema_error_count": schema_error_count,
        "manifest_byte_size": sum(int(report.get("manifest_byte_size", 0)) for report in reports),
        "manifest_validation_latency_ms": sum(
            float(report.get("manifest_validation_latency_ms", 0.0)) for report in reports
        ),
        "reports": reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Melix export target manifest fixtures.")
    parser.add_argument("--manifest", type=Path, action="append", dest="manifests")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = build_report(args.manifests)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if payload.get("ok") is True else 1


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
