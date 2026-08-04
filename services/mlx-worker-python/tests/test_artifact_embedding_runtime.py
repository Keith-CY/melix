from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from threading import get_ident

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

import worker.runtime.artifact_embedding_runtime as artifact_runtime
import worker.model_registry.catalog as model_catalog
import worker.runtime.mlx_embedding_encoder as mlx_encoder
from worker.engine.embedding_core import EmbeddingCore
from worker.registry import WorkerRegistry
from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime.artifact_embedding_runtime import (
    ArtifactEmbeddingError,
    EmbeddingBatchResult,
    MLXArtifactEmbeddingBackend,
    MLXEmbeddingRuntime,
    finite_attention_mask_bias,
    inspect_embedding_artifact,
    pool_mlx_hidden_states,
)
from worker.runtime.embedding_runtime import EmbeddingRuntime
from worker.runtime.mlx_executor import MLXRuntimeExecutor


class RecordingBackendLoader:
    def __init__(self) -> None:
        self.descriptors = []

    def __call__(self, descriptor):
        self.descriptors.append(descriptor)
        return type("LoadedProbeBackend", (), {"dtype": "float32"})()


class RecordingBatchBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], int, str, str]] = []

    def embed_batch(self, inputs, descriptor):
        self.calls.append(
            (
                tuple(inputs),
                descriptor.max_length,
                descriptor.pooling_mode,
                descriptor.normalization,
            )
        )
        return EmbeddingBatchResult(
            vectors=(
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
            ),
            input_token_count=7,
            forward_count=1,
            dtype="float16",
        )


class FixedTokenizer:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def __call__(self, inputs, **kwargs):
        self.calls += 1
        return self.payload


class CountingEncoder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        raise AssertionError("encoder must not run for a fully padded batch")


class ReturningEncoder:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls = 0

    def __call__(self, **_kwargs):
        self.calls += 1
        return self.value


class ThreadTrackedResource:
    def __init__(self, released_thread_ids: list[int]) -> None:
        self._released_thread_ids = released_thread_ids

    def __del__(self) -> None:
        self._released_thread_ids.append(get_ident())


class StaticBatchBackend:
    def __init__(self, result: object) -> None:
        self.result = result

    def embed_batch(self, _inputs, _descriptor):
        return self.result


class RecordingRouteRuntime:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[str, object]] = []

    def estimate_resident_bytes(self, model_spec) -> int:
        self.calls.append(("estimate", model_spec.model_id))
        return 123

    def load_model(self, model_spec) -> dict[str, object]:
        self.calls.append(("load", model_spec.model_id))
        return {
            "model_id": model_spec.model_id,
            "embedding_backend_id": model_spec.ext.get("embedding_backend_id", ""),
        }

    def embed_inputs(self, _loaded_model, inputs):
        self.calls.append(("embed", tuple(inputs)))
        return [[1.0]]

    def close_loaded_model(self, loaded_model) -> None:
        self.calls.append(("close", loaded_model["model_id"]))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _loadable_embedding_config(
    *,
    model_type: str = "bert",
    **overrides: object,
) -> dict[str, object]:
    config: dict[str, object] = {
        "model_type": model_type,
        "hidden_size": 4,
        "num_attention_heads": 2,
        "intermediate_size": 4,
        "vocab_size": 7,
        "max_position_embeddings": 16,
        "hidden_act": "gelu",
    }
    config.update(overrides)
    return config


def _write_catalog_embedding_files(
    model_dir: Path,
    config: dict[str, object],
) -> None:
    _write_json(model_dir / "config.json", config)
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")


def _bert_model_spec(model_dir: Path) -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="local-bert-embedding",
        model_path=str(model_dir),
        model_kind="embedding",
        tokenizer_hash="catalog-tokenizer-hash",
        max_context=10,
        ext={
            "embedding_backend_id": "mlx-bert-v1",
            "embedding_pooling_mode": "mean",
            "embedding_normalization": "l2",
            "embedding_dimensions": "4",
        },
    )


def _write_tiny_bert_checkpoint(
    model_dir: Path,
    *,
    num_hidden_layers: int = 0,
    dtype: str = "float32",
) -> None:
    import mlx.core as mx

    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        {
            "model_type": "bert",
            "architectures": ["BertModel"],
            "hidden_size": 4,
            "num_hidden_layers": num_hidden_layers,
            "num_attention_heads": 2,
            "intermediate_size": 4,
            "vocab_size": 7,
            "max_position_embeddings": 8,
            "type_vocab_size": 2,
            "layer_norm_eps": 1e-12,
            "hidden_act": "gelu",
            "torch_dtype": dtype,
        },
    )
    _write_json(
        model_dir / "tokenizer_config.json",
        {
            "tokenizer_class": "BertTokenizer",
            "do_lower_case": True,
            "model_max_length": 8,
        },
    )
    (model_dir / "vocab.txt").write_text(
        "[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nalpha\nbeta\n",
        encoding="utf-8",
    )
    word_embeddings = mx.array(
        [
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
            [1.0, -1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0, 1.0],
            [0.0, 0.0, 0.0, 0.0],
            [1.0, 1.0, -1.0, -1.0],
            [-1.0, 1.0, 1.0, -1.0],
        ],
        dtype=mx.float32,
    )
    weights = {
            "bert.embeddings.word_embeddings.weight": word_embeddings,
            "bert.embeddings.position_embeddings.weight": mx.zeros((8, 4)),
            "bert.embeddings.token_type_embeddings.weight": mx.zeros((2, 4)),
            "bert.embeddings.LayerNorm.weight": mx.ones((4,)),
            "bert.embeddings.LayerNorm.bias": mx.zeros((4,)),
    }
    for layer_index in range(num_hidden_layers):
        prefix = f"bert.encoder.layer.{layer_index}"
        for projection in ("query", "key", "value"):
            weights[f"{prefix}.attention.self.{projection}.weight"] = mx.zeros((4, 4))
            weights[f"{prefix}.attention.self.{projection}.bias"] = mx.zeros((4,))
        weights[f"{prefix}.attention.output.dense.weight"] = mx.zeros((4, 4))
        weights[f"{prefix}.attention.output.dense.bias"] = mx.zeros((4,))
        weights[f"{prefix}.attention.output.LayerNorm.weight"] = mx.ones((4,))
        weights[f"{prefix}.attention.output.LayerNorm.bias"] = mx.zeros((4,))
        weights[f"{prefix}.intermediate.dense.weight"] = mx.zeros((4, 4))
        weights[f"{prefix}.intermediate.dense.bias"] = mx.zeros((4,))
        weights[f"{prefix}.output.dense.weight"] = mx.zeros((4, 4))
        weights[f"{prefix}.output.dense.bias"] = mx.zeros((4,))
        weights[f"{prefix}.output.LayerNorm.weight"] = mx.ones((4,))
        weights[f"{prefix}.output.LayerNorm.bias"] = mx.zeros((4,))
    if dtype == "float16":
        weights = {key: value.astype(mx.float16) for key, value in weights.items()}
    mx.save_safetensors(str(model_dir / "model.safetensors"), weights)


def _write_tiny_xlmr_checkpoint(model_dir: Path) -> list[list[float]]:
    import mlx.core as mx
    import sentencepiece as spm

    model_dir.mkdir()
    corpus_path = model_dir / "corpus.txt"
    corpus_path.write_text(
        "alpha beta gamma delta\nalpha gamma\nbeta delta\n",
        encoding="utf-8",
    )
    model_prefix = model_dir / "sentencepiece"
    spm.SentencePieceTrainer.train(
        input=str(corpus_path),
        model_prefix=str(model_prefix),
        vocab_size=24,
        model_type="bpe",
        bos_id=0,
        pad_id=1,
        eos_id=2,
        unk_id=3,
        hard_vocab_limit=False,
    )
    (model_dir / "sentencepiece.model").rename(
        model_dir / "sentencepiece.bpe.model"
    )
    processor = spm.SentencePieceProcessor(
        model_file=str(model_dir / "sentencepiece.bpe.model")
    )
    vocab_size = processor.get_piece_size()
    _write_json(
        model_dir / "config.json",
        {
            "model_type": "xlm-roberta",
            "architectures": ["XLMRobertaModel"],
            "hidden_size": 4,
            "num_hidden_layers": 0,
            "num_attention_heads": 2,
            "intermediate_size": 4,
            "vocab_size": vocab_size,
            "max_position_embeddings": 16,
            "type_vocab_size": 1,
            "layer_norm_eps": 1e-5,
            "hidden_act": "gelu",
            "pad_token_id": 1,
            "bos_token_id": 0,
            "eos_token_id": 2,
            "torch_dtype": "float32",
        },
    )
    _write_json(
        model_dir / "tokenizer_config.json",
        {
            "tokenizer_class": "XLMRobertaTokenizer",
            "model_max_length": 10,
            "bos_token": "<s>",
            "eos_token": "</s>",
            "unk_token": "<unk>",
            "pad_token": "<pad>",
        },
    )
    patterns = (
        (1.0, -1.0, 1.0, -1.0),
        (1.0, 1.0, -1.0, -1.0),
        (-1.0, 1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0, 1.0),
    )
    word_embeddings = [list(patterns[index % len(patterns)]) for index in range(vocab_size)]
    mx.save_safetensors(
        str(model_dir / "model.safetensors"),
        {
            "roberta.embeddings.word_embeddings.weight": mx.array(word_embeddings),
            "roberta.embeddings.position_embeddings.weight": mx.zeros((16, 4)),
            "roberta.embeddings.token_type_embeddings.weight": mx.zeros((1, 4)),
            "roberta.embeddings.LayerNorm.weight": mx.ones((4,)),
            "roberta.embeddings.LayerNorm.bias": mx.zeros((4,)),
        },
    )
    return word_embeddings


