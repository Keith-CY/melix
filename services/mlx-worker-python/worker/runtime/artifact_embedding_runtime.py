from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import hashlib
import json
import math
from numbers import Integral
import os
from pathlib import Path
import stat
import tempfile
from threading import Lock
from typing import Any, Protocol

from worker.runtime.artifact_embedding_contract import (
    normalized_embedding_hidden_activation,
    supported_sentence_transformer_pooling_mode,
    unsupported_embedding_encoder_config,
    unsupported_embedding_media_components,
)
from worker.runtime.mlx_executor import MLXRuntimeExecutor


_BACKEND_ARCHITECTURES = {
    "mlx-bert-v1": "bert",
    "mlx-xlmr-v1": "xlmr",
}
_MODEL_TYPE_ARCHITECTURES = {
    "bert": "bert",
    "xlm-roberta": "xlmr",
    "xlm_roberta": "xlmr",
}
_POOLING_MODES = {"cls", "mean", "last_token"}
_NORMALIZATION_MODES = {"l2", "none"}
_REQUEST_RECEIPT_LIMIT = 64
_LOCK_TYPE = type(Lock())
_SENTENCE_TRANSFORMER_MODULE_TYPES = {
    "sentence_transformers.models.Transformer": "Transformer",
    "sentence_transformers.models.Pooling": "Pooling",
    "sentence_transformers.models.Normalize": "Normalize",
}
_TOKENIZER_FILENAMES = (
    "added_tokens.json",
    "merges.txt",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "spiece.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "tokenizer.model",
    "vocab.json",
    "vocab.model",
    "vocab.txt",
)


class ArtifactEmbeddingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class ArtifactEmbeddingDescriptor:
    model_path: Path
    architecture: str
    backend_id: str
    config: Mapping[str, object]
    config_path: Path
    tokenizer_paths: tuple[Path, ...]
    weight_paths: tuple[Path, ...]
    model_hash: str
    tokenizer_hash: str
    pooling_mode: str
    normalization: str
    dimensions: int
    max_length: int
    vector_kind: str
    dtype: str
    estimated_resident_bytes: int
    model_hash_paths: tuple[Path, ...] = ()
    file_identities: tuple[tuple[Path, tuple[int, int, int, int, int]], ...] = ()
    source_model_path: Path | None = None


@dataclass(frozen=True)
class EmbeddingBatchResult:
    vectors: tuple[tuple[float, ...], ...]
    input_token_count: int
    forward_count: int
    dtype: str


class ArtifactEmbeddingTensorOps(Protocol):
    def int_array(self, rows: list[list[int]]) -> Any: ...

    def pool(
        self,
        hidden_states: Any,
        attention_mask: Any,
        *,
        pooling_mode: str,
        normalization: str,
    ) -> Any: ...

    def evaluate(self, value: Any) -> None: ...


class _ArtifactSnapshot:
    def __init__(self, source_model_path: Path) -> None:
        self.source_model_path = source_model_path
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="melix-embedding-artifact-"
        )
        self.model_path = Path(self._temporary_directory.name)
        self._closed = False

    def seal(self) -> None:
        for path in self.model_path.rglob("*"):
            path.chmod(0o500 if path.is_dir() else 0o400)
        self.model_path.chmod(0o500)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.model_path.exists():
            self.model_path.chmod(0o700)
            for path in self.model_path.rglob("*"):
                path.chmod(0o700 if path.is_dir() else 0o600)
        self._temporary_directory.cleanup()


class _ModelSpecSnapshotView:
    def __init__(self, model_spec: Any, model_path: Path) -> None:
        self._model_spec = model_spec
        self.model_path = str(model_path)

    def __getattr__(self, name: str) -> object:
        return getattr(self._model_spec, name)


