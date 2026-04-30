from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_dataset import HFDatasetFetcher

_HF_DATASETS_SERVER_URL = "https://datasets-server.huggingface.co"


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


@dataclass(frozen=True)
class BenchmarkCase:
    prompt: str
    image_uris: tuple[str, ...] = ()
    source_image_uri: str = ""
    mask_uri: str = ""


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
    sample_size: int
    batch_factor: int
    prompt_batches: tuple[str, ...]
    cases: tuple[BenchmarkCase, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "suite_id": self.suite_id,
            "task_kind": self.task_kind,
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
        self._definitions = {
            (definition.task_kind, definition.suite_id): definition
            for definition in resolved_definitions
        }
        self._hf_dataset_fetcher = hf_dataset_fetcher or _fetch_hf_dataset_server_json
        self._resolved_suite_cache: dict[
            tuple[str, str, Path, int, int],
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

        sample_size = _parse_positive_int(parameters.get("sample_size", ""), definition.default_sample_size)
        batch_factor = _parse_positive_int(parameters.get("batch_factor", ""), definition.default_batch_factor)
        cache_key = (definition.task_kind, definition.suite_id, jobs_root, sample_size, batch_factor)
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
            ),
            materialized_package_path=materialized["package_path"],
            cache_key=materialized["cache_key"],
            cache_hit=materialized["cache_hit"],
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
            "dataset_name": str(manifest.get("dataset_name", definition.dataset_name or "default")),
            "rows": _load_materialized_rows(rows_path, limit=sample_hint),
        }

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
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _write_jsonl_rows(rows_path, rows)
    return {
        "package_path": package_path,
        "cache_key": cache_key,
        "cache_hit": False,
        "dataset_name": dataset_name,
        "rows": rows,
    }


def _suite_cases(
    definition: BenchmarkSuiteDefinition,
    *,
    rows: list[dict[str, Any]],
    sample_size: int,
    batch_factor: int,
) -> list[BenchmarkCase]:
    if definition.task_kind == "text-generation":
        prompts = _text_prompts(definition, rows)
        return [
            BenchmarkCase(prompt=prompt)
            for prompt in _batched_text_prompts(prompts, sample_size=sample_size, batch_factor=batch_factor)
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
    prompts: list[str] = []
    for row in rows:
        if definition.prompt_feature == "messages":
            messages = row.get("messages")
            if isinstance(messages, list):
                prompt_parts = [
                    str(message.get("content", "")).strip()
                    for message in messages
                    if isinstance(message, dict) and str(message.get("role", "")).strip() != "assistant"
                ]
                prompt = "\n".join(part for part in prompt_parts if part)
                if prompt:
                    prompts.append(prompt)
                    continue
        prompt = _string_value(row.get(definition.prompt_feature)) if definition.prompt_feature else ""
        if prompt:
            prompts.append(prompt)
            continue
        text_value = _string_value(row.get(definition.text_feature)) if definition.text_feature else ""
        if text_value:
            prompts.append(text_value)
            continue
    if prompts:
        return prompts
    if definition.default_prompt:
        return [definition.default_prompt]
    raise ModelOperationError(
        code="invalid_benchmark_suite",
        message="Benchmark suite materialization did not produce any text prompts.",
        details={"suite_id": definition.suite_id, "task_kind": definition.task_kind},
    )


def _batched_text_prompts(
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
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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
