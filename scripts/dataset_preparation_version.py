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

from worker.productization.dataset_preparation import (
    DatasetRetryFailedRequest,
    DatasetVersionRequest,
    list_dataset_versions,
    prepare_dataset_version,
    retry_failed_dataset_version,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Melix dataset versions.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_version_parser(subparsers)
    _add_retry_parser(subparsers)
    _add_list_parser(subparsers)
    args = parser.parse_args(argv)

    if args.command == "version":
        payload = prepare_dataset_version(
            DatasetVersionRequest(
                workspace_manifest_path=args.workspace_manifest,
                ingest_receipt_path=args.ingest_receipt,
                output_root=args.output_root,
                dataset_id=args.dataset_id,
                version_id=args.version_id or "",
                created_at=args.created_at or "",
                mode=args.mode,
                generator_model=args.generator_model,
                output_kind=args.output_kind,
                output_format=args.output_format,
                validation_ratio=args.validation_ratio,
                fail_segment_ids=tuple(args.fail_segment_id),
            )
        )
    elif args.command == "retry-failed":
        payload = retry_failed_dataset_version(
            DatasetRetryFailedRequest(
                workspace_manifest_path=args.workspace_manifest,
                dataset_version_path=args.dataset_version,
                output_root=args.output_root,
                version_id=args.version_id or "",
                created_at=args.created_at or "",
                generator_model=args.generator_model or "",
            )
        )
    else:
        payload = list_dataset_versions(
            workspace_manifest_path=args.workspace_manifest,
            output_root=args.output_root,
            dataset_id=args.dataset_id,
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status", "ready") == "ready" else 1


def _add_version_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("version")
    parser.add_argument("--workspace-manifest", type=Path, required=True)
    parser.add_argument("--ingest-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--version-id", default="")
    parser.add_argument("--created-at", default="")
    parser.add_argument("--mode", default="chat")
    parser.add_argument("--generator-model", default="melix.local.dataset-versioner.v1")
    parser.add_argument("--output-kind", default="training")
    parser.add_argument("--output-format", default="prompt_completion")
    parser.add_argument("--validation-ratio", type=float, default=0.0)
    parser.add_argument("--fail-segment-id", action="append", default=[])
    parser.add_argument("--output", type=Path)


def _add_retry_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("retry-failed")
    parser.add_argument("--workspace-manifest", type=Path, required=True)
    parser.add_argument("--dataset-version", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--version-id", default="")
    parser.add_argument("--created-at", default="")
    parser.add_argument("--generator-model", default="")
    parser.add_argument("--output", type=Path)


def _add_list_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("list-versions")
    parser.add_argument("--workspace-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", type=Path)


if __name__ == "__main__":
    raise SystemExit(main())
