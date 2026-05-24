#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from google.protobuf.json_format import MessageToDict

from worker.productization.workspace_manifest import validate_workspace_manifest_file


DEFAULT_FIXTURE = (
    ROOT
    / "services/mlx-worker-python/fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json"
)


def build_report(manifest_path: Path) -> dict[str, object]:
    report = validate_workspace_manifest_file(manifest_path)
    return MessageToDict(
        report,
        always_print_fields_with_no_presence=True,
        preserving_proto_field_name=True,
        use_integers_for_enums=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Melix workspace manifest fixtures.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = build_report(args.manifest)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if payload.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
