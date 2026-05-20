from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from tests.test_maintenance_service import (
    FakeBenchmarkHFDatasetFetcher,
    RecordingBenchmarkBackend,
    build_service,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog, BenchmarkSuiteDefinition
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime


def test_run_bench_matrix_aggregates_agentic_tool_turn_fields(tmp_path: Path) -> None:
    class AgenticBenchmarkFetcher(FakeBenchmarkHFDatasetFetcher):
        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            dataset = params.get("dataset", "")
            if dataset == "HuggingFaceH4/ultrachat_200k" and endpoint == "rows":
                return {
                    "rows": [
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Visit the fixture page."},
                                ],
                                "tool_calls": [
                                    {
                                        "id": "visit-1",
                                        "name": "visit",
                                        "arguments": {"url": "fixture://bench"},
                                    }
                                ],
                                "tool_fixture_context": {
                                    "pages": {"fixture://bench": {"text": "Benchmark page."}},
                                },
                            }
                        },
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Visit the slow fixture page."},
                                ],
                                "tool_calls": [
                                    {
                                        "id": "visit-2",
                                        "name": "visit",
                                        "arguments": {"url": "fixture://slow"},
                                    }
                                ],
                                "tool_fixture_context": {
                                    "tool_status_overrides": {
                                        "visit-2": {
                                            "status": "timeout",
                                            "message": "fixture timeout",
                                        }
                                    }
                                },
                            }
                        },
                    ]
                }
            return super().__call__(endpoint, params)

    service = build_service(
        tmp_path,
        registry=WorkerRegistry(
            runtime=MLXTextRuntime(backend=RecordingBenchmarkBackend()),
            model_catalog=WorkerModelCatalog(environment={}),
        ),
        benchmark_fetcher=AgenticBenchmarkFetcher(),
    )
    service._core._benchmark_suite_catalog = BenchmarkSuiteCatalog(
        definitions=(
            BenchmarkSuiteDefinition(
                task_kind="text-generation",
                suite_id="agentic",
                title="Agentic Fixture",
                dataset_path="HuggingFaceH4/ultrachat_200k",
                dataset_name="default",
                dataset_revision="main",
                dataset_split="train_sft",
                prompt_feature="messages",
                text_feature="",
                image_feature="",
                source_image_feature="",
                mask_feature="",
                default_prompt="",
                default_sample_size=2,
                default_batch_factor=1,
            ),
        ),
        hf_dataset_fetcher=AgenticBenchmarkFetcher(),
    )

    response = service._core.bench_matrix_response(
        maintenance_pb2.RunBenchMatrixRequest(
            model_handle="melix-dev-text::1",
            task_kind="text-generation",
            suite_ids=["agentic"],
            context_lengths=[128],
            generation_lengths=[16],
            batch_sizes=[1],
            cache_profiles=["cold"],
            reasoning_modes=["default"],
            structured_output_modes=["plain_text"],
            concurrency_levels=[1],
            requests=2,
        )
    )

    run_dir = tmp_path / "model-ops" / "bench" / "matrix-runs" / response.job.job_id
    request_rows = [
        json.loads(line)
        for line in (run_dir / "bench-matrix-requests.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary_rows = [
        json.loads(line)
        for line in (run_dir / "bench-matrix-summary.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert [row["tool_call_count"] for row in request_rows] == [1, 1]
    assert [row["turn_count"] for row in request_rows] == [2, 2]
    assert request_rows[0]["fatal_rate"] == 0.0
    assert request_rows[1]["fatal_rate"] == 1.0
    assert all(row["observation_bytes"] > 0 for row in request_rows)
    assert summary_rows[0]["tool_call_count"] == 2
    assert summary_rows[0]["observation_bytes"] == sum(row["observation_bytes"] for row in request_rows)
    assert summary_rows[0]["fatal_rate"] == 0.5
    assert summary_rows[0]["turn_count"] == 4