def _xlmr_model_spec(model_dir: Path) -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="local-xlmr-embedding",
        model_path=str(model_dir),
        model_kind="embedding",
        max_context=10,
        ext={
            "embedding_backend_id": "mlx-xlmr-v1",
            "embedding_pooling_mode": "mean",
            "embedding_normalization": "l2",
            "embedding_dimensions": "4",
        },
    )


def test_load_model_binds_local_bert_artifact_and_effective_receipt(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "bert-embedding"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(torch_dtype="float16"),
    )
    _write_json(model_dir / "tokenizer_config.json", {"model_max_length": 12})
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")

    backend_loader = RecordingBackendLoader()
    memory_samples = iter((1_000, 1_200))
    runtime = MLXEmbeddingRuntime(
        backend_loader=backend_loader,
        active_memory_bytes=lambda: next(memory_samples),
    )

    loaded = runtime.load_model(_bert_model_spec(model_dir))

    assert len(backend_loader.descriptors) == 1
    descriptor = backend_loader.descriptors[0]
    assert descriptor.source_model_path == model_dir.resolve()
    assert descriptor.model_path != model_dir.resolve()
    assert not descriptor.model_path.exists()
    assert descriptor.architecture == "bert"
    assert tuple(path.name for path in descriptor.weight_paths) == ("model.safetensors",)
    assert descriptor.dimensions == 4
    assert descriptor.max_length == 10
    assert descriptor.pooling_mode == "mean"
    assert descriptor.normalization == "l2"
    assert descriptor.dtype == "float16"

    receipt = loaded["embedding_load_receipt"]
    assert receipt["requested_backend_id"] == "mlx-bert-v1"
    assert receipt["effective_backend_id"] == "mlx-bert-v1"
    assert receipt["requested_pooling_mode"] == "mean"
    assert receipt["effective_pooling_mode"] == "mean"
    assert receipt["requested_normalization"] == "l2"
    assert receipt["effective_normalization"] == "l2"
    assert receipt["requested_dimensions"] == 4
    assert receipt["effective_dimensions"] == 4
    assert receipt["requested_max_length"] == 10
    assert receipt["effective_max_length"] == 10
    assert receipt["requested_vector_kind"] == ""
    assert receipt["effective_vector_kind"] == "single_dense"
    assert receipt["requested_dtype"] == "float16"
    assert receipt["effective_dtype"] == "float32"
    assert receipt["estimated_resident_bytes"] == len(b"weights")
    assert receipt["measured_resident_bytes"] == 200
    assert receipt["model_hash"].startswith("sha256:")
    assert receipt["tokenizer_hash"].startswith("sha256:")
    assert receipt["tokenizer_hash"] != "catalog-tokenizer-hash"


def test_residency_estimate_does_not_hash_artifact_weights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_dir = tmp_path / "bert-embedding"
    _write_tiny_bert_checkpoint(model_dir)
    weight_path = model_dir / "model.safetensors"

    def fail_if_hashed(*_args, **_kwargs):
        raise AssertionError("residency estimate must not hash artifact bytes")

    monkeypatch.setattr(artifact_runtime, "_files_hash", fail_if_hashed)

    assert MLXEmbeddingRuntime().estimate_resident_bytes(
        _bert_model_spec(model_dir)
    ) == weight_path.stat().st_size


