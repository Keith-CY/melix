from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from worker.model_ops.errors import ModelOperationError
import worker.productization.benchmark_suites as benchmark_suites
from worker.productization.benchmark_suites import (
    BenchmarkSuiteCatalog,
    BenchmarkSuiteDefinition,
    _write_jsonl_rows,
)


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

        if dataset == "huggingface/documentation-images":
            if endpoint == "rows":
                return {
                    "rows": [
                        {"row": {"image": {"src": "https://example.com/doc-image-1.jpg"}}},
                        {"row": {"image": {"src": "https://example.com/doc-image-2.jpg"}}},
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}

        raise AssertionError(f"Unexpected benchmark fetch: endpoint={endpoint} dataset={dataset}")


class _RecordingWriter:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, chunk: str) -> int:
        self.writes.append(chunk)
        return len(chunk)

    def __enter__(self) -> "_RecordingWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


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
    assert first.prompt_batches[0] == "Say hi.\n\nSay bye."
    assert first.metadata()["dataset_uri"].startswith("hf://HuggingFaceH4/ultrachat_200k")
    assert first.metadata()["source_kind"] == "hf_dataset"


def test_benchmark_text_cases_preserve_agentic_tool_fixture_contract() -> None:
    definition = BenchmarkSuiteDefinition(
        task_kind="text-generation",
        suite_id="agentic",
        title="Agentic",
        dataset_path="dataset/agentic",
        dataset_name="default",
        dataset_revision="main",
        dataset_split="train",
        prompt_feature="prompt",
        text_feature="",
        image_feature="",
        source_image_feature="",
        mask_feature="",
        default_prompt="",
        default_sample_size=1,
        default_batch_factor=1,
    )

    cases = benchmark_suites._suite_cases(
        definition,
        rows=[
            {
                "prompt": "Find the receipt total.",
                "tool_calls": [
                    {"id": "call-1", "name": "visit", "arguments": {"url": "fixture://receipt"}}
                ],
                "tool_context": {
                    "pages": {"fixture://receipt": {"text": "Total is 42."}},
                },
            }
        ],
        sample_size=1,
        batch_factor=1,
    )

    assert cases[0].prompt == "Find the receipt total."
    assert cases[0].tool_calls[0]["name"] == "visit"
    assert cases[0].tool_fixture_context["pages"]["fixture://receipt"]["text"] == "Total is 42."


