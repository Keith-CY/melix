from __future__ import annotations

import json
from pathlib import Path

from worker.productization.benchmark_schemas import (
    ServingBenchmarkJob,
    ServingBenchmarkResult,
)


class BenchmarkStore:
    def persist_serving_benchmark(
        self,
        *,
        jobs_root: Path,
        job: ServingBenchmarkJob,
        results: tuple[ServingBenchmarkResult, ...],
    ) -> dict[str, Path]:
        jobs_root.mkdir(parents=True, exist_ok=True)

        job_path = jobs_root / "bench-job.json"
        job_path.write_text(
            json.dumps(job.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        persisted: dict[str, Path] = {"job": job_path}
        for result in results:
            result_path = jobs_root / f"bench-result-{result.suite}.json"
            result_path.write_text(
                json.dumps(result.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            persisted[result.suite] = result_path

        return persisted
