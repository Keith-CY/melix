from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from worker.dataset_registry.catalog import (
    read_hf_dataset_snapshot_rows,
    resolve_cached_hf_dataset_snapshot,
)
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_dataset import HFDatasetFetcher

_HF_DATASETS_SERVER_URL = "https://datasets-server.huggingface.co"
_BENCHMARK_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "benchmark"
_BENCHMARK_FIXTURE_SOURCE_KIND = "melix_benchmark_fixture"


@dataclass(frozen=True)
class BenchmarkSuiteDefinition:
    task_kind: str
    suite_id: str
    title: str
    dataset_path: str
    dataset_name: str
    dataset_revision: str
    dataset_split: str
    prompt_feature: str
    text_feature: str
    image_feature: str
    source_image_feature: str
    mask_feature: str
    default_prompt: str
    default_sample_size: int
    default_batch_factor: int
    fixture_package_id: str = ""


@dataclass(frozen=True)
class BenchmarkCase:
    prompt: str
    image_uris: tuple[str, ...] = ()
    source_image_uri: str = ""
    mask_uri: str = ""
    tool_calls: tuple[dict[str, Any], ...] = ()
    tool_fixture_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResolvedBenchmarkSuite:
    task_kind: str
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
    source_kind: str
    sample_size: int
    batch_factor: int
    prompt_batches: tuple[str, ...]
    cases: tuple[BenchmarkCase, ...]
    hf_snapshot_id: str = ""
    hf_snapshot_path: str = ""
    hf_cache_repo_path: str = ""
    fixture_package_id: str = ""

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "suite_id": self.suite_id,
            "task_kind": self.task_kind,
            "title": self.title,
            "source_kind": self.source_kind,
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
        if self.hf_snapshot_id:
            metadata["hf_snapshot_id"] = self.hf_snapshot_id
            metadata["hf_snapshot_path"] = self.hf_snapshot_path
            metadata["hf_cache_repo_path"] = self.hf_cache_repo_path
        if self.fixture_package_id:
            metadata["fixture_package_id"] = self.fixture_package_id
        return metadata


class BenchmarkSuiteCatalog:
    def __init__(
        self,
        *,
        definitions: tuple[BenchmarkSuiteDefinition, ...] | None = None,
        hf_dataset_fetcher: HFDatasetFetcher | None = None,
    ) -> None:
        resolved_definitions = definitions or default_benchmark_suite_definitions()
        self._definitions = {
            (definition.task_kind, definition.suite_id): definition
            for definition in resolved_definitions
        }
        self._hf_dataset_fetcher = hf_dataset_fetcher or _fetch_hf_dataset_server_json
        self._resolved_suite_cache: dict[
            tuple[str, str, Path, int, int, str],
            ResolvedBenchmarkSuite,
        ] = {}

    def list_definitions(self) -> tuple[BenchmarkSuiteDefinition, ...]:
        return tuple(self._definitions.values())

    def resolve_suite(
        self,
        suite_id: str,
        *,
        jobs_root: Path,
        parameters: dict[str, str],
        task_kind: str = "text-generation",
    ) -> ResolvedBenchmarkSuite:
        definition = self._definitions.get((task_kind, suite_id))
        if definition is None:
            raise ModelOperationError(
                code="invalid_benchmark_suite",
                message=f"Unknown benchmark suite: {suite_id}",
                details={"suite_id": suite_id, "task_kind": task_kind},
            )
        definition = _definition_with_dataset_override(definition, parameters)

        sample_size = _parse_positive_int(parameters.get("sample_size", ""), definition.default_sample_size)
        batch_factor = _parse_positive_int(parameters.get("batch_factor", ""), definition.default_batch_factor)
        cache_key = (
            definition.task_kind,
            definition.suite_id,
            jobs_root,
            sample_size,
            batch_factor,
            _benchmark_suite_cache_key(definition),
        )
        cached_suite = self._resolved_suite_cache.get(cache_key)
        if cached_suite is not None:
            return cached_suite

        sample_hint = _materialized_sample_hint(sample_size=sample_size, batch_factor=batch_factor)
        materialized = _materialize_benchmark_suite(
            definition,
            cache_root=jobs_root / "datasets",
            fetch_json=self._hf_dataset_fetcher,
            sample_hint=sample_hint,
        )
        cases = tuple(
            _suite_cases(
                definition,
                rows=materialized["rows"],
                sample_size=sample_size,
                batch_factor=batch_factor,
            )
        )
        resolved_suite = ResolvedBenchmarkSuite(
            task_kind=definition.task_kind,
            suite_id=definition.suite_id,
            title=definition.title,
            dataset_path=definition.dataset_path,
            dataset_name=materialized["dataset_name"],
            dataset_revision=definition.dataset_revision,
            dataset_split=definition.dataset_split,
            dataset_uri=_hf_dataset_uri(
                dataset_path=definition.dataset_path,
                dataset_name=materialized["dataset_name"],
                dataset_revision=definition.dataset_revision,
                dataset_split=definition.dataset_split,
            )
            if not materialized.get("dataset_uri")
            else str(materialized["dataset_uri"]),
            materialized_package_path=materialized["package_path"],
            cache_key=materialized["cache_key"],
            cache_hit=materialized["cache_hit"],
            source_kind=materialized["source_kind"],
            hf_snapshot_id=materialized.get("hf_snapshot_id", ""),
            hf_snapshot_path=materialized.get("hf_snapshot_path", ""),
            hf_cache_repo_path=materialized.get("hf_cache_repo_path", ""),
            fixture_package_id=materialized.get("fixture_package_id", ""),
            sample_size=sample_size,
            batch_factor=batch_factor,
            prompt_batches=tuple(case.prompt for case in cases),
            cases=cases,
        )
        self._resolved_suite_cache[cache_key] = replace(resolved_suite, cache_hit=True)
        return resolved_suite


