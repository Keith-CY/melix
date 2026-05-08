#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.report_evidence_gate import (  # noqa: E402
    build_report_evidence_gate,
    write_report_evidence_gate_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-json", action="append", default=[])
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--require-release-matrix", action="store_true")
    parser.add_argument("--require-hardware-telemetry", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.report_json:
        print("at least one --report-json is required", file=sys.stderr)
        return 2

    try:
        gate_report = build_report_evidence_gate(
            args.report_json,
            require_release_matrix=args.require_release_matrix,
            require_hardware_telemetry=args.require_hardware_telemetry,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.output_dir:
        write_report_evidence_gate_outputs(gate_report, args.output_dir)
    print(json.dumps(gate_report, indent=2, sort_keys=True))
    return 0 if gate_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
