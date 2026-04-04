#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.homebrew_formula import read_melix_version, render_homebrew_formula


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    formula_path = repo_root / "infra/homebrew/Formula/melix.rb"

    started_at = time.perf_counter()
    version = read_melix_version(repo_root)
    rendered_formula = render_homebrew_formula(version=version)
    checked_in_formula = formula_path.read_text(encoding="utf-8")
    checks = {
        "formula_exists": formula_path.exists(),
        "formula_matches_renderer": checked_in_formula == rendered_formula,
        "service_block_present": "service do" in checked_in_formula,
        "local_source_url_present": 'url "file://#{repo_root}"' in checked_in_formula,
        "service_wrapper_present": 'opt_bin/"melix-homebrew-service"' in checked_in_formula,
    }
    result = {
        "homebrew_formula_render_ms": round((time.perf_counter() - started_at) * 1_000, 2),
        "formula_bytes": len(checked_in_formula.encode("utf-8")),
        "checks": checks,
        "version": version,
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