def default_benchmark_suite_definitions() -> tuple[BenchmarkSuiteDefinition, ...]:
    return (
        BenchmarkSuiteDefinition(
            task_kind="text-generation",
            suite_id="smoke",
            title="UltraChat Smoke",
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
            default_sample_size=1,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="text-generation",
            suite_id="latency",
            title="Dolly Latency",
            dataset_path="databricks/databricks-dolly-15k",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train",
            prompt_feature="instruction",
            text_feature="",
            image_feature="",
            source_image_feature="",
            mask_feature="",
            default_prompt="",
            default_sample_size=5,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="text-generation",
            suite_id="agentic_image",
            title="Agentic Image Fixture",
            dataset_path="agentic-image.dev.v1",
            dataset_name="default",
            dataset_revision="1",
            dataset_split="validation",
            prompt_feature="prompt",
            text_feature="",
            image_feature="",
            source_image_feature="",
            mask_feature="",
            default_prompt="",
            default_sample_size=1,
            default_batch_factor=1,
            fixture_package_id="agentic-image.dev.v1",
        ),
        BenchmarkSuiteDefinition(
            task_kind="text-generation",
            suite_id="agentic_search",
            title="Agentic Search Fixture",
            dataset_path="agentic-search.dev.v1",
            dataset_name="default",
            dataset_revision="1",
            dataset_split="validation",
            prompt_feature="prompt",
            text_feature="",
            image_feature="",
            source_image_feature="",
            mask_feature="",
            default_prompt="",
            default_sample_size=1,
            default_batch_factor=1,
            fixture_package_id="agentic-search.dev.v1",
        ),
        BenchmarkSuiteDefinition(
            task_kind="text-generation",
            suite_id="agentic_visit",
            title="Agentic Visit Fixture",
            dataset_path="agentic-visit.dev.v1",
            dataset_name="default",
            dataset_revision="1",
            dataset_split="validation",
            prompt_feature="prompt",
            text_feature="",
            image_feature="",
            source_image_feature="",
            mask_feature="",
            default_prompt="",
            default_sample_size=1,
            default_batch_factor=1,
            fixture_package_id="agentic-visit.dev.v1",
        ),
        BenchmarkSuiteDefinition(
            task_kind="image-to-text",
            suite_id="smoke",
            title="Docs Images OCR Smoke",
            dataset_path="huggingface/documentation-images",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train",
            prompt_feature="",
            text_feature="",
            image_feature="image",
            source_image_feature="",
            mask_feature="",
            default_prompt="Describe the image.",
            default_sample_size=1,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="image-to-text",
            suite_id="latency",
            title="Docs Images OCR Latency",
            dataset_path="huggingface/documentation-images",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="validation",
            prompt_feature="",
            text_feature="",
            image_feature="image",
            source_image_feature="",
            mask_feature="",
            default_prompt="Describe the image.",
            default_sample_size=4,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="image-text-to-text",
            suite_id="smoke",
            title="Docs Images VLM Smoke",
            dataset_path="huggingface/documentation-images",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train",
            prompt_feature="",
            text_feature="",
            image_feature="image",
            source_image_feature="",
            mask_feature="",
            default_prompt="Describe the image in one sentence.",
            default_sample_size=1,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="image-text-to-text",
            suite_id="latency",
            title="Docs Images VLM Latency",
            dataset_path="huggingface/documentation-images",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="validation",
            prompt_feature="",
            text_feature="",
            image_feature="image",
            source_image_feature="",
            mask_feature="",
            default_prompt="Describe the image in one sentence.",
            default_sample_size=4,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="text-to-image",
            suite_id="smoke",
            title="Dolly Text-to-Image Smoke",
            dataset_path="databricks/databricks-dolly-15k",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train",
            prompt_feature="instruction",
            text_feature="",
            image_feature="",
            source_image_feature="",
            mask_feature="",
            default_prompt="Generate an image from the prompt.",
            default_sample_size=1,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="text-to-image",
            suite_id="latency",
            title="UltraChat Text-to-Image Latency",
            dataset_path="HuggingFaceH4/ultrachat_200k",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train_sft",
            prompt_feature="messages",
            text_feature="",
            image_feature="",
            source_image_feature="",
            mask_feature="",
            default_prompt="Generate an image from the prompt.",
            default_sample_size=4,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="image-text-to-image",
            suite_id="smoke",
            title="Docs Images Edit Smoke",
            dataset_path="huggingface/documentation-images",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="train",
            prompt_feature="",
            text_feature="",
            image_feature="",
            source_image_feature="image",
            mask_feature="",
            default_prompt="Edit the image to look like a watercolor painting.",
            default_sample_size=1,
            default_batch_factor=1,
        ),
        BenchmarkSuiteDefinition(
            task_kind="image-text-to-image",
            suite_id="latency",
            title="Docs Images Edit Latency",
            dataset_path="huggingface/documentation-images",
            dataset_name="default",
            dataset_revision="main",
            dataset_split="validation",
            prompt_feature="",
            text_feature="",
            image_feature="",
            source_image_feature="image",
            mask_feature="",
            default_prompt="Edit the image to have warmer lighting.",
            default_sample_size=4,
            default_batch_factor=1,
        ),
    )


