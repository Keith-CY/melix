#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from phase8_runtime_probes import (
    collect_restart_recovery_evidence,
    collect_runtime_core_evidence,
    measure_cold_boot_to_ready,
)
from worker.productization.acceptance_metrics import (
    build_phase8_metrics_report,
    collect_operator_action_evidence,
)
from worker.productization.closure_audit import build_closure_audit
from worker.productization.release_gates import (
    build_release_gate_report,
    load_release_gate_policy,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument(
        "--policy",
        default=str(ROOT / "infra/release/phase8-release-gate-policy.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    policy = load_release_gate_policy(args.policy)
    cold_boot = measure_cold_boot_to_ready(repo_root)
    recovery = collect_restart_recovery_evidence(repo_root)
    runtime_core = collect_runtime_core_evidence(repo_root)
    release_gate_report = build_release_gate_report(
        repo_root,
        policy=policy,
        recovery=recovery,
        runtime_core=runtime_core,
    )
    closure_audit = build_closure_audit(repo_root).to_dict()
    operator = collect_operator_action_evidence(repo_root / ".runtime" / "phase8-metrics")
    report = build_phase8_metrics_report(
        cold_boot=cold_boot,
        operator=operator,
        release_gate_report=release_gate_report,
        runtime_core=runtime_core,
        closure_audit=closure_audit,
        policy=policy,
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if release_gate_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