def test_default_catalog_materializes_agentic_fixture_suites_without_remote_fetch(
    tmp_path: Path,
) -> None:
    def fail_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        raise AssertionError(f"agentic fixture suite should not fetch remote data: {endpoint} {params}")

    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=fail_fetcher)
    definitions_by_id = {
        definition.suite_id: definition
        for definition in catalog.list_definitions()
        if definition.task_kind == "text-generation"
    }

    assert definitions_by_id["agentic_image"].title == "Agentic Image Fixture"
    assert definitions_by_id["agentic_search"].title == "Agentic Search Fixture"
    assert definitions_by_id["agentic_visit"].title == "Agentic Visit Fixture"

    image_suite = catalog.resolve_suite(
        "agentic_image",
        jobs_root=tmp_path,
        parameters={"sample_size": "1"},
    )
    search_suite = catalog.resolve_suite(
        "agentic_search",
        jobs_root=tmp_path,
        parameters={"sample_size": "1"},
    )
    visit_suite = catalog.resolve_suite(
        "agentic_visit",
        jobs_root=tmp_path,
        parameters={"sample_size": "1"},
    )

    assert image_suite.source_kind == "melix_benchmark_fixture"
    assert image_suite.metadata()["dataset_uri"] == (
        "melix-fixture://benchmark/agentic-image.dev.v1"
    )
    assert image_suite.metadata()["fixture_package_id"] == "agentic-image.dev.v1"
    assert image_suite.dataset_path == "agentic-image.dev.v1"
    assert image_suite.prompt_batches == (
        "Inspect the storefront image, find the matching visual listing, and answer with the visible brand.",
    )
    assert [call["name"] for call in image_suite.cases[0].tool_calls] == [
        "image_crop",
        "image_search",
    ]
    assert image_suite.cases[0].tool_fixture_context["crops"]["storefront#sign"]["text"] == "MELIX LABS"
    assert image_suite.cases[0].tool_fixture_context["image_corpus"][0]["media_ref"] == "storefront"

    assert search_suite.source_kind == "melix_benchmark_fixture"
    assert search_suite.metadata()["dataset_uri"] == (
        "melix-fixture://benchmark/agentic-search.dev.v1"
    )
    assert search_suite.cases[0].tool_calls[0]["name"] == "text_search"
    assert search_suite.cases[0].tool_fixture_context["text_corpus"][0]["id"] == "doc-melix-runtime"

    assert visit_suite.source_kind == "melix_benchmark_fixture"
    assert visit_suite.metadata()["dataset_uri"] == (
        "melix-fixture://benchmark/agentic-visit.dev.v1"
    )
    assert visit_suite.cases[0].tool_calls[0]["name"] == "visit"
    assert visit_suite.cases[0].tool_fixture_context["pages"]["fixture://melix/runtime"]["title"] == (
        "Melix Runtime Brief"
    )

    manifest = json.loads(
        (image_suite.materialized_package_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_kind"] == "melix_benchmark_fixture"
    assert manifest["fixture_package_id"] == "agentic-image.dev.v1"
    assert manifest["dataset_uri"] == "melix-fixture://benchmark/agentic-image.dev.v1"


def test_benchmark_fixture_materialization_raises_typed_errors_for_invalid_packages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = tmp_path / "fixtures"
    monkeypatch.setattr(benchmark_suites, "_BENCHMARK_FIXTURES_ROOT", fixture_root)

    missing_definition = BenchmarkSuiteDefinition(
        task_kind="text-generation",
        suite_id="missing-fixture",
        title="Missing Fixture",
        dataset_path="missing.dev.v1",
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
        fixture_package_id="missing.dev.v1",
    )
    with pytest.raises(ModelOperationError) as missing_error:
        benchmark_suites._materialize_benchmark_suite(
            missing_definition,
            cache_root=tmp_path / "cache-missing",
            fetch_json=FakeBenchmarkSuiteFetcher(),
            sample_hint=1,
        )
    assert missing_error.value.code == "invalid_benchmark_suite"
    assert missing_error.value.details["fixture_package_id"] == "missing.dev.v1"

    empty_fixture_root = fixture_root / "empty.dev.v1"
    empty_fixture_root.mkdir(parents=True)
    (empty_fixture_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.benchmark_fixture_package.v1",
                "fixture_package_id": "empty.dev.v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (empty_fixture_root / "samples.jsonl").write_text("\n", encoding="utf-8")
    empty_definition = replace(
        missing_definition,
        suite_id="empty-fixture",
        dataset_path="empty.dev.v1",
        fixture_package_id="empty.dev.v1",
    )
    with pytest.raises(ModelOperationError) as empty_error:
        benchmark_suites._materialize_benchmark_suite(
            empty_definition,
            cache_root=tmp_path / "cache-empty",
            fetch_json=FakeBenchmarkSuiteFetcher(),
            sample_hint=1,
        )
    assert empty_error.value.code == "invalid_benchmark_suite"
    assert empty_error.value.details["fixture_package_id"] == "empty.dev.v1"

    invalid_definition = replace(
        missing_definition,
        suite_id="invalid-fixture",
        dataset_path="../bad",
        fixture_package_id="../bad",
    )
    with pytest.raises(ModelOperationError) as invalid_error:
        benchmark_suites._materialize_benchmark_suite(
            invalid_definition,
            cache_root=tmp_path / "cache-invalid",
            fetch_json=FakeBenchmarkSuiteFetcher(),
            sample_hint=1,
        )
    assert invalid_error.value.code == "invalid_benchmark_suite"
    assert invalid_error.value.details == {"fixture_package_id": "../bad"}


def test_load_materialized_rows_streams_without_read_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        "\n".join(
            [
                json.dumps({"prompt": "Say hi."}),
                "",
                json.dumps(["ignored", "list"]),
                json.dumps({"prompt": "Say bye."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == rows_path:
            raise AssertionError("rows loader should stream from disk instead of calling read_text")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    assert benchmark_suites._load_materialized_rows(rows_path) == [
        {"prompt": "Say hi."},
        {"prompt": "Say bye."},
    ]


def test_write_jsonl_rows_streams_one_row_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows_path = tmp_path / "rows.jsonl"
    recorder = _RecordingWriter()

    def fake_open(self: Path, mode: str = "r", encoding: str | None = None):
        assert self == rows_path
        assert mode == "w"
        assert encoding == "utf-8"
        return recorder

    monkeypatch.setattr(Path, "open", fake_open)

    _write_jsonl_rows(rows_path, [{"prompt": "Say hi."}, {"prompt": "Say bye."}])

    assert recorder.writes == [
        '{"prompt": "Say hi."}',
        "\n",
        '{"prompt": "Say bye."}',
        "\n",
    ]


def test_load_materialized_rows_respects_limit(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        "\n".join(
            [
                json.dumps({"prompt": "prompt-1"}),
                json.dumps({"prompt": "prompt-2"}),
                json.dumps({"prompt": "prompt-3"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert benchmark_suites._load_materialized_rows(rows_path, limit=2) == [
        {"prompt": "prompt-1"},
        {"prompt": "prompt-2"},
    ]


def test_benchmark_suite_catalog_reuses_in_memory_resolved_suite_for_identical_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = FakeBenchmarkSuiteFetcher()
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=fetcher)

    first = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "2", "batch_factor": "2"},
    )

    def fail_materialization(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("identical suite resolution should reuse the in-memory result")

    monkeypatch.setattr(benchmark_suites, "_materialize_benchmark_suite", fail_materialization)

    second = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "2", "batch_factor": "2"},
    )

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.prompt_batches == first.prompt_batches
    assert second.cases == first.cases


def test_benchmark_suite_catalog_cache_hit_reads_only_requested_prefix(tmp_path: Path) -> None:
    fetcher = FakeBenchmarkSuiteFetcher()
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=fetcher)

    first = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "2", "batch_factor": "2"},
    )

    assert first.cache_hit is False

    package_path = Path(first.materialized_package_path)
    rows_path = package_path / "rows.jsonl"
    original_rows = rows_path.read_text(encoding="utf-8").rstrip("\n").splitlines()
    extra_rows = [json.dumps({"messages": [{"role": "user", "content": f"extra-{index}"}]}) for index in range(8, 20)]
    rows_path.write_text("\n".join([*original_rows, *extra_rows]) + "\n", encoding="utf-8")

    second = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "1", "batch_factor": "1"},
    )

    assert second.cache_hit is True
    assert second.prompt_batches == ("Say hi.",)
    assert fetcher.calls == [
        (
            "rows",
            {
                "dataset": "HuggingFaceH4/ultrachat_200k",
                "config": "default",
                "split": "train_sft",
                "offset": "0",
                "length": "8",
            },
        )
    ]


def test_benchmark_suite_catalog_raises_typed_error_for_unknown_suite(tmp_path: Path) -> None:
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkSuiteFetcher())

    with pytest.raises(ModelOperationError) as error:
        catalog.resolve_suite("missing-suite", jobs_root=tmp_path, parameters={})

    assert error.value.code == "invalid_benchmark_suite"
    assert error.value.details == {"suite_id": "missing-suite", "task_kind": "text-generation"}


def test_benchmark_suite_catalog_materializes_vlm_suite_with_image_uris(tmp_path: Path) -> None:
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkSuiteFetcher())

    suite = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "2", "batch_factor": "2"},
        task_kind="image-text-to-text",
    )

    assert suite.task_kind == "image-text-to-text"
    assert suite.dataset_path == "huggingface/documentation-images"
    assert suite.cache_hit is False
    assert len(suite.cases) == 2
    assert suite.cases[0].prompt == "Describe the image in one sentence."
    assert len(suite.cases[0].image_uris) == 2
    assert suite.cases[0].image_uris[0] == "https://example.com/doc-image-1.jpg"