def _materialize_benchmark_suite(
    definition: BenchmarkSuiteDefinition,
    *,
    cache_root: Path,
    fetch_json: HFDatasetFetcher,
    sample_hint: int,
) -> dict[str, Any]:
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_key = _benchmark_suite_cache_key(definition)
    package_path = cache_root / cache_key
    manifest_path = package_path / "manifest.json"
    rows_path = package_path / "rows.jsonl"
    if manifest_path.is_file() and rows_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "package_path": package_path,
            "cache_key": cache_key,
            "cache_hit": True,
            "source_kind": str(manifest.get("source_kind", "hf_dataset")),
            "dataset_uri": str(manifest.get("dataset_uri", "")),
            "fixture_package_id": str(manifest.get("fixture_package_id", "")),
            "hf_snapshot_id": str(manifest.get("hf_snapshot_id", "")),
            "hf_snapshot_path": str(manifest.get("hf_snapshot_path", "")),
            "hf_cache_repo_path": str(manifest.get("hf_cache_repo_path", "")),
            "dataset_name": str(manifest.get("dataset_name", definition.dataset_name or "default")),
            "rows": _load_materialized_rows(rows_path, limit=sample_hint),
        }

    if definition.fixture_package_id:
        return _materialize_fixture_benchmark_suite(
            definition,
            package_path=package_path,
            manifest_path=manifest_path,
            rows_path=rows_path,
            cache_key=cache_key,
            sample_hint=sample_hint,
        )

    source_kind = "hf_dataset"
    local_snapshot = None
    snapshot = resolve_cached_hf_dataset_snapshot(
        repo_id=definition.dataset_path,
        revision=definition.dataset_revision or "main",
    )
    if snapshot is not None:
        dataset_name = definition.dataset_name or (snapshot.configs[0] if snapshot.configs else "default")
        rows = read_hf_dataset_snapshot_rows(
            snapshot.snapshot_path,
            split=definition.dataset_split,
            limit=sample_hint,
        )
        if rows:
            source_kind = "hf_cache_snapshot"
            local_snapshot = snapshot
    if local_snapshot is None:
        dataset_name = definition.dataset_name or _resolve_dataset_name(definition, fetch_json)
        row_payload = fetch_json(
            "rows",
            {
                "dataset": definition.dataset_path,
                "config": dataset_name,
                "split": definition.dataset_split,
                "offset": "0",
                "length": str(max(1, sample_hint)),
            },
        )
        rows = [
            entry["row"]
            for entry in row_payload.get("rows", [])
            if isinstance(entry, dict) and isinstance(entry.get("row"), dict)
        ]
    if not rows:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Benchmark suite materialization did not return any usable rows.",
            details={"suite_id": definition.suite_id, "task_kind": definition.task_kind},
        )

    package_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "melix.benchmark_suite_materialization.v1",
        "source_kind": source_kind,
        "task_kind": definition.task_kind,
        "suite_id": definition.suite_id,
        "dataset_path": definition.dataset_path,
        "dataset_name": dataset_name,
        "dataset_revision": definition.dataset_revision,
        "dataset_split": definition.dataset_split,
        "prompt_feature": definition.prompt_feature,
        "text_feature": definition.text_feature,
        "image_feature": definition.image_feature,
        "source_image_feature": definition.source_image_feature,
        "mask_feature": definition.mask_feature,
        "default_prompt": definition.default_prompt,
    }
    if local_snapshot is not None:
        manifest.update(
            {
                "hf_snapshot_id": local_snapshot.snapshot_id,
                "hf_snapshot_path": str(local_snapshot.snapshot_path),
                "hf_cache_repo_path": str(local_snapshot.cache_repo_path),
            }
        )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _write_jsonl_rows(rows_path, rows)
    return {
        "package_path": package_path,
        "cache_key": cache_key,
        "cache_hit": False,
        "source_kind": source_kind,
        "dataset_uri": "",
        "fixture_package_id": "",
        "hf_snapshot_id": local_snapshot.snapshot_id if local_snapshot is not None else "",
        "hf_snapshot_path": str(local_snapshot.snapshot_path) if local_snapshot is not None else "",
        "hf_cache_repo_path": str(local_snapshot.cache_repo_path) if local_snapshot is not None else "",
        "dataset_name": dataset_name,
        "rows": rows,
    }


