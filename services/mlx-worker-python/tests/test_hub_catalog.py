from __future__ import annotations

import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

import worker.model_ops.hub_catalog as hub_catalog_module
from worker.model_ops.hub_catalog import (
    HubCatalog,
    HubCatalogError,
    _is_mlx_compatible,
    _local_fit_evidence,
    _size_hint_from_text,
)


KB = 1024
MB = 1024 ** 2
GB = 1024 ** 3


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


def test_search_models_with_mlx_only_prefilters_payloads_before_local_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {
            "id": "plain/standard-model",
            "author": "plain",
            "pipeline_tag": "text-generation",
            "tags": ["transformers"],
            "siblings": [{"rfilename": "model.safetensors"}],
            "cardData": {},
        },
        {
            "id": "tagged/model",
            "author": "tagged",
            "pipeline_tag": "text-generation",
            "tags": ["MLX", "text-generation"],
            "siblings": [{"rfilename": "model.safetensors"}],
            "cardData": {},
        },
        {
            "id": "library/model",
            "author": "library",
            "pipeline_tag": "text-generation",
            "tags": ["transformers"],
            "library_name": "mlx",
            "siblings": [{"rfilename": "model.safetensors"}],
            "cardData": {},
        },
        {
            "id": "card/model",
            "author": "card",
            "pipeline_tag": "text-generation",
            "tags": ["transformers"],
            "siblings": [{"rfilename": "model.safetensors"}],
            "cardData": {"tags": ["mlx"]},
        },
        {
            "id": "owner/repo-mlx-suffix",
            "author": "owner",
            "pipeline_tag": "text-generation",
            "tags": ["transformers"],
            "siblings": [{"rfilename": "model.safetensors"}],
            "cardData": {},
        },
    ]
    local_fit_repo_ids: list[str] = []
    original_local_fit = hub_catalog_module._local_fit_evidence

    def counting_local_fit(**kwargs):
        local_fit_repo_ids.append(kwargs["repo_id"])
        return original_local_fit(**kwargs)

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    monkeypatch.setattr(hub_catalog_module, "_local_fit_evidence", counting_local_fit)

    catalog = HubCatalog(opener=opener)
    page = catalog.search_models(query="model", page_size=10, cursor="", mlx_only=True)

    assert [item.repo_id for item in page.items] == [
        "tagged/model",
        "library/model",
        "card/model",
        "owner/repo-mlx-suffix",
    ]
    assert local_fit_repo_ids == [
        "tagged/model",
        "library/model",
        "card/model",
        "owner/repo-mlx-suffix",
    ]


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


def test_is_mlx_compatible_preserves_card_data_tag_signal_after_fast_paths() -> None:
    assert _is_mlx_compatible(
        repo_id="plain/card-tagged-model",
        tags=["transformers"],
        library_name="transformers",
        card_data={"tags": ["MLX"]},
        lowered_tags={"transformers"},
    ) is True


def test_is_mlx_compatible_skips_empty_card_tag_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    string_list = Mock(side_effect=AssertionError("empty cardData.tags should not be normalized"))
    monkeypatch.setattr(hub_catalog_module, "_string_list", string_list)

    assert _is_mlx_compatible(
        repo_id="plain/standard-model",
        tags=["transformers"],
        library_name="transformers",
        card_data={},
        lowered_tags={"transformers"},
    ) is False
    string_list.assert_not_called()


def test_is_mlx_compatible_keeps_library_name_fast_path() -> None:
    assert _is_mlx_compatible(
        repo_id="plain/library-tagged-model",
        tags=["transformers"],
        library_name="MLX",
        card_data={"tags": []},
        lowered_tags={"transformers"},
    ) is True


def test_next_cursor_from_link_extracts_encoded_next_cursor_without_full_query_parse() -> None:
    assert not hasattr(hub_catalog_module, "urlparse")
    assert not hasattr(hub_catalog_module, "parse_qs")
    link_header = (
        '<https://huggingface.co/api/models?cursor=ignored>; rel="prev", '
        '<https://huggingface.co/api/models?limit=10&cursor=abc%2Fdef+ghi&full=true#page>; rel="next"'
    )

    assert hub_catalog_module._next_cursor_from_link(link_header) == "abc/def ghi"


def test_next_cursor_from_link_scans_segments_without_splitting_on_url_commas() -> None:
    link_header = (
        '<https://huggingface.co/api/models?cursor=prev>; rel="prev", '
        '<https://huggingface.co/api/models?note=a,b&cursor=page%2C2&full=true>; rel="next"'
    )

    assert hub_catalog_module._next_cursor_from_link(link_header) == "page,2"


def test_next_cursor_from_link_accepts_cursor_at_query_start() -> None:
    link_header = '<https://huggingface.co/api/models?cursor=page%2Fstart&limit=10>; rel="next"'

    assert hub_catalog_module._next_cursor_from_link(link_header) == "page/start"


