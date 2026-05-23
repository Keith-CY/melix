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
    DatasetIngestRequest,
    prepare_dataset_ingest,
)


def build_receipt(
    *,
    workspace_project_id: str,
    workspace_manifest_path: Path,
    input_path: Path,
    output_dir: Path,
    dataset_preparation_id: str,
    pii_mask: bool,
    exact_dedup: bool,
    fuzzy_dedup: bool,
    segmentation: bool,
    segmentation_strategy: str,
    output_path: Path | None = None,
) -> dict[str, object]:
    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id=workspace_project_id,
            workspace_manifest_path=workspace_manifest_path,
            input_path=input_path,
            output_dir=output_dir,
            dataset_preparation_id=dataset_preparation_id,
            pii_mask=pii_mask,
            exact_dedup=exact_dedup,
            fuzzy_dedup=fuzzy_dedup,
            segmentation=segmentation,
            segmentation_strategy=segmentation_strategy,
        )
    )
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a Melix dataset ingest receipt.")
    parser.add_argument("--workspace-project-id", required=True)
    parser.add_argument("--workspace-manifest", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-preparation-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pii-mask", type=_parse_bool, default=True)
    parser.add_argument("--exact-dedup", type=_parse_bool, default=True)
    parser.add_argument("--fuzzy-dedup", type=_parse_bool, default=True)
    parser.add_argument("--segmentation", type=_parse_bool, default=True)
    parser.add_argument("--segmentation-strategy", default="paragraph")
    args = parser.parse_args(argv)

    receipt = build_receipt(
        workspace_project_id=args.workspace_project_id,
        workspace_manifest_path=args.workspace_manifest,
        input_path=args.input,
        output_dir=args.output_dir,
        dataset_preparation_id=args.dataset_preparation_id,
        pii_mask=args.pii_mask,
        exact_dedup=args.exact_dedup,
        fuzzy_dedup=args.fuzzy_dedup,
        segmentation=args.segmentation,
        segmentation_strategy=args.segmentation_strategy,
        output_path=args.output,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("status") == "ready" else 1


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


if __name__ == "__main__":
    raise SystemExit(main())