def test_benchmark_suite_catalog_materializes_text_to_image_and_image_edit_suites(tmp_path: Path) -> None:
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkSuiteFetcher())

    generation_suite = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "2"},
        task_kind="text-to-image",
    )
    edit_suite = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path,
        parameters={"sample_size": "2"},
        task_kind="image-text-to-image",
    )

    assert generation_suite.task_kind == "text-to-image"
    assert [case.prompt for case in generation_suite.cases] == [
        "List two colors.",
        "List two animals.",
    ]
    assert edit_suite.task_kind == "image-text-to-image"
    assert edit_suite.cases[0].prompt == "Edit the image to look like a watercolor painting."
    assert edit_suite.cases[0].source_image_uri == "https://example.com/doc-image-1.jpg"


def test_benchmark_suite_catalog_raises_typed_errors_for_empty_materialization_and_missing_images(
    tmp_path: Path,
) -> None:
    class EmptyRowsFetcher:
        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            if endpoint == "rows":
                return {"rows": []}
            return {"splits": [{"dataset": params.get("dataset", ""), "config": "default", "split": "train"}]}

    class MissingImageFetcher:
        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            if endpoint == "rows":
                return {"rows": [{"row": {"instruction": "No image here."}}]}
            return {"splits": [{"dataset": params.get("dataset", ""), "config": "default", "split": "train"}]}

    with pytest.raises(ModelOperationError) as empty_rows_error:
        BenchmarkSuiteCatalog(hf_dataset_fetcher=EmptyRowsFetcher()).resolve_suite(
            "smoke",
            jobs_root=tmp_path,
            parameters={},
        )
    assert empty_rows_error.value.code == "hf_dataset_fetch_failed"

    with pytest.raises(ModelOperationError) as missing_generation_images:
        BenchmarkSuiteCatalog(hf_dataset_fetcher=MissingImageFetcher()).resolve_suite(
            "smoke",
            jobs_root=tmp_path,
            parameters={},
            task_kind="image-text-to-text",
        )
    assert missing_generation_images.value.code == "invalid_benchmark_suite"

    with pytest.raises(ModelOperationError) as missing_edit_images:
        BenchmarkSuiteCatalog(hf_dataset_fetcher=MissingImageFetcher()).resolve_suite(
            "smoke",
            jobs_root=tmp_path,
            parameters={},
            task_kind="image-text-to-image",
        )
    assert missing_edit_images.value.code == "invalid_benchmark_suite"


