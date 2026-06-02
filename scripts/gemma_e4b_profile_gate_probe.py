#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "mlx-worker-python"))

from worker.productization.gemma_e4b_profile_gate import (  # noqa: E402
    default_passing_evidence,
    evaluate_gemma_e4b_profile_gate_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Gemma E4B selected-profile release-gate evidence."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Read a persisted Gemma E4B profile-gate evidence JSON payload.",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Emit flat numeric metrics for the PR-scoped performance runner.",
    )
    return parser.parse_args()


def load_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return default_passing_evidence()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gemma E4B profile gate evidence must be a JSON object")
    return payload


def main() -> int:
    args = parse_args()
    report = evaluate_gemma_e4b_profile_gate_evidence(load_evidence(args.input))
    if args.metrics:
        print(json.dumps(report["metrics"], sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
