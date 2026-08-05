from __future__ import annotations

import json
from pathlib import Path

import pytest

import worker.model_registry.catalog as model_catalog
from worker.model_registry.catalog import WorkerModelCatalog


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _embedding_config(
    *,
    model_type: str = "bert",
    **overrides: object,
) -> dict[str, object]:
    config: dict[str, object] = {
        "model_type": model_type,
        "hidden_size": 4,
        "num_hidden_layers": 1,
        "num_attention_heads": 2,
        "intermediate_size": 4,
        "vocab_size": 7,
        "max_position_embeddings": 16,
        "hidden_act": "gelu",
    }
    config.update(overrides)
    return config


def _write_embedding_files(model_dir: Path, config: dict[str, object]) -> None:
    _write_json(model_dir / "config.json", config)
    _write_json(model_dir / "tokenizer.json", {"version": "1.0"})
    (model_dir / "model.safetensors").write_bytes(b"weights")


def _write_pooling(
    model_dir: Path,
    *,
    dirname: str = "1_Pooling",
    payload: object | None = None,
) -> Path:
    pooling_path = model_dir / dirname / "config.json"
    pooling_path.parent.mkdir()
    _write_json(
        pooling_path,
        payload
        if payload is not None
        else {
            "pooling_mode_mean_tokens": True,
            "word_embedding_dimension": 4,
        },
    )
    return pooling_path


def _modules(*, normalize: bool = False) -> list[dict[str, object]]:
    modules: list[dict[str, object]] = [
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
    ]
    if normalize:
        modules.append(
            {
                "idx": 2,
                "path": "2_Normalize",
                "type": "sentence_transformers.models.Normalize",
            }
        )
    return modules


@pytest.mark.parametrize(
    "modules",
    [
        {"unexpected": "mapping"},
        ["not-a-module"],
        [
            {
                "idx": True,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            }
        ],
        [
            {
                "idx": 1,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            }
        ],
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Unknown",
            }
        ],
        [
            {
                "idx": 0,
                "path": "0_Transformer",
                "type": "sentence_transformers.models.Transformer",
            }
        ],
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
        [
            {
                "idx": 0,
                "path": "",
                "type": "sentence_transformers.models.Transformer",
            }
        ],
    ],
)
def test_catalog_rejects_invalid_sentence_transformer_module_contract(
    tmp_path: Path,
    modules: object,
) -> None:
    _write_json(tmp_path / "modules.json", modules)

    assert model_catalog._artifact_embedding_module_paths(tmp_path) is None


def test_catalog_rejects_unreadable_or_incomplete_sentence_transformer_modules(
    tmp_path: Path,
) -> None:
    modules_path = tmp_path / "modules.json"
    modules_path.write_text("{", encoding="utf-8")
    assert model_catalog._artifact_embedding_module_paths(tmp_path) is None

    _write_json(modules_path, _modules())
    assert model_catalog._artifact_embedding_module_paths(tmp_path) is None

    _write_pooling(tmp_path)
    _write_json(modules_path, _modules(normalize=True))
    assert model_catalog._artifact_embedding_module_paths(tmp_path) is None


def test_catalog_resolves_explicit_and_fallback_sentence_transformer_modules(
    tmp_path: Path,
) -> None:
    pooling_path = _write_pooling(tmp_path)
    normalize_path = tmp_path / "2_Normalize" / "config.json"
    normalize_path.parent.mkdir()
    _write_json(normalize_path, {})
    modules_path = tmp_path / "modules.json"
    _write_json(modules_path, _modules(normalize=True))

    assert model_catalog._artifact_embedding_module_paths(tmp_path) == (
        pooling_path,
        normalize_path,
    )

    modules_path.unlink()
    assert model_catalog._artifact_embedding_module_paths(tmp_path) == (
        pooling_path,
        normalize_path,
    )

    _write_pooling(tmp_path, dirname="9_Pooling")
    assert model_catalog._artifact_embedding_module_paths(tmp_path) is None