def _materialize_fixture_benchmark_suite(
    definition: BenchmarkSuiteDefinition,
    *,
    package_path: Path,
    manifest_path: Path,
    rows_path: Path,
    cache_key: str,
    sample_hint: int,
) -> dict[str, Any]:
    fixture_dir = _benchmark_fixture_package_path(definition.fixture_package_id)
    source_manifest_path = fixture_dir / "manifest.json"
    source_rows_path = fixture_dir / "samples.jsonl"
    if not source_manifest_path.is_file() or not source_rows_path.is_file():
        raise ModelOperationError(
            code="invalid_benchmark_suite",
            message="Benchmark fixture package is missing manifest.json or samples.jsonl.",
            details={
                "suite_id": definition.suite_id,
                "task_kind": definition.task_kind,
                "fixture_package_id": definition.fixture_package_id,
            },
        )

    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    fixture_package_id = str(
        source_manifest.get("fixture_package_id") or definition.fixture_package_id
    )
    rows = _load_materialized_rows(source_rows_path, limit=sample_hint)
    if not rows:
        raise ModelOperationError(
            code="invalid_benchmark_suite",
            message="Benchmark fixture package did not contain any usable rows.",
            details={
                "suite_id": definition.suite_id,
                "task_kind": definition.task_kind,
                "fixture_package_id": fixture_package_id,
            },
        )

    dataset_name = str(source_manifest.get("dataset_name") or definition.dataset_name or "default")
    dataset_uri = _benchmark_fixture_dataset_uri(fixture_package_id)
    package_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "melix.benchmark_suite_materialization.v1",
        "source_kind": _BENCHMARK_FIXTURE_SOURCE_KIND,
        "task_kind": definition.task_kind,
        "suite_id": definition.suite_id,
        "dataset_path": definition.dataset_path,
        "dataset_name": dataset_name,
        "dataset_revision": definition.dataset_revision,
        "dataset_split": definition.dataset_split,
        "dataset_uri": dataset_uri,
        "fixture_package_id": fixture_package_id,
        "fixture_package_path": str(fixture_dir),
        "fixture_schema_version": str(source_manifest.get("schema_version", "")),
        "prompt_feature": definition.prompt_feature,
        "text_feature": definition.text_feature,
        "image_feature": definition.image_feature,
        "source_image_feature": definition.source_image_feature,
        "mask_feature": definition.mask_feature,
        "default_prompt": definition.default_prompt,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _write_jsonl_rows(rows_path, rows)
    return {
        "package_path": package_path,
        "cache_key": cache_key,
        "cache_hit": False,
        "source_kind": _BENCHMARK_FIXTURE_SOURCE_KIND,
        "dataset_uri": dataset_uri,
        "fixture_package_id": fixture_package_id,
        "hf_snapshot_id": "",
        "hf_snapshot_path": "",
        "hf_cache_repo_path": "",
        "dataset_name": dataset_name,
        "rows": rows,
    }


