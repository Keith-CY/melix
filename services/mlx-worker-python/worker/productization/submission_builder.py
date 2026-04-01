from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from worker.productization.benchmark_export import build_export_bundle
from worker.productization.device_identity import DeviceIdentity

_SUBMISSION_SCHEMA_VERSION = "melix.submission.v1"


@dataclass(frozen=True)
class SubmissionPayload:
    schema_version: str
    device: dict[str, object]
    benchmark_jobs: list[dict[str, object]]
    benchmark_results: list[dict[str, object]]
    evaluation_jobs: list[dict[str, object]]
    evaluation_results: list[dict[str, object]]
    submitted_at_unix_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "device": dict(self.device),
            "benchmark_jobs": list(self.benchmark_jobs),
            "benchmark_results": list(self.benchmark_results),
            "evaluation_jobs": list(self.evaluation_jobs),
            "evaluation_results": list(self.evaluation_results),
            "submitted_at_unix_ms": self.submitted_at_unix_ms,
        }


def build_submission_payload(
    jobs_root: Path,
    device: DeviceIdentity,
) -> SubmissionPayload:
    bundle = build_export_bundle(jobs_root)
    return SubmissionPayload(
        schema_version=_SUBMISSION_SCHEMA_VERSION,
        device=device.to_dict(),
        benchmark_jobs=bundle.get("benchmark_jobs", []),
        benchmark_results=bundle.get("benchmark_results", []),
        evaluation_jobs=bundle.get("evaluation_jobs", []),
        evaluation_results=bundle.get("evaluation_results", []),
        submitted_at_unix_ms=int(time.time() * 1000),
    )
