#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worker.productization.quantization_gates import (
    collect_quantization_benchmark_evidence,
    evaluate_quantization_gate,
    load_quantization_gate_policy,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = ROOT / "infra/release/quantization-release-gate-policy.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs-root", default="")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    policy = load_quantization_gate_policy(args.policy)
    jobs_root = Path(args.jobs_root) if args.jobs_root else None
    if jobs_root is None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix="melix-quant-gate-") as tmpdir:
            evidence = collect_quantization_benchmark_evidence(Path(tmpdir))
    else:
        evidence = collect_quantization_benchmark_evidence(jobs_root)

    failures = evaluate_quantization_gate(evidence, policy)
    payload = {
        "passed": not failures,
        "failures": failures,
        "summary": evidence["summary"],
        "profiles": evidence["profiles"],
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("passed" if payload["passed"] else "failed")
        for failure in failures:
            print(f"- {failure}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
