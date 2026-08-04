from __future__ import annotations

import math
import re
from typing import Any

import mlx.core as mx
import mlx.nn as nn

from worker.runtime.artifact_embedding_runtime import (
    ArtifactEmbeddingDescriptor,
    ArtifactEmbeddingError,
    MLXArtifactEmbeddingBackend,
    finite_attention_mask_bias,
    normalized_embedding_hidden_activation,
)


class _EncoderEmbeddings(nn.Module):
    def __init__(self, config: dict[str, object], *, architecture: str) -> None:
        hidden_size = int(config["hidden_size"])
        self.word_embeddings = nn.Embedding(int(config["vocab_size"]), hidden_size)
        self.position_embeddings = nn.Embedding(
            int(config["max_position_embeddings"]),
            hidden_size,
        )
        self.token_type_embeddings = nn.Embedding(
            int(config.get("type_vocab_size", 1)),
            hidden_size,
        )
        self.norm = nn.LayerNorm(
            hidden_size,
            eps=float(config.get("layer_norm_eps", 1e-12)),
        )
        self._architecture = architecture
        self._padding_index = int(config.get("pad_token_id", 1 if architecture == "xlmr" else 0))

    def __call__(
        self,
        input_ids: mx.array,
        attention_mask: mx.array,
        token_type_ids: mx.array | None,
    ) -> mx.array:
        if token_type_ids is None:
            token_type_ids = mx.zeros_like(input_ids)
        if self._architecture == "xlmr":
            position_ids = mx.cumsum(attention_mask, axis=1) * attention_mask
            position_ids = position_ids + self._padding_index
        else:
            position_ids = mx.broadcast_to(mx.arange(input_ids.shape[1]), input_ids.shape)
        embeddings = (
            self.word_embeddings(input_ids)
            + self.position_embeddings(position_ids)
            + self.token_type_embeddings(token_type_ids)
        )
        return self.norm(embeddings)


class _SelfAttention(nn.Module):
    def __init__(self, hidden_size: int, num_heads: int) -> None:
        if hidden_size % num_heads != 0:
            raise ArtifactEmbeddingError(
                "embedding_artifact_invalid_attention",
                "Embedding hidden_size must be divisible by num_attention_heads.",
            )
        self.query = nn.Linear(hidden_size, hidden_size)
        self.key = nn.Linear(hidden_size, hidden_size)
        self.value = nn.Linear(hidden_size, hidden_size)
        self.output = nn.Linear(hidden_size, hidden_size)
        self._num_heads = num_heads
        self._head_size = hidden_size // num_heads
        self._scale = 1.0 / math.sqrt(self._head_size)

    def __call__(self, hidden_states: mx.array, attention_mask: mx.array) -> mx.array:
        batch_size, sequence_length, hidden_size = hidden_states.shape

        def split_heads(value: mx.array) -> mx.array:
            return value.reshape(
                batch_size,
                sequence_length,
                self._num_heads,
                self._head_size,
            ).transpose(0, 2, 1, 3)

        query = split_heads(self.query(hidden_states))
        key = split_heads(self.key(hidden_states))
        value = split_heads(self.value(hidden_states))
        mask_bias = finite_attention_mask_bias(attention_mask, query.dtype)
        attended = mx.fast.scaled_dot_product_attention(
            query,
            key,
            value,
            scale=self._scale,
            mask=mask_bias,
        )
        merged = attended.transpose(0, 2, 1, 3).reshape(
            batch_size,
            sequence_length,
            hidden_size,
        )
        return self.output(merged)


def _gelu_new(value: mx.array) -> mx.array:
    coefficient = math.sqrt(2.0 / math.pi)
    return 0.5 * value * (1.0 + mx.tanh(coefficient * (value + 0.044715 * value**3)))


class _EncoderLayer(nn.Module):
    def __init__(self, config: dict[str, object]) -> None:
        hidden_size = int(config["hidden_size"])
        self.attention = _SelfAttention(hidden_size, int(config["num_attention_heads"]))
        self.attention_norm = nn.LayerNorm(
            hidden_size,
            eps=float(config.get("layer_norm_eps", 1e-12)),
        )
        self.intermediate = nn.Linear(hidden_size, int(config["intermediate_size"]))
        self.output = nn.Linear(int(config["intermediate_size"]), hidden_size)
        self.output_norm = nn.LayerNorm(
            hidden_size,
            eps=float(config.get("layer_norm_eps", 1e-12)),
        )
        hidden_act = normalized_embedding_hidden_activation(config)
        if hidden_act not in {"gelu", "gelu_new"}:
            raise ArtifactEmbeddingError(
                "embedding_artifact_unsupported_activation",
                f"Unsupported embedding hidden_act: {hidden_act}.",
            )
        self._hidden_act = hidden_act

    def __call__(self, hidden_states: mx.array, attention_mask: mx.array) -> mx.array:
        attention_output = self.attention(hidden_states, attention_mask)
        hidden_states = self.attention_norm(hidden_states + attention_output)
        intermediate = self.intermediate(hidden_states)
        activated = (
            _gelu_new(intermediate)
            if self._hidden_act == "gelu_new"
            else nn.gelu(intermediate)
        )
        feed_forward = self.output(activated)
        return self.output_norm(hidden_states + feed_forward)