def _definition_with_dataset_override(
    definition: BenchmarkSuiteDefinition,
    parameters: dict[str, str],
) -> BenchmarkSuiteDefinition:
    dataset_ref = parameters.get("dataset_ref", "").strip()
    dataset_path = parameters.get("hf_dataset_path", "").strip()
    dataset_revision = parameters.get("hf_dataset_revision", "").strip()
    if dataset_ref:
        ref_path, ref_revision = _parse_dataset_ref(dataset_ref)
        dataset_path = dataset_path or ref_path
        dataset_revision = dataset_revision or ref_revision

    if not dataset_path:
        return definition

    return replace(
        definition,
        dataset_path=dataset_path,
        dataset_name=parameters.get("hf_dataset_name", "").strip() or definition.dataset_name,
        dataset_revision=dataset_revision or definition.dataset_revision or "main",
        dataset_split=parameters.get("hf_dataset_split", "").strip()
        or parameters.get("dataset_split", "").strip()
        or definition.dataset_split,
        prompt_feature=parameters.get("prompt_feature", "").strip() or definition.prompt_feature,
        text_feature=parameters.get("text_feature", "").strip() or definition.text_feature,
        image_feature=parameters.get("image_feature", "").strip() or definition.image_feature,
        source_image_feature=parameters.get("source_image_feature", "").strip() or definition.source_image_feature,
        mask_feature=parameters.get("mask_feature", "").strip() or definition.mask_feature,
        fixture_package_id="",
    )


def _parse_dataset_ref(dataset_ref: str) -> tuple[str, str]:
    # Keep this grammar in sync with MelixCLIParser.parseDatasetReference.
    trimmed = dataset_ref.strip()
    if "@" not in trimmed:
        repo_id, revision = trimmed, "main"
    else:
        repo_id, revision = trimmed.rsplit("@", 1)
        repo_id = repo_id.strip()
        revision = revision.strip() or "main"
    if not repo_id or "@" in repo_id:
        raise ModelOperationError(
            code="invalid_argument",
            message="Invalid dataset_ref. Expected format: repo/name[@revision].",
            details={"dataset_ref": dataset_ref},
        )
    return repo_id, revision