def test_load_model_refuses_media_embedding_artifact_before_backend_load(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "media-embedding"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    model_spec = _bert_model_spec(model_dir)
    model_spec.ext["embedding_input_modalities"] = "text,image"
    backend_loader = RecordingBackendLoader()
    runtime = MLXEmbeddingRuntime(backend_loader=backend_loader)

    with pytest.raises(ArtifactEmbeddingError) as caught:
        runtime.load_model(model_spec)

    assert caught.value.code == "embedding_media_artifact_unsupported"
    assert backend_loader.descriptors == []


def test_load_model_does_not_misclassify_roberta_as_xlmr(tmp_path: Path) -> None:
    model_dir = tmp_path / "roberta-embedding"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(model_type="roberta"),
    )
    model_spec = _bert_model_spec(model_dir)
    model_spec.ext["embedding_backend_id"] = "mlx-xlmr-v1"

    with pytest.raises(ArtifactEmbeddingError) as caught:
        MLXEmbeddingRuntime(backend_loader=RecordingBackendLoader()).load_model(
            model_spec
        )

    assert caught.value.code == "embedding_artifact_unsupported_architecture"


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing_path", "embedding_artifact_path_missing"),
        ("invalid_json", "embedding_artifact_invalid_config"),
        ("non_object_json", "embedding_artifact_invalid_config"),
        ("unsupported_backend", "embedding_backend_unsupported"),
        ("backend_mismatch", "embedding_backend_artifact_mismatch"),
        ("invalid_dimensions", "embedding_artifact_invalid_dimensions"),
        ("dimension_mismatch", "embedding_dimension_mismatch"),
        ("pooling_unsupported", "embedding_pooling_unsupported"),
        ("normalization_unsupported", "embedding_normalization_unsupported"),
        ("tokenizer_missing", "embedding_tokenizer_missing"),
        ("weights_missing", "embedding_weights_missing"),
        ("max_length_missing", "embedding_artifact_unsupported_config"),
        ("multi_vector", "embedding_multi_vector_unsupported"),
        ("pooling_ambiguous", "embedding_pooling_ambiguous"),
        ("pooling_dimension_mismatch", "embedding_dimension_mismatch"),
        ("normalization_ambiguous", "embedding_normalization_ambiguous"),
    ],
)
def test_artifact_inspection_fails_closed_for_invalid_contracts(
    tmp_path: Path,
    case: str,
    expected_code: str,
) -> None:
    model_dir = tmp_path / "artifact"
    model_dir.mkdir()
    config = _loadable_embedding_config()
    _write_json(model_dir / "config.json", config)
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    model_spec = _bert_model_spec(model_dir)

    if case == "missing_path":
        model_spec.model_path = ""
    elif case == "invalid_json":
        (model_dir / "config.json").write_text("{", encoding="utf-8")
    elif case == "non_object_json":
        (model_dir / "config.json").write_text("[]", encoding="utf-8")
    elif case == "unsupported_backend":
        model_spec.ext["embedding_backend_id"] = "unknown-v1"
    elif case == "backend_mismatch":
        model_spec.ext["embedding_backend_id"] = "mlx-xlmr-v1"
    elif case == "invalid_dimensions":
        config["hidden_size"] = 0
        _write_json(model_dir / "config.json", config)
    elif case == "dimension_mismatch":
        model_spec.ext["embedding_dimensions"] = "5"
    elif case == "pooling_unsupported":
        model_spec.ext["embedding_pooling_mode"] = "weighted"
    elif case == "normalization_unsupported":
        model_spec.ext["embedding_normalization"] = "layer_norm"
    elif case == "tokenizer_missing":
        (model_dir / "tokenizer.json").unlink()
    elif case == "weights_missing":
        (model_dir / "model.safetensors").unlink()
    elif case == "max_length_missing":
        model_spec.max_context = 0
        config.pop("max_position_embeddings")
        _write_json(model_dir / "config.json", config)
    elif case == "multi_vector":
        model_spec.ext["embedding_vector_kind"] = "multi_vector"
    elif case in {"pooling_ambiguous", "pooling_dimension_mismatch"}:
        pooling_count = 2 if case == "pooling_ambiguous" else 1
        for index in range(pooling_count):
            pooling_dir = model_dir / f"{index}_Pooling"
            pooling_dir.mkdir()
            _write_json(
                pooling_dir / "config.json",
                {
                    "pooling_mode_mean_tokens": True,
                    "word_embedding_dimension": (
                        5 if case == "pooling_dimension_mismatch" else 4
                    ),
                },
            )
    elif case == "normalization_ambiguous":
        for index in range(2):
            normalize_dir = model_dir / f"{index}_Normalize"
            normalize_dir.mkdir()
            _write_json(normalize_dir / "config.json", {})

    with pytest.raises(ArtifactEmbeddingError) as caught:
        inspect_embedding_artifact(model_spec)

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    "unsupported_pooling_flag",
    [
        "pooling_mode_max_tokens",
        "pooling_mode_mean_sqrt_len_tokens",
        "pooling_mode_weightedmean_tokens",
        "pooling_mode_future_composite_tokens",
    ],
)
def test_artifact_loader_rejects_composite_or_unknown_pooling_modes(
    tmp_path: Path,
    unsupported_pooling_flag: str,
) -> None:
    model_dir = tmp_path / "artifact"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    pooling_dir = model_dir / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {
            "pooling_mode_mean_tokens": True,
            unsupported_pooling_flag: True,
            "word_embedding_dimension": 4,
        },
    )

    with pytest.raises(ArtifactEmbeddingError) as caught:
        inspect_embedding_artifact(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_pooling_unsupported"


@pytest.mark.parametrize(
    "media_component_key",
    [
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
    ],
)
def test_load_model_refuses_media_component_declared_by_artifact_config(
    tmp_path: Path,
    media_component_key: str,
) -> None:
    model_dir = tmp_path / "media-config-embedding"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(
            **{media_component_key: {"component_type": "unsupported"}}
        ),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    backend_loader = RecordingBackendLoader()
    runtime = MLXEmbeddingRuntime(backend_loader=backend_loader)

    with pytest.raises(ArtifactEmbeddingError) as caught:
        runtime.load_model(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_media_artifact_unsupported"
    assert backend_loader.descriptors == []


def test_embed_inputs_executes_one_ordered_batch_and_records_shape_receipt(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "batched-bert"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(torch_dtype="float16"),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    backend = RecordingBatchBackend()
    runtime = MLXEmbeddingRuntime(
        backend_loader=lambda descriptor: backend,
        active_memory_bytes=lambda: 0,
    )
    loaded = runtime.load_model(_bert_model_spec(model_dir))

    vectors = runtime.embed_inputs(loaded, ("first", "second", "third"))

    assert backend.calls == [
        (("first", "second", "third"), 10, "mean", "l2")
    ]
    assert vectors == [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ]
    assert loaded["embedding_request_receipt"] == {
        "backend_id": "mlx-bert-v1",
        "batch_size": 3,
        "input_token_count": 7,
        "forward_count": 1,
        "output_row_count": 3,
        "dimensions": 4,
        "vector_kind": "single_dense",
        "dtype": "float16",
        "finite_output": True,
    }


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("invalid_handle", "embedding_model_handle_invalid"),
        ("missing_method", "embedding_backend_unavailable"),
        ("invalid_result", "embedding_backend_contract_invalid"),
        ("forward_count", "embedding_forward_count_invalid"),
        ("row_count", "embedding_output_row_count_invalid"),
        ("dimensions", "embedding_output_dimension_invalid"),
        ("nonfinite", "embedding_output_nonfinite"),
    ],
)
def test_runtime_rejects_invalid_backend_batch_contracts(
    tmp_path: Path,
    case: str,
    expected_code: str,
) -> None:
    model_dir = tmp_path / "bert"
    _write_tiny_bert_checkpoint(model_dir)
    descriptor = inspect_embedding_artifact(_bert_model_spec(model_dir))
    valid_row = (1.0, 0.0, 0.0, 0.0)
    loaded: dict[str, object] = {
        "embedding_artifact_descriptor": descriptor,
        "embedding_backend": StaticBatchBackend(
            EmbeddingBatchResult(
                vectors=(valid_row,),
                input_token_count=1,
                forward_count=1,
                dtype="float32",
            )
        ),
    }
    if case == "invalid_handle":
        loaded = {}
    elif case == "missing_method":
        loaded["embedding_backend"] = object()
    elif case == "invalid_result":
        loaded["embedding_backend"] = StaticBatchBackend(object())
    elif case == "forward_count":
        loaded["embedding_backend"] = StaticBatchBackend(
            EmbeddingBatchResult((valid_row,), 1, 2, "float32")
        )
    elif case == "row_count":
        loaded["embedding_backend"] = StaticBatchBackend(
            EmbeddingBatchResult((), 1, 1, "float32")
        )
    elif case == "dimensions":
        loaded["embedding_backend"] = StaticBatchBackend(
            EmbeddingBatchResult(((1.0,),), 1, 1, "float32")
        )
    elif case == "nonfinite":
        loaded["embedding_backend"] = StaticBatchBackend(
            EmbeddingBatchResult(((math.nan, 0.0, 0.0, 0.0),), 1, 1, "float32")
        )

    with pytest.raises(ArtifactEmbeddingError) as caught:
        MLXEmbeddingRuntime().embed_inputs(loaded, ("alpha",))

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("payload", "encoder_value", "expected_code"),
    [
        ([], None, "embedding_tokenizer_output_invalid"),
        ({"input_ids": [[1]]}, None, "embedding_tokenizer_output_invalid"),
        (
            {"input_ids": [[1]], "attention_mask": [[1], [1]]},
            None,
            "embedding_tokenizer_row_count_invalid",
        ),
        (
            {"input_ids": [[]], "attention_mask": [[]]},
            None,
            "embedding_tokenizer_shape_invalid",
        ),
        (
            {"input_ids": [1], "attention_mask": [[1]]},
            None,
            "embedding_tokenizer_output_invalid",
        ),
        (
            {
                "input_ids": [[1]],
                "attention_mask": [[1]],
                "token_type_ids": [[0], [0]],
            },
            None,
            "embedding_tokenizer_row_count_invalid",
        ),
        (
            {
                "input_ids": [[1, 2]],
                "attention_mask": [[1, 1]],
                "token_type_ids": [[0]],
            },
            None,
            "embedding_tokenizer_shape_invalid",
        ),
        (
            {"input_ids": [[1.5]], "attention_mask": [[1]]},
            None,
            "embedding_tokenizer_output_invalid",
        ),
        (
            {"input_ids": [[1]], "attention_mask": [["1"]]},
            None,
            "embedding_tokenizer_output_invalid",
        ),
        (
            {"input_ids": [[1]], "attention_mask": [[1]]},
            {},
            "embedding_encoder_output_invalid",
        ),
        (
            {"input_ids": [[1]], "attention_mask": [[1]]},
            (),
            "embedding_encoder_output_invalid",
        ),
    ],
)
def test_mlx_backend_fails_closed_for_tokenizer_and_encoder_contracts(
    tmp_path: Path,
    payload: object,
    encoder_value: object,
    expected_code: str,
) -> None:
    model_dir = tmp_path / "bert"
    _write_tiny_bert_checkpoint(model_dir)
    descriptor = inspect_embedding_artifact(_bert_model_spec(model_dir))
    backend = MLXArtifactEmbeddingBackend(
        tokenizer=FixedTokenizer(payload),
        encoder=ReturningEncoder(encoder_value),
    )

    with pytest.raises(ArtifactEmbeddingError) as caught:
        backend.embed_batch(("alpha",), descriptor)

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    "payload",
    [
        {
            "input_ids": [[1], [2, 3]],
            "attention_mask": [[1], [1, 1]],
        },
        {
            "input_ids": [[1, 2], [3, 4]],
            "attention_mask": [[1, 1], [1, 1]],
            "token_type_ids": [[0], [0, 0]],
        },
    ],
)
def test_mlx_backend_rejects_ragged_tokenizer_rows_before_mlx_conversion(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    model_dir = tmp_path / "bert"
    _write_tiny_bert_checkpoint(model_dir)
    descriptor = inspect_embedding_artifact(_bert_model_spec(model_dir))
    encoder = ReturningEncoder(None)
    backend = MLXArtifactEmbeddingBackend(
        tokenizer=FixedTokenizer(payload),
        encoder=encoder,
    )

    with pytest.raises(ArtifactEmbeddingError) as caught:
        backend.embed_batch(("alpha", "beta"), descriptor)

    assert caught.value.code == "embedding_tokenizer_shape_invalid"
    assert encoder.calls == 0


def test_mlx_backend_empty_batch_and_pooling_refusals(tmp_path: Path) -> None:
    import mlx.core as mx

    model_dir = tmp_path / "bert"
    _write_tiny_bert_checkpoint(model_dir)
    descriptor = inspect_embedding_artifact(_bert_model_spec(model_dir))
    tokenizer = FixedTokenizer({})
    empty_result = MLXArtifactEmbeddingBackend(
        tokenizer=tokenizer,
        encoder=ReturningEncoder(None),
    ).embed_batch((), descriptor)

    assert empty_result.forward_count == 0
    assert tokenizer.calls == 0
    hidden_states = mx.ones((1, 1, 4))
    attention_mask = mx.ones((1, 1), dtype=mx.int32)
    with pytest.raises(ArtifactEmbeddingError) as pooling_error:
        pool_mlx_hidden_states(
            hidden_states,
            attention_mask,
            pooling_mode="weighted",
            normalization="none",
        )
    assert pooling_error.value.code == "embedding_pooling_unsupported"
    with pytest.raises(ArtifactEmbeddingError) as normalization_error:
        pool_mlx_hidden_states(
            hidden_states,
            attention_mask,
            pooling_mode="mean",
            normalization="layer_norm",
        )
    assert normalization_error.value.code == "embedding_normalization_unsupported"


def test_embedding_runtime_routes_artifacts_fixtures_and_fallback_handles() -> None:
    artifact_runtime = RecordingRouteRuntime("artifact")
    fixture_runtime = RecordingRouteRuntime("fixture")
    runtime = EmbeddingRuntime(
        artifact_runtime=artifact_runtime,
        fixture_runtime=fixture_runtime,
    )
    artifact_spec = common_pb2.ModelSpec(
        model_id="artifact",
        ext={"embedding_backend_id": "mlx-bert-v1"},
    )
    fixture_spec = common_pb2.ModelSpec(
        model_id="fixture",
        ext={"embedding_backend_id": "deterministic-fixture-v1"},
    )

    assert runtime.estimate_resident_bytes(artifact_spec) == 123
    fixture_loaded = runtime.load_model(fixture_spec)
    assert fixture_loaded["embedding_runtime"] is fixture_runtime
    assert runtime.embed_inputs(fixture_loaded, ("alpha",)) == [[1.0]]
    fixture_loaded.pop("embedding_runtime")
    assert runtime.embed_inputs(fixture_loaded, ("beta",)) == [[1.0]]
    fixture_loaded["embedding_runtime"] = fixture_runtime
    runtime.close_loaded_model(fixture_loaded)

    assert artifact_runtime.calls == [("estimate", "artifact")]
    assert fixture_runtime.calls == [
        ("load", "fixture"),
        ("embed", ("alpha",)),
        ("embed", ("beta",)),
        ("close", "fixture"),
    ]

    with pytest.raises(ArtifactEmbeddingError) as caught:
        runtime.load_model(
            common_pb2.ModelSpec(
                model_id="unknown",
                ext={"embedding_backend_id": "unknown-v1"},
            )
        )
    assert caught.value.code == "embedding_backend_unsupported"

    with pytest.raises(ArtifactEmbeddingError) as missing_backend:
        runtime.load_model(common_pb2.ModelSpec(model_id="missing-backend"))
    assert missing_backend.value.code == "embedding_backend_unsupported"


def test_mlx_encoder_rejects_invalid_attention_activation_and_weights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ArtifactEmbeddingError) as attention_error:
        mlx_encoder._SelfAttention(3, 2)
    assert attention_error.value.code == "embedding_artifact_invalid_attention"

    invalid_activation_config = {
        "hidden_size": 4,
        "num_attention_heads": 2,
        "intermediate_size": 4,
        "hidden_act": "relu",
    }
    with pytest.raises(ArtifactEmbeddingError) as activation_error:
        mlx_encoder._EncoderLayer(invalid_activation_config)
    assert activation_error.value.code == "embedding_artifact_unsupported_activation"

    assert mlx_encoder._mapped_weight_key(
        "model.roberta.embeddings.word_embeddings.weight",
        architecture="bert",
    ) is None
    assert mlx_encoder._mapped_weight_key(
        "bert.pooler.dense.weight",
        architecture="bert",
    ) is None
    with pytest.raises(ArtifactEmbeddingError) as unsupported_tensor:
        mlx_encoder._mapped_weight_key(
            "bert.encoder.layer.0.unsupported.weight",
            architecture="bert",
        )
    assert unsupported_tensor.value.code == "embedding_weights_unsupported_tensor"

    model_dir = tmp_path / "bert"
    _write_tiny_bert_checkpoint(model_dir)
    descriptor = inspect_embedding_artifact(_bert_model_spec(model_dir))
    monkeypatch.setattr(mlx_encoder.mx, "load", lambda _path: [])
    with pytest.raises(ArtifactEmbeddingError) as invalid_weights:
        mlx_encoder._load_weights(descriptor)
    assert invalid_weights.value.code == "embedding_weights_invalid"