def _read_json_object(path: Path, *, error_code: str) -> dict[str, object]:
    identity_before = _file_identity(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactEmbeddingError(error_code, f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArtifactEmbeddingError(error_code, f"{path.name} must contain a JSON object.")
    if _file_identity(path) != identity_before:
        raise ArtifactEmbeddingError(
            "embedding_artifact_changed_during_load",
            f"Embedding artifact file {path.name} changed while it was being read.",
        )
    return payload


def _read_json_array(path: Path, *, error_code: str) -> list[object]:
    identity_before = _file_identity(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactEmbeddingError(error_code, f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, list):
        raise ArtifactEmbeddingError(error_code, f"{path.name} must contain a JSON array.")
    if _file_identity(path) != identity_before:
        raise ArtifactEmbeddingError(
            "embedding_artifact_changed_during_load",
            f"Embedding artifact file {path.name} changed while it was being read.",
        )
    return payload


def _require_contained_file(model_path: Path, path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ArtifactEmbeddingError(
            "embedding_artifact_missing",
            f"Cannot resolve embedding artifact file {path.name}: {exc}",
        ) from exc
    if not resolved.is_relative_to(model_path):
        raise ArtifactEmbeddingError(
            "embedding_artifact_path_escape",
            f"Embedding artifact file {path.name} escapes the admitted model directory.",
        )
    if not resolved.is_file():
        raise ArtifactEmbeddingError(
            "embedding_artifact_missing",
            f"Embedding artifact file {path.name} is not a regular file.",
        )
    return resolved


def _file_identity(path: Path) -> tuple[int, int, int, int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise ArtifactEmbeddingError(
            "embedding_artifact_changed_during_load",
            f"Cannot stat embedding artifact file {path.name}: {exc}",
        ) from exc
    return (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )


def _files_hash(paths: tuple[Path, ...], *, root: Path) -> str:
    identities_before = tuple((path, _file_identity(path)) for path in paths)
    digest = hashlib.sha256()
    for path in paths:
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative_path).to_bytes(8, "big"))
        digest.update(relative_path)
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    if any(_file_identity(path) != identity for path, identity in identities_before):
        raise ArtifactEmbeddingError(
            "embedding_artifact_changed_during_load",
            "Embedding artifact files changed while their identity was being computed.",
        )
    return f"sha256:{digest.hexdigest()}"


def _resolved_model_path(model_spec: Any) -> Path:
    raw_model_path = str(getattr(model_spec, "model_path", "") or "").strip()
    if not raw_model_path:
        raise ArtifactEmbeddingError(
            "embedding_artifact_path_missing",
            "Artifact-backed embedding requires a local model path.",
        )
    model_path = Path(raw_model_path).expanduser().resolve()
    if not model_path.is_dir():
        raise ArtifactEmbeddingError(
            "embedding_artifact_path_missing",
            "Artifact-backed embedding model path is not a local directory.",
        )
    return model_path


def _embedding_weight_paths(model_path: Path) -> tuple[Path, ...]:
    weight_paths = tuple(
        _require_contained_file(model_path, candidate)
        for candidate in sorted(model_path.glob("*.safetensors"))
    )
    if not weight_paths:
        raise ArtifactEmbeddingError(
            "embedding_weights_missing",
            "Artifact-backed embedding requires local safetensors weights.",
        )
    return weight_paths


def _resolved_max_length(
    model_spec: Any,
    config: Mapping[str, object],
    tokenizer_config: Mapping[str, object],
    sentence_transformer_config: Mapping[str, object],
) -> int:
    candidates = (
        _positive_int(getattr(model_spec, "max_context", 0)),
        _positive_int(config.get("max_position_embeddings")),
        _positive_int(tokenizer_config.get("model_max_length")),
        _positive_int(sentence_transformer_config.get("max_seq_length")),
    )
    limits = [candidate for candidate in candidates if candidate is not None]
    if not limits:
        raise ArtifactEmbeddingError(
            "embedding_artifact_invalid_max_length",
            "Embedding artifact does not declare a positive maximum length.",
        )
    return min(limits)


def _validated_sentence_transformer_pipeline(
    modules: list[object],
) -> tuple[Mapping[str, object], ...]:
    validated: list[Mapping[str, object]] = []
    stages: list[str] = []
    for position, module in enumerate(modules):
        if not isinstance(module, Mapping):
            raise ArtifactEmbeddingError(
                "embedding_artifact_invalid_modules",
                "Sentence Transformers modules must be JSON objects.",
            )
        module_index = module.get("idx")
        if (
            not isinstance(module_index, Integral)
            or isinstance(module_index, bool)
            or int(module_index) != position
        ):
            raise ArtifactEmbeddingError(
                "embedding_artifact_unsupported_pipeline",
                "Sentence Transformers module indexes must match pipeline order.",
            )
        module_type = str(module.get("type", "") or "").strip()
        stage = _SENTENCE_TRANSFORMER_MODULE_TYPES.get(module_type)
        if stage is None:
            raise ArtifactEmbeddingError(
                "embedding_artifact_unsupported_pipeline",
                f"Unsupported active Sentence Transformers module: {module_type or '<missing>'}.",
            )
        relative_module_path = str(module.get("path", "") or "").strip()
        if stage == "Transformer":
            if relative_module_path not in {"", "."}:
                raise ArtifactEmbeddingError(
                    "embedding_artifact_unsupported_pipeline",
                    "Nested Sentence Transformers Transformer modules are unsupported.",
                )
        elif not relative_module_path:
            raise ArtifactEmbeddingError(
                "embedding_artifact_invalid_modules",
                f"Sentence Transformers {stage} module requires a local path.",
            )
        stages.append(stage)
        validated.append(module)

    if tuple(stages) not in {
        ("Transformer", "Pooling"),
        ("Transformer", "Pooling", "Normalize"),
    }:
        raise ArtifactEmbeddingError(
            "embedding_artifact_unsupported_pipeline",
            "Supported Sentence Transformers pipeline is Transformer -> Pooling -> optional Normalize.",
        )
    return tuple(validated)


def _sentence_transformers_contract(
    model_path: Path,
    *,
    dimensions: int,
) -> tuple[str | None, str | None, tuple[Path, ...]]:
    contract_paths: list[Path] = []
    modules_path = model_path / "modules.json"
    if modules_path.is_file():
        resolved_modules_path = _require_contained_file(model_path, modules_path)
        modules = _validated_sentence_transformer_pipeline(
            _read_json_array(
                resolved_modules_path,
                error_code="embedding_artifact_invalid_modules",
            )
        )
        contract_paths.append(resolved_modules_path)

        def module_paths(module_name: str) -> tuple[Path, ...]:
            paths: list[Path] = []
            for module in modules:
                module_type = str(module.get("type", "") or "")
                if _SENTENCE_TRANSFORMER_MODULE_TYPES[module_type] != module_name:
                    continue
                relative_module_path = str(module.get("path", "") or "").strip()
                paths.append(
                    _require_contained_file(
                        model_path,
                        model_path / relative_module_path / "config.json",
                    )
                )
            return tuple(paths)

        pooling_paths = module_paths("Pooling")
        normalize_paths = module_paths("Normalize")
    else:
        pooling_paths = tuple(
            _require_contained_file(model_path, path)
            for path in sorted(model_path.glob("*_Pooling/config.json"))
        )
        normalize_paths = tuple(
            _require_contained_file(model_path, path)
            for path in sorted(model_path.glob("*_Normalize/config.json"))
        )
    if len(pooling_paths) > 1:
        raise ArtifactEmbeddingError(
            "embedding_pooling_ambiguous",
            "Embedding artifact contains multiple pooling modules.",
        )
    pooling_mode: str | None = None
    if pooling_paths:
        pooling_path = pooling_paths[0]
        pooling_config = _read_json_object(
            pooling_path,
            error_code="embedding_artifact_invalid_pooling_config",
        )
        supported_pooling_mode = supported_sentence_transformer_pooling_mode(
            pooling_config
        )
        if supported_pooling_mode is None:
            raise ArtifactEmbeddingError(
                "embedding_pooling_unsupported",
                "Embedding pooling metadata must enable exactly one supported mode.",
            )
        pooling_dimensions = _positive_int(pooling_config.get("word_embedding_dimension"))
        if pooling_dimensions is not None and pooling_dimensions != dimensions:
            raise ArtifactEmbeddingError(
                "embedding_dimension_mismatch",
                "Embedding pooling dimensions do not match artifact hidden_size.",
            )
        pooling_mode = supported_pooling_mode
        contract_paths.append(pooling_path)

    if len(normalize_paths) > 1:
        raise ArtifactEmbeddingError(
            "embedding_normalization_ambiguous",
            "Embedding artifact contains multiple normalization modules.",
        )
    normalization: str | None = None
    if normalize_paths:
        normalize_path = normalize_paths[0]
        _read_json_object(
            normalize_path,
            error_code="embedding_artifact_invalid_normalization_config",
        )
        normalization = "l2"
        contract_paths.append(normalize_path)
    return pooling_mode, normalization, tuple(contract_paths)


def _snapshot_relative_path(raw_path: str | Path) -> Path:
    relative_path = Path(raw_path)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise ArtifactEmbeddingError(
            "embedding_artifact_path_escape",
            f"Invalid embedding artifact relative path: {raw_path}.",
        )
    return relative_path


def _copy_snapshot_file(
    source_model_path: Path,
    relative_path: str | Path,
    snapshot_model_path: Path,
) -> None:
    relative_path = _snapshot_relative_path(relative_path)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    opened_directories: list[int] = []
    source_fd: int | None = None
    try:
        directory_fd = os.open(source_model_path, directory_flags)
        opened_directories.append(directory_fd)
        for component in relative_path.parts[:-1]:
            directory_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            opened_directories.append(directory_fd)
        source_fd = os.open(relative_path.name, file_flags, dir_fd=directory_fd)
        identity_before = os.fstat(source_fd)
        if not stat.S_ISREG(identity_before.st_mode):
            raise ArtifactEmbeddingError(
                "embedding_artifact_missing",
                f"Embedding artifact file {relative_path} is not a regular file.",
            )

        destination = snapshot_model_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(source_fd, "rb", closefd=False) as source, destination.open("xb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        identity_after = os.fstat(source_fd)
        if (
            identity_before.st_dev,
            identity_before.st_ino,
            identity_before.st_size,
            identity_before.st_mtime_ns,
            identity_before.st_ctime_ns,
        ) != (
            identity_after.st_dev,
            identity_after.st_ino,
            identity_after.st_size,
            identity_after.st_mtime_ns,
            identity_after.st_ctime_ns,
        ):
            raise ArtifactEmbeddingError(
                "embedding_artifact_changed_during_load",
                f"Embedding artifact file {relative_path} changed while it was snapshotted.",
            )
        destination.chmod(0o400)
    except ArtifactEmbeddingError:
        raise
    except OSError as exc:
        raise ArtifactEmbeddingError(
            "embedding_artifact_snapshot_failed",
            f"Cannot snapshot embedding artifact file {relative_path}: {exc}",
        ) from exc
    finally:
        if source_fd is not None:
            os.close(source_fd)
        for directory_fd in reversed(opened_directories):
            os.close(directory_fd)


def _snapshot_embedding_artifact(model_spec: Any) -> _ArtifactSnapshot:
    source_model_path = _resolved_model_path(model_spec)
    snapshot = _ArtifactSnapshot(source_model_path)
    copied_paths: set[Path] = set()

    def copy(relative_path: str | Path) -> None:
        normalized_path = _snapshot_relative_path(relative_path)
        if normalized_path in copied_paths:
            return
        _copy_snapshot_file(source_model_path, normalized_path, snapshot.model_path)
        copied_paths.add(normalized_path)

    try:
        with os.scandir(source_model_path) as entries:
            root_names = {entry.name for entry in entries}
        copy("config.json")
        for filename in _TOKENIZER_FILENAMES:
            if filename in root_names:
                copy(filename)
        for filename in ("modules.json", "sentence_bert_config.json"):
            if filename in root_names:
                copy(filename)
        for filename in sorted(name for name in root_names if name.endswith(".safetensors")):
            copy(filename)

        modules_path = snapshot.model_path / "modules.json"
        if modules_path.is_file():
            modules = _validated_sentence_transformer_pipeline(
                _read_json_array(
                    modules_path,
                    error_code="embedding_artifact_invalid_modules",
                )
            )
            for module in modules:
                stage = _SENTENCE_TRANSFORMER_MODULE_TYPES[str(module["type"])]
                if stage == "Transformer":
                    continue
                module_path = _snapshot_relative_path(str(module.get("path", "")))
                copy(module_path / "config.json")
        else:
            for pattern in ("*_Pooling/config.json", "*_Normalize/config.json"):
                for path in sorted(source_model_path.glob(pattern)):
                    copy(path.relative_to(source_model_path))
        snapshot.seal()
        return snapshot
    except ArtifactEmbeddingError:
        snapshot.close()
        raise
    except OSError as exc:
        snapshot.close()
        raise ArtifactEmbeddingError(
            "embedding_artifact_snapshot_failed",
            f"Cannot create private embedding artifact snapshot: {exc}",
        ) from exc


def inspect_embedding_artifact(model_spec: Any) -> ArtifactEmbeddingDescriptor:
    model_path = _resolved_model_path(model_spec)

    config_path = _require_contained_file(model_path, model_path / "config.json")
    config = _read_json_object(config_path, error_code="embedding_artifact_invalid_config")
    if unsupported_embedding_media_components(config):
        raise ArtifactEmbeddingError(
            "embedding_media_artifact_unsupported",
            "Artifact-backed embeddings do not support media model components.",
        )
    model_type = str(config.get("model_type", "") or "").strip().lower()
    architecture = _MODEL_TYPE_ARCHITECTURES.get(model_type)
    if architecture is None:
        raise ArtifactEmbeddingError(
            "embedding_artifact_unsupported_architecture",
            f"Unsupported embedding artifact model_type: {model_type or '<missing>'}.",
        )
    dimensions = _positive_int(config.get("hidden_size"))
    if dimensions is None:
        raise ArtifactEmbeddingError(
            "embedding_artifact_invalid_dimensions",
            "Embedding artifact hidden_size must be a positive integer.",
        )
    unsupported_config = unsupported_embedding_encoder_config(config)
    if unsupported_config:
        raise ArtifactEmbeddingError(
            "embedding_artifact_unsupported_config",
            "Unsupported embedding encoder configuration: "
            + ", ".join(unsupported_config)
            + ".",
        )

    ext = getattr(model_spec, "ext", {})
    backend_id = str(ext.get("embedding_backend_id", "") or "").strip().lower()
    expected_architecture = _BACKEND_ARCHITECTURES.get(backend_id)
    if expected_architecture is None:
        raise ArtifactEmbeddingError(
            "embedding_backend_unsupported",
            f"Unsupported artifact embedding backend: {backend_id or '<missing>'}.",
        )
    if architecture != expected_architecture:
        raise ArtifactEmbeddingError(
            "embedding_backend_artifact_mismatch",
            f"Backend {backend_id} cannot execute model_type {model_type}.",
        )

    requested_dimensions = _positive_int(ext.get("embedding_dimensions"))
    if requested_dimensions is not None and requested_dimensions != dimensions:
        raise ArtifactEmbeddingError(
            "embedding_dimension_mismatch",
            f"Requested dimensions {requested_dimensions} do not match artifact hidden_size {dimensions}.",
        )

    artifact_pooling, artifact_normalization, contract_paths = _sentence_transformers_contract(
        model_path,
        dimensions=dimensions,
    )
    pooling_mode = (
        str(ext.get("embedding_pooling_mode", "") or "").strip().lower()
        or artifact_pooling
        or "cls"
    )
    if pooling_mode not in _POOLING_MODES:
        raise ArtifactEmbeddingError(
            "embedding_pooling_unsupported",
            f"Unsupported embedding pooling mode: {pooling_mode}.",
        )
    normalization = (
        str(ext.get("embedding_normalization", "") or "").strip().lower()
        or artifact_normalization
        or "none"
    )
    if normalization not in _NORMALIZATION_MODES:
        raise ArtifactEmbeddingError(
            "embedding_normalization_unsupported",
            f"Unsupported embedding normalization: {normalization}.",
        )
    artifact_input_modalities = {
        modality.strip().lower()
        for modality in str(config.get("embedding_input_modalities", "text") or "").split(",")
        if modality.strip()
    }
    requested_input_modalities = {
        modality.strip().lower()
        for modality in str(
            ext.get("embedding_input_modalities", ",".join(sorted(artifact_input_modalities)))
            or ""
        ).split(",")
        if modality.strip()
    }
    if artifact_input_modalities != {"text"} or requested_input_modalities != artifact_input_modalities:
        raise ArtifactEmbeddingError(
            "embedding_media_artifact_unsupported",
            "Artifact-backed embeddings currently support text-only input artifacts.",
        )

    tokenizer_paths = tuple(
        _require_contained_file(model_path, candidate)
        for filename in _TOKENIZER_FILENAMES
        if (candidate := model_path / filename).exists()
    )
    if not tokenizer_paths:
        raise ArtifactEmbeddingError(
            "embedding_tokenizer_missing",
            "Artifact-backed embedding requires local tokenizer files.",
        )
    tokenizer_config_path = model_path / "tokenizer_config.json"
    tokenizer_config = (
        _read_json_object(
            tokenizer_config_path,
            error_code="embedding_artifact_invalid_tokenizer_config",
        )
        if tokenizer_config_path.is_file()
        else {}
    )
    sentence_transformer_config_path = model_path / "sentence_bert_config.json"
    sentence_transformer_config = (
        _read_json_object(
            sentence_transformer_config_path,
            error_code="embedding_artifact_invalid_sentence_transformer_config",
        )
        if sentence_transformer_config_path.is_file()
        else {}
    )
    if sentence_transformer_config:
        contract_paths = (*contract_paths, _require_contained_file(model_path, sentence_transformer_config_path))

    weight_paths = _embedding_weight_paths(model_path)

    artifact_vector_kind = str(
        config.get("embedding_vector_kind", "single_dense") or ""
    ).strip().lower()
    vector_kind = str(
        ext.get("embedding_vector_kind", artifact_vector_kind) or ""
    ).strip().lower()
    if artifact_vector_kind != "single_dense" or vector_kind != artifact_vector_kind:
        raise ArtifactEmbeddingError(
            "embedding_multi_vector_unsupported",
            f"Unsupported embedding vector kind: {vector_kind}.",
        )
    dtype = str(config.get("torch_dtype", "") or "float32").strip().lower()
    estimated_resident_bytes = sum(path.stat().st_size for path in weight_paths)
    model_hash_paths = (config_path, *contract_paths, *weight_paths)
    identity_paths = tuple(dict.fromkeys((*model_hash_paths, *tokenizer_paths)))
    model_hash = _files_hash(model_hash_paths, root=model_path)
    tokenizer_hash = _files_hash(tokenizer_paths, root=model_path)
    file_identities = tuple((path, _file_identity(path)) for path in identity_paths)
    return ArtifactEmbeddingDescriptor(
        model_path=model_path,
        architecture=architecture,
        backend_id=backend_id,
        config=config,
        config_path=config_path,
        tokenizer_paths=tokenizer_paths,
        weight_paths=weight_paths,
        model_hash=model_hash,
        tokenizer_hash=tokenizer_hash,
        pooling_mode=pooling_mode,
        normalization=normalization,
        dimensions=dimensions,
        max_length=_resolved_max_length(
            model_spec,
            config,
            tokenizer_config,
            sentence_transformer_config,
        ),
        vector_kind=vector_kind,
        dtype=dtype,
        estimated_resident_bytes=estimated_resident_bytes,
        model_hash_paths=model_hash_paths,
        file_identities=file_identities,
        source_model_path=model_path,
    )


def verify_embedding_artifact_identity(descriptor: ArtifactEmbeddingDescriptor) -> None:
    if not descriptor.file_identities:
        return
    if any(
        _file_identity(path) != expected
        for path, expected in descriptor.file_identities
    ):
        raise ArtifactEmbeddingError(
            "embedding_artifact_changed_during_load",
            "Embedding artifact files changed after admission and before load completed.",
        )
    if _files_hash(descriptor.model_hash_paths, root=descriptor.model_path) != descriptor.model_hash:
        raise ArtifactEmbeddingError(
            "embedding_artifact_changed_during_load",
            "Embedding model bytes no longer match the admitted model hash.",
        )
    if _files_hash(descriptor.tokenizer_paths, root=descriptor.model_path) != descriptor.tokenizer_hash:
        raise ArtifactEmbeddingError(
            "embedding_artifact_changed_during_load",
            "Embedding tokenizer bytes no longer match the admitted tokenizer hash.",
        )


def embedding_request_receipt_snapshot(
    loaded_model: object,
) -> dict[str, object] | None:
    if not isinstance(loaded_model, Mapping):
        return None
    lock = loaded_model.get("_embedding_request_receipt_lock")
    if not isinstance(lock, _LOCK_TYPE):
        receipt = loaded_model.get("embedding_request_receipt")
        return dict(receipt) if isinstance(receipt, Mapping) else None
    with lock:
        receipt = loaded_model.get("embedding_request_receipt")
        return dict(receipt) if isinstance(receipt, Mapping) else None


def _record_embedding_request_receipt(
    loaded_model: dict[str, object],
    *,
    request_id: str,
    receipt: dict[str, object],
) -> None:
    lock = loaded_model.get("_embedding_request_receipt_lock")
    if not isinstance(lock, _LOCK_TYPE):
        lock = Lock()
        loaded_model["_embedding_request_receipt_lock"] = lock
    with lock:
        receipts = loaded_model.get("embedding_request_receipts")
        if not isinstance(receipts, OrderedDict):
            receipts = OrderedDict()
            loaded_model["embedding_request_receipts"] = receipts
        sequence = int(loaded_model.get("_embedding_request_receipt_sequence", 0)) + 1
        loaded_model["_embedding_request_receipt_sequence"] = sequence
        receipt_key = request_id or f"anonymous-{sequence}"
        receipt_copy = dict(receipt)
        if request_id:
            receipt_copy["request_id"] = request_id
        receipts[receipt_key] = receipt_copy
        receipts.move_to_end(receipt_key)
        while len(receipts) > _REQUEST_RECEIPT_LIMIT:
            receipts.popitem(last=False)
        loaded_model["embedding_request_receipt"] = dict(receipt_copy)


def _mlx_active_memory_bytes() -> int:
    try:
        import mlx.core as mx
    except ImportError:
        return 0
    get_active_memory = getattr(mx, "get_active_memory", mx.metal.get_active_memory)
    return int(get_active_memory())


def finite_attention_mask_bias(attention_mask: Any, dtype: Any) -> Any:
    import mlx.core as mx

    active = attention_mask.astype(mx.bool_)
    zero = mx.array(0.0, dtype=dtype)
    sentinel = mx.array(mx.finfo(dtype).min, dtype=dtype)
    return mx.where(active[:, None, None, :], zero, sentinel)


def pool_mlx_hidden_states(
    hidden_states: Any,
    attention_mask: Any,
    *,
    pooling_mode: str,
    normalization: str,
) -> Any:
    import mlx.core as mx

    active = attention_mask.astype(mx.bool_)
    batch_size, sequence_length, _ = hidden_states.shape
    positions = mx.broadcast_to(mx.arange(sequence_length), (batch_size, sequence_length))
    if pooling_mode == "cls":
        selected_positions = mx.argmax(active, axis=1)
        pooled = hidden_states[mx.arange(batch_size), selected_positions]
    elif pooling_mode == "mean":
        float_hidden = hidden_states.astype(mx.float32)
        weights = active.astype(mx.float32)[..., None]
        counts = mx.sum(weights, axis=1)
        pooled = mx.sum(float_hidden * weights, axis=1) / counts
    elif pooling_mode == "last_token":
        selected_positions = mx.max(mx.where(active, positions, -1), axis=1)
        pooled = hidden_states[mx.arange(batch_size), selected_positions]
    else:
        raise ArtifactEmbeddingError(
            "embedding_pooling_unsupported",
            f"Unsupported embedding pooling mode: {pooling_mode}.",
        )

    pooled = pooled.astype(mx.float32)
    if normalization == "l2":
        norms = mx.linalg.norm(pooled, axis=1, keepdims=True)
        pooled = pooled / mx.maximum(norms, mx.array(1e-12, dtype=mx.float32))
    elif normalization != "none":
        raise ArtifactEmbeddingError(
            "embedding_normalization_unsupported",
            f"Unsupported embedding normalization: {normalization}.",
        )
    return pooled


class _MLXEmbeddingTensorOps:
    def int_array(self, rows: list[list[int]]) -> Any:
        import mlx.core as mx

        return mx.array(rows, dtype=mx.int32)

    def pool(
        self,
        hidden_states: Any,
        attention_mask: Any,
        *,
        pooling_mode: str,
        normalization: str,
    ) -> Any:
        return pool_mlx_hidden_states(
            hidden_states,
            attention_mask,
            pooling_mode=pooling_mode,
            normalization=normalization,
        )

    def evaluate(self, value: Any) -> None:
        import mlx.core as mx

        mx.eval(value)


def _nested_int_rows(value: object, *, field_name: str) -> list[list[int]]:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    if not isinstance(value, (list, tuple)):
        raise ArtifactEmbeddingError(
            "embedding_tokenizer_output_invalid",
            f"Tokenizer field {field_name} must be a rank-2 array.",
        )
    rows: list[list[int]] = []
    for raw_row in value:
        if not isinstance(raw_row, (list, tuple)):
            raise ArtifactEmbeddingError(
                "embedding_tokenizer_output_invalid",
                f"Tokenizer field {field_name} must be a rank-2 array.",
            )
        row: list[int] = []
        for item in raw_row:
            if not isinstance(item, Integral) or isinstance(item, bool):
                raise ArtifactEmbeddingError(
                    "embedding_tokenizer_output_invalid",
                    f"Tokenizer field {field_name} must contain integral values.",
                )
            row.append(int(item))
        rows.append(row)
    return rows


class MLXArtifactEmbeddingBackend:
    def __init__(
        self,
        *,
        tokenizer: object,
        encoder: object,
        dtype: str | None = None,
        tensor_ops: ArtifactEmbeddingTensorOps | None = None,
    ) -> None:
        self._tokenizer = tokenizer
        self._encoder = encoder
        self.dtype = dtype
        self._tensor_ops = tensor_ops or _MLXEmbeddingTensorOps()
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._tokenizer = None
        self._encoder = None

    def embed_batch(
        self,
        inputs: Any,
        descriptor: ArtifactEmbeddingDescriptor,
    ) -> EmbeddingBatchResult:
        if self._closed:
            raise ArtifactEmbeddingError(
                "embedding_backend_closed",
                "Embedding backend is closed.",
            )
        batch_size = len(inputs)
        if batch_size == 0:
            return EmbeddingBatchResult(
                vectors=(),
                input_token_count=0,
                forward_count=0,
                dtype=descriptor.dtype,
            )
        encoded = self._tokenizer(
            inputs,
            padding=True,
            truncation=True,
            max_length=descriptor.max_length,
            return_tensors="np",
        )
        if not isinstance(encoded, Mapping):
            raise ArtifactEmbeddingError(
                "embedding_tokenizer_output_invalid",
                "Embedding tokenizer must return a mapping.",
            )
        if "input_ids" not in encoded or "attention_mask" not in encoded:
            raise ArtifactEmbeddingError(
                "embedding_tokenizer_output_invalid",
                "Embedding tokenizer output requires input_ids and attention_mask.",
            )
        input_ids_rows = _nested_int_rows(encoded["input_ids"], field_name="input_ids")
        attention_mask_rows = _nested_int_rows(
            encoded["attention_mask"],
            field_name="attention_mask",
        )
        if len(input_ids_rows) != batch_size or len(attention_mask_rows) != batch_size:
            raise ArtifactEmbeddingError(
                "embedding_tokenizer_row_count_invalid",
                "Embedding tokenizer row count does not match the request batch.",
            )
        sequence_length = len(input_ids_rows[0]) if input_ids_rows else 0
        if sequence_length == 0 or any(
            len(row) != sequence_length
            for row in (*input_ids_rows, *attention_mask_rows)
        ) or any(
            len(input_row) != len(mask_row)
            for input_row, mask_row in zip(input_ids_rows, attention_mask_rows, strict=True)
        ):
            raise ArtifactEmbeddingError(
                "embedding_tokenizer_shape_invalid",
                "Embedding tokenizer returned inconsistent token and mask shapes.",
            )
        active_token_counts = [sum(1 for value in row if value != 0) for row in attention_mask_rows]
        if any(count == 0 for count in active_token_counts):
            raise ArtifactEmbeddingError(
                "embedding_fully_padded_input",
                "Embedding tokenizer produced a fully padded input row.",
            )

        input_ids = self._tensor_ops.int_array(input_ids_rows)
        attention_mask = self._tensor_ops.int_array(attention_mask_rows)
        encoder_kwargs: dict[str, object] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        token_type_ids = encoded.get("token_type_ids")
        if token_type_ids is not None:
            token_type_rows = _nested_int_rows(token_type_ids, field_name="token_type_ids")
            if len(token_type_rows) != batch_size:
                raise ArtifactEmbeddingError(
                    "embedding_tokenizer_row_count_invalid",
                    "Embedding tokenizer token_type_ids do not match the request batch.",
                )
            if any(len(row) != sequence_length for row in token_type_rows):
                raise ArtifactEmbeddingError(
                    "embedding_tokenizer_shape_invalid",
                    "Embedding tokenizer token_type_ids do not match the token sequence shape.",
                )
            encoder_kwargs["token_type_ids"] = self._tensor_ops.int_array(
                token_type_rows
            )
        hidden_states = self._encoder(**encoder_kwargs)
        if isinstance(hidden_states, Mapping):
            hidden_states = hidden_states.get("last_hidden_state")
        elif isinstance(hidden_states, tuple):
            hidden_states = hidden_states[0] if hidden_states else None
        if hidden_states is None:
            raise ArtifactEmbeddingError(
                "embedding_encoder_output_invalid",
                "Embedding encoder did not return token hidden states.",
            )
        vectors = self._tensor_ops.pool(
            hidden_states,
            attention_mask,
            pooling_mode=descriptor.pooling_mode,
            normalization=descriptor.normalization,
        )
        self._tensor_ops.evaluate(vectors)
        return EmbeddingBatchResult(
            vectors=tuple(tuple(float(value) for value in row) for row in vectors.tolist()),
            input_token_count=sum(active_token_counts),
            forward_count=1,
            dtype=str(hidden_states.dtype),
        )


class MLXEmbeddingRuntime:
    runtime_name = "mlx-embedding"

    def __init__(
        self,
        *,
        backend_loader: Callable[[ArtifactEmbeddingDescriptor], object] | None = None,
        active_memory_bytes: Callable[[], int] | None = None,
        executor: MLXRuntimeExecutor | None = None,
    ) -> None:
        self._backend_loader = backend_loader or _load_default_mlx_backend
        self._active_memory_bytes = active_memory_bytes or _mlx_active_memory_bytes
        self._executor = executor

    def estimate_resident_bytes(self, model_spec: Any) -> int:
        model_path = _resolved_model_path(model_spec)
        return sum(path.stat().st_size for path in _embedding_weight_paths(model_path))

    @staticmethod
    def estimate_loaded_resident_bytes(loaded_model: Mapping[str, object]) -> int:
        receipt = loaded_model.get("embedding_load_receipt")
        if not isinstance(receipt, Mapping):
            raise ArtifactEmbeddingError(
                "embedding_load_receipt_invalid",
                "Artifact embedding load is missing its snapshot-bound receipt.",
            )
        estimated = receipt.get("estimated_resident_bytes")
        if (
            not isinstance(estimated, Integral)
            or isinstance(estimated, bool)
            or int(estimated) < 0
        ):
            raise ArtifactEmbeddingError(
                "embedding_load_receipt_invalid",
                "Artifact embedding load receipt has an invalid resident-byte estimate.",
            )
        return int(estimated)

    def load_model(self, model_spec: Any) -> dict[str, object]:
        if self._executor is not None:
            return self._executor.run(lambda: self._load_model(model_spec))
        return self._load_model(model_spec)

    def _load_model(self, model_spec: Any) -> dict[str, object]:
        snapshot = _snapshot_embedding_artifact(model_spec)
        backend: object | None = None
        try:
            descriptor = inspect_embedding_artifact(
                _ModelSpecSnapshotView(model_spec, snapshot.model_path)
            )
            descriptor = replace(
                descriptor,
                source_model_path=snapshot.source_model_path,
            )
            memory_before = self._active_memory_bytes()
            backend = self._backend_loader(descriptor)
            verify_embedding_artifact_identity(descriptor)
            memory_after = self._active_memory_bytes()
        except Exception:
            close = getattr(backend, "close", None)
            if callable(close):
                close()
            raise
        finally:
            snapshot.close()
        ext = getattr(model_spec, "ext", {})
        requested_dimensions = _positive_int(ext.get("embedding_dimensions")) or descriptor.dimensions
        requested_max_length = _positive_int(getattr(model_spec, "max_context", 0)) or descriptor.max_length
        effective_dtype = str(getattr(backend, "dtype", "") or descriptor.dtype)
        receipt: dict[str, object] = {
            "requested_backend_id": str(ext.get("embedding_backend_id", "") or "").strip(),
            "effective_backend_id": descriptor.backend_id,
            "model_hash": descriptor.model_hash,
            "tokenizer_hash": descriptor.tokenizer_hash,
            "requested_pooling_mode": str(ext.get("embedding_pooling_mode", "") or "").strip(),
            "effective_pooling_mode": descriptor.pooling_mode,
            "requested_normalization": str(ext.get("embedding_normalization", "") or "").strip(),
            "effective_normalization": descriptor.normalization,
            "requested_dimensions": requested_dimensions,
            "effective_dimensions": descriptor.dimensions,
            "requested_max_length": requested_max_length,
            "effective_max_length": descriptor.max_length,
            "requested_vector_kind": str(
                ext.get("embedding_vector_kind", "") or ""
            ).strip(),
            "effective_vector_kind": descriptor.vector_kind,
            "requested_dtype": descriptor.dtype,
            "effective_dtype": effective_dtype,
            "vector_kind": descriptor.vector_kind,
            "dtype": effective_dtype,
            "estimated_resident_bytes": descriptor.estimated_resident_bytes,
            "measured_resident_bytes": max(0, memory_after - memory_before),
        }
        return {
            "model_id": getattr(model_spec, "model_id", ""),
            "dimensions": descriptor.dimensions,
            "embedding_backend_id": descriptor.backend_id,
            "embedding_backend": backend,
            "embedding_artifact_descriptor": descriptor,
            "embedding_load_receipt": receipt,
            "_embedding_request_receipt_lock": Lock(),
            "embedding_request_receipts": OrderedDict(),
            "_embedding_request_receipt_sequence": 0,
        }

    def embed_inputs(
        self,
        loaded_model: dict[str, object],
        inputs: Any,
        *,
        request_id: str = "",
    ) -> list[list[float]]:
        if self._executor is not None:
            return self._executor.run(
                lambda: self._embed_inputs(
                    loaded_model,
                    inputs,
                    request_id=request_id,
                )
            )
        return self._embed_inputs(loaded_model, inputs, request_id=request_id)

    def _embed_inputs(
        self,
        loaded_model: dict[str, object],
        inputs: Any,
        *,
        request_id: str,
    ) -> list[list[float]]:
        descriptor = loaded_model.get("embedding_artifact_descriptor")
        backend = loaded_model.get("embedding_backend")
        if not isinstance(descriptor, ArtifactEmbeddingDescriptor) or backend is None:
            raise ArtifactEmbeddingError(
                "embedding_model_handle_invalid",
                "Loaded embedding model is missing its artifact backend.",
            )
        embed_batch = getattr(backend, "embed_batch", None)
        if not callable(embed_batch):
            raise ArtifactEmbeddingError(
                "embedding_backend_unavailable",
                "Loaded embedding backend does not implement batched execution.",
            )

        input_batch = list(inputs)
        batch_size = len(input_batch)
        result = embed_batch(input_batch, descriptor)
        if not isinstance(result, EmbeddingBatchResult):
            raise ArtifactEmbeddingError(
                "embedding_backend_contract_invalid",
                "Embedding backend returned an invalid batch result.",
            )
        expected_forward_count = 1 if batch_size else 0
        if result.forward_count != expected_forward_count:
            raise ArtifactEmbeddingError(
                "embedding_forward_count_invalid",
                f"Embedding batch performed {result.forward_count} forwards; expected {expected_forward_count}.",
            )
        if len(result.vectors) != batch_size:
            raise ArtifactEmbeddingError(
                "embedding_output_row_count_invalid",
                f"Embedding backend returned {len(result.vectors)} rows for batch size {batch_size}.",
            )

        vectors: list[list[float]] = []
        for row in result.vectors:
            if len(row) != descriptor.dimensions:
                raise ArtifactEmbeddingError(
                    "embedding_output_dimension_invalid",
                    f"Embedding backend returned dimension {len(row)}; expected {descriptor.dimensions}.",
                )
            vector = [float(value) for value in row]
            if not all(math.isfinite(value) for value in vector):
                raise ArtifactEmbeddingError(
                    "embedding_output_nonfinite",
                    "Embedding backend returned a non-finite vector value.",
                )
            vectors.append(vector)

        receipt = {
            "backend_id": descriptor.backend_id,
            "batch_size": batch_size,
            "input_token_count": max(0, int(result.input_token_count)),
            "forward_count": result.forward_count,
            "output_row_count": len(vectors),
            "dimensions": descriptor.dimensions,
            "vector_kind": descriptor.vector_kind,
            "dtype": result.dtype,
            "finite_output": True,
        }
        _record_embedding_request_receipt(
            loaded_model,
            request_id=request_id,
            receipt=receipt,
        )
        return vectors

    def close_loaded_model(self, loaded_model: dict[str, object]) -> None:
        backend = loaded_model.get("embedding_backend")
        close = getattr(backend, "close", None)
        if not callable(close):
            return
        if self._executor is None:
            close()
        else:
            self._executor.run(close)


def _load_default_mlx_backend(descriptor: ArtifactEmbeddingDescriptor) -> object:
    try:
        from worker.runtime.mlx_embedding_encoder import load_mlx_artifact_backend
    except ImportError as exc:
        raise ArtifactEmbeddingError(
            "embedding_backend_unavailable",
            "MLX embedding backend dependencies are unavailable.",
        ) from exc
    return load_mlx_artifact_backend(descriptor)
