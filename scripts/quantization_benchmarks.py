#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worker.productization.quantization_gates import collect_quantization_benchmark_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs-root", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    jobs_root = Path(args.jobs_root) if args.jobs_root else None
    if jobs_root is None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix="melix-quant-bench-") as tmpdir:
            payload = collect_quantization_benchmark_evidence(Path(tmpdir))
    else:
        payload = collect_quantization_benchmark_evidence(jobs_root)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