def test_mlx_encoder_applies_gelu_new_activation() -> None:
    import mlx.core as mx

    values = mx.array([[-2.0, -0.5, 0.5, 2.0]], dtype=mx.float32)
    actual = mlx_encoder._gelu_new(values)
    mx.eval(actual)
    expected = [
        0.5
        * value
        * (
            1.0
            + math.tanh(
                math.sqrt(2.0 / math.pi) * (value + 0.044715 * value**3)
            )
        )
        for value in (-2.0, -0.5, 0.5, 2.0)
    ]

    assert actual.tolist()[0] == pytest.approx(expected, abs=1e-6)


def test_mlx_loader_normalizes_tokenizer_config_and_weight_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from transformers import AutoTokenizer

    model_dir = tmp_path / "bert"
    _write_tiny_bert_checkpoint(model_dir)
    descriptor = inspect_embedding_artifact(_bert_model_spec(model_dir))

    def fail_tokenizer(*_args, **_kwargs):
        raise ValueError("bad tokenizer")

    monkeypatch.setattr(AutoTokenizer, "from_pretrained", fail_tokenizer)
    with pytest.raises(ArtifactEmbeddingError) as tokenizer_error:
        mlx_encoder.load_mlx_artifact_backend(descriptor)
    assert tokenizer_error.value.code == "embedding_tokenizer_load_failed"

    monkeypatch.setattr(AutoTokenizer, "from_pretrained", lambda *_args, **_kwargs: object())
    invalid_config = replace(
        descriptor,
        config={**descriptor.config, "num_attention_heads": "invalid"},
    )
    with pytest.raises(ArtifactEmbeddingError) as config_error:
        mlx_encoder.load_mlx_artifact_backend(invalid_config)
    assert config_error.value.code == "embedding_artifact_invalid_config"

    monkeypatch.setattr(mlx_encoder, "_load_weights", lambda _descriptor: {})
    with pytest.raises(ArtifactEmbeddingError) as weights_error:
        mlx_encoder.load_mlx_artifact_backend(descriptor)
    assert weights_error.value.code == "embedding_weights_incompatible"


