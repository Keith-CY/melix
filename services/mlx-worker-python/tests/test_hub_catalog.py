from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from worker.model_ops.hub_catalog import HubCatalog, HubCatalogError


class FakeHTTPResponse:
    def __init__(self, payload: object):
        self._payload = json.dumps(payload).encode("utf-8")
        self.headers: dict[str, str] = {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_model_card_treats_repo_ids_with_mlx_suffix_as_mlx_compatible() -> None:
    payload = [
        {
            "id": "unsloth/gemma-4-E4B-it-MLX-8bit",
            "author": "unsloth",
            "pipeline_tag": "image-text-to-text",
            "tags": ["gemma4", "image-text-to-text"],
            "siblings": [
                {"rfilename": "config.json"},
                {"rfilename": "model-00001-of-00002.safetensors"},
                {"rfilename": "tokenizer.json"},
            ],
            "cardData": {
                "tags": ["gemma4", "image-text-to-text"],
            },
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener)
    card = catalog.get_model_card(repo_id="unsloth/gemma-4-E4B-it-MLX-8bit")

    assert card.repo_id == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert card.pipeline_tag == "image-text-to-text"
    assert card.mlx_compatible is True


def test_search_models_with_mlx_only_keeps_repo_ids_with_mlx_suffix() -> None:
    payload = [
        {
            "id": "unsloth/gemma-4-E4B-it-MLX-8bit",
            "author": "unsloth",
            "pipeline_tag": "image-text-to-text",
            "tags": ["gemma4"],
            "siblings": [],
            "cardData": {},
        },
        {
            "id": "plain/example-model",
            "author": "plain",
            "pipeline_tag": "text-generation",
            "tags": ["transformers"],
            "siblings": [],
            "cardData": {},
        },
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener)
    page = catalog.search_models(query="gemma", page_size=10, cursor="", mlx_only=True)

    assert [item.repo_id for item in page.items] == ["unsloth/gemma-4-E4B-it-MLX-8bit"]


def test_get_model_card_raises_invalid_argument_for_blank_repo_id() -> None:
    catalog = HubCatalog()

    with pytest.raises(HubCatalogError) as error:
        catalog.get_model_card(repo_id="   ")

    assert error.value.code == "invalid_argument"


def test_get_model_card_raises_not_found_when_model_absent_from_search_results() -> None:
    def opener(_request: Request):
        return FakeHTTPResponse([{"id": "other/model", "tags": [], "siblings": [], "cardData": {}}])

    catalog = HubCatalog(opener=opener)

    with pytest.raises(HubCatalogError) as error:
        catalog.get_model_card(repo_id="exact/target-model")

    assert error.value.code == "not_found"


def test_hub_catalog_raises_rate_limited_on_http_429() -> None:
    def opener(_request: Request):
        raise HTTPError(url="https://huggingface.co/api/models", code=429, msg="Too Many Requests", hdrs={}, fp=None)  # type: ignore[arg-type]

    catalog = HubCatalog(opener=opener)

    with pytest.raises(HubCatalogError) as error:
        catalog.search_models(query="test", page_size=10, cursor="", mlx_only=False)

    assert error.value.code == "hub_rate_limited"
    assert error.value.retriable is False


def test_hub_catalog_raises_retriable_on_http_500() -> None:
    def opener(_request: Request):
        raise HTTPError(url="https://huggingface.co/api/models", code=500, msg="Internal Server Error", hdrs={}, fp=None)  # type: ignore[arg-type]

    catalog = HubCatalog(opener=opener)

    with pytest.raises(HubCatalogError) as error:
        catalog.search_models(query="test", page_size=10, cursor="", mlx_only=False)

    assert error.value.code == "hub_request_failed"
    assert error.value.retriable is True


def test_hub_catalog_raises_hub_unreachable_on_url_error() -> None:
    def opener(_request: Request):
        raise URLError("connection refused")

    catalog = HubCatalog(opener=opener)

    with pytest.raises(HubCatalogError) as error:
        catalog.search_models(query="test", page_size=10, cursor="", mlx_only=False)

    assert error.value.code == "hub_unreachable"
    assert error.value.retriable is True


def test_hub_catalog_raises_hub_payload_invalid_on_non_list_json_response() -> None:
    def opener(_request: Request):
        return FakeHTTPResponse({"error": "unexpected object"})

    catalog = HubCatalog(opener=opener)

    with pytest.raises(HubCatalogError) as error:
        catalog.search_models(query="test", page_size=10, cursor="", mlx_only=False)

    assert error.value.code == "hub_payload_invalid"


def test_hub_catalog_raises_hub_payload_invalid_on_malformed_json() -> None:
    class BrokenResponse:
        headers: dict = {}

        def read(self) -> bytes:
            return b"not { valid } json ]["

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    def opener(_request: Request):
        return BrokenResponse()

    catalog = HubCatalog(opener=opener)

    with pytest.raises(HubCatalogError) as error:
        catalog.search_models(query="test", page_size=10, cursor="", mlx_only=False)

    assert error.value.code == "hub_payload_invalid"


def test_search_models_with_mlx_only_false_returns_all_results() -> None:
    payload = [
        {
            "id": "mlx-community/llama-3.1-8b",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx"],
            "siblings": [],
            "cardData": {},
        },
        {
            # repo_id, tags, and library_name contain no "mlx" substring at all
            "id": "plain/standard-llm",
            "author": "plain",
            "pipeline_tag": "text-generation",
            "tags": ["transformers"],
            "siblings": [],
            "cardData": {},
        },
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener)
    page = catalog.search_models(query="llama", page_size=10, cursor="", mlx_only=False)

    assert len(page.items) == 2
    assert page.items[0].mlx_compatible is True
    assert page.items[1].mlx_compatible is False


def test_search_models_marks_small_mlx_model_as_good_local_fit() -> None:
    payload = [
        {
            "id": "mlx-community/Qwen3.5-4B-OptiQ-4bit",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx", "safetensors", "4-bit", "optiq", "apple-silicon"],
            "library_name": "mlx",
            "usedStorage": 2_811_000_000,
            "siblings": [
                {"rfilename": "config.json", "size": 4096},
                {"rfilename": "model.safetensors", "size": 2_811_000_000},
            ],
            "safetensors": {
                "parameters": {"F32": 10_000, "BF16": 1_000_000},
            },
            "cardData": {
                "base_model": "Qwen/Qwen3.5-4B",
            },
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="qwen", page_size=10, cursor="", mlx_only=True)

    assert len(page.items) == 1
    model = page.items[0]
    assert model.local_fit_status == "good"
    assert model.estimated_artifact_bytes == 2_811_000_000
    assert model.estimated_resident_bytes > model.estimated_artifact_bytes
    assert model.parameter_count == 1_010_000
    assert model.quantization_summary == "4-bit, optiq"
    assert model.gated is False
    assert model.recommended_action == "download"
    assert any("MLX-compatible" in reason for reason in model.local_fit_reasons)


def test_search_models_marks_non_mlx_results_blocked_for_local_run() -> None:
    payload = [
        {
            "id": "plain/standard-llm",
            "author": "plain",
            "pipeline_tag": "text-generation",
            "tags": ["transformers"],
            "library_name": "transformers",
            "siblings": [{"rfilename": "model.safetensors", "size": 2_000_000_000}],
            "cardData": {},
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="llm", page_size=10, cursor="", mlx_only=False)

    model = page.items[0]
    assert model.local_fit_status == "blocked"
    assert model.recommended_action == "unavailable"
    assert model.estimated_artifact_bytes == 2_000_000_000
    assert "No MLX compatibility signal" in model.local_fit_reasons


def test_search_models_marks_missing_size_mlx_model_as_unknown() -> None:
    payload = [
        {
            "id": "mlx-community/missing-size",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx"],
            "library_name": "mlx",
            "siblings": [{"rfilename": "README.md"}],
            "cardData": {},
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="missing", page_size=10, cursor="", mlx_only=True)

    model = page.items[0]
    assert model.local_fit_status == "unknown"
    assert model.recommended_action == "inspect_metadata"
    assert model.estimated_artifact_bytes == 0
    assert "No artifact size metadata" in model.local_fit_reasons


def test_search_models_marks_large_mlx_model_as_heavy_not_blocked() -> None:
    payload = [
        {
            "id": "mlx-community/huge-4bit",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx", "4-bit"],
            "library_name": "mlx",
            "usedStorage": 48 * 1024 * 1024 * 1024,
            "siblings": [{"rfilename": "model.safetensors", "size": 48 * 1024 * 1024 * 1024}],
            "cardData": {},
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="huge", page_size=10, cursor="", mlx_only=True)

    model = page.items[0]
    assert model.local_fit_status == "heavy"
    assert model.recommended_action == "review_risk"
    assert model.estimated_resident_bytes > int(64 * 1024 * 1024 * 1024 * 0.60)
    assert any("memory comfort budget" in reason for reason in model.local_fit_reasons)


def test_get_model_card_includes_local_fit_evidence_from_readme_size_hint() -> None:
    payload = [
        {
            "id": "mlx-community/readme-size",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx", "4bit", "optiq"],
            "library_name": "mlx",
            "siblings": [{"rfilename": "README.md"}],
            "cardData": {
                "model_name": "Readme Size",
                "base_model": "base/model",
                "description": "Model size 570 MB",
            },
            "description": "This MLX model has Model size 570 MB in the card.",
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    card = catalog.get_model_card(repo_id="mlx-community/readme-size")

    assert card.local_fit_status == "good"
    assert card.estimated_artifact_bytes == 570 * 1024 * 1024
    assert card.quantization_summary == "4-bit, optiq"
    assert card.base_models == ["base/model"]
