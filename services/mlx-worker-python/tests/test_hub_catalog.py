from __future__ import annotations

import json
from urllib.request import Request

from worker.model_ops.hub_catalog import HubCatalog


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
