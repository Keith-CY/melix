from __future__ import annotations

from pathlib import Path

import pytest

from worker.model_ops.errors import ModelOperationError
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog


class FakeBenchmarkSuiteFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
        self.calls.append((endpoint, dict(params)))
        dataset = params.get("dataset", "")
        offset = params.get("offset", "0")
        if endpoint == "rows" and offset != "0":
            return {"rows": []}

        if dataset == "HuggingFaceH4/ultrachat_200k":
            if endpoint == "rows":
                return {
                    "rows": [
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Say hi."},
                                    {"role": "assistant", "content": "Hi."},
                                ]
                            }
                        },
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Say bye."},
                                    {"role": "assistant", "content": "Bye."},
                                ]
                            }
                        },
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train_sft"}]}

        if dataset == "databricks/databricks-dolly-15k":
            if endpoint == "rows":
                return {
                    "rows": [
                        {"row": {"instruction": "List two colors.", "response": "Red and blue."}},
                        {"row": {"instruction": "List two animals.", "response": "Cat and dog."}},
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}

        raise AssertionError(f"Unexpected benchmark fetch: endpoint={endpoint} dataset={dataset}")


def test_benchmark_suite_catalog_materializes_curated_hf_suite_and_reuses_cache(
    tmp_path: Path,
) -> None:
    fetcher = FakeBenchmarkSuiteFetcher()
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=fetcher)

    first = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "2", "batch_factor": "2"},
    )
    second = catalog.resolve_suite("smoke", jobs_root=tmp_path, parameters={})

    assert first.suite_id == "smoke"
    assert first.dataset_path == "HuggingFaceH4/ultrachat_200k"
    assert first.dataset_name == "default"
    assert first.dataset_split == "train_sft"
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.sample_size == 2
    assert first.batch_factor == 2
    assert len(first.prompt_batches) == 2
    assert "Say hi." in first.prompt_batches[0]
    assert "Say bye." in first.prompt_batches[0]
    assert first.metadata()["dataset_uri"].startswith("hf://HuggingFaceH4/ultrachat_200k")


def test_benchmark_suite_catalog_raises_typed_error_for_unknown_suite(tmp_path: Path) -> None:
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkSuiteFetcher())

    with pytest.raises(ModelOperationError) as error:
        catalog.resolve_suite("missing-suite", jobs_root=tmp_path, parameters={})

    assert error.value.code == "invalid_benchmark_suite"
    assert error.value.details == {"suite_id": "missing-suite"}