class _EncoderStack(nn.Module):
    def __init__(self, config: dict[str, object]) -> None:
        self.layers = [
            _EncoderLayer(config)
            for _ in range(int(config.get("num_hidden_layers", 0)))
        ]

    def __call__(self, hidden_states: mx.array, attention_mask: mx.array) -> mx.array:
        for layer in self.layers:
            hidden_states = layer(hidden_states, attention_mask)
        return hidden_states


class MLXBERTEncoder(nn.Module):
    def __init__(self, config: dict[str, object], *, architecture: str) -> None:
        self.embeddings = _EncoderEmbeddings(config, architecture=architecture)
        self.encoder = _EncoderStack(config)

    def __call__(
        self,
        *,
        input_ids: mx.array,
        attention_mask: mx.array,
        token_type_ids: mx.array | None = None,
    ) -> mx.array:
        hidden_states = self.embeddings(input_ids, attention_mask, token_type_ids)
        return self.encoder(hidden_states, attention_mask)


_LAYER_KEY = re.compile(r"^encoder\.layer\.(\d+)\.(.+)$")


def _mapped_weight_key(raw_key: str, *, architecture: str) -> str | None:
    key = raw_key
    for prefix in ("model.", "module."):
        if key.startswith(prefix):
            key = key[len(prefix) :]
    architecture_prefix = "bert." if architecture == "bert" else "roberta."
    if key.startswith(architecture_prefix):
        key = key[len(architecture_prefix) :]
    elif key.startswith(("bert.", "roberta.")):
        return None
    if key.startswith(("pooler.", "cls.", "lm_head.")):
        return None
    key = key.replace("embeddings.LayerNorm.", "embeddings.norm.")
    layer_match = _LAYER_KEY.match(key)
    if layer_match is None:
        return key
    layer_index, suffix = layer_match.groups()
    replacements = {
        "attention.self.query.": "attention.query.",
        "attention.self.key.": "attention.key.",
        "attention.self.value.": "attention.value.",
        "attention.output.dense.": "attention.output.",
        "attention.output.LayerNorm.": "attention_norm.",
        "intermediate.dense.": "intermediate.",
        "output.dense.": "output.",
        "output.LayerNorm.": "output_norm.",
    }
    for source, target in replacements.items():
        if suffix.startswith(source):
            return f"encoder.layers.{layer_index}.{target}{suffix[len(source):]}"
    raise ArtifactEmbeddingError(
        "embedding_weights_unsupported_tensor",
        f"Unsupported embedding encoder tensor: {raw_key}.",
    )


def _load_weights(descriptor: ArtifactEmbeddingDescriptor) -> dict[str, mx.array]:
    mapped: dict[str, mx.array] = {}
    for weight_path in descriptor.weight_paths:
        payload = mx.load(str(weight_path))
        if not isinstance(payload, dict):
            raise ArtifactEmbeddingError(
                "embedding_weights_invalid",
                f"Embedding weight file {weight_path.name} did not contain named tensors.",
            )
        for raw_key, value in payload.items():
            mapped_key = _mapped_weight_key(str(raw_key), architecture=descriptor.architecture)
            if mapped_key is not None:
                if mapped_key in mapped:
                    raise ArtifactEmbeddingError(
                        "embedding_weights_duplicate",
                        f"Duplicate embedding tensor after mapping: {mapped_key}.",
                    )
                mapped[mapped_key] = value
    return mapped


def load_mlx_artifact_backend(
    descriptor: ArtifactEmbeddingDescriptor,
) -> MLXArtifactEmbeddingBackend:
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise ArtifactEmbeddingError(
            "embedding_tokenizer_runtime_unavailable",
            "The local tokenizer runtime is unavailable.",
        ) from exc

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            descriptor.model_path,
            local_files_only=True,
            trust_remote_code=False,
        )
    except Exception as exc:
        raise ArtifactEmbeddingError(
            "embedding_tokenizer_load_failed",
            f"Cannot load local embedding tokenizer: {exc}",
        ) from exc

    config = dict(descriptor.config)
    required_positive_ints = (
        "hidden_size",
        "num_attention_heads",
        "intermediate_size",
        "vocab_size",
        "max_position_embeddings",
    )
    for key in required_positive_ints:
        try:
            valid = int(config.get(key, 0)) > 0
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ArtifactEmbeddingError(
                "embedding_artifact_invalid_config",
                f"Embedding config field {key} must be a positive integer.",
            )
    encoder = MLXBERTEncoder(config, architecture=descriptor.architecture)
    weights = _load_weights(descriptor)
    embedding_weight = weights.get("embeddings.word_embeddings.weight")
    effective_dtype = (
        str(embedding_weight.dtype).removeprefix("mlx.core.")
        if embedding_weight is not None
        else descriptor.dtype
    )
    try:
        encoder.load_weights(list(weights.items()), strict=True)
    except (KeyError, ValueError) as exc:
        raise ArtifactEmbeddingError(
            "embedding_weights_incompatible",
            f"Embedding weights do not match the local encoder config: {exc}",
        ) from exc
    encoder.eval()
    mx.eval(encoder.parameters())
    return MLXArtifactEmbeddingBackend(
        tokenizer=tokenizer,
        encoder=encoder,
        dtype=effective_dtype,
    )
