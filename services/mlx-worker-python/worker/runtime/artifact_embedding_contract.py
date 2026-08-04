from __future__ import annotations

from collections.abc import Mapping


_SENTENCE_TRANSFORMER_POOLING_MODES = {
    "pooling_mode_cls_token": "cls",
    "pooling_mode_mean_tokens": "mean",
    "pooling_mode_lasttoken": "last_token",
}
_EMBEDDING_MEDIA_COMPONENT_KEYS = (
    "vision_config",
    "visual_config",
    "audio_config",
    "speech_config",
    "video_config",
    "image_config",
    "projector_config",
    "multi_modal_projector",
    "multimodal_projector",
    "mm_projector",
)
_EMBEDDING_ENCODER_POSITIVE_INT_KEYS = (
    "hidden_size",
    "num_attention_heads",
    "intermediate_size",
    "vocab_size",
    "max_position_embeddings",
)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalized_embedding_hidden_activation(config: Mapping[str, object]) -> str:
    return str(config.get("hidden_act", "gelu") or "gelu").strip().lower()


def unsupported_embedding_encoder_config(
    config: Mapping[str, object],
) -> tuple[str, ...]:
    unsupported = []
    if config.get("is_decoder") is True:
        unsupported.append("is_decoder")
    if config.get("is_encoder_decoder") is True:
        unsupported.append("is_encoder_decoder")
    if config.get("add_cross_attention") is True:
        unsupported.append("add_cross_attention")
    if config.get("cross_attention_hidden_size") is not None:
        unsupported.append("cross_attention_hidden_size")
    position_embedding_type = str(
        config.get("position_embedding_type", "absolute") or "absolute"
    ).strip().lower()
    if position_embedding_type != "absolute":
        unsupported.append(f"position_embedding_type={position_embedding_type}")
    parsed_positive_ints = {
        key: _positive_int(config.get(key))
        for key in _EMBEDDING_ENCODER_POSITIVE_INT_KEYS
    }
    unsupported.extend(
        key for key, value in parsed_positive_ints.items() if value is None
    )
    hidden_size = parsed_positive_ints["hidden_size"]
    attention_heads = parsed_positive_ints["num_attention_heads"]
    if (
        hidden_size is not None
        and attention_heads is not None
        and hidden_size % attention_heads != 0
    ):
        unsupported.append("hidden_size_not_divisible_by_num_attention_heads")
    hidden_act = normalized_embedding_hidden_activation(config)
    if hidden_act not in {"gelu", "gelu_new"}:
        unsupported.append(f"hidden_act={hidden_act}")
    return tuple(unsupported)


def unsupported_embedding_media_components(
    config: Mapping[str, object],
) -> tuple[str, ...]:
    return tuple(
        key for key in _EMBEDDING_MEDIA_COMPONENT_KEYS if config.get(key) is not None
    )


def supported_sentence_transformer_pooling_mode(
    config: Mapping[str, object],
) -> str | None:
    enabled_supported_modes = [
        mode
        for key, mode in _SENTENCE_TRANSFORMER_POOLING_MODES.items()
        if config.get(key) is True
    ]
    has_unsupported_mode = any(
        isinstance(key, str)
        and key.startswith("pooling_mode_")
        and value is True
        and key not in _SENTENCE_TRANSFORMER_POOLING_MODES
        for key, value in config.items()
    )
    if has_unsupported_mode or len(enabled_supported_modes) != 1:
        return None
    return enabled_supported_modes[0]