def test_next_cursor_from_link_returns_empty_for_missing_or_malformed_next_cursor() -> None:
    assert hub_catalog_module._next_cursor_from_link('<https://huggingface.co/api/models?cursor=prev>; rel="prev"') == ""
    assert hub_catalog_module._next_cursor_from_link('<https://huggingface.co/api/models>; rel="next"') == ""
    assert hub_catalog_module._next_cursor_from_link('<https://huggingface.co/api/models?limit=10>; rel="next"') == ""
    assert hub_catalog_module._next_cursor_from_link('<https://huggingface.co/api/models?cursor>; rel="next"') == ""
    assert hub_catalog_module._next_cursor_from_link('https://huggingface.co/api/models?cursor=broken; rel="next"') == ""


def test_next_cursor_from_link_requires_cursor_parameter_boundary() -> None:
    link_header = (
        '<https://huggingface.co/api/models?cursor=prev>; rel="prev", '
        '<https://huggingface.co/api/models?limit=10&notcursor=wrong&mycursor=bad>; rel="next"'
    )

    assert hub_catalog_module._next_cursor_from_link(link_header) == ""


def test_search_models_uses_next_cursor_from_link_header() -> None:
    response = FakeHTTPResponse([{"id": "mlx-community/example", "tags": ["mlx"], "siblings": [], "cardData": {}}])
    response.headers["Link"] = '<https://huggingface.co/api/models?limit=1&cursor=page%2B2>; rel="next"'

    def opener(_request: Request):
        return response

    catalog = HubCatalog(opener=opener)
    page = catalog.search_models(query="mlx", page_size=1, cursor="", mlx_only=False)

    assert page.next_cursor == "page+2"


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


def test_size_hint_from_empty_text_skips_regex_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hub_catalog_module, "_BARE_SIZE_HINT_RE", object())
    monkeypatch.setattr(hub_catalog_module, "_EXPLICIT_SIZE_HINT_RE", object())

    assert _size_hint_from_text("", allow_bare=True) == 0
    assert _size_hint_from_text("", allow_bare=False) == 0


def test_size_hint_bytes_skips_direct_hint_parser_when_card_model_size_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bool]] = []

    def tracked(text: str, *, allow_bare: bool) -> int:
        calls.append((text, allow_bare))
        return 0

    monkeypatch.setattr(hub_catalog_module, "_size_hint_from_text", tracked)

    assert hub_catalog_module._size_hint_bytes({"cardData": {}}) == 0
    assert calls == []

    assert hub_catalog_module._size_hint_bytes({"cardData": {}, "readme": "Model size: 7 MB"}) == 0
    assert calls == [("Model size: 7 MB", False)]


