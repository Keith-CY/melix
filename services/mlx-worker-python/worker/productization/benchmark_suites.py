from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_dataset import (
    HFDatasetFetcher,
    HFDatasetReference,
    TrainingDatasetPackage,
    load_training_dataset_package,
    materialize_hf_training_dataset_package,
)


@dataclass(frozen=True)
class BenchmarkSuiteDefinition:
    suite_id: str
    title: str
    dataset_path: str
    dataset_name: str
    dataset_revision: str
    dataset_split: str
    chat_feature: str
    prompt_feature: str
    completion_feature: str
    text_feature: str
    default_sample_size: int
    default_batch_factor: int

    def reference(self) -> HFDatasetReference:
        return HFDatasetReference(
            dataset_path=self.dataset_path,
            dataset_name=self.dataset_name,
            dataset_revision=self.dataset_revision,
            train_split=self.dataset_split,
            chat_feature=self.chat_feature,
            prompt_feature=self.prompt_feature,
            completion_feature=self.completion_feature,
            text_feature=self.text_feature,
        )


@dataclass(frozen=True)
class ResolvedBenchmarkSuite:
    suite_id: str
    title: str
    dataset_path: str
    dataset_name: str
    dataset_revision: str
    dataset_split: str
    dataset_uri: str
    materialized_package_path: Path
    cache_key: str
    cache_hit: bool
    sample_size: int
    batch_factor: int
    prompt_batches: tuple[str, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "suite_id": self.suite_id,
            "title": self.title,
            "source_kind": "hf_dataset",
            "dataset_uri": self.dataset_uri,
            "dataset_path": self.dataset_path,
            "dataset_name": self.dataset_name,
            "dataset_revision": self.dataset_revision,
            "dataset_split": self.dataset_split,
            "materialized_package_path": str(self.materialized_package_path),
            "cache_key": self.cache_key,
            "cache_hit": self.cache_hit,
            "sample_size": self.sample_size,
            "batch_factor": self.batch_factor,
        }


class BenchmarkSuiteCatalog:
    def __init__(
        self,
        *,
        definitions: tuple[BenchmarkSuiteDefinition, ...] | None = None,
        hf_dataset_fetcher: HFDatasetFetcher | None = None,
    ) -> None:
        resolved_definitions = definitions or default_benchmark_suite_definitions()
        self._definitions = {definition.suite_id: definition for definition in resolved_definitions}
        self._hf_dataset_fetcher = hf_dataset_fetcher

    def list_definitions(self) -> tuple[BenchmarkSuiteDefinition, ...]:
        return tuple(self._definitions.values())

    def resolve_suite(
        self,
        suite_id: str,
        *,
        jobs_root: Path,
        parameters: dict[str, str],
    ) -> ResolvedBenchmarkSuite:
        definition = self._definitions.get(suite_id)
        if definition is None:
            raise ModelOperationError(
                code="invalid_benchmark_suite",
                message=f"Unknown benchmark suite: {suite_id}",
                details={"suite_id": suite_id},
            )

        materialized = materialize_hf_training_dataset_package(
            definition.reference(),
            cache_root=jobs_root / "datasets",
            fetch_json=self._hf_dataset_fetcher,
        )
        package = load_training_dataset_package(str(materialized.package_path))
        sample_size = _parse_positive_int(parameters.get("sample_size", ""), definition.default_sample_size)
        batch_factor = _parse_positive_int(parameters.get("batch_factor", ""), definition.default_batch_factor)

        return ResolvedBenchmarkSuite(
            suite_id=definition.suite_id,
            title=definition.title,
            dataset_path=materialized.reference.dataset_path,
            dataset_name=materialized.reference.dataset_name,
            dataset_revision=materialized.reference.dataset_revision,
            dataset_split=materialized.reference.train_split,
            dataset_uri=materialized.dataset_uri,
            materialized_package_path=materialized.package_path,
            cache_key=materialized.cache_key,
            cache_hit=materialized.cache_hit,
            sample_size=sample_size,
            batch_factor=batch_factor,
            prompt_batches=tuple(
                _prompt_batches(
                    _prompt_rows_from_package(package),
                    sample_size=sample_size,
                    batch_factor=batch_factor,
                )
            ),
        )


def default_benchmark_suite_definitions() -> tuple[BenchmarkSuiteDefinition, ...]:
    return (
        BenchmarkSuiteDefinition(
            suite_id="smoke",
            title="UltraChat Smoke",
            dataset_path="HuggingFaceH4/ultrachat_200k",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train_sft",
            chat_feature="messages",
            prompt_feature="",
            completion_feature="",
            text_feature="",
            default_sample_size=1,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            suite_id="latency",
            title="Dolly Latency",
            dataset_path="databricks/databricks-dolly-15k",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train",
            chat_feature="",
            prompt_feature="instruction",
            completion_feature="response",
            text_feature="",
            default_sample_size=5,
            default_batch_factor=1,
        ),
    )


def _prompt_rows_from_package(package: TrainingDatasetPackage) -> list[str]:
    prompts: list[str] = []
    for sample in package.normalized_samples:
        if "messages" in sample and isinstance(sample["messages"], list):
            non_assistant = [
                str(message.get("content", "")).strip()
                for message in sample["messages"]
                if isinstance(message, dict) and str(message.get("role", "")).strip() != "assistant"
            ]
            if non_assistant:
                prompts.append("\n".join(part for part in non_assistant if part))
            continue
        if "prompt" in sample:
            prompt = str(sample.get("prompt", "")).strip()
            if prompt:
                prompts.append(prompt)
            continue
        if "text" in sample:
            text = str(sample.get("text", "")).strip()
            if text:
                prompts.append(text)

    if prompts:
        return prompts
    raise ModelOperationError(
        code="invalid_benchmark_suite",
        message="Benchmark suite materialization did not produce any prompt rows.",
    )


def _prompt_batches(
    prompts: list[str],
    *,
    sample_size: int,
    batch_factor: int,
) -> list[str]:
    batches: list[str] = []
    for batch_index in range(sample_size):
        parts: list[str] = []
        for offset in range(batch_factor):
            prompt_index = ((batch_index * batch_factor) + offset) % len(prompts)
            parts.append(prompts[prompt_index])
        batches.append("\n\n".join(parts))
    return batches


def _parse_positive_int(raw_value: str, default: int) -> int:
    normalized = raw_value.strip()
    if not normalized:
        return max(1, default)
    try:
        return max(1, int(normalized))
    except ValueError:
        return max(1, default)