def test_catalog_regular_file_guard_rejects_escape_missing_and_directory(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-config.json"
    _write_json(outside, {})
    assert model_catalog._artifact_embedding_regular_file(tmp_path, outside) is False
    assert (
        model_catalog._artifact_embedding_regular_file(
            tmp_path,
            tmp_path / "missing" / "config.json",
        )
        is False
    )
    directory = tmp_path / "directory"
    directory.mkdir()
    assert model_catalog._artifact_embedding_regular_file(tmp_path, directory) is False


def test_catalog_projects_supported_artifact_metadata_and_xlmr_identity(
    tmp_path: Path,
) -> None:
    config = _embedding_config(model_type="xlm-roberta")
    _write_embedding_files(tmp_path, config)
    _write_pooling(tmp_path)

    metadata = model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    )

    assert metadata is not None
    assert metadata["embedding_backend_id"] == "mlx-xlmr-v1"
    assert metadata["embedding_execution_kind"] == "artifact"
    assert metadata["embedding_family_id"] == "xlmr"
    assert metadata["embedding_pooling_mode"] == "mean"
    assert metadata["embedding_normalization"] == "none"
    assert metadata["embedding_dimensions"] == "4"
    assert metadata["embedding_vector_kind"] == "single_dense"
    assert metadata["embedding_input_modalities"] == "text"
    assert metadata["model_architecture"] == "xlmr"


@pytest.mark.parametrize(
    "config",
    [
        None,
        _embedding_config(model_type="gpt2"),
        _embedding_config(position_embedding_type="relative_key"),
        _embedding_config(is_decoder=True),
        _embedding_config(hidden_size=5),
        _embedding_config(num_hidden_layers=1.5),
        _embedding_config(hidden_act="relu"),
        _embedding_config(vision_config={"component_type": "unsupported"}),
        _embedding_config(embedding_input_modalities="text,image"),
        _embedding_config(embedding_vector_kind="multi_vector"),
    ],
)
def test_catalog_refuses_unsupported_artifact_config_contracts(
    tmp_path: Path,
    config: dict[str, object] | None,
) -> None:
    if config is not None:
        _write_embedding_files(tmp_path, config)
        _write_pooling(tmp_path)

    assert (
        model_catalog._artifact_embedding_metadata(
            tmp_path,
            config,
            json_cache={},
        )
        is None
    )