def test_mlx_pooling_uses_active_tokens_and_finite_float16_masks() -> None:
    import mlx.core as mx

    hidden_states = mx.array(
        [
            [[3.0, 4.0], [0.0, 2.0], [9.0, 9.0]],
            [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
        ],
        dtype=mx.float16,
    )
    attention_mask = mx.array([[1, 1, 0], [0, 1, 1]], dtype=mx.int32)

    cls = pool_mlx_hidden_states(
        hidden_states,
        attention_mask,
        pooling_mode="cls",
        normalization="l2",
    )
    mean = pool_mlx_hidden_states(
        hidden_states,
        attention_mask,
        pooling_mode="mean",
        normalization="none",
    )
    last = pool_mlx_hidden_states(
        hidden_states,
        attention_mask,
        pooling_mode="last_token",
        normalization="none",
    )
    mask_bias = finite_attention_mask_bias(attention_mask, mx.float16)
    mx.eval(cls, mean, last, mask_bias)

    assert cls[0].tolist() == pytest.approx([0.6, 0.8], abs=0.001)
    assert cls[1].tolist() == pytest.approx([0.6, 0.8], abs=0.001)
    assert mean[0].tolist() == pytest.approx([1.5, 3.0], abs=0.001)
    assert mean[1].tolist() == pytest.approx([4.0, 5.0], abs=0.001)
    assert last[0].tolist() == pytest.approx([0.0, 2.0], abs=0.001)
    assert last[1].tolist() == pytest.approx([5.0, 6.0], abs=0.001)
    assert mask_bias.shape == (2, 1, 1, 3)
    assert bool(mx.all(mx.isfinite(mask_bias)).item()) is True
    assert mask_bias[0, 0, 0].tolist() == [0.0, 0.0, -65504.0]
    assert mask_bias[1, 0, 0].tolist() == [-65504.0, 0.0, 0.0]


def test_mlx_backend_refuses_fully_padded_row_before_encoder_forward(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "padded-bert"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(torch_dtype="float16"),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    tokenizer = FixedTokenizer(
        {
            "input_ids": [[101, 102], [0, 0]],
            "attention_mask": [[1, 1], [0, 0]],
            "token_type_ids": [[0, 0], [0, 0]],
        }
    )
    encoder = CountingEncoder()
    backend = MLXArtifactEmbeddingBackend(tokenizer=tokenizer, encoder=encoder)
    runtime = MLXEmbeddingRuntime(
        backend_loader=lambda descriptor: backend,
        active_memory_bytes=lambda: 0,
    )
    loaded = runtime.load_model(_bert_model_spec(model_dir))

    with pytest.raises(ArtifactEmbeddingError) as caught:
        runtime.embed_inputs(loaded, ("valid", "fully padded"))

    assert caught.value.code == "embedding_fully_padded_input"
    assert tokenizer.calls == 1
    assert encoder.calls == 0


def test_tiny_local_bert_checkpoint_matches_golden_mean_vectors(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "tiny-bert"
    _write_tiny_bert_checkpoint(model_dir)
    runtime = MLXEmbeddingRuntime()
    model_spec = _bert_model_spec(model_dir)

    loaded = runtime.load_model(model_spec)
    vectors = runtime.embed_inputs(loaded, ("alpha beta", "beta"))

    assert vectors[0] == pytest.approx(
        [0.0, 0.0, 0.70710677, -0.70710677],
        abs=1e-5,
    )
    assert vectors[1] == pytest.approx(
        [-0.28867513, -0.28867513, 0.8660254, -0.28867513],
        abs=1e-5,
    )
    assert loaded["embedding_request_receipt"]["forward_count"] == 1
    assert loaded["embedding_request_receipt"]["finite_output"] is True


def test_worker_registry_routes_mlx_embedding_model_through_artifact_handle(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "registry-bert"
    _write_tiny_bert_checkpoint(model_dir)
    registry = WorkerRegistry()

    loaded = registry.load_model(_bert_model_spec(model_dir))
    response = EmbeddingCore(registry).embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="artifact-receipt-1"),
            model_handle=loaded.handle,
            inputs=["alpha beta", "beta"],
        )
    )
    vectors = [list(embedding.values) for embedding in response.embeddings]

    assert response.error.code == ""
    assert loaded.runtime_kind == "embedding"
    assert loaded.runtime_model["embedding_backend_id"] == "mlx-bert-v1"
    assert loaded.runtime_model["embedding_load_receipt"]["model_hash"].startswith(
        "sha256:"
    )
    assert len(vectors) == 2
    assert loaded.runtime_model["embedding_request_receipt"]["forward_count"] == 1
    summary_ext = registry.list_loaded_model_summaries()[0].model.ext
    assert summary_ext["melix.embedding.request.schema"] == (
        "melix.embedding_request_receipt.v1"
    )
    assert summary_ext["melix.embedding.request.request_id"] == "artifact-receipt-1"
    assert summary_ext["melix.embedding.request.batch_size"] == "2"
    assert summary_ext["melix.embedding.request.forward_count"] == "1"
    assert summary_ext["melix.embedding.request.dimensions"] == "4"
    assert summary_ext["melix.embedding.request.finite_output"] == "True"


def test_artifact_embedding_uses_shared_mlx_executor_owner_thread(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "executor-bert"
    _write_tiny_bert_checkpoint(model_dir)
    owner_thread_ids: list[int] = []
    backend = RecordingBatchBackend()

    def load_backend(_descriptor):
        owner_thread_ids.append(get_ident())
        return backend

    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    try:
        runtime = MLXEmbeddingRuntime(
            backend_loader=load_backend,
            active_memory_bytes=lambda: 0,
            executor=executor,
        )
        loaded = runtime.load_model(_bert_model_spec(model_dir))
        runtime.embed_inputs(
            loaded,
            ("first", "second", "third"),
            request_id="executor-request",
        )
        executor_thread_id = executor.run(get_ident)

        assert owner_thread_ids == [executor_thread_id]
        assert loaded["embedding_request_receipt"]["request_id"] == (
            "executor-request"
        )
    finally:
        executor.shutdown()


def test_real_mlx_backend_releases_resources_on_executor_and_cannot_be_reused(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "closing-bert"
    _write_tiny_bert_checkpoint(model_dir)
    released_thread_ids: list[int] = []
    backend = MLXArtifactEmbeddingBackend(
        tokenizer=ThreadTrackedResource(released_thread_ids),
        encoder=ThreadTrackedResource(released_thread_ids),
    )
    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    try:
        runtime = MLXEmbeddingRuntime(
            backend_loader=lambda _descriptor: backend,
            active_memory_bytes=lambda: 0,
            executor=executor,
        )
        loaded = runtime.load_model(_bert_model_spec(model_dir))
        descriptor = loaded["embedding_artifact_descriptor"]
        executor_thread_id = executor.run(get_ident)

        runtime.close_loaded_model(loaded)
        runtime.close_loaded_model(loaded)

        assert released_thread_ids == [executor_thread_id, executor_thread_id]
        assert backend._tokenizer is None
        assert backend._encoder is None
        with pytest.raises(ArtifactEmbeddingError) as caught:
            backend.embed_batch(("alpha",), descriptor)
        assert caught.value.code == "embedding_backend_closed"
    finally:
        executor.shutdown()


def test_artifact_embedding_request_receipts_are_bounded_and_keyed(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "bounded-receipt-bert"
    _write_tiny_bert_checkpoint(model_dir)
    runtime = MLXEmbeddingRuntime(
        backend_loader=lambda _descriptor: RecordingBatchBackend(),
        active_memory_bytes=lambda: 0,
    )
    loaded = runtime.load_model(_bert_model_spec(model_dir))

    for index in range(70):
        runtime.embed_inputs(
            loaded,
            ("first", "second", "third"),
            request_id=f"request-{index}",
        )

    receipts = loaded["embedding_request_receipts"]
    assert len(receipts) == 64
    assert "request-5" not in receipts
    assert list(receipts)[0] == "request-6"
    assert list(receipts)[-1] == "request-69"
    assert loaded["embedding_request_receipt"]["request_id"] == "request-69"


def test_development_catalog_advertises_digest_projection_as_fixture_only() -> None:
    bert = WorkerModelCatalog.dev_embedding_model()
    xlmr = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "xlmr"}
    )

    assert bert.ext["embedding_backend_id"] == "deterministic-fixture-v1"
    assert xlmr.ext["embedding_backend_id"] == "deterministic-fixture-v1"
    assert bert.ext["embedding_execution_kind"] == "fixture"
    assert xlmr.ext["embedding_execution_kind"] == "fixture"


def test_development_catalog_preserves_detected_xlmr_family_with_fixture_backend() -> None:
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_MODEL_PATH": "models/xlm-r-base"}
    )

    assert model.ext["embedding_backend_id"] == "deterministic-fixture-v1"
    assert model.ext["embedding_family_id"] == "xlmr"
    assert model.ext["model_architecture"] == "xlmr"


def test_loaded_model_summary_exposes_artifact_embedding_load_receipt(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "receipt-bert"
    _write_tiny_bert_checkpoint(model_dir)
    registry = WorkerRegistry()

    registry.load_model(_bert_model_spec(model_dir))
    summary = registry.list_loaded_model_summaries()[0]
    receipt = summary.model.ext

    assert receipt["melix.embedding.load.schema"] == "melix.embedding_load_receipt.v1"
    assert receipt["melix.embedding.load.effective_backend_id"] == "mlx-bert-v1"
    assert receipt["melix.embedding.load.model_hash"].startswith("sha256:")
    assert receipt["melix.embedding.load.tokenizer_hash"].startswith("sha256:")
    assert receipt["melix.embedding.load.effective_pooling_mode"] == "mean"
    assert receipt["melix.embedding.load.effective_dimensions"] == "4"
    assert receipt["melix.embedding.load.effective_max_length"] == "8"
    assert receipt["melix.embedding.load.vector_kind"] == "single_dense"
    assert receipt["melix.embedding.load.dtype"] == "float32"
    assert int(receipt["melix.embedding.load.measured_resident_bytes"]) >= 0


def test_load_model_resolves_sentence_transformers_pooling_and_normalization(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "sentence-transformers-bert"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    pooling_dir = model_dir / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {
            "pooling_mode_cls_token": False,
            "pooling_mode_mean_tokens": True,
            "pooling_mode_lasttoken": False,
            "word_embedding_dimension": 4,
        },
    )
    normalize_dir = model_dir / "2_Normalize"
    normalize_dir.mkdir()
    _write_json(normalize_dir / "config.json", {})
    model_spec = _bert_model_spec(model_dir)
    del model_spec.ext["embedding_pooling_mode"]
    del model_spec.ext["embedding_normalization"]
    backend_loader = RecordingBackendLoader()
    runtime = MLXEmbeddingRuntime(
        backend_loader=backend_loader,
        active_memory_bytes=lambda: 0,
    )

    loaded = runtime.load_model(model_spec)

    descriptor = backend_loader.descriptors[0]
    assert descriptor.pooling_mode == "mean"
    assert descriptor.normalization == "l2"
    assert loaded["embedding_load_receipt"]["requested_pooling_mode"] == ""
    assert loaded["embedding_load_receipt"]["effective_pooling_mode"] == "mean"
    assert loaded["embedding_load_receipt"]["requested_normalization"] == ""
    assert loaded["embedding_load_receipt"]["effective_normalization"] == "l2"


def test_sentence_transformers_modules_select_contract_and_max_length(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "sentence-transformers-modules"
    _write_tiny_bert_checkpoint(model_dir)
    selected_pooling_dir = model_dir / "1_Pooling"
    selected_pooling_dir.mkdir()
    _write_json(
        selected_pooling_dir / "config.json",
        {
            "pooling_mode_mean_tokens": True,
            "word_embedding_dimension": 4,
        },
    )
    stale_pooling_dir = model_dir / "9_Pooling"
    stale_pooling_dir.mkdir()
    _write_json(
        stale_pooling_dir / "config.json",
        {
            "pooling_mode_cls_token": True,
            "word_embedding_dimension": 4,
        },
    )
    normalize_dir = model_dir / "2_Normalize"
    normalize_dir.mkdir()
    _write_json(normalize_dir / "config.json", {})
    _write_json(
        model_dir / "modules.json",
        [
            {
                "idx": 0,
                "name": "0",
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "name": "1",
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
            {
                "idx": 2,
                "name": "2",
                "path": "2_Normalize",
                "type": "sentence_transformers.models.Normalize",
            },
        ],
    )
    _write_json(model_dir / "sentence_bert_config.json", {"max_seq_length": 6})
    model_spec = _bert_model_spec(model_dir)
    del model_spec.ext["embedding_pooling_mode"]
    del model_spec.ext["embedding_normalization"]

    descriptor = inspect_embedding_artifact(model_spec)

    assert descriptor.pooling_mode == "mean"
    assert descriptor.normalization == "l2"
    assert descriptor.max_length == 6
    assert model_dir / "modules.json" in descriptor.model_hash_paths
    assert model_dir / "sentence_bert_config.json" in descriptor.model_hash_paths


@pytest.mark.parametrize(
    "modules",
    [
        [
            {
                "idx": 1,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 2,
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
        ],
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
            {
                "idx": 2,
                "path": "2_Dense",
                "type": "sentence_transformers.models.Dense",
            },
        ],
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "1_WeightedLayerPooling",
                "type": "sentence_transformers.models.WeightedLayerPooling",
            },
            {
                "idx": 2,
                "path": "2_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
        ],
        [
            {
                "idx": 0,
                "path": "0_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
            {
                "idx": 1,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
        ],
        [
            {
                "idx": 0,
                "path": "0_Transformer",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
        ],
    ],
)
def test_sentence_transformers_modules_reject_unsupported_active_pipeline(
    tmp_path: Path,
    modules: list[object],
) -> None:
    model_dir = tmp_path / "unsupported-sentence-transformers-pipeline"
    _write_tiny_bert_checkpoint(model_dir)
    _write_json(model_dir / "modules.json", modules)

    with pytest.raises(ArtifactEmbeddingError) as caught:
        inspect_embedding_artifact(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_artifact_unsupported_pipeline"


@pytest.mark.parametrize(
    "modules",
    [
        ["not-a-module"],
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "",
                "type": "sentence_transformers.models.Pooling",
            },
        ],
    ],
)
def test_sentence_transformers_modules_reject_invalid_module_metadata(
    tmp_path: Path,
    modules: list[object],
) -> None:
    model_dir = tmp_path / "invalid-sentence-transformers-modules"
    _write_tiny_bert_checkpoint(model_dir)
    _write_json(model_dir / "modules.json", modules)

    with pytest.raises(ArtifactEmbeddingError) as caught:
        inspect_embedding_artifact(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_artifact_invalid_modules"


def test_catalog_rejects_malformed_sentence_transformer_modules_json(
    tmp_path: Path,
) -> None:
    (tmp_path / "modules.json").write_text("{", encoding="utf-8")

    assert model_catalog._artifact_embedding_module_paths(tmp_path) is None


@pytest.mark.parametrize(
    ("modules", "create_pooling"),
    [
        ({"unexpected": "mapping"}, False),
        (["not-a-module"], False),
        (
            [
                {
                    "idx": 1,
                    "path": "",
                    "type": "sentence_transformers.models.Transformer",
                }
            ],
            False,
        ),
        (
            [
                {
                    "idx": 0,
                    "path": "0_Transformer",
                    "type": "sentence_transformers.models.Transformer",
                }
            ],
            False,
        ),
        (
            [
                {
                    "idx": 0,
                    "path": "",
                    "type": "sentence_transformers.models.Transformer",
                },
                {
                    "idx": 1,
                    "path": "../outside",
                    "type": "sentence_transformers.models.Pooling",
                },
            ],
            False,
        ),
        (
            [
                {
                    "idx": 0,
                    "path": "",
                    "type": "sentence_transformers.models.Transformer",
                }
            ],
            False,
        ),
        (
            [
                {
                    "idx": 0,
                    "path": "",
                    "type": "sentence_transformers.models.Transformer",
                },
                {
                    "idx": 1,
                    "path": "1_Pooling",
                    "type": "sentence_transformers.models.Pooling",
                },
            ],
            False,
        ),
        (
            [
                {
                    "idx": 0,
                    "path": "",
                    "type": "sentence_transformers.models.Transformer",
                },
                {
                    "idx": 1,
                    "path": "1_Pooling",
                    "type": "sentence_transformers.models.Pooling",
                },
                {
                    "idx": 2,
                    "path": "2_Normalize",
                    "type": "sentence_transformers.models.Normalize",
                },
            ],
            True,
        ),
    ],
)
def test_catalog_rejects_invalid_sentence_transformer_module_contract(
    tmp_path: Path,
    modules: object,
    create_pooling: bool,
) -> None:
    if create_pooling:
        pooling_dir = tmp_path / "1_Pooling"
        pooling_dir.mkdir()
        _write_json(pooling_dir / "config.json", {})
    _write_json(tmp_path / "modules.json", modules)

    assert model_catalog._artifact_embedding_module_paths(tmp_path) is None


def test_catalog_resolves_valid_sentence_transformer_module_contract(
    tmp_path: Path,
) -> None:
    pooling_path = tmp_path / "1_Pooling" / "config.json"
    pooling_path.parent.mkdir()
    _write_json(pooling_path, {})
    _write_json(
        tmp_path / "modules.json",
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
        ],
    )

    assert model_catalog._artifact_embedding_module_paths(tmp_path) == (
        pooling_path,
        None,
    )


def test_load_model_snapshots_selected_sentence_transformer_contract_files(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "snapshot-sentence-transformers-contract"
    _write_tiny_bert_checkpoint(model_dir)
    pooling_dir = model_dir / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {
            "pooling_mode_mean_tokens": True,
            "word_embedding_dimension": 4,
        },
    )
    normalize_dir = model_dir / "2_Normalize"
    normalize_dir.mkdir()
    _write_json(normalize_dir / "config.json", {})
    _write_json(
        model_dir / "modules.json",
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
            {
                "idx": 2,
                "path": "2_Normalize",
                "type": "sentence_transformers.models.Normalize",
            },
        ],
    )
    _write_json(model_dir / "sentence_bert_config.json", {"max_seq_length": 6})
    model_spec = _bert_model_spec(model_dir)
    del model_spec.ext["embedding_pooling_mode"]
    del model_spec.ext["embedding_normalization"]
    backend_loader = RecordingBackendLoader()

    loaded = MLXEmbeddingRuntime(
        backend_loader=backend_loader,
        active_memory_bytes=lambda: 0,
    ).load_model(model_spec)

    descriptor = backend_loader.descriptors[0]
    assert descriptor.pooling_mode == "mean"
    assert descriptor.normalization == "l2"
    assert descriptor.max_length == 6
    assert descriptor.source_model_path == model_dir.resolve()
    assert not descriptor.model_path.exists()
    assert loaded["embedding_load_receipt"]["model_hash"] == descriptor.model_hash


def test_load_model_rejects_snapshot_module_path_escape(tmp_path: Path) -> None:
    model_dir = tmp_path / "snapshot-module-path-escape"
    _write_tiny_bert_checkpoint(model_dir)
    _write_json(
        model_dir / "modules.json",
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "../outside",
                "type": "sentence_transformers.models.Pooling",
            },
        ],
    )

    with pytest.raises(ArtifactEmbeddingError) as caught:
        MLXEmbeddingRuntime().load_model(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_artifact_path_escape"


def test_load_model_rejects_symlinked_snapshot_source_file(tmp_path: Path) -> None:
    model_dir = tmp_path / "symlinked-source"
    _write_tiny_bert_checkpoint(model_dir)
    outside_config = tmp_path / "outside-config.json"
    outside_config.write_bytes((model_dir / "config.json").read_bytes())
    (model_dir / "config.json").unlink()
    (model_dir / "config.json").symlink_to(outside_config)

    with pytest.raises(ArtifactEmbeddingError) as caught:
        MLXEmbeddingRuntime().load_model(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_artifact_snapshot_failed"


@pytest.mark.parametrize(
    "unsupported_config",
    [
        {"position_embedding_type": "relative_key"},
        {"position_embedding_type": "relative_key_query"},
        {"is_decoder": True},
        {"is_encoder_decoder": True},
        {"add_cross_attention": True},
        {"cross_attention_hidden_size": 4},
        {"num_attention_heads": 0},
        {"intermediate_size": 0},
        {"vocab_size": 0},
        {"max_position_embeddings": 0},
        {"hidden_size": 5},
        {"hidden_act": "relu"},
    ],
)
def test_artifact_inspection_rejects_unsupported_encoder_configs(
    tmp_path: Path,
    unsupported_config: dict[str, object],
) -> None:
    model_dir = tmp_path / "unsupported-bert"
    _write_tiny_bert_checkpoint(model_dir)
    config_path = model_dir / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update(unsupported_config)
    _write_json(config_path, config)

    with pytest.raises(ArtifactEmbeddingError) as caught:
        inspect_embedding_artifact(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_artifact_unsupported_config"


def test_tokenizer_hash_covers_added_tokens_used_by_local_tokenizer(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "tokenizer-identity"
    _write_tiny_bert_checkpoint(model_dir)
    added_tokens_path = model_dir / "added_tokens.json"
    _write_json(added_tokens_path, {"<domain-token>": 7})

    first = inspect_embedding_artifact(_bert_model_spec(model_dir))
    _write_json(added_tokens_path, {"<domain-token>": 8})
    second = inspect_embedding_artifact(_bert_model_spec(model_dir))

    assert added_tokens_path in first.tokenizer_paths
    assert first.tokenizer_hash != second.tokenizer_hash


def test_load_model_rejects_artifact_mutation_after_hashing(tmp_path: Path) -> None:
    model_dir = tmp_path / "mutating-bert"
    _write_tiny_bert_checkpoint(model_dir)

    def mutate_after_inspection(descriptor):
        descriptor.weight_paths[0].chmod(0o600)
        descriptor.weight_paths[0].write_bytes(b"replaced-after-hash")
        return type("LoadedProbeBackend", (), {"dtype": "float32"})()

    runtime = MLXEmbeddingRuntime(
        backend_loader=mutate_after_inspection,
        active_memory_bytes=lambda: 0,
    )

    with pytest.raises(ArtifactEmbeddingError) as caught:
        runtime.load_model(_bert_model_spec(model_dir))

    assert caught.value.code == "embedding_artifact_changed_during_load"


def test_backend_consumes_bound_snapshot_during_repeated_source_aba_swaps(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "aba-bert"
    _write_tiny_bert_checkpoint(model_dir)
    source_weight_path = model_dir / "model.safetensors"
    admitted_bytes = source_weight_path.read_bytes()
    admitted_descriptor = inspect_embedding_artifact(_bert_model_spec(model_dir))
    consumed_bytes: list[bytes] = []

    def swap_source_while_loading(descriptor):
        source_weight_path.write_bytes(b"unbound-replacement")
        try:
            assert descriptor.source_model_path == model_dir.resolve()
            assert descriptor.weight_paths[0] != source_weight_path
            consumed_bytes.append(descriptor.weight_paths[0].read_bytes())
        finally:
            source_weight_path.write_bytes(admitted_bytes)
        return type("LoadedProbeBackend", (), {"dtype": "float32"})()

    runtime = MLXEmbeddingRuntime(
        backend_loader=swap_source_while_loading,
        active_memory_bytes=lambda: 0,
    )

    receipts = [
        runtime.load_model(_bert_model_spec(model_dir))["embedding_load_receipt"]
        for _ in range(8)
    ]

    assert consumed_bytes == [admitted_bytes] * 8
    assert {receipt["model_hash"] for receipt in receipts} == {
        admitted_descriptor.model_hash
    }
    assert {receipt["tokenizer_hash"] for receipt in receipts} == {
        admitted_descriptor.tokenizer_hash
    }


def test_registry_discovers_explicit_local_bert_embedding_artifact(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "models" / "local-bert-embedding"
    model_dir.mkdir(parents=True)
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    (model_dir / "README.md").write_text(
        "---\nlibrary_name: mlx\ntags:\n- sentence-transformers\n---\n",
        encoding="utf-8",
    )
    pooling_dir = model_dir / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {
            "pooling_mode_cls_token": False,
            "pooling_mode_mean_tokens": True,
            "pooling_mode_lasttoken": False,
            "word_embedding_dimension": 4,
        },
    )
    catalog = WorkerModelCatalog(
        environment={"MELIX_MODEL_ROOTS": str(tmp_path / "models")}
    )

    discovered = {model.model_id: model for model in catalog.registry_snapshot().models}
    model = discovered["local-bert-embedding"]

    assert model.model_kind == "embedding"
    assert model.ext["embedding_backend_id"] == "mlx-bert-v1"
    assert model.ext["embedding_execution_kind"] == "artifact"
    assert model.ext["embedding_family_id"] == "bert"
    assert model.ext["embedding_pooling_mode"] == "mean"
    assert model.ext["embedding_normalization"] == "none"
    assert model.ext["embedding_dimensions"] == "4"
    assert model.ext["embedding_vector_kind"] == "single_dense"
    assert model.ext["embedding_input_modalities"] == "text"


@pytest.mark.parametrize(
    ("config_payload", "pooling_payload", "expected_backend"),
    [
        (None, None, None),
        (_loadable_embedding_config(model_type="gpt2"), None, None),
        (
            _loadable_embedding_config(model_type="xlm-roberta"),
            {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
            "mlx-xlmr-v1",
        ),
        (
            _loadable_embedding_config(),
            {"pooling_mode_mean_tokens": False},
            None,
        ),
        (
            _loadable_embedding_config(),
            {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 5},
            None,
        ),
        (
            _loadable_embedding_config(),
            {
                "pooling_mode_mean_tokens": True,
                "pooling_mode_max_tokens": True,
                "word_embedding_dimension": 4,
            },
            None,
        ),
        (
            _loadable_embedding_config(),
            {
                "pooling_mode_weightedmean_tokens": True,
                "word_embedding_dimension": 4,
            },
            None,
        ),
    ],
)
def test_catalog_artifact_metadata_requires_supported_architecture_and_pooling(
    tmp_path: Path,
    config_payload: dict[str, object] | None,
    pooling_payload: dict[str, object] | None,
    expected_backend: str | None,
) -> None:
    _write_json(tmp_path / "tokenizer.json", {"version": "1.0"})
    (tmp_path / "model.safetensors").write_bytes(b"weights")
    if config_payload is not None:
        _write_json(tmp_path / "config.json", config_payload)
    if pooling_payload is not None:
        pooling_dir = tmp_path / "1_Pooling"
        pooling_dir.mkdir()
        _write_json(pooling_dir / "config.json", pooling_payload)

    metadata = model_catalog._artifact_embedding_metadata(
        tmp_path,
        config_payload,
        json_cache={},
    )

    if expected_backend is None:
        assert metadata is None
    else:
        assert metadata is not None
        assert metadata["embedding_backend_id"] == expected_backend
        assert metadata["model_architecture"] == "xlmr"


@pytest.mark.parametrize(
    "unsupported_metadata",
    [
        {"embedding_input_modalities": "text,image"},
        {"embedding_vector_kind": "multi_vector"},
        *[
            {key: {"component_type": "unsupported"}}
            for key in (
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
        ],
    ],
)
def test_catalog_refuses_unsupported_artifact_embedding_output_contracts(
    tmp_path: Path,
    unsupported_metadata: dict[str, object],
) -> None:
    config = _loadable_embedding_config(**unsupported_metadata)
    _write_catalog_embedding_files(tmp_path, config)
    pooling_dir = tmp_path / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )
    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is None


@pytest.mark.parametrize(
    "unsupported_config",
    [
        {"position_embedding_type": "relative_key"},
        {"position_embedding_type": "relative_key_query"},
        {"is_decoder": True},
        {"is_encoder_decoder": True},
        {"add_cross_attention": True},
        {"cross_attention_hidden_size": 4},
        {"hidden_size": 0},
        {"num_attention_heads": 0},
        {"intermediate_size": 0},
        {"vocab_size": 0},
        {"max_position_embeddings": 0},
        {"hidden_size": 5},
        {"hidden_act": "relu"},
    ],
)
def test_catalog_refuses_loader_unsupported_encoder_configs(
    tmp_path: Path,
    unsupported_config: dict[str, object],
) -> None:
    config = _loadable_embedding_config(**unsupported_config)
    _write_catalog_embedding_files(tmp_path, config)
    pooling_dir = tmp_path / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )

    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is None


def test_catalog_and_encoder_share_hidden_activation_normalization(
    tmp_path: Path,
) -> None:
    config = _loadable_embedding_config(hidden_act=" GELU_NEW ")
    _write_catalog_embedding_files(tmp_path, config)
    pooling_dir = tmp_path / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )

    metadata = model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    )
    descriptor = inspect_embedding_artifact(_bert_model_spec(tmp_path))
    encoder_layer = mlx_encoder._EncoderLayer(dict(descriptor.config))

    assert metadata is not None
    assert encoder_layer._hidden_act == "gelu_new"


@pytest.mark.parametrize(
    "missing_key",
    [
        "hidden_size",
        "num_attention_heads",
        "intermediate_size",
        "vocab_size",
        "max_position_embeddings",
    ],
)
def test_catalog_refuses_missing_required_encoder_dimensions(
    tmp_path: Path,
    missing_key: str,
) -> None:
    config = _loadable_embedding_config()
    del config[missing_key]
    _write_catalog_embedding_files(tmp_path, config)
    pooling_dir = tmp_path / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )

    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is None


@pytest.mark.parametrize(
    "missing_filename",
    ["config.json", "model.safetensors", "tokenizer.json"],
)
def test_catalog_requires_loader_compatible_embedding_files(
    tmp_path: Path,
    missing_filename: str,
) -> None:
    config = _loadable_embedding_config()
    _write_catalog_embedding_files(tmp_path, config)
    pooling_dir = tmp_path / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )
    (tmp_path / missing_filename).unlink()

    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is None


def test_catalog_matches_loader_fallback_sidecars_and_refuses_symlinks(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    config = _loadable_embedding_config()
    _write_catalog_embedding_files(model_dir, config)
    pooling_dir = model_dir / "9_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )
    metadata = model_catalog._artifact_embedding_metadata(
        model_dir,
        config,
        json_cache={},
    )
    assert metadata is not None

    symlink_model_dir = tmp_path / "symlink-model"
    symlink_model_dir.mkdir()
    _write_catalog_embedding_files(symlink_model_dir, config)
    (symlink_model_dir / "1_Pooling").symlink_to(pooling_dir, target_is_directory=True)

    assert model_catalog._artifact_embedding_metadata(
        symlink_model_dir,
        config,
        json_cache={},
    ) is None


@pytest.mark.parametrize(
    "symlink_filename",
    ["config.json", "vocab.txt", "extra.safetensors"],
)
def test_catalog_refuses_any_symlinked_embedding_load_input(
    tmp_path: Path,
    symlink_filename: str,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    config = _loadable_embedding_config()
    _write_catalog_embedding_files(model_dir, config)
    pooling_dir = model_dir / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )
    outside_file = tmp_path / f"outside-{symlink_filename}"
    if symlink_filename == "config.json":
        _write_json(outside_file, config)
        (model_dir / symlink_filename).unlink()
    else:
        outside_file.write_bytes(b"outside")
    (model_dir / symlink_filename).symlink_to(outside_file)

    assert model_catalog._artifact_embedding_metadata(
        model_dir,
        config,
        json_cache={},
    ) is None


def test_catalog_rejects_unsupported_active_sentence_transformer_pipeline(
    tmp_path: Path,
) -> None:
    config = _loadable_embedding_config()
    _write_catalog_embedding_files(tmp_path, config)
    pooling_dir = tmp_path / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )
    _write_json(
        tmp_path / "modules.json",
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
            {
                "idx": 2,
                "path": "2_Dense",
                "type": "sentence_transformers.models.Dense",
            },
        ],
    )

    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is None


@pytest.mark.parametrize("normalize_payload", ["{", []])
def test_catalog_rejects_invalid_sentence_transformer_normalize_config(
    tmp_path: Path,
    normalize_payload: object,
) -> None:
    config = _loadable_embedding_config()
    _write_catalog_embedding_files(tmp_path, config)
    pooling_dir = tmp_path / "1_Pooling"
    pooling_dir.mkdir()
    _write_json(
        pooling_dir / "config.json",
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 4},
    )
    normalize_dir = tmp_path / "2_Normalize"
    normalize_dir.mkdir()
    if isinstance(normalize_payload, str):
        (normalize_dir / "config.json").write_text(
            normalize_payload,
            encoding="utf-8",
        )
    else:
        _write_json(normalize_dir / "config.json", normalize_payload)
    _write_json(
        tmp_path / "modules.json",
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            },
            {
                "idx": 1,
                "path": "1_Pooling",
                "type": "sentence_transformers.models.Pooling",
            },
            {
                "idx": 2,
                "path": "2_Normalize",
                "type": "sentence_transformers.models.Normalize",
            },
        ],
    )

    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is None


