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