def test_text_prompt_and_image_uri_helpers_cover_messages_defaults_and_path_shapes() -> None:
    messages_definition = BenchmarkSuiteDefinition(
        task_kind="text-generation",
        suite_id="messages",
        title="Messages",
        dataset_path="dataset/messages",
        dataset_name="default",
        dataset_revision="main",
        dataset_split="train",
        prompt_feature="messages",
        text_feature="",
        image_feature="",
        source_image_feature="",
        mask_feature="",
        default_prompt="",
        default_sample_size=1,
        default_batch_factor=1,
    )
    text_definition = BenchmarkSuiteDefinition(
        task_kind="text-generation",
        suite_id="text-only",
        title="Text",
        dataset_path="dataset/text",
        dataset_name="default",
        dataset_revision="main",
        dataset_split="train",
        prompt_feature="",
        text_feature="text",
        image_feature="",
        source_image_feature="",
        mask_feature="",
        default_prompt="fallback prompt",
        default_sample_size=1,
        default_batch_factor=1,
    )

    prompts = benchmark_suites._text_prompts(
        messages_definition,
        [
            {
                "messages": [
                    {"role": "system", "content": "Stay brief."},
                    {"role": "user", "content": "Explain colors."},
                    {"role": "assistant", "content": "Red and blue."},
                ]
            }
        ],
    )
    assert prompts == ["Stay brief.\nExplain colors."]
    assert benchmark_suites._text_prompts(text_definition, [{"text": "plain prompt"}]) == ["plain prompt"]
    assert benchmark_suites._text_prompts(text_definition, [{}]) == ["fallback prompt"]

    with pytest.raises(ModelOperationError) as missing_prompt_error:
        benchmark_suites._text_prompts(
            BenchmarkSuiteDefinition(
                task_kind="text-generation",
                suite_id="empty",
                title="Empty",
                dataset_path="dataset/empty",
                dataset_name="default",
                dataset_revision="main",
                dataset_split="train",
                prompt_feature="",
                text_feature="",
                image_feature="",
                source_image_feature="",
                mask_feature="",
                default_prompt="",
                default_sample_size=1,
                default_batch_factor=1,
            ),
            [{}],
        )
    assert missing_prompt_error.value.code == "invalid_benchmark_suite"

    assert benchmark_suites._image_uri_from_value(" https://example.com/image.png ") == "https://example.com/image.png"
    assert benchmark_suites._image_uri_from_value({"src": "https://example.com/src.jpg"}) == "https://example.com/src.jpg"
    assert benchmark_suites._image_uri_from_value({"path": "/tmp/local-image.png"}) == "/tmp/local-image.png"
    assert benchmark_suites._image_uris([{"image": {"path": "/tmp/local-image.png"}}], "image") == ["/tmp/local-image.png"]
    assert benchmark_suites._image_uris([{"image": "ignored"}], "") == []