@pytest.mark.parametrize(
    "missing_key",
    [
        "hidden_size",
        "num_hidden_layers",
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
    config = _embedding_config()
    del config[missing_key]
    _write_embedding_files(tmp_path, config)
    _write_pooling(tmp_path)

    assert (
        model_catalog._artifact_embedding_metadata(
            tmp_path,
            config,
            json_cache={},
        )
        is None
    )


@pytest.mark.parametrize(
    "missing_filename",
    ["config.json", "model.safetensors", "tokenizer.json"],
)
def test_catalog_requires_loader_compatible_embedding_files(
    tmp_path: Path,
    missing_filename: str,
) -> None:
    config = _embedding_config()
    _write_embedding_files(tmp_path, config)
    _write_pooling(tmp_path)
    (tmp_path / missing_filename).unlink()

    assert (
        model_catalog._artifact_embedding_metadata(
            tmp_path,
            config,
            json_cache={},
        )
        is None
    )


@pytest.mark.parametrize(
    "auxiliary_filename",
    ["added_tokens.json", "special_tokens_map.json", "tokenizer_config.json"],
)
def test_catalog_refuses_auxiliary_only_tokenizer_artifacts(
    tmp_path: Path,
    auxiliary_filename: str,
) -> None:
    config = _embedding_config()
    _write_embedding_files(tmp_path, config)
    _write_pooling(tmp_path)
    (tmp_path / "tokenizer.json").unlink()
    _write_json(tmp_path / auxiliary_filename, {})

    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is None


@pytest.mark.parametrize(
    "primary_filenames",
    [
        ("tokenizer.json",),
        ("vocab.txt",),
        ("sentencepiece.bpe.model",),
        ("spiece.model",),
        ("tokenizer.model",),
        ("vocab.json", "merges.txt"),
    ],
)
def test_catalog_accepts_supported_primary_tokenizer_artifacts(
    tmp_path: Path,
    primary_filenames: tuple[str, ...],
) -> None:
    config = _embedding_config()
    _write_embedding_files(tmp_path, config)
    _write_pooling(tmp_path)
    (tmp_path / "tokenizer.json").unlink()
    for filename in primary_filenames:
        (tmp_path / filename).write_text("{}", encoding="utf-8")

    assert model_catalog._artifact_embedding_metadata(
        tmp_path,
        config,
        json_cache={},
    ) is not None

    if set(primary_filenames) == {"vocab.json", "merges.txt"}:
        (tmp_path / "merges.txt").unlink()
        assert model_catalog._artifact_embedding_metadata(
            tmp_path,
            config,
            json_cache={},
        ) is None


@pytest.mark.parametrize(
    "pooling_payload",
    [
        {},
        {"pooling_mode_mean_tokens": False},
        {"pooling_mode_mean_tokens": True, "word_embedding_dimension": 5},
        {
            "pooling_mode_mean_tokens": True,
            "pooling_mode_max_tokens": True,
            "word_embedding_dimension": 4,
        },
    ],
)
def test_catalog_refuses_invalid_pooling_contracts(
    tmp_path: Path,
    pooling_payload: object,
) -> None:
    config = _embedding_config()
    _write_embedding_files(tmp_path, config)
    _write_pooling(tmp_path, payload=pooling_payload)

    assert (
        model_catalog._artifact_embedding_metadata(
            tmp_path,
            config,
            json_cache={},
        )
        is None
    )


@pytest.mark.parametrize("normalize_payload", ["{", []])
def test_catalog_refuses_invalid_sentence_transformer_normalize_config(
    tmp_path: Path,
    normalize_payload: object,
) -> None:
    config = _embedding_config()
    _write_embedding_files(tmp_path, config)
    _write_pooling(tmp_path)
    normalize_path = tmp_path / "2_Normalize" / "config.json"
    normalize_path.parent.mkdir()
    if isinstance(normalize_payload, str):
        normalize_path.write_text(normalize_payload, encoding="utf-8")
    else:
        _write_json(normalize_path, normalize_payload)
    _write_json(tmp_path / "modules.json", _modules(normalize=True))

    assert (
        model_catalog._artifact_embedding_metadata(
            tmp_path,
            config,
            json_cache={},
        )
        is None
    )


@pytest.mark.parametrize(
    "symlink_filename",
    ["config.json", "vocab.txt", "extra.safetensors"],
)
def test_catalog_refuses_symlinked_embedding_load_inputs(
    tmp_path: Path,
    symlink_filename: str,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    config = _embedding_config()
    _write_embedding_files(model_dir, config)
    _write_pooling(model_dir)
    outside_file = tmp_path / f"outside-{symlink_filename}"
    if symlink_filename == "config.json":
        _write_json(outside_file, config)
        (model_dir / symlink_filename).unlink()
    else:
        outside_file.write_bytes(b"outside")
    (model_dir / symlink_filename).symlink_to(outside_file)

    assert (
        model_catalog._artifact_embedding_metadata(
            model_dir,
            config,
            json_cache={},
        )
        is None
    )


def test_registry_discovers_explicit_local_bert_embedding_artifact(
    tmp_path: Path,
) -> None:
    models_root = tmp_path / "models"
    model_dir = models_root / "local-bert-embedding"
    model_dir.mkdir(parents=True)
    config = _embedding_config()
    _write_embedding_files(model_dir, config)
    _write_pooling(model_dir)
    (model_dir / "README.md").write_text(
        "---\nlibrary_name: mlx\ntags:\n- sentence-transformers\n---\n",
        encoding="utf-8",
    )

    discovered = {
        model.model_id: model
        for model in WorkerModelCatalog(
            environment={"MELIX_MODEL_ROOTS": str(models_root)}
        ).registry_snapshot().models
    }

    model = discovered["local-bert-embedding"]
    assert model.model_kind == "embedding"
    assert model.ext["embedding_backend_id"] == "mlx-bert-v1"
    assert model.ext["embedding_execution_kind"] == "artifact"


def test_development_catalog_uses_explicit_fixture_and_artifact_identities() -> None:
    fixture = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_MODEL_PATH": "models/xlm-r-base"}
    )
    artifact = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_BACKEND_ID": "mlx-xlmr-v1"}
    )

    assert fixture.ext["embedding_backend_id"] == "deterministic-fixture-v1"
    assert fixture.ext["embedding_family_id"] == "xlmr"
    assert fixture.ext["embedding_execution_kind"] == "fixture"
    assert artifact.ext["embedding_backend_id"] == "mlx-xlmr-v1"
    assert artifact.ext["embedding_family_id"] == "xlmr"
    assert artifact.ext["embedding_execution_kind"] == "artifact"
