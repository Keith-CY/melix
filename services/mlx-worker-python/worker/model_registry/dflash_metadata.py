from __future__ import annotations

from collections.abc import Mapping

DRAFT_RUNTIME_KIND_KEY = "melix.draft.runtime_kind"
DRAFT_ARCHITECTURE_KEY = "melix.draft.architecture"
DFLASH_BLOCK_SIZE_KEY = "melix.dflash.block_size"
DFLASH_TARGET_LAYER_IDS_KEY = "melix.dflash.target_layer_ids"


def dflash_draft_metadata(config_payload: Mapping[str, object] | None) -> dict[str, str]:
    if config_payload is None or not is_dflash_draft_config(config_payload):
        return {}

    metadata = {
        DRAFT_RUNTIME_KIND_KEY: "dflash",
        DRAFT_ARCHITECTURE_KEY: "DFlashDraftModel",
    }

    block_size = config_payload.get("block_size")
    if isinstance(block_size, int) and block_size > 0:
        metadata[DFLASH_BLOCK_SIZE_KEY] = str(block_size)

    dflash_config = config_payload.get("dflash_config")
    if isinstance(dflash_config, Mapping):
        target_layer_ids = dflash_config.get("target_layer_ids")
        if isinstance(target_layer_ids, list):
            normalized_ids = [str(item) for item in target_layer_ids if isinstance(item, int)]
            if normalized_ids:
                metadata[DFLASH_TARGET_LAYER_IDS_KEY] = ",".join(normalized_ids)

    return metadata


def is_dflash_draft_config(config_payload: Mapping[str, object] | None) -> bool:
    if config_payload is None:
        return False
    architectures = config_payload.get("architectures")
    if isinstance(architectures, list):
        if any(_normalized(item) == "dflashdraftmodel" for item in architectures):
            return True

    auto_map = config_payload.get("auto_map")
    if isinstance(auto_map, Mapping):
        if any("dflashdraftmodel" in _normalized(value) for value in auto_map.values()):
            return True

    return isinstance(config_payload.get("dflash_config"), Mapping)


def _normalized(value: object) -> str:
    return str(value or "").strip().lower()