def test_benchmark_suite_dataset_helpers_cover_split_resolution_and_http_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = BenchmarkSuiteDefinition(
        task_kind="text-generation",
        suite_id="smoke",
        title="Smoke",
        dataset_path="demo/dataset",
        dataset_name="",
        dataset_revision="main",
        dataset_split="validation",
        prompt_feature="prompt",
        text_feature="",
        image_feature="",
        source_image_feature="",
        mask_feature="",
        default_prompt="",
        default_sample_size=1,
        default_batch_factor=1,
    )

    resolved_name = benchmark_suites._resolve_dataset_name(
        definition,
        lambda endpoint, params: {
            "splits": [
                {"split": "train", "config": "train-default"},
                {"split": "validation", "config": "validation-default"},
            ]
        },
    )
    assert resolved_name == "validation-default"

    class FakeResponse:
        def __init__(self, payload: str) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return self.payload.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(
        benchmark_suites,
        "urlopen",
        lambda request, timeout=20.0: FakeResponse('["not-a-dict"]'),
    )
    with pytest.raises(ModelOperationError) as invalid_json_error:
        benchmark_suites._fetch_hf_dataset_server_json("rows", {"dataset": "demo/dataset"})
    assert invalid_json_error.value.code == "hf_dataset_fetch_failed"

    def raise_os_error(request, timeout=20.0):
        raise OSError("network down")

    monkeypatch.setattr(benchmark_suites, "urlopen", raise_os_error)
    with pytest.raises(ModelOperationError) as fetch_error:
        benchmark_suites._fetch_hf_dataset_server_json("rows", {"dataset": "demo/dataset"})
    assert fetch_error.value.code == "hf_dataset_fetch_failed"


def _make_definition(task_kind: str) -> BenchmarkSuiteDefinition:
    return BenchmarkSuiteDefinition(
        task_kind=task_kind,
        suite_id="smoke",
        title="Smoke",
        dataset_path="demo/dataset",
        dataset_name="default",
        dataset_revision="main",
        dataset_split="train",
        prompt_feature="instruction",
        text_feature="",
        image_feature="image",
        source_image_feature="image",
        mask_feature="",
        default_prompt="Describe this.",
        default_sample_size=1,
        default_batch_factor=1,
    )


def test_suite_cases_raises_for_unknown_task_kind() -> None:
    definition = _make_definition("audio-to-text")
    rows = [{"instruction": "Transcribe the audio."}]

    with pytest.raises(ModelOperationError) as error:
        benchmark_suites._suite_cases(definition, rows=rows, sample_size=1, batch_factor=1)

    assert error.value.code == "invalid_benchmark_suite"


def test_suite_cases_raises_when_image_to_text_rows_have_no_image_uris() -> None:
    definition = _make_definition("image-to-text")
    rows = [{"instruction": "no image here"}]

    with pytest.raises(ModelOperationError) as error:
        benchmark_suites._suite_cases(definition, rows=rows, sample_size=1, batch_factor=1)

    assert error.value.code == "invalid_benchmark_suite"


def test_suite_cases_raises_when_image_text_to_image_rows_have_no_source_uris() -> None:
    definition = _make_definition("image-text-to-image")
    rows = [{"instruction": "no source image here"}]

    with pytest.raises(ModelOperationError) as error:
        benchmark_suites._suite_cases(definition, rows=rows, sample_size=1, batch_factor=1)

    assert error.value.code == "invalid_benchmark_suite"


def test_parse_positive_int_clamps_to_one_for_zero_and_negative_values() -> None:
    assert benchmark_suites._parse_positive_int("0", 5) == 1
    assert benchmark_suites._parse_positive_int("-3", 5) == 1
    assert benchmark_suites._parse_positive_int("-1", 2) == 1


def test_parse_positive_int_returns_default_for_non_numeric_and_empty_input() -> None:
    assert benchmark_suites._parse_positive_int("abc", 7) == 7
    assert benchmark_suites._parse_positive_int("", 3) == 3
    assert benchmark_suites._parse_positive_int("  ", 4) == 4