def test_search_models_ignores_sibling_sizes_without_weight_or_config_filenames() -> None:
    payload = [
        {
            "id": "mlx-community/malformed-siblings",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx"],
            "library_name": "mlx",
            "siblings": [
                {"size": 9 * 1024 * 1024 * 1024},
                {"rfilename": "", "size": 7 * 1024 * 1024 * 1024},
                {"rfilename": "README.md", "size": 3 * 1024 * 1024 * 1024},
                {"rfilename": "model.safetensors", "size": 1024 * 1024 * 1024},
            ],
            "cardData": {},
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="malformed", page_size=10, cursor="", mlx_only=True)

    model = page.items[0]
    assert model.estimated_artifact_bytes == 1024 * 1024 * 1024
    assert model.local_fit_status == "good"


def test_search_models_counts_fp32_parameters_as_four_bytes_for_local_fit() -> None:
    payload = [
        {
            "id": "mlx-community/fp32-large",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx", "fp32"],
            "library_name": "mlx",
            "siblings": [{"rfilename": "config.json"}],
            "safetensors": {"total": 10_000_000_000},
            "cardData": {},
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="fp32", page_size=10, cursor="", mlx_only=True)

    model = page.items[0]
    assert model.local_fit_status == "heavy"
    assert model.estimated_resident_bytes > int(64 * 1024 * 1024 * 1024 * 0.60)


def test_tag_lowering_fallbacks_preserve_direct_helper_compatibility() -> None:
    assert _is_mlx_compatible(
        repo_id="plain/model",
        tags=["MLX"],
        library_name="transformers",
        card_data={},
    ) is True

    evidence = _local_fit_evidence(
        payload={
            "safetensors": {"total": 2_000_000_000},
            "siblings": [{"rfilename": "config.json"}],
        },
        repo_id="mlx-community/direct-helper",
        pipeline_tag="text-generation",
        tags=["MLX", "4-bit"],
        mlx_compatible=True,
        local_memory_gb=64.0,
    )

    assert evidence["quantization_summary"] == "4-bit"
    assert evidence["estimated_resident_bytes"] == int(
        2_000_000_000 * 0.5 * hub_catalog_module.RESIDENT_MEMORY_OVERHEAD_FACTOR
    )


def test_search_models_treats_gated_auto_as_soft_access_not_blocked() -> None:
    payload = [
        {
            "id": "mlx-community/auto-gated",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx", "4-bit"],
            "library_name": "mlx",
            "gated": "auto",
            "siblings": [{"rfilename": "model.safetensors", "size": 1024 * 1024 * 1024}],
            "cardData": {},
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="auto-gated", page_size=10, cursor="", mlx_only=True)

    model = page.items[0]
    assert model.gated is False
    assert model.local_fit_status == "good"
    assert model.recommended_action == "download"


def test_size_hint_bytes_normalizes_each_payload_text_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    original = hub_catalog_module._string

    def tracked(value: object) -> str:
        calls.append(value)
        return original(value)

    monkeypatch.setattr(hub_catalog_module, "_string", tracked)

    assert (
        hub_catalog_module._size_hint_bytes(
            {
                "description": "Model",
                "readme": "size: 512 MB",
                "cardData": {"description": "extra notes"},
            }
        )
        == 512 * MB
    )
    assert calls == [None, "Model", "size: 512 MB", "extra notes"]


def test_search_models_ignores_non_model_size_hints_in_readme_text() -> None:
    payload = [
        {
            "id": "mlx-community/context-size-only",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx"],
            "library_name": "mlx",
            "siblings": [{"rfilename": "README.md"}],
            "description": "Recommended batch size: 4 GB. Context size: 128 KB.",
            "cardData": {},
        }
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="context-size", page_size=10, cursor="", mlx_only=True)

    model = page.items[0]
    assert model.estimated_artifact_bytes == 0
    assert model.local_fit_status == "unknown"


def test_search_models_marks_gated_true_and_unsupported_pipeline_as_blocked() -> None:
    payload = [
        {
            "id": "mlx-community/hard-gated",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["mlx"],
            "library_name": "mlx",
            "gated": True,
            "siblings": [{"rfilename": "model.safetensors", "size": 1024 * 1024 * 1024}],
            "cardData": {},
        },
        {
            "id": "mlx-community/audio-only",
            "author": "mlx-community",
            "pipeline_tag": "automatic-speech-recognition",
            "tags": ["mlx"],
            "library_name": "mlx",
            "siblings": [{"rfilename": "model.safetensors", "size": 1024 * 1024 * 1024}],
            "cardData": {},
        },
    ]

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="blocked", page_size=10, cursor="", mlx_only=True)

    hard_gated, unsupported = page.items
    assert hard_gated.local_fit_status == "blocked"
    assert hard_gated.recommended_action == "request_access"
    assert hard_gated.gated is True
    assert unsupported.local_fit_status == "blocked"
    assert unsupported.recommended_action == "unavailable"
    assert any("Unsupported Melix pipeline tag" in reason for reason in unsupported.local_fit_reasons)


def test_summary_record_reuses_lowered_tags_for_local_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {
            "id": "mlx-community/reused-tags",
            "author": "mlx-community",
            "pipeline_tag": "text-generation",
            "tags": ["MLX", "4-BIT", "OptiQ"],
            "library_name": "mlx",
            "siblings": [{"rfilename": "config.json"}],
            "safetensors": {"total": 2_000_000_000},
            "cardData": {},
        }
    ]
    calls = 0
    original_lowered_tag_set = hub_catalog_module._lowered_tag_set

    def counting_lowered_tag_set(tags: list[str]) -> set[str]:
        nonlocal calls
        calls += 1
        return original_lowered_tag_set(tags)

    monkeypatch.setattr(hub_catalog_module, "_lowered_tag_set", counting_lowered_tag_set)

    def opener(_request: Request):
        return FakeHTTPResponse(payload)

    catalog = HubCatalog(opener=opener, local_memory_gb=64.0)
    page = catalog.search_models(query="reused-tags", page_size=10, cursor="", mlx_only=True)

    model = page.items[0]
    assert model.quantization_summary == "4-bit, optiq"
    assert model.estimated_resident_bytes == int(
        2_000_000_000 * 0.5 * hub_catalog_module.RESIDENT_MEMORY_OVERHEAD_FACTOR
    )
    assert calls == 1


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
    assert card.estimated_artifact_bytes == 570 * MB
    assert card.quantization_summary == "4-bit, optiq"
    assert card.base_models == ["base/model"]


def test_size_hint_parser_uses_precompiled_patterns(monkeypatch: pytest.MonkeyPatch) -> None:
    def dynamic_search_forbidden(*_args, **_kwargs):
        raise AssertionError("size hint parsing should use precompiled pattern.search")

    monkeypatch.setattr(hub_catalog_module.re, "search", dynamic_search_forbidden)

    assert hub_catalog_module._size_hint_from_text("2.5 GB", allow_bare=True) == int(2.5 * GB)
    assert hub_catalog_module._size_hint_from_text("Model size: 768 MB", allow_bare=False) == 768 * MB
    assert hub_catalog_module._size_hint_from_text("Readme says 768 MB", allow_bare=False) == 0
    assert hub_catalog_module._size_hint_from_text("MODEL SIZE | 512 kb", allow_bare=False) == 512 * KB


def test_size_hint_parser_preserves_all_unit_multipliers() -> None:
    assert hub_catalog_module._size_hint_from_text("Model size: 1 KB", allow_bare=False) == KB
    assert hub_catalog_module._size_hint_from_text("Model size: 1.5 MB", allow_bare=False) == int(1.5 * MB)
    assert hub_catalog_module._size_hint_from_text("Model size: 2 GB", allow_bare=False) == 2 * GB