@pytest.mark.parametrize(
    ("artifact_field", "artifact_value", "override_value", "expected_code"),
    [
        (
            "embedding_input_modalities",
            "text,image",
            "text",
            "embedding_media_artifact_unsupported",
        ),
        (
            "embedding_vector_kind",
            "multi_vector",
            "single_dense",
            "embedding_multi_vector_unsupported",
        ),
    ],
)
def test_runtime_does_not_allow_catalog_ext_to_mask_unsupported_artifact_contract(
    tmp_path: Path,
    artifact_field: str,
    artifact_value: str,
    override_value: str,
    expected_code: str,
) -> None:
    model_dir = tmp_path / "artifact-contract"
    model_dir.mkdir()
    _write_json(
        model_dir / "config.json",
        _loadable_embedding_config(**{artifact_field: artifact_value}),
    )
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    model_spec = _bert_model_spec(model_dir)
    model_spec.ext[artifact_field] = override_value

    with pytest.raises(ArtifactEmbeddingError) as caught:
        inspect_embedding_artifact(model_spec)

    assert caught.value.code == expected_code


def test_catalog_keeps_plain_bert_text_and_rejects_invalid_pooling_sidecar(
    tmp_path: Path,
) -> None:
    models_root = tmp_path / "models"
    model_dir = models_root / "plain-bert"
    model_dir.mkdir(parents=True)
    config = _loadable_embedding_config()
    _write_json(model_dir / "config.json", config)
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")
    (model_dir / "README.md").write_text(
        "---\nlibrary_name: mlx\n---\n",
        encoding="utf-8",
    )

    discovered = {
        model.model_id: model
        for model in WorkerModelCatalog(
            environment={"MELIX_MODEL_ROOTS": str(models_root)}
        ).registry_snapshot().models
    }

    assert discovered["plain-bert"].model_kind == "text"

    pooling_dir = model_dir / "1_Pooling"
    pooling_dir.mkdir()
    (pooling_dir / "config.json").write_text("{", encoding="utf-8")
    assert model_catalog._artifact_embedding_metadata(
        model_dir,
        config,
        json_cache={},
    ) is None