def test_benchmark_dataset_ref_parser_supports_explicit_revision() -> None:
    assert benchmark_suites._parse_dataset_ref("org/bench@feature-branch") == ("org/bench", "feature-branch")
    with pytest.raises(ModelOperationError) as error:
        benchmark_suites._parse_dataset_ref("org@bench@main")
    assert error.value.code == "invalid_argument"


def test_benchmark_suite_catalog_raises_for_unknown_task_kind(tmp_path: Path) -> None:
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkSuiteFetcher())

    with pytest.raises(ModelOperationError) as error:
        catalog.resolve_suite(
            "smoke",
            jobs_root=tmp_path,
            parameters={},
            task_kind="audio-to-text",
        )

    assert error.value.code == "invalid_benchmark_suite"
    assert error.value.details == {"suite_id": "smoke", "task_kind": "audio-to-text"}


def test_benchmark_suite_dataset_ref_prefers_local_cache_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    cache_repo = home / ".cache" / "huggingface" / "hub" / "datasets--org--bench"
    snapshot = cache_repo / "snapshots" / "abc123"
    data_dir = snapshot / "data"
    data_dir.mkdir(parents=True)
    (cache_repo / "refs").mkdir()
    (cache_repo / "refs" / "main").write_text("abc123", encoding="utf-8")
    (data_dir / "train-00000-of-00001.jsonl").write_text(
        '{"instruction":"Use the local cache."}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))

    def fail_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        raise AssertionError(f"unexpected remote fetch {endpoint} {params}")

    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=fail_fetcher)
    suite = catalog.resolve_suite(
        "latency",
        jobs_root=tmp_path / "jobs",
        parameters={
            "dataset_ref": "org/bench",
            "prompt_feature": "instruction",
            "sample_size": "1",
        },
        task_kind="text-generation",
    )
    manifest = json.loads((suite.materialized_package_path / "manifest.json").read_text(encoding="utf-8"))

    assert suite.dataset_path == "org/bench"
    assert suite.dataset_revision == "main"
    assert suite.prompt_batches == ("Use the local cache.",)
    assert suite.cache_hit is False
    assert suite.metadata()["source_kind"] == "hf_cache_snapshot"
    assert suite.metadata()["hf_snapshot_id"] == "abc123"
    assert suite.metadata()["hf_snapshot_path"] == str(snapshot.resolve())
    assert manifest["source_kind"] == "hf_cache_snapshot"
    assert manifest["hf_snapshot_id"] == "abc123"
    assert manifest["hf_snapshot_path"] == str(snapshot.resolve())


def test_benchmark_suite_dataset_ref_falls_back_when_local_split_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    cache_repo = home / ".cache" / "huggingface" / "hub" / "datasets--org--bench"
    snapshot = cache_repo / "snapshots" / "abc123"
    data_dir = snapshot / "data"
    data_dir.mkdir(parents=True)
    (cache_repo / "refs").mkdir()
    (cache_repo / "refs" / "main").write_text("abc123", encoding="utf-8")
    (data_dir / "test-00000-of-00001.jsonl").write_text(
        '{"instruction":"Wrong split."}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    calls: list[tuple[str, dict[str, str]]] = []

    def fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        calls.append((endpoint, dict(params)))
        assert endpoint == "rows"
        return {"rows": [{"row": {"instruction": "Use the remote fallback."}}]}

    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=fetcher)
    suite = catalog.resolve_suite(
        "latency",
        jobs_root=tmp_path / "jobs",
        parameters={
            "dataset_ref": "org/bench",
            "prompt_feature": "instruction",
            "sample_size": "1",
        },
        task_kind="text-generation",
    )
    manifest = json.loads((suite.materialized_package_path / "manifest.json").read_text(encoding="utf-8"))

    assert calls == [
        (
            "rows",
            {
                "dataset": "org/bench",
                "config": "default",
                "split": "train",
                "offset": "0",
                "length": "8",
            },
        )
    ]
    assert suite.prompt_batches == ("Use the remote fallback.",)
    assert suite.metadata()["source_kind"] == "hf_dataset"
    assert "hf_snapshot_id" not in suite.metadata()
    assert manifest["source_kind"] == "hf_dataset"
    assert "hf_snapshot_id" not in manifest