def _suite_cases(
    definition: BenchmarkSuiteDefinition,
    *,
    rows: list[dict[str, Any]],
    sample_size: int,
    batch_factor: int,
) -> list[BenchmarkCase]:
    if definition.task_kind == "text-generation":
        text_cases = _text_cases(definition, rows)
        return [
            BenchmarkCase(
                prompt=case["prompt"],
                tool_calls=tuple(dict(call) for call in case["tool_calls"]),
                tool_fixture_context=dict(case["tool_fixture_context"]),
            )
            for case in _batched_text_cases(
                text_cases,
                sample_size=sample_size,
                batch_factor=batch_factor,
            )
        ]

    if definition.task_kind == "text-to-image":
        prompts = _text_prompts(definition, rows)
        return [
            BenchmarkCase(prompt=prompts[index % len(prompts)])
            for index in range(sample_size)
        ]

    if definition.task_kind in {"image-to-text", "image-text-to-text"}:
        image_uris = _image_uris(rows, definition.image_feature)
        if not image_uris:
            raise ModelOperationError(
                code="invalid_benchmark_suite",
                message="Benchmark suite materialization did not produce any image URIs.",
                details={"suite_id": definition.suite_id, "task_kind": definition.task_kind},
            )
        return [
            BenchmarkCase(
                prompt=definition.default_prompt,
                image_uris=tuple(
                    image_uris[(index * batch_factor + offset) % len(image_uris)]
                    for offset in range(batch_factor)
                ),
            )
            for index in range(sample_size)
        ]

    if definition.task_kind == "image-text-to-image":
        image_uris = _image_uris(rows, definition.source_image_feature)
        if not image_uris:
            raise ModelOperationError(
                code="invalid_benchmark_suite",
                message="Benchmark suite materialization did not produce any source image URIs.",
                details={"suite_id": definition.suite_id, "task_kind": definition.task_kind},
            )
        return [
            BenchmarkCase(
                prompt=definition.default_prompt,
                source_image_uri=image_uris[index % len(image_uris)],
            )
            for index in range(sample_size)
        ]

    raise ModelOperationError(
        code="invalid_benchmark_suite",
        message=f"Unsupported task kind for benchmark suite resolution: {definition.task_kind}",
    )


def _text_prompts(definition: BenchmarkSuiteDefinition, rows: list[dict[str, Any]]) -> list[str]:
    return [case["prompt"] for case in _text_cases(definition, rows)]


