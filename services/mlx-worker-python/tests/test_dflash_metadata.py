from __future__ import annotations

from worker.model_registry.dflash_metadata import (
    DFLASH_BLOCK_SIZE_KEY,
    DFLASH_TARGET_LAYER_IDS_KEY,
    DRAFT_ARCHITECTURE_KEY,
    DRAFT_RUNTIME_KIND_KEY,
    dflash_draft_metadata,
    is_dflash_draft_config,
)


def test_dflash_draft_metadata_uses_mapping_without_copying() -> None:
    payload = {
        "architectures": ["DFlashDraftModel"],
        "block_size": 8,
        "dflash_config": {"target_layer_ids": [1, "skip", 3]},
    }

    assert dflash_draft_metadata(payload) == {
        DRAFT_RUNTIME_KIND_KEY: "dflash",
        DRAFT_ARCHITECTURE_KEY: "DFlashDraftModel",
        DFLASH_BLOCK_SIZE_KEY: "8",
        DFLASH_TARGET_LAYER_IDS_KEY: "1,3",
    }


def test_is_dflash_draft_config_detects_auto_map_and_nested_config() -> None:
    assert is_dflash_draft_config({"auto_map": {"AutoModel": "pkg.DFlashDraftModel"}}) is True
    assert is_dflash_draft_config({"dflash_config": {"target_layer_ids": []}}) is True


def test_dflash_draft_metadata_ignores_empty_and_non_dflash_configs() -> None:
    assert is_dflash_draft_config(None) is False
    assert dflash_draft_metadata(None) == {}
    assert dflash_draft_metadata({"architectures": ["OtherModel"]}) == {}
