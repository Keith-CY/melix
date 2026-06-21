#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = REPO_ROOT / "services" / "mlx-worker-python"
for candidate in (REPO_ROOT, WORKER_ROOT):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from worker.productization.agent_reliability import (
    DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT,
    AgentReliabilityRunConfig,
    expand_ablation_presets,
    load_agent_reliability_scenarios,
    persist_agent_reliability_run,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Melix agent reliability fixture track.")
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-id", default="fixture-model")
    parser.add_argument("--backend", default="fixture")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--ablation", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    presets = expand_ablation_presets()
    selected_ablation_ids = args.ablation or list(presets)
    unknown = sorted(set(selected_ablation_ids) - set(presets))
    if unknown:
        raise ValueError(f"Unknown agent reliability ablation preset(s): {', '.join(unknown)}")
    result = persist_agent_reliability_run(
        AgentReliabilityRunConfig(
            output_dir=args.output_dir,
            model_id=args.model_id,
            backend=args.backend,
            profile=args.profile,
            resume=args.resume,
        ),
        scenarios=load_agent_reliability_scenarios(args.fixture_root),
        ablations=tuple(presets[preset_id] for preset_id in selected_ablation_ids),
    )
    payload = {
        "schema_version": "melix.agent_reliability_script_result.v1",
        "rows_path": str(result.rows_path),
        "summary_path": str(result.summary_path),
        "report_path": str(result.report_path),
        "summary": result.summary,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Agent reliability report: {result.report_path}")
        print(f"Rows: {result.rows_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