def test_float16_padded_bert_layer_matches_finite_golden_vectors(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "tiny-bert-layer"
    _write_tiny_bert_checkpoint(
        model_dir,
        num_hidden_layers=1,
        dtype="float16",
    )
    runtime = MLXEmbeddingRuntime()

    loaded = runtime.load_model(_bert_model_spec(model_dir))
    vectors = runtime.embed_inputs(loaded, ("alpha beta", "beta"))

    assert vectors[0] == pytest.approx(
        [0.0, 0.0, 0.70710677, -0.70710677],
        abs=0.002,
    )
    assert vectors[1] == pytest.approx(
        [-0.28867513, -0.28867513, 0.8660254, -0.28867513],
        abs=0.002,
    )
    assert all(value == value and abs(value) != float("inf") for row in vectors for value in row)
    assert loaded["embedding_request_receipt"]["dtype"] == "mlx.core.float16"
    assert loaded["embedding_request_receipt"]["forward_count"] == 1


def test_tiny_local_xlmr_checkpoint_matches_independent_golden_vectors(
    tmp_path: Path,
) -> None:
    from transformers import AutoTokenizer

    model_dir = tmp_path / "tiny-xlmr"
    word_embeddings = _write_tiny_xlmr_checkpoint(model_dir)
    inputs = ("alpha beta", "gamma")
    tokenizer = AutoTokenizer.from_pretrained(
        model_dir,
        local_files_only=True,
        trust_remote_code=False,
    )
    encoded = tokenizer(
        inputs,
        padding=True,
        truncation=True,
        max_length=10,
    )
    expected: list[list[float]] = []
    for token_ids, attention_mask in zip(
        encoded["input_ids"],
        encoded["attention_mask"],
        strict=True,
    ):
        active_vectors = [
            word_embeddings[token_id]
            for token_id, active in zip(token_ids, attention_mask, strict=True)
            if active
        ]
        mean = [
            sum(vector[index] for vector in active_vectors) / len(active_vectors)
            for index in range(4)
        ]
        norm = math.sqrt(sum(value * value for value in mean))
        expected.append([value / max(norm, 1e-12) for value in mean])

    runtime = MLXEmbeddingRuntime()
    loaded = runtime.load_model(_xlmr_model_spec(model_dir))
    vectors = runtime.embed_inputs(loaded, inputs)

    assert vectors[0] == pytest.approx(expected[0], abs=1e-5)
    assert vectors[1] == pytest.approx(expected[1], abs=1e-5)
    assert loaded["embedding_load_receipt"]["effective_backend_id"] == "mlx-xlmr-v1"
    assert loaded["embedding_request_receipt"]["forward_count"] == 1


def test_pr_scoped_probes_replay_artifact_embedding_coverage() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    probes = json.loads(
        (repo_root / "infra/perf/pr_scoped_probes.json").read_text(encoding="utf-8")
    )
    probes_by_id = {probe["id"]: probe for probe in probes}
    maintenance_test = (
        "services/mlx-worker-python/tests/test_maintenance_service.py::"
        "test_get_model_info_returns_known_dev_model_metadata"
    )
    maintenance_probe_ids = (
        "maintenance-bench-report-readback",
        "maintenance-percentile-vector-reuse",
        "vlm-batch1-comparison-artifact",
        "vlm-speculative-smoke-probe",
        "maintenance-prompt-shape-vector-repeat",
        "maintenance-benchmark-parameter-normalization-single-convert",
        "maintenance-capability-split-single-strip",
        "upload-receipt-published-files-scandir",
        "model-ops-bundle-artifact-byte-accounting",
    )
    artifact_test_file = (
        "services/mlx-worker-python/tests/test_artifact_embedding_runtime.py"
    )
    registry_contract_test_file = (
        "services/mlx-worker-python/tests/"
        "test_artifact_embedding_registry_contract.py"
    )
    catalog_contract_test_file = (
        "services/mlx-worker-python/tests/"
        "test_artifact_embedding_catalog_contract.py"
    )
    linux_context_probe_ids = (
        "worker-registry-resident-bytes-accumulator",
        "model-registry-plain-local-manifest-stat-elision",
        "model-registry-readme-source-fastpath",
    )
    performance_test_file = (
        "services/mlx-worker-python/tests/test_pr_scoped_performance.py"
    )
    performance_test_names = (
        "test_scope_report_selects_worker_registry_probe",
        "test_scope_report_selects_model_registry_catalog_probe",
        "test_scope_report_selects_embedding_project_digest_probe",
        "test_scope_report_selects_deterministic_embedding_probe",
        "test_scope_report_selects_embedding_core_inputs_probe",
        "test_scope_report_selects_artifact_embedding_batch_probe",
        "test_artifact_embedding_batch_probe_script_emits_metrics",
        "test_artifact_embedding_batch_probe_reports_legacy_base_strategy",
        "test_artifact_embedding_batch_probe_main_emits_metrics",
        "test_registered_probes_expose_focused_commands",
    )
    performance_test_nodes = tuple(
        f"{performance_test_file}::{test_name}"
        for test_name in performance_test_names
    )

    for probe_id in maintenance_probe_ids:
        for command_field in ("test_command", "coverage_command"):
            assert maintenance_test in probes_by_id[probe_id][command_field]
    for probe_id in linux_context_probe_ids:
        for command_field in ("test_command", "coverage_command"):
            assert artifact_test_file not in probes_by_id[probe_id][command_field]
    worker_probe = probes_by_id["worker-registry-resident-bytes-accumulator"]
    assert registry_contract_test_file in worker_probe["watch_globs"]
    for probe_id in (
        "model-registry-plain-local-manifest-stat-elision",
        "model-registry-readme-source-fastpath",
    ):
        assert catalog_contract_test_file in probes_by_id[probe_id]["watch_globs"]
        for command_field in ("test_command", "coverage_command"):
            assert catalog_contract_test_file in probes_by_id[probe_id][command_field]
    for command_field in ("test_command", "coverage_command"):
        assert registry_contract_test_file in worker_probe[command_field]
        artifact_command = probes_by_id["artifact-embedding-batch"][command_field]
        assert artifact_test_file in artifact_command
        assert catalog_contract_test_file in artifact_command
        assert registry_contract_test_file in artifact_command
        assert " --extra mlx " in artifact_command
    contract_probe_ids = (
        *maintenance_probe_ids,
        *linux_context_probe_ids,
    )
    for probe_id in contract_probe_ids:
        for command_field in ("test_command", "coverage_command"):
            command = probes_by_id[probe_id][command_field]
            assert " --extra mlx " in command
            for test_node in performance_test_nodes:
                assert test_node in command, (
                    f"{probe_id}.{command_field} is missing {test_node}"
                )