def _text_cases(definition: BenchmarkSuiteDefinition, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        prompt = ""
        if definition.prompt_feature == "messages":
            messages = row.get("messages")
            if isinstance(messages, list):
                prompt_parts = [
                    str(message.get("content", "")).strip()
                    for message in messages
                    if isinstance(message, dict) and str(message.get("role", "")).strip() != "assistant"
                ]
                prompt = "\n".join(part for part in prompt_parts if part)
        if not prompt and definition.prompt_feature:
            prompt = _string_value(row.get(definition.prompt_feature))
        if not prompt and definition.text_feature:
            prompt = _string_value(row.get(definition.text_feature))
        if prompt:
            cases.append(
                {
                    "prompt": prompt,
                    "tool_calls": _tool_calls_from_row(row),
                    "tool_fixture_context": _tool_fixture_context_from_row(row),
                }
            )
    if cases:
        return cases
    if definition.default_prompt:
        return [{"prompt": definition.default_prompt, "tool_calls": (), "tool_fixture_context": {}}]
    raise ModelOperationError(
        code="invalid_benchmark_suite",
        message="Benchmark suite materialization did not produce any text prompts.",
        details={"suite_id": definition.suite_id, "task_kind": definition.task_kind},
    )


def _tool_calls_from_row(row: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    tool_calls = row.get("tool_calls")
    if not isinstance(tool_calls, list):
        return ()
    return tuple(dict(call) for call in tool_calls if isinstance(call, dict))


def _tool_fixture_context_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_context = row.get("tool_fixture_context") or row.get("tool_context")
    return dict(raw_context) if isinstance(raw_context, dict) else {}


def _batched_text_cases(
    cases: list[dict[str, Any]],
    *,
    sample_size: int,
    batch_factor: int,
) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for batch_index in range(sample_size):
        prompts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_fixture_context: dict[str, Any] = {}
        for offset in range(batch_factor):
            case_index = ((batch_index * batch_factor) + offset) % len(cases)
            case = cases[case_index]
            prompts.append(str(case["prompt"]))
            tool_calls.extend(dict(call) for call in case["tool_calls"])
            raw_context = case.get("tool_fixture_context", {})
            if isinstance(raw_context, dict):
                tool_fixture_context.update(raw_context)
        batches.append(
            {
                "prompt": "\n\n".join(prompts),
                "tool_calls": tuple(tool_calls),
                "tool_fixture_context": tool_fixture_context,
            }
        )
    return batches


def _image_uris(rows: list[dict[str, Any]], feature_name: str) -> list[str]:
    uris: list[str] = []
    for row in rows:
        if not feature_name:
            continue
        uri = _image_uri_from_value(row.get(feature_name))
        if uri:
            uris.append(uri)
    return uris


def _image_uri_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        src = str(value.get("src", "")).strip()
        if src:
            return src
        path = str(value.get("path", "")).strip()
        if path:
            return path
    return ""


def _resolve_dataset_name(
    definition: BenchmarkSuiteDefinition,
    fetch_json: HFDatasetFetcher,
) -> str:
    payload = fetch_json("splits", {"dataset": definition.dataset_path})
    for split in payload.get("splits", []):
        if not isinstance(split, dict):
            continue
        if str(split.get("split", "")).strip() == definition.dataset_split:
            return str(split.get("config", "")).strip() or "default"
    return "default"


def _materialized_sample_hint(*, sample_size: int, batch_factor: int) -> int:
    return max(sample_size * batch_factor, 8)


def _write_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        if not rows:
            handle.write("\n")
            return
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def _load_materialized_rows(rows_path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with rows_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
                if limit is not None and len(rows) >= limit:
                    break
    return rows


def _benchmark_suite_cache_key(definition: BenchmarkSuiteDefinition) -> str:
    payload = "|".join(
        [
            definition.task_kind,
            definition.suite_id,
            definition.dataset_path,
            definition.dataset_name,
            definition.dataset_revision,
            definition.dataset_split,
            definition.prompt_feature,
            definition.text_feature,
            definition.image_feature,
            definition.source_image_feature,
            definition.mask_feature,
            definition.default_prompt,
            definition.fixture_package_id,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _benchmark_fixture_package_path(fixture_package_id: str) -> Path:
    normalized = fixture_package_id.strip()
    if not normalized or "/" in normalized or "\\" in normalized:
        raise ModelOperationError(
            code="invalid_benchmark_suite",
            message="Invalid benchmark fixture package id.",
            details={"fixture_package_id": fixture_package_id},
        )
    return _BENCHMARK_FIXTURES_ROOT / normalized


def _benchmark_fixture_dataset_uri(fixture_package_id: str) -> str:
    return f"melix-fixture://benchmark/{fixture_package_id}"


def _hf_dataset_uri(
    *,
    dataset_path: str,
    dataset_name: str,
    dataset_revision: str,
    dataset_split: str,
) -> str:
    query = urlencode(
        {
            "config": dataset_name,
            "split": dataset_split,
            "revision": dataset_revision,
        }
    )
    return f"hf://{dataset_path}?{query}"


def _parse_positive_int(raw_value: str, default: int) -> int:
    normalized = raw_value.strip()
    if not normalized:
        return max(1, default)
    try:
        return max(1, int(normalized))
    except ValueError:
        return max(1, default)


def _string_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _fetch_hf_dataset_server_json(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"{_HF_DATASETS_SERVER_URL}/{endpoint}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "melix-benchmark-suite/1"})
    try:
        with urlopen(request, timeout=20.0) as response:
            payload = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message=f"Hugging Face dataset request failed: {endpoint}",
            details={"endpoint": endpoint, "dataset": params.get("dataset", "")},
        ) from exc
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Hugging Face dataset response was not a JSON object.",
            details={"endpoint": endpoint},
        )
    return parsed
