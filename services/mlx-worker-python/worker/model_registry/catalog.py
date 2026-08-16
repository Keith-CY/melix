from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import Iterable, Mapping

from packages.protocol.python.worker.v1 import common_pb2
from worker.runtime.artifact_embedding_contract import (
    has_supported_embedding_tokenizer_files,
    supported_sentence_transformer_pooling_mode,
    unsupported_embedding_encoder_config,
    unsupported_embedding_media_components,
)
from worker.runtime.image_family_adapters import (
    detect_image_family_identity,
    resolve_image_family_config,
)
from worker.runtime.text_family_adapters import (
    detect_text_family_identity,
    resolve_text_family_config,
)
from worker.runtime.vision_family_adapters import resolve_vision_family_config
from worker.model_registry.dflash_metadata import dflash_draft_metadata

_ADAPTER_SET_HASH_KEY = "melix.adapter_set_hash"
_CAPABILITY_ROUTE_KIND_KEY = "melix.capability.route_kind"
_CAPABILITY_CLASS_KEY = "melix.capability.class"
_CAPABILITY_SUPPORTED_MODALITIES_KEY = "melix.capability.supported_modalities"
_CAPABILITY_SUPPORTED_TASKS_KEY = "melix.capability.supported_tasks"
_CAPABILITY_SUPPORTED_PARSERS_KEY = "melix.capability.supported_parsers"
_REGISTRY_ROOTS_ENV_KEY = "MELIX_MODEL_ROOTS"
_MANAGED_MODEL_ROOT_ENV_KEY = "MELIX_MANAGED_MODEL_ROOT"
_REGISTRY_PROVIDER_ID_KEY = "melix.registry_provider_id"
_REGISTRY_ORGANIZATION_ID_KEY = "melix.registry_organization_id"
_REGISTRY_MODEL_NAME_KEY = "melix.registry_model_name"
_REGISTRY_VARIANT_ID_KEY = "melix.registry_variant_id"
_TEXT_BACKEND_ID_KEY = "text_backend_id"
_AUDIO_BACKEND_ID_KEY = "melix.audio.backend_id"
_AUDIO_FAMILY_ID_KEY = "melix.audio.family_id"
_AUDIO_INSTALL_PROFILE_KEY = "melix.audio.install_profile"
_AUDIO_LANGUAGES_KEY = "melix.audio.languages"
_AUDIO_VOICE_MODE_KEY = "melix.audio.voice_mode"
_AUDIO_OUTPUT_FORMATS_KEY = "melix.audio.output_formats"
_AUDIO_SUPPORTS_INSTRUCTIONS_KEY = "melix.audio.supports_instructions"
_AUDIO_VOICE_CATALOG_SUMMARY_KEY = "melix.audio.voice_catalog_summary"
_AUDIO_VOICE_LOCALES_KEY = "melix.audio.voice_locales"
_AUDIO_DEFAULT_LOCALE_KEY = "melix.audio.default_locale"
_AUDIO_PACKAGED_DEFAULT_LOCALE_KEY = "melix.audio.packaged_default_locale"
_AUDIO_LOCALE_POLICY_KEY = "melix.audio.locale_policy"
_GENERATION_CONFIG_SOURCE_KEY = "melix.generation_config.source"
_GENERATION_CONFIG_TEMPERATURE_KEY = "melix.generation_config.temperature"
_GENERATION_CONFIG_TOP_P_KEY = "melix.generation_config.top_p"
_GENERATION_CONFIG_TOP_K_KEY = "melix.generation_config.top_k"
_GENERATION_CONFIG_MAX_TOKENS_KEY = "melix.generation_config.max_tokens"
_GENERATION_CONFIG_DO_SAMPLE_KEY = "melix.generation_config.do_sample"
_REGISTRY_SCAN_PRUNED_DIR_NAMES = frozenset({"blobs", ".git", "__pycache__"})
_HF_CACHE_REPO_PREFIX = "models--"
_HF_CACHE_REPO_PREFIX_LEN = len(_HF_CACHE_REPO_PREFIX)
_HF_CACHE_PRUNED_SUBTREE_NAMES = frozenset({"snapshots", "refs"})
_MODEL_INVENTORY_SOURCE_DESCRIPTOR_SCHEMA = "melix.model_inventory_source_descriptor.v1"
_SOURCE_KIND_MELIX_MANAGED_ROOT = "melix_managed_root"
_SOURCE_KIND_HUGGINGFACE_CACHE = "huggingface_cache"
_SOURCE_KIND_MODELSCOPE_CACHE = "modelscope_cache"
_SOURCE_KIND_OLLAMA_STORE = "ollama_store"
_SOURCE_KIND_LM_STUDIO_STORE = "lm_studio_store"
_MODEL_INVENTORY_SCAN_RECEIPT_SCHEMA = "melix.model_inventory_scan_receipt.v1"
_MODEL_INVENTORY_CLASSIFICATION_SCHEMA = "melix.model_inventory_classification.v1"
_MODEL_INVENTORY_SOURCE_KINDS = (
    _SOURCE_KIND_MELIX_MANAGED_ROOT,
    _SOURCE_KIND_HUGGINGFACE_CACHE,
    _SOURCE_KIND_MODELSCOPE_CACHE,
    _SOURCE_KIND_OLLAMA_STORE,
    _SOURCE_KIND_LM_STUDIO_STORE,
)
_MODEL_WEIGHT_FILE_SUFFIXES = (".safetensors", ".npz")
_MODEL_WEIGHT_FILE_SUFFIX_LAST_CHARS = frozenset("sz")
_ARTIFACT_EMBEDDING_TOKENIZER_FILENAMES = (
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
_ARTIFACT_EMBEDDING_MODULE_TYPES = {
    "sentence_transformers.models.Transformer": "Transformer",
    "sentence_transformers.models.Pooling": "Pooling",
    "sentence_transformers.models.Normalize": "Normalize",
}
_REGISTRY_SCAN_SENTINEL_FILENAMES = frozenset(
    {
        "manifest.json",
        "config.json",
        "generation_config.json",
        "tokenizer_config.json",
        "model.safetensors.index.json",
    }
)
_SECRET_LIKE_PATTERN = re.compile(
    r"(?i)(?:token|secret|api[_-]?key|authorization|bearer|hf_[a-z0-9]{8,})"
)
_GEMMA4_QAT_AUTOMATIC_ORG = "mlx-community"
_GEMMA4_QAT_AUTOMATIC_SCOPE = "mlx-community-gemma4-q4"
_GEMMA4_QAT_BASE_MODEL_MARKER = "base_model:"
_GEMMA4_QAT_BASE_MODEL_MARKER_LEN = len(_GEMMA4_QAT_BASE_MODEL_MARKER)
_GEMMA4_QAT_BASE_MODEL_STRIP_CHARS = " \t\r\n'\"[]"
_GEMMA4_QAT_QUOTED_BASE_MODEL_PREFIX_LEN = len("\n  '")
_GEMMA4_QAT_QUOTED_BASE_MODEL_MARKER = "\n  'base_model:"
_GEMMA4_QAT_QUOTED_BASE_MODEL_MARKER_LEN = len(_GEMMA4_QAT_QUOTED_BASE_MODEL_MARKER)
_GEMMA4_QAT_SIZE_NAMES = {
    "e2b": "E2B",
    "e4b": "E4B",
    "12b": "12B",
    "26b-a4b": "26B-A4B",
}
_GEMMA4_QAT_DRAFT_COMPANION_RECOVERY_HINT = (
    "Download or select a compatible Gemma 4 QAT draft companion."
)
_JSON_LOADS = json.loads


@dataclass(frozen=True, slots=True)
class RegistryRootSnapshot:
    root_id: str
    root_path: str
    root_order: int
    accessible: bool
    error_code: str = ""
    error_message: str = ""
    discovered_model_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelInventorySourceDescriptor:
    descriptor_id: str
    source_kind: str
    display_name: str
    ownership: str
    requested_roots: tuple[str, ...]
    effective_roots: tuple[str, ...]
    path_policy: Mapping[str, object]
    discovery_policy: Mapping[str, object]
    receipt_policy: Mapping[str, object]
    redaction_policy: Mapping[str, object]
    failure_modes: tuple[str, ...]
    catalog_policy: Mapping[str, object] = field(default_factory=dict)
    pull_policy: Mapping[str, object] = field(default_factory=dict)
    metrics_policy: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = _MODEL_INVENTORY_SOURCE_DESCRIPTOR_SCHEMA

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "descriptor_id": self.descriptor_id,
            "source_kind": self.source_kind,
            "display_name": self.display_name,
            "ownership": self.ownership,
            "requested_roots": list(self.requested_roots),
            "effective_roots": list(self.effective_roots),
            "path_policy": dict(self.path_policy),
            "discovery_policy": dict(self.discovery_policy),
            "receipt_policy": dict(self.receipt_policy),
            "redaction_policy": dict(self.redaction_policy),
            "failure_modes": list(self.failure_modes),
            "catalog_policy": dict(self.catalog_policy),
            "pull_policy": dict(self.pull_policy),
            "metrics_policy": dict(self.metrics_policy),
        }


@dataclass(frozen=True, slots=True)
class ModelInventoryClassification:
    source_kind: str
    source_descriptor_id: str
    source_model_id: str
    model_id: str
    model_path: str
    file_layout: str
    family_signal: str
    mlx_compatibility: str
    trainability: str
    exportability: str
    missing_file_state: str
    estimated_size_bytes: int
    artifact_state: str
    usable_state: str
    operator_message: str
    remediation: str
    metrics: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = _MODEL_INVENTORY_CLASSIFICATION_SCHEMA

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
            "source_descriptor_id": self.source_descriptor_id,
            "source_model_id": self.source_model_id,
            "model_id": self.model_id,
            "model_path": self.model_path,
            "file_layout": self.file_layout,
            "family_signal": self.family_signal,
            "mlx_compatibility": self.mlx_compatibility,
            "trainability": self.trainability,
            "exportability": self.exportability,
            "missing_file_state": self.missing_file_state,
            "estimated_size_bytes": self.estimated_size_bytes,
            "artifact_state": self.artifact_state,
            "usable_state": self.usable_state,
            "operator_message": self.operator_message,
            "remediation": self.remediation,
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True, slots=True)
class ModelInventorySourceScanReceipt:
    descriptor_id: str
    source_kind: str
    requested_root: str
    effective_root: str
    root_redaction: Mapping[str, object]
    root_path_digest: str
    accessible: bool
    scan_status: str
    failure_code: str
    failure_message: str
    discovered_model_count: int
    usable_model_count: int
    unsupported_model_count: int
    incomplete_model_count: int
    ambiguous_model_count: int
    invalid_entry_count: int
    redaction_count: int
    scan_latency_ms: float
    payload_byte_size: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "descriptor_id": self.descriptor_id,
            "source_kind": self.source_kind,
            "requested_root": self.requested_root,
            "effective_root": self.effective_root,
            "root_redaction": dict(self.root_redaction),
            "root_path_digest": self.root_path_digest,
            "accessible": self.accessible,
            "scan_status": self.scan_status,
            "failure_code": self.failure_code,
            "failure_message": self.failure_message,
            "discovered_model_count": self.discovered_model_count,
            "usable_model_count": self.usable_model_count,
            "unsupported_model_count": self.unsupported_model_count,
            "incomplete_model_count": self.incomplete_model_count,
            "ambiguous_model_count": self.ambiguous_model_count,
            "invalid_entry_count": self.invalid_entry_count,
            "redaction_count": self.redaction_count,
            "scan_latency_ms": round(self.scan_latency_ms, 3),
            "payload_byte_size": self.payload_byte_size,
        }


@dataclass(frozen=True, slots=True)
class ModelInventoryScanReceipt:
    scan_id: str
    started_at_unix_ms: int
    completed_at_unix_ms: int
    requested_sources: tuple[Mapping[str, object], ...]
    effective_sources: tuple[Mapping[str, object], ...]
    source_receipts: tuple[ModelInventorySourceScanReceipt, ...]
    discovered_models: tuple[ModelInventoryClassification, ...]
    summary: Mapping[str, object]
    redaction_summary: Mapping[str, object]
    metrics: Mapping[str, object]
    schema_version: str = _MODEL_INVENTORY_SCAN_RECEIPT_SCHEMA

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scan_id": self.scan_id,
            "started_at_unix_ms": self.started_at_unix_ms,
            "completed_at_unix_ms": self.completed_at_unix_ms,
            "requested_sources": [dict(source) for source in self.requested_sources],
            "effective_sources": [dict(source) for source in self.effective_sources],
            "source_receipts": [
                source_receipt.to_payload()
                for source_receipt in self.source_receipts
            ],
            "discovered_models": [
                classification.to_payload()
                for classification in self.discovered_models
            ],
            "summary": dict(self.summary),
            "redaction_summary": dict(self.redaction_summary),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    roots: tuple[RegistryRootSnapshot, ...]
    models: tuple[common_pb2.ModelSpec, ...]
    scanned_at_unix_ms: int
    source_descriptors: tuple[ModelInventorySourceDescriptor, ...] = ()
    scan_started_at_unix_ms: int = 0
    scan_id: str = ""
    hf_cache_roots: frozenset[str] = frozenset()
    candidate_findings: tuple[_InventoryScanCandidate, ...] = ()
    aggregated_invalid_entry_counts: Mapping[str, int] = field(default_factory=dict)
    root_scan_latency_ms: Mapping[str, float] = field(default_factory=dict)
    scan_receipt: ModelInventoryScanReceipt | None = None
    model_classifications: Mapping[str, ModelInventoryClassification] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _PlainLocalModelScan:
    model_dir: Path
    has_model_weight_files: bool
    has_generation_config: bool
    has_tokenizer_config: bool
    estimated_size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class _InventoryScanCandidate:
    root_path: str
    model_id: str
    source_model_id: str
    model_path: str
    file_layout: str
    family_signal: str
    mlx_compatibility: str
    trainability: str
    exportability: str
    missing_file_state: str
    estimated_size_bytes: int
    artifact_state: str
    usable_state: str
    operator_message: str
    remediation: str
    metrics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _InventoryClassificationRecord:
    root_path: str
    invalid_entry: bool
    classification: ModelInventoryClassification


@dataclass(slots=True)
class _RegistryScanResult:
    roots: list[RegistryRootSnapshot]
    discovered_models: dict[str, common_pb2.ModelSpec]
    hf_cache_roots: frozenset[str]
    candidate_findings: list[_InventoryScanCandidate]
    aggregated_invalid_entry_counts: dict[str, int]
    root_scan_latency_ms: dict[str, float]


@dataclass(frozen=True, slots=True)
class _TensorIndexEvidence:
    source_path: str
    status: str
    modalities: tuple[str, ...]
    tensor_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class _ProjectorEvidence:
    status: str
    family_id: str
    components_available: bool = True


def _normalized(value: str | None) -> str:
    return (value or "").strip()


def _normalized_generation_config_value(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _load_json_dict_file(
    path: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> dict[str, object]:
    try:
        stat_result = path.stat()
    except OSError:
        if json_cache is not None:
            json_cache.pop(path, None)
        return {}

    if not stat.S_ISREG(stat_result.st_mode):
        if json_cache is not None:
            json_cache.pop(path, None)
        return {}

    if json_cache is not None:
        cached_entry = json_cache.get(path)
        if cached_entry is not None:
            cached_mtime_ns, cached_size, cached_payload = cached_entry
            if cached_mtime_ns == stat_result.st_mtime_ns and cached_size == stat_result.st_size:
                return cached_payload

    try:
        payload = _JSON_LOADS(path.read_bytes())
    except (OSError, json.JSONDecodeError):
        payload = {}

    if not isinstance(payload, dict):
        payload = {}
    if json_cache is not None:
        json_cache[path] = (stat_result.st_mtime_ns, stat_result.st_size, payload)
    return payload


def _merge_generation_config_metadata(
    model_dir: Path,
    *,
    ext: dict[str, str],
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    known_present: bool | None = None,
) -> None:
    generation_config_path = model_dir / "generation_config.json"
    if known_present is False:
        if json_cache is not None:
            json_cache.pop(generation_config_path, None)
        return
    payload = _load_json_dict_file(generation_config_path, json_cache=json_cache)
    if not payload:
        return

    recognized_values = {
        _GENERATION_CONFIG_TEMPERATURE_KEY: payload.get("temperature"),
        _GENERATION_CONFIG_TOP_P_KEY: payload.get("top_p"),
        _GENERATION_CONFIG_TOP_K_KEY: payload.get("top_k"),
        _GENERATION_CONFIG_MAX_TOKENS_KEY: payload.get("max_new_tokens"),
        _GENERATION_CONFIG_DO_SAMPLE_KEY: payload.get("do_sample"),
    }
    imported_any = False
    for ext_key, raw_value in recognized_values.items():
        if _normalized(ext.get(ext_key)):
            continue
        normalized_value = _normalized_generation_config_value(raw_value)
        if normalized_value is None:
            continue
        ext[ext_key] = normalized_value
        imported_any = True

    if imported_any and not _normalized(ext.get(_GENERATION_CONFIG_SOURCE_KEY)):
        ext[_GENERATION_CONFIG_SOURCE_KEY] = str(generation_config_path)


def _load_model_config_payload(
    model_dir: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> dict[str, object]:
    config_path = model_dir / "config.json"
    return _load_json_dict_file(config_path, json_cache=json_cache)


_CONTEXT_WINDOW_KEYS = (
    "max_position_embeddings",
    "max_seq_len",
    "max_seq_length",
    "seq_length",
    "n_positions",
)
_TEXT_CONTEXT_CONFIG_KEYS = ("text_config", "language_config", "llm_config")
_TOKENIZER_MAX_LENGTH_SENTINEL = 10**18


def _config_context_window(config_payload: Mapping[str, object] | None) -> tuple[int, str]:
    if not isinstance(config_payload, Mapping):
        return 0, ""

    for key in _CONTEXT_WINDOW_KEYS:
        value = _positive_int_value(config_payload.get(key))
        if value > 0:
            return value, f"config.{key}"

    for config_key in _TEXT_CONTEXT_CONFIG_KEYS:
        nested = config_payload.get(config_key)
        if not isinstance(nested, Mapping):
            continue
        for key in _CONTEXT_WINDOW_KEYS:
            value = _positive_int_value(nested.get(key))
            if value > 0:
                return value, f"config.{config_key}.{key}"

    return 0, ""


def _tokenizer_context_window(
    model_dir: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> tuple[int, str]:
    tokenizer_payload = _load_json_dict_file(model_dir / "tokenizer_config.json", json_cache=json_cache)
    value = _positive_int_value(tokenizer_payload.get("model_max_length"))
    if 0 < value < _TOKENIZER_MAX_LENGTH_SENTINEL:
        return value, "tokenizer_config.model_max_length"
    return 0, ""


def _model_context_window(
    model_dir: Path,
    config_payload: Mapping[str, object] | None,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    has_tokenizer_config: bool | None = None,
) -> tuple[int, str]:
    config_value, config_source = _config_context_window(config_payload)
    if config_value > 0:
        return config_value, config_source
    if has_tokenizer_config is False:
        return 0, ""
    return _tokenizer_context_window(model_dir, json_cache=json_cache)


def _load_tensor_index_payload(
    model_dir: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> tuple[Path, dict[str, object], str]:
    index_path = model_dir / "model.safetensors.index.json"
    try:
        stat_result = index_path.stat()
    except OSError:
        if json_cache is not None:
            json_cache.pop(index_path, None)
        return index_path, {}, "missing_tensor_index"
    if not stat.S_ISREG(stat_result.st_mode):
        if json_cache is not None:
            json_cache.pop(index_path, None)
        return index_path, {}, "missing_tensor_index"

    payload = _load_json_dict_file(index_path, json_cache=json_cache)
    if not payload:
        return index_path, {}, "malformed_tensor_index"
    weight_map = payload.get("weight_map")
    if not isinstance(weight_map, Mapping):
        return index_path, {}, "malformed_tensor_index"
    return index_path, payload, ""


def _tensor_index_evidence(
    model_dir: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> _TensorIndexEvidence:
    index_path, payload, warning_code = _load_tensor_index_payload(model_dir, json_cache=json_cache)
    if warning_code:
        return _TensorIndexEvidence(
            source_path=str(index_path),
            status=warning_code,
            modalities=(),
            tensor_counts={},
        )

    weight_map = payload.get("weight_map")
    if not isinstance(weight_map, Mapping):
        return _TensorIndexEvidence(
            source_path=str(index_path),
            status="malformed_tensor_index",
            modalities=(),
            tensor_counts={},
        )

    counts = {
        "text": 0,
        "vision": 0,
        "audio": 0,
        "video": 0,
        "projector": 0,
        "draft": 0,
    }
    for raw_name in weight_map:
        name = str(raw_name)
        if _tensor_name_is_vision(name):
            counts["vision"] += 1
        elif _tensor_name_is_audio(name):
            counts["audio"] += 1
        elif _tensor_name_is_video(name):
            counts["video"] += 1
        else:
            # Lowercase once and reuse for the projector/draft checks that need it
            # instead of recomputing it inside each helper.
            lowered = name.lower()
            if _tensor_name_is_projector(name, lowered):
                counts["projector"] += 1
            elif _tensor_name_is_draft(name, lowered):
                counts["draft"] += 1
            elif _tensor_name_is_text(name):
                counts["text"] += 1

    modalities = tuple(
        modality
        for modality in ("text", "vision", "audio", "video", "projector", "draft")
        if counts[modality] > 0
    )
    return _TensorIndexEvidence(
        source_path=str(index_path),
        status="ok",
        modalities=modalities,
        tensor_counts={key: value for key, value in counts.items() if value > 0},
    )


def _weight_map_tensor_names(
    model_dir: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> tuple[str, ...]:
    _, payload, warning_code = _load_tensor_index_payload(model_dir, json_cache=json_cache)
    if warning_code:
        return ()
    weight_map = payload.get("weight_map")
    if not isinstance(weight_map, Mapping):
        return ()
    return tuple(str(raw_name) for raw_name in weight_map)


def _tensor_name_is_vision(name: str) -> bool:
    return name.startswith(("vision_tower.", "vision_model.", "embed_vision.", "visual.", "vision_encoder."))


def _tensor_name_is_audio(name: str) -> bool:
    return name.startswith(("audio_tower.", "audio_model.", "embed_audio.", "audio_encoder."))


def _tensor_name_is_video(name: str) -> bool:
    return name.startswith(("video_tower.", "video_model.", "embed_video.", "video_encoder."))


def _tensor_name_is_projector(name: str, lowered: str | None = None) -> bool:
    if lowered is None:
        lowered = name.lower()
    return (
        name.startswith(("multi_modal_projector.", "multimodal_projector.", "mm_projector.", "projector."))
        or ".multi_modal_projector." in lowered
        or ".multimodal_projector." in lowered
        or ".mm_projector." in lowered
    )


def _tensor_name_is_gemma4_vision_weight_remap(name: str, lowered: str | None = None) -> bool:
    if name.startswith("embed_vision.proj."):
        return True
    if lowered is None:
        lowered = name.lower()
    return ".embed_vision.proj." in lowered


def _tensor_name_is_draft(name: str, lowered: str | None = None) -> bool:
    if lowered is None:
        lowered = name.lower()
    return name.startswith(("draft_model.", "mtp.", "dflash.")) or ".draft_" in lowered or ".mtp_" in lowered


def _tensor_name_is_text(name: str) -> bool:
    return name.startswith(
        (
            "model.",
            "language_model.",
            "text_model.",
            "text_config.",
            "transformer.",
            "lm_head.",
        )
    )


def _has_model_weight_files(model_dir: Path) -> bool:
    index_path = model_dir / "model.safetensors.index.json"
    if index_path.is_file():
        payload = _load_json_dict_file(index_path)
        weight_map = payload.get("weight_map")
        if not isinstance(weight_map, Mapping) or not weight_map:
            return False
        shard_names = {str(shard).strip() for shard in weight_map.values()}
        shard_names.discard("")
        if not shard_names:
            return False
        return all((model_dir / shard_name).is_file() for shard_name in shard_names)
    try:
        with os.scandir(os.fspath(model_dir)) as entries:
            for entry in entries:
                if not entry.name.endswith(_MODEL_WEIGHT_FILE_SUFFIXES):
                    continue
                try:
                    if entry.is_file():
                        return True
                except OSError:
                    continue
    except OSError:
        return False
    return False


def _read_text_prefix(
    path: Path,
    *,
    max_chars: int = 16_384,
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] | None = None,
) -> str:
    try:
        stat_result = path.stat()
    except OSError:
        if text_prefix_cache is not None:
            text_prefix_cache.pop(path, None)
        return ""

    if not stat.S_ISREG(stat_result.st_mode):
        if text_prefix_cache is not None:
            text_prefix_cache.pop(path, None)
        return ""

    if text_prefix_cache is not None:
        cached_entry = text_prefix_cache.get(path)
        if cached_entry is not None:
            cached_mtime_ns, cached_size, cached_mode, cached_max_chars, cached_payload = cached_entry
            if (
                cached_mtime_ns == stat_result.st_mtime_ns
                and cached_size == stat_result.st_size
                and cached_mode == stat_result.st_mode
                and cached_max_chars >= max_chars
            ):
                return cached_payload[:max_chars]

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            payload = handle.read(max_chars)
    except OSError:
        if text_prefix_cache is not None:
            text_prefix_cache.pop(path, None)
        return ""

    if text_prefix_cache is not None:
        text_prefix_cache[path] = (stat_result.st_mtime_ns, stat_result.st_size, stat_result.st_mode, max_chars, payload)
    return payload


def _metadata_text_has_mlx_signal(metadata_text: str) -> bool:
    if "mlx" not in metadata_text:
        return False
    return (
        "library_name: mlx" in metadata_text
        or '"library_name": "mlx"' in metadata_text
        or "\n- mlx" in metadata_text
        or "\n  - mlx" in metadata_text
        or '"mlx"' in metadata_text and '"tags"' in metadata_text
    )


def _metadata_payload_has_mlx_signal(metadata_payload: Mapping[str, object]) -> bool:
    if _metadata_payload_has_direct_mlx_signal(metadata_payload):
        return True
    try:
        metadata_text = json.dumps(metadata_payload).lower()
    except (TypeError, ValueError):
        return False
    return _metadata_text_has_mlx_signal(metadata_text)


def _metadata_payload_has_direct_mlx_signal(metadata_payload: Mapping[str, object]) -> bool:
    library_name = metadata_payload.get("library_name")
    if isinstance(library_name, str):
        if library_name == "mlx":
            return True
        if library_name.strip().lower() == "mlx":
            return True

    tags = metadata_payload.get("tags")
    if isinstance(tags, (list, tuple)):
        for tag in tags:
            if isinstance(tag, str):
                if tag == "mlx":
                    return True
                if tag.strip().lower() == "mlx":
                    return True
    return False


def _has_mlx_signal(
    *,
    model_dir: Path,
    repo_id: str = "",
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] | None = None,
    config_payload: Mapping[str, object] | None = None,
) -> bool:
    lowered_repo_id = repo_id.lower()
    lowered_path = model_dir.name.lower()
    if repo_id.startswith("mlx-community/") or "mlx" in lowered_repo_id or "mlx" in lowered_path:
        return True

    for metadata_filename in ("README.md", "config.json", "model_index.json"):
        if metadata_filename == "config.json" and config_payload is not None and config_payload:
            if _metadata_payload_has_direct_mlx_signal(config_payload):
                return True
            try:
                config_payload_text = json.dumps(config_payload).lower()
            except (TypeError, ValueError):
                config_payload_text = ""
            else:
                if _metadata_text_has_mlx_signal(config_payload_text):
                    return True
                continue
        metadata_text = _read_text_prefix(
            model_dir / metadata_filename,
            text_prefix_cache=text_prefix_cache,
        ).lower()
        if metadata_text and _metadata_text_has_mlx_signal(metadata_text):
            return True
    return False


def _hf_cache_repo_id(cache_repo_dir: Path) -> str | None:
    name = cache_repo_dir.name
    if not name.startswith(_HF_CACHE_REPO_PREFIX):
        return None
    separator_index = name.find("--", _HF_CACHE_REPO_PREFIX_LEN)
    suffix_index = separator_index + 2
    if (
        separator_index == -1
        or separator_index == _HF_CACHE_REPO_PREFIX_LEN
        or suffix_index == len(name)
    ):
        return None
    return f"{name[_HF_CACHE_REPO_PREFIX_LEN:separator_index]}/{name[suffix_index:]}"


def _sorted_child_directories(root: Path, *, name_prefix: str | None = None) -> tuple[Path, ...]:
    child_names: list[str] = []
    try:
        with os.scandir(os.fspath(root)) as entries:
            for entry in entries:
                if name_prefix is not None and not entry.name.startswith(name_prefix):
                    continue
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                child_names.append(entry.name)
    except OSError:
        return ()
    return tuple(root / name for name in sorted(child_names))


def _inventory_receipt_policy(*, source_kind: str) -> dict[str, object]:
    return {
        "schema_version": "melix.model_inventory_receipt.v1",
        "source_kind": source_kind,
        "root_fields": [
            "root_id",
            "root_path",
            "root_order",
            "accessible",
            "error_code",
            "error_message",
            "discovered_model_ids",
        ],
        "model_fields": [
            "model_id",
            "model_path",
            "revision",
            "melix.source_kind",
            "melix.registry_root_id",
            "melix.registry_relative_path",
        ],
        "scan_fields": [
            "scanned_at_unix_ms",
            "requested_roots",
            "effective_roots",
            "descriptor_id",
        ],
    }


def _inventory_redaction_policy() -> dict[str, object]:
    return {
        "path_fields": [
            "requested_roots",
            "effective_roots",
            "root_path",
            "model_path",
            "melix.model_path",
            "melix.registry_root_path",
            "melix.registry_descriptor_path",
        ],
        "redaction": "preserve_basename_and_digest_absolute_prefix",
        "digest": "sha256",
        "secret_fields": [
            "token",
            "authorization",
            "cookie",
            "api_key",
        ],
    }


def _inventory_metrics_policy() -> dict[str, object]:
    return {
        "counters": [
            "source_count",
            "requested_source_root_count",
            "effective_source_root_count",
            "invalid_source_count",
            "redaction_count",
            "discovered_model_count",
            "usable_model_count",
            "unsupported_model_count",
            "incomplete_model_count",
            "ambiguous_model_count",
        ],
        "timers": [
            "source_scan_latency_ms",
            "catalog_scan_latency_ms",
            "classification_latency_ms",
            "pull_cancel_latency_ms",
            "partial_artifact_cleanup_latency_ms",
        ],
        "sizes": [
            "discovery_receipt_byte_size",
            "catalog_result_count",
        ],
    }


def _source_descriptor_id_for_kind(source_kind: str) -> str:
    if source_kind == _SOURCE_KIND_HUGGINGFACE_CACHE:
        return "huggingface-cache"
    if source_kind == _SOURCE_KIND_MODELSCOPE_CACHE:
        return "modelscope-cache"
    if source_kind == _SOURCE_KIND_OLLAMA_STORE:
        return "ollama-store"
    if source_kind == _SOURCE_KIND_LM_STUDIO_STORE:
        return "lm-studio-store"
    return "melix-managed-root"


def _inventory_path_digest(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def _redacted_inventory_path(path: str) -> tuple[dict[str, object], int, str]:
    normalized = path.strip()
    digest = _inventory_path_digest(normalized)
    if not normalized:
        return {"strategy": "empty", "display": "", "redacted": False}, 0, digest
    basename = Path(normalized).name or normalized
    redacted = os.path.isabs(normalized)
    if _SECRET_LIKE_PATTERN.search(normalized):
        basename = "<secret-redacted>"
        redacted = True
    display = f"{basename}#{digest}" if redacted else normalized
    return {
        "strategy": "basename_sha256_16" if redacted else "unchanged",
        "display": display,
        "redacted": redacted,
    }, 1 if redacted else 0, digest


def _inventory_redacted_value(value: str) -> tuple[str, int]:
    redaction, count, _ = _redacted_inventory_path(value)
    return str(redaction["display"]), count


def _inventory_nonnegative_int(value: object) -> int:
    try:
        return max(0, int(_normalized(str(value))))
    except (TypeError, ValueError):
        return 0


def _family_signal_from_config(config_payload: Mapping[str, object] | None) -> str:
    if not isinstance(config_payload, Mapping):
        return "unknown"
    model_type = _normalized(str(config_payload.get("model_type") or ""))
    if model_type:
        return model_type
    text_config = config_payload.get("text_config")
    if isinstance(text_config, Mapping):
        text_model_type = _normalized(str(text_config.get("model_type") or ""))
        if text_model_type:
            return text_model_type
    architectures = config_payload.get("architectures")
    if isinstance(architectures, (list, tuple)) and architectures:
        first = _normalized(str(architectures[0] or ""))
        if first:
            return first
    return "unknown"


def _file_layout_for_model(model: common_pb2.ModelSpec) -> str:
    source_kind = _normalized(model.ext.get("melix.source_kind"))
    if source_kind == "hf_cache_snapshot":
        return "huggingface_snapshot"
    if source_kind == "local_mlx_directory":
        return "plain_mlx_directory"
    if _normalized(model.ext.get("melix.registry_descriptor_path")):
        return "melix_manifest"
    return "unknown"


def _source_kind_for_model(model: common_pb2.ModelSpec) -> str:
    source_kind = _normalized(model.ext.get("melix.source_kind"))
    if source_kind == "hf_cache_snapshot":
        return _SOURCE_KIND_HUGGINGFACE_CACHE
    return _SOURCE_KIND_MELIX_MANAGED_ROOT


def _source_model_id_for_model(model: common_pb2.ModelSpec) -> str:
    source_kind = _normalized(model.ext.get("melix.source_kind"))
    if source_kind == "hf_cache_snapshot":
        revision = _normalized(model.ext.get("melix.hf_revision")) or model.revision
        return f"{model.model_id}@{revision}"
    relative_path = _normalized(model.ext.get("melix.registry_relative_path"))
    return relative_path or model.model_id


def _classification_for_admitted_model(model: common_pb2.ModelSpec) -> ModelInventoryClassification:
    source_kind = _source_kind_for_model(model)
    model_path = model.model_path or model.ext.get("melix.model_path", "")
    redacted_model_path, model_path_redaction_count = _inventory_redacted_value(model_path)
    redacted_source_model_id, source_model_redaction_count = _inventory_redacted_value(
        _source_model_id_for_model(model)
    )
    family_signal = (
        _normalized(model.ext.get("detected_family_id"))
        or _normalized(model.ext.get("text_family_id"))
        or _normalized(model.ext.get("vision_family_id"))
        or _normalized(model.ext.get("embedding_family_id"))
        or _normalized(model.ext.get("rerank_family_id"))
        or _normalized(model.ext.get("melix.audio.family_id"))
        or model.model_kind
        or "unknown"
    )
    missing_file_state = "complete"
    artifact_state = "ready"
    usable_state = "usable"
    mlx_compatibility = "compatible"
    operator_message = "Model is usable by Melix."
    remediation = ""
    if model.ext.get("melix.model_path_missing") == "true":
        missing_file_state = "missing_companion"
        artifact_state = "incomplete"
        usable_state = "incomplete"
        mlx_compatibility = "unknown"
        operator_message = "Model manifest points at a missing runtime path."
        remediation = "Restore the missing model path or remove the stale manifest."
    pull_state = _normalized(model.ext.get("melix.pull_state"))
    if pull_state == "cancelled":
        artifact_state = "cancelled_pull"
        usable_state = "incomplete"
        operator_message = "Model pull was cancelled before admission completed."
        remediation = "Restart the pull or remove the cancelled artifact receipt."
    elif pull_state in {"partial_cleanup_pending", "partial_cleanup_done"}:
        artifact_state = pull_state
        usable_state = "incomplete"
        operator_message = "Model pull left partial artifacts."
        remediation = "Review cleanup evidence before retrying the pull."

    training_ready = _normalized(model.ext.get("melix.lora.training_ready"))
    if training_ready == "true":
        trainability = "trainable"
    elif model.model_kind in {"text", "vlm"}:
        trainability = "adapter_only"
    elif training_ready == "false":
        trainability = "not_trainable"
    else:
        trainability = "unknown"

    exportability = "exportable" if usable_state == "usable" else "unknown"

    return ModelInventoryClassification(
        source_kind=source_kind,
        source_descriptor_id=_source_descriptor_id_for_kind(source_kind),
        source_model_id=redacted_source_model_id,
        model_id=model.model_id,
        model_path=redacted_model_path,
        file_layout=_file_layout_for_model(model),
        family_signal=family_signal,
        mlx_compatibility=mlx_compatibility,
        trainability=trainability,
        exportability=exportability,
        missing_file_state=missing_file_state,
        estimated_size_bytes=_inventory_nonnegative_int(model.ext.get("melix.estimated_size_bytes")),
        artifact_state=artifact_state,
        usable_state=usable_state,
        operator_message=operator_message,
        remediation=remediation,
        metrics={
            "classification_latency_ms": 0.0,
            "max_context": model.max_context,
            "redaction_count": model_path_redaction_count + source_model_redaction_count,
        },
    )


def _classification_record_from_candidate(
    candidate: _InventoryScanCandidate,
    *,
    source_kind: str,
    invalid_entry: bool = False,
) -> _InventoryClassificationRecord:
    redacted_model_path, model_path_redaction_count = _inventory_redacted_value(candidate.model_path)
    redacted_source_model_id, source_model_redaction_count = _inventory_redacted_value(
        candidate.source_model_id
    )
    metrics = dict(candidate.metrics)
    metrics["redaction_count"] = (
        int(metrics.get("redaction_count", 0) or 0)
        + model_path_redaction_count
        + source_model_redaction_count
    )
    classification = ModelInventoryClassification(
        source_kind=source_kind,
        source_descriptor_id=_source_descriptor_id_for_kind(source_kind),
        source_model_id=redacted_source_model_id,
        model_id=candidate.model_id,
        model_path=redacted_model_path,
        file_layout=candidate.file_layout,
        family_signal=candidate.family_signal,
        mlx_compatibility=candidate.mlx_compatibility,
        trainability=candidate.trainability,
        exportability=candidate.exportability,
        missing_file_state=candidate.missing_file_state,
        estimated_size_bytes=candidate.estimated_size_bytes,
        artifact_state=candidate.artifact_state,
        usable_state=candidate.usable_state,
        operator_message=candidate.operator_message,
        remediation=candidate.remediation,
        metrics=metrics,
    )
    return _InventoryClassificationRecord(
        root_path=candidate.root_path,
        invalid_entry=invalid_entry,
        classification=classification,
    )


def _scan_status_for_counts(
    *,
    accessible: bool,
    failure_code: str,
    unsupported_model_count: int,
    incomplete_model_count: int,
    ambiguous_model_count: int,
    invalid_entry_count: int,
) -> str:
    if not accessible:
        return "failed" if failure_code else "skipped"
    if unsupported_model_count or incomplete_model_count or ambiguous_model_count or invalid_entry_count:
        return "completed_with_warnings"
    return "completed"


def _payload_size_bytes(payload: Mapping[str, object]) -> int:
    try:
        return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _iter_relative_file_paths_sorted(root: Path, *, prefix: str = "") -> Iterable[tuple[Path, str]]:
    try:
        with os.scandir(os.fspath(root)) as entries:
            child_entries = sorted(entries, key=lambda entry: entry.name)
    except OSError as exc:
        raise OSError(str(exc)) from exc

    for entry in child_entries:
        try:
            if entry.is_dir():
                child_prefix = f"{prefix}{entry.name}/"
                yield from _iter_relative_file_paths_sorted(root / entry.name, prefix=child_prefix)
                continue
            if entry.is_file():
                yield root / entry.name, f"{prefix}{entry.name}"
        except OSError as exc:
            raise OSError(str(exc)) from exc



def _hf_cache_revision_map(
    cache_repo_dir: Path,
    *,
    snapshot_ids: set[str] | None = None,
) -> dict[str, str]:
    refs_dir = cache_repo_dir / "refs"
    revisions: dict[str, str] = {}
    remaining_snapshot_ids = set(snapshot_ids) if snapshot_ids is not None else None
    if remaining_snapshot_ids is not None and not remaining_snapshot_ids:
        return revisions

    if refs_dir.is_dir():
        try:
            for ref_path, relative_name in _iter_relative_file_paths_sorted(refs_dir):
                try:
                    snapshot_id = ref_path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if not snapshot_id:
                    continue
                if remaining_snapshot_ids is not None and snapshot_id not in remaining_snapshot_ids:
                    continue

                revisions.setdefault(snapshot_id, relative_name)
                if remaining_snapshot_ids is not None:
                    remaining_snapshot_ids.discard(snapshot_id)
                    if not remaining_snapshot_ids:
                        return revisions
        except OSError:
            return revisions
    return revisions


def _hf_cache_revision(
    cache_repo_dir: Path,
    snapshot_id: str,
    *,
    revision_map: Mapping[str, str] | None = None,
) -> str:
    revisions = revision_map if revision_map is not None else _hf_cache_revision_map(cache_repo_dir)
    return revisions.get(snapshot_id, snapshot_id)


def _is_hf_cache_snapshot_dir(root: Path, model_dir: Path) -> bool:
    try:
        relative_parts = model_dir.relative_to(root).parts
    except ValueError:
        return False
    if len(relative_parts) < 3 or relative_parts[1] != "snapshots":
        return False
    return _hf_cache_repo_id(root / relative_parts[0]) is not None


def _is_hf_cache_pruned_subtree(root: Path, current: Path) -> bool:
    try:
        relative_parts = current.relative_to(root).parts
    except ValueError:
        return False
    if len(relative_parts) < 2 or relative_parts[1] not in _HF_CACHE_PRUNED_SUBTREE_NAMES:
        return False
    return _hf_cache_repo_id(root / relative_parts[0]) is not None


def _local_model_id(root: Path, model_dir: Path) -> str:
    try:
        relative = model_dir.relative_to(root)
    except ValueError:
        return model_dir.name
    relative_text = os.fspath(relative)
    return model_dir.name if relative_text in {"", "."} else relative_text


def _path_derived_registry_identity(relative_parts: tuple[str, ...]) -> tuple[str, str, str, str] | None:
    if len(relative_parts) == 3:
        organization_id, model_name, variant_id = relative_parts
        return "", organization_id, model_name, variant_id
    if len(relative_parts) == 4:
        provider_id, organization_id, model_name, variant_id = relative_parts
        return provider_id, organization_id, model_name, variant_id
    return None


def _apply_registry_identity_metadata(
    model: common_pb2.ModelSpec,
    *,
    relative_parts: tuple[str, ...],
) -> bool:
    path_identity = _path_derived_registry_identity(relative_parts)
    if path_identity is None:
        return False

    (
        path_provider_id,
        path_organization_id,
        path_model_name,
        path_variant_id,
    ) = path_identity
    provider_id = _normalized(model.ext.get(_REGISTRY_PROVIDER_ID_KEY)) or path_provider_id
    organization_id = _normalized(model.ext.get(_REGISTRY_ORGANIZATION_ID_KEY)) or path_organization_id
    model_name = _normalized(model.ext.get(_REGISTRY_MODEL_NAME_KEY)) or path_model_name
    variant_id = _normalized(model.ext.get(_REGISTRY_VARIANT_ID_KEY)) or path_variant_id
    if not organization_id or not model_name or not variant_id:
        return False

    model.ext[_REGISTRY_PROVIDER_ID_KEY] = provider_id
    model.ext[_REGISTRY_ORGANIZATION_ID_KEY] = organization_id
    model.ext[_REGISTRY_MODEL_NAME_KEY] = model_name
    model.ext[_REGISTRY_VARIANT_ID_KEY] = variant_id
    return True


def _capability_metadata(
    *,
    adapter_set_hash: str,
    route_kind: str,
    capability_class: str,
    supported_modalities: tuple[str, ...],
    supported_tasks: tuple[str, ...],
    supported_parsers: tuple[str, ...],
    tool_parser_mode: str = "",
    tool_parser_namespaces: tuple[str, ...] = (),
    tool_parser_xml_fallback: bool = False,
) -> dict[str, str]:
    metadata = {
        _ADAPTER_SET_HASH_KEY: adapter_set_hash,
        _CAPABILITY_ROUTE_KIND_KEY: route_kind,
        _CAPABILITY_CLASS_KEY: capability_class,
        _CAPABILITY_SUPPORTED_MODALITIES_KEY: ",".join(supported_modalities),
        _CAPABILITY_SUPPORTED_TASKS_KEY: ",".join(supported_tasks),
        _CAPABILITY_SUPPORTED_PARSERS_KEY: ",".join(supported_parsers),
    }
    if tool_parser_mode:
        metadata["tool_parser_mode"] = tool_parser_mode
    if tool_parser_namespaces:
        metadata["tool_parser_namespaces"] = ",".join(tool_parser_namespaces)
    if tool_parser_xml_fallback:
        metadata["tool_parser_xml_fallback"] = "true"
    return metadata


def _text_capability_metadata(
    *,
    model_path: str,
    metadata: dict[str, str] | None = None,
    config_payload: dict[str, object] | None = None,
    default_route_kind: str,
) -> dict[str, str]:
    resolved = resolve_text_family_config(
        metadata,
        model_path=model_path,
        config_payload=config_payload,
        default_route_kind=default_route_kind,
    )
    detected = detect_text_family_identity(
        model_path=model_path,
        config_payload=config_payload,
        explicit_family_id="",
    )
    identity_override = (
        resolved.family_id != detected.family_id
        or resolved.architecture != detected.architecture
    )
    return {
        **resolved.capability_metadata(),
        **_text_lora_support_metadata(
            resolved.family_id,
            moe_enabled=resolved.moe_enabled,
            expert_count_source=resolved.expert_count_source,
        ),
        "detected_architecture": detected.architecture,
        "detected_family_id": detected.family_id,
        "detected_identity_source": detected.source,
        "identity_override": "true" if identity_override else "false",
    }


def _text_layer_count(config_payload: Mapping[str, object] | None) -> int:
    layer_count = _config_positive_int(config_payload, "num_hidden_layers")
    if layer_count == 0 and isinstance(config_payload, Mapping):
        layer_count = _config_positive_int(config_payload.get("text_config"), "num_hidden_layers")
    return layer_count


def _merge_text_layer_count_metadata(
    ext: dict[str, str],
    config_payload: Mapping[str, object] | None,
) -> None:
    layer_count = _text_layer_count(config_payload)
    if layer_count > 0:
        ext["text_layer_count"] = str(layer_count)


def _text_lora_support_metadata(
    family_id: str,
    *,
    moe_enabled: bool,
    expert_count_source: str = "",
) -> dict[str, str]:
    stable_dense_families = {"llama", "qwen", "gemma", "kimi"}
    if family_id in stable_dense_families:
        return {
            "melix.lora.family_id": family_id,
            "melix.lora.family_kind": "dense",
            "melix.lora.support_tier": "stable",
            "melix.lora.training_ready": "true",
            "melix.lora.default_target_preset": "attention_mlp",
        }
    if family_id == "mixtral":
        return {
            "melix.lora.family_id": family_id,
            "melix.lora.family_kind": "moe",
            "melix.lora.support_tier": "experimental",
            "melix.lora.training_ready": "true",
            "melix.lora.default_target_preset": "attention",
        }
    if family_id == "qwen3moe":
        expert_count_confirmed = moe_enabled and expert_count_source == "config"
        return {
            "melix.lora.family_id": family_id,
            "melix.lora.family_kind": "moe",
            "melix.lora.support_tier": "experimental",
            "melix.lora.training_ready": "true" if expert_count_confirmed else "false",
            "melix.lora.default_target_preset": "attention",
        }
    return {
        "melix.lora.family_id": family_id,
        "melix.lora.family_kind": "moe" if moe_enabled else "advanced_text",
        "melix.lora.support_tier": "experimental",
        "melix.lora.training_ready": "false",
        "melix.lora.default_target_preset": "attention",
    }


def _embedding_lora_support_metadata(family_id: str) -> dict[str, str]:
    return {
        "melix.lora.family_id": family_id,
        "melix.lora.family_kind": "embedding",
        "melix.lora.support_tier": "blocked",
        "melix.lora.training_ready": "false",
        "melix.lora.default_target_preset": "unsupported",
    }


def _image_capability_metadata(
    *,
    model_path: str,
    metadata: dict[str, str] | None = None,
    default_task_kind: str,
) -> dict[str, str]:
    metadata = dict(metadata or {})
    resolved = resolve_image_family_config(
        metadata,
        model_path=model_path,
        default_task_kind=default_task_kind,
    )
    detected = detect_image_family_identity(
        model_path=model_path,
        explicit_family_id=metadata.get("melix.image.family_id", ""),
        explicit_task_kind=metadata.get("melix.image.task_kind", ""),
    )
    identity_override = bool(metadata.get("melix.image.family_id")) or resolved.family_id != detected.family_id
    task_override = bool(metadata.get("melix.image.task_kind")) or resolved.task_kind != detected.task_kind
    return {
        **resolved.capability_metadata(),
        "detected_family_id": detected.family_id,
        "detected_identity_source": detected.source,
        "detected_task_kind": detected.task_kind,
        "identity_override": "true" if identity_override else "false",
        "task_override": "true" if task_override else "false",
    }


def _embedding_capability_metadata(family_id: str) -> dict[str, str]:
    return _capability_metadata(
        adapter_set_hash=f"embedding-family-{family_id}",
        route_kind="python_embedding",
        capability_class="embedding",
        supported_modalities=("text",),
        supported_tasks=("embed",),
        supported_parsers=("text",),
    )


def _infer_embedding_identity(model_path: str) -> dict[str, str]:
    normalized_path = model_path.lower()
    if "mxbai" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "mxbai-embed",
            "source": "directory_name",
        }
    if "bge" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "bge-m3",
            "source": "directory_name",
        }
    if "xlmr" in normalized_path or "xlm-r" in normalized_path:
        return {
            "architecture": "xlmr",
            "family_id": "xlmr",
            "source": "directory_name",
        }
    if "bert" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "bert",
            "source": "directory_name",
        }
    return {
        "architecture": "bert",
        "family_id": "bert",
        "source": "default",
    }


def _embedding_backend_for_family(family_id: str) -> str:
    return "deterministic-fixture-v1"


def _embedding_architecture_for_family(family_id: str) -> str:
    return "xlmr" if family_id == "xlmr" else "bert"


def _default_embedding_family_for_backend(backend_id: str, detected_family_id: str) -> str:
    if backend_id in {"mlx-xlmr-v1", "xlmr-v1"}:
        return "xlmr"
    if detected_family_id in {"bert", "xlmr", "bge-m3", "mxbai-embed"}:
        return detected_family_id
    return "bert"


def _default_embedding_pooling_mode(family_id: str) -> str:
    return {
        "bert": "cls",
        "xlmr": "mean",
        "bge-m3": "cls",
        "mxbai-embed": "mean",
    }.get(family_id, "cls")


def _default_embedding_dimensions(family_id: str) -> str:
    return {"mxbai-embed": "10"}.get(family_id, "8")


def _artifact_embedding_module_paths(
    model_dir: Path,
) -> tuple[Path, Path | None] | None:
    modules_path = model_dir / "modules.json"
    if modules_path.exists() or modules_path.is_symlink():
        if not _artifact_embedding_regular_file(model_dir, modules_path):
            return None
        try:
            modules = _JSON_LOADS(modules_path.read_bytes())
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(modules, list):
            return None
        stages: list[str] = []
        stage_paths: dict[str, Path] = {}
        for position, module in enumerate(modules):
            if not isinstance(module, Mapping):
                return None
            module_index = module.get("idx")
            if (
                not isinstance(module_index, int)
                or isinstance(module_index, bool)
                or module_index != position
            ):
                return None
            stage = _ARTIFACT_EMBEDDING_MODULE_TYPES.get(
                str(module.get("type", "") or "").strip()
            )
            if stage is None:
                return None
            raw_module_path = str(module.get("path", "") or "").strip()
            if stage == "Transformer":
                if raw_module_path not in {"", "."}:
                    return None
            else:
                relative_path = Path(raw_module_path)
                if (
                    not raw_module_path
                    or relative_path.is_absolute()
                    or any(part in {"", ".", ".."} for part in relative_path.parts)
                ):
                    return None
                stage_paths[stage] = model_dir / relative_path / "config.json"
            stages.append(stage)
        if tuple(stages) not in {
            ("Transformer", "Pooling"),
            ("Transformer", "Pooling", "Normalize"),
        }:
            return None
        pooling_path = stage_paths.get("Pooling")
        normalize_path = stage_paths.get("Normalize")
        if pooling_path is None or not _artifact_embedding_regular_file(
            model_dir, pooling_path
        ):
            return None
        if normalize_path is not None and not _artifact_embedding_regular_file(
            model_dir, normalize_path
        ):
            return None
        return pooling_path, normalize_path

    pooling_paths: list[Path] = []
    normalize_paths: list[Path] = []
    try:
        with os.scandir(os.fspath(model_dir)) as entries:
            for entry in entries:
                entry_name = entry.name
                if not (
                    entry_name.endswith("_Pooling")
                    or entry_name.endswith("_Normalize")
                ):
                    continue
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    return None
                config_path = Path(entry.path) / "config.json"
                if not _artifact_embedding_regular_file(model_dir, config_path):
                    return None
                if entry_name.endswith("_Pooling"):
                    pooling_paths.append(config_path)
                else:
                    normalize_paths.append(config_path)
    except OSError:
        return None
    pooling_paths.sort()
    normalize_paths.sort()
    if len(pooling_paths) != 1 or len(normalize_paths) > 1:
        return None
    return pooling_paths[0], normalize_paths[0] if normalize_paths else None


def _artifact_embedding_regular_file(model_dir: Path, path: Path) -> bool:
    if path.parent == model_dir:
        try:
            return stat.S_ISREG(path.lstat().st_mode)
        except OSError:
            return False
    try:
        relative_path = path.relative_to(model_dir)
    except ValueError:
        return False
    current = model_dir
    try:
        for component in relative_path.parts[:-1]:
            current /= component
            if not stat.S_ISDIR(current.lstat().st_mode):
                return False
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _artifact_embedding_weight_paths(model_dir: Path) -> tuple[Path, ...]:
    weight_paths: list[Path] = []
    try:
        with os.scandir(os.fspath(model_dir)) as entries:
            for entry in entries:
                if entry.name.endswith(".safetensors"):
                    weight_paths.append(Path(entry.path))
    except OSError:
        return ()
    weight_paths.sort()
    return tuple(weight_paths)


def _artifact_embedding_metadata(
    model_dir: Path,
    config_payload: Mapping[str, object] | None,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]],
) -> dict[str, str] | None:
    if not isinstance(config_payload, Mapping):
        return None
    model_type = _normalized(str(config_payload.get("model_type", ""))).lower()
    if model_type == "bert":
        architecture = "bert"
        backend_id = "mlx-bert-v1"
        family_id = "bert"
    elif model_type in {"xlm-roberta", "xlm_roberta"}:
        architecture = "xlmr"
        backend_id = "mlx-xlmr-v1"
        family_id = "xlmr"
    else:
        return None
    if unsupported_embedding_encoder_config(config_payload):
        return None
    if unsupported_embedding_media_components(config_payload):
        return None

    config_path = model_dir / "config.json"
    if not _artifact_embedding_regular_file(model_dir, config_path):
        return None

    raw_input_modalities = config_payload.get("embedding_input_modalities", "text")
    input_modalities = {
        value.strip().lower()
        for value in str(raw_input_modalities or "").split(",")
        if value.strip()
    }
    vector_kind = str(
        config_payload.get("embedding_vector_kind", "single_dense") or ""
    ).strip().lower()
    if input_modalities != {"text"} or vector_kind != "single_dense":
        return None

    weight_paths = _artifact_embedding_weight_paths(model_dir)
    tokenizer_paths = tuple(
        path
        for filename in _ARTIFACT_EMBEDDING_TOKENIZER_FILENAMES
        if (path := model_dir / filename).exists() or path.is_symlink()
    )
    if (
        not weight_paths
        or any(
            not _artifact_embedding_regular_file(model_dir, path)
            for path in weight_paths
        )
        or not has_supported_embedding_tokenizer_files(
            {path.name for path in tokenizer_paths}
        )
        or any(
            not _artifact_embedding_regular_file(model_dir, path)
            for path in tokenizer_paths
        )
    ):
        return None

    module_paths = _artifact_embedding_module_paths(model_dir)
    if module_paths is None:
        return None
    pooling_path, normalize_path = module_paths
    pooling_config = _load_json_dict_file(pooling_path, json_cache=json_cache)
    if not pooling_config:
        return None
    if normalize_path is not None:
        try:
            normalize_config = _JSON_LOADS(normalize_path.read_bytes())
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(normalize_config, Mapping):
            return None
    pooling_mode = supported_sentence_transformer_pooling_mode(pooling_config)
    if pooling_mode is None:
        return None
    dimensions = _config_positive_int(config_payload, "hidden_size")
    pooling_dimensions = _inventory_nonnegative_int(
        pooling_config.get("word_embedding_dimension")
    )
    if dimensions <= 0 or (pooling_dimensions > 0 and pooling_dimensions != dimensions):
        return None
    normalization = "l2" if normalize_path is not None else "none"
    return {
        **_embedding_capability_metadata(family_id),
        **_embedding_lora_support_metadata(family_id),
        "embedding_backend_id": backend_id,
        "embedding_execution_kind": "artifact",
        "embedding_family_id": family_id,
        "embedding_pooling_mode": pooling_mode,
        "embedding_normalization": normalization,
        "embedding_dimensions": str(dimensions),
        "embedding_vector_kind": vector_kind,
        "embedding_input_modalities": ",".join(sorted(input_modalities)),
        "model_architecture": architecture,
        "detected_architecture": architecture,
        "detected_family_id": family_id,
        "detected_identity_source": "artifact_metadata",
        "identity_override": "false",
    }


def _rerank_capability_metadata(family_id: str) -> dict[str, str]:
    return _capability_metadata(
        adapter_set_hash=f"rerank-family-{family_id}",
        route_kind="python_rerank",
        capability_class="rerank",
        supported_modalities=("text",),
        supported_tasks=("rerank",),
        supported_parsers=("text",),
    )


def _infer_rerank_identity(model_path: str) -> dict[str, str]:
    normalized_path = model_path.lower()
    if "causal-lm" in normalized_path or "causallm" in normalized_path:
        return {
            "architecture": "causal-lm",
            "family_id": "causal-lm",
            "source": "directory_name",
        }
    if "basic" in normalized_path:
        return {
            "architecture": "cross-encoder",
            "family_id": "basic",
            "source": "directory_name",
        }
    if "jina" in normalized_path:
        return {
            "architecture": "cross-encoder",
            "family_id": "jina-v3",
            "source": "directory_name",
        }
    return {
        "architecture": "cross-encoder",
        "family_id": "jina-v3",
        "source": "default",
    }


def _rerank_architecture_for_family(family_id: str) -> str:
    return "causal-lm" if family_id == "causal-lm" else "cross-encoder"


def _default_rerank_scoring_mode(family_id: str) -> str:
    return {
        "basic": "set-overlap",
        "causal-lm": "yes-no-logits",
        "jina-v3": "order-aware-overlap",
    }.get(family_id, "order-aware-overlap")


def _vision_capability_metadata(family_id: str) -> dict[str, str]:
    if family_id == "paligemma-v1":
        return _capability_metadata(
            adapter_set_hash="vision-family-paligemma-v1",
            route_kind="python_vlm",
            capability_class="vlm",
            supported_modalities=("text", "image"),
            supported_tasks=("vlm", "generate"),
            supported_parsers=("text",),
        )
    if family_id == "gemma4-v1":
        return _capability_metadata(
            adapter_set_hash="vision-family-gemma4-v1",
            route_kind="python_vlm",
            capability_class="vlm",
            supported_modalities=("text", "image", "video"),
            supported_tasks=("vlm", "generate"),
            supported_parsers=("text", "gemma"),
            tool_parser_mode="gemma",
            tool_parser_namespaces=("tools.vision",),
            tool_parser_xml_fallback=True,
        )
    return _capability_metadata(
        adapter_set_hash=f"vision-family-{family_id}",
        route_kind="python_vlm",
        capability_class="vlm",
        supported_modalities=("text", "image", "video"),
        supported_tasks=("vlm", "generate"),
        supported_parsers=("text", "qwen"),
        tool_parser_mode="qwen",
        tool_parser_namespaces=("tools.vision",),
        tool_parser_xml_fallback=True,
    )


def _is_gemma4_vlm_config(config_payload: Mapping[str, object] | None) -> bool:
    config_payload = dict(config_payload or {})
    model_type = _normalized(str(config_payload.get("model_type", ""))).lower()
    if model_type == "gemma4":
        return True

    architectures = config_payload.get("architectures")
    if isinstance(architectures, list):
        for item in architectures:
            if _normalized(str(item)).lower() == "gemma4forconditionalgeneration":
                return True

    text_config = config_payload.get("text_config")
    if isinstance(text_config, Mapping):
        nested_model_type = _normalized(str(text_config.get("model_type", ""))).lower()
        if nested_model_type == "gemma4_text":
            return True

    return False


def _gemma4_execution_mode(
    model_dir: Path,
    config_payload: Mapping[str, object] | None,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    tensor_evidence: _TensorIndexEvidence | None = None,
) -> str:
    config_payload = dict(config_payload or {})
    tensor_evidence = tensor_evidence or _tensor_index_evidence(model_dir, json_cache=json_cache)
    if tensor_evidence.status != "ok":
        return "text_backed"
    if "vision" not in tensor_evidence.modalities and "audio" not in tensor_evidence.modalities and "video" not in tensor_evidence.modalities:
        return "text_backed"
    if _tensor_index_missing_declared_modalities(tensor_evidence, config_payload):
        return "text_backed"
    vision_config = config_payload.get("vision_config")
    if isinstance(vision_config, Mapping) and len(vision_config) > 0:
        return ""
    if (model_dir / "processor_config.json").is_file() or (model_dir / "preprocessor_config.json").is_file():
        return ""
    has_multimodal_marker = any(
        key in config_payload and config_payload.get(key) not in (None, "", [], {})
        for key in ("image_token_id", "boi_token_id", "eoi_token_id")
    )
    if has_multimodal_marker and _gemma4_index_has_vision_weights(model_dir, json_cache=json_cache):
        return ""
    return "text_backed"


def _gemma4_text_backbone_config(config_payload: Mapping[str, object] | None) -> Mapping[str, object] | None:
    config_payload = config_payload or {}
    text_config = config_payload.get("text_config")
    if not isinstance(text_config, Mapping):
        return None
    nested_model_type = _normalized(str(text_config.get("model_type", ""))).lower()
    if nested_model_type != "gemma4_text":
        return None
    return text_config


def _gemma4_has_vision_component(
    model_dir: Path,
    config_payload: Mapping[str, object] | None,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    tensor_evidence: _TensorIndexEvidence | None = None,
) -> bool:
    has_explicit_tensor_evidence = tensor_evidence is not None
    tensor_evidence = tensor_evidence or _tensor_index_evidence(model_dir, json_cache=json_cache)
    if "vision" in tensor_evidence.modalities:
        return True
    if has_explicit_tensor_evidence and tensor_evidence.status != "ok":
        return False
    if tensor_evidence.status == "ok":
        return False
    if (model_dir / "processor_config.json").is_file() or (model_dir / "preprocessor_config.json").is_file():
        return True
    return _gemma4_index_has_vision_weights(model_dir, json_cache=json_cache)


def _gemma4_component_lora_metadata(
    *,
    model_path: str,
    model_dir: Path,
    config_payload: Mapping[str, object] | None,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    tensor_evidence: _TensorIndexEvidence | None = None,
    projector_components_available: bool = True,
) -> dict[str, str]:
    text_config = _gemma4_text_backbone_config(config_payload)
    if text_config is None:
        return {}

    components = ["text_backbone"]
    has_vision_component = _gemma4_has_vision_component(
        model_dir,
        config_payload,
        json_cache=json_cache,
        tensor_evidence=tensor_evidence,
    )
    if has_vision_component:
        components.append("vision_encoder")
        if projector_components_available:
            components.append("multimodal_projector")
    if tensor_evidence is not None and "audio" in tensor_evidence.modalities:
        components.append("audio_encoder")

    ext = {
        **_text_lora_support_metadata("gemma", moe_enabled=False),
        "melix.model.components": ",".join(components),
        "melix.model.component_contract": "component_scoped_v1",
        "melix.component.text_backbone.model_type": "gemma4_text",
        "melix.component.text_backbone.family_id": "gemma",
        "melix.component.text_backbone.lora_supported": "true",
        "melix.component.text_backbone.training_ready": "true",
        "melix.component.text_backbone.path": model_path,
        "melix.lora.adapter_scope": "text_backbone",
        "melix.lora.training_surface": "text_backbone",
        "melix.lora.base_model_path": model_path,
        "melix.lora.component_model_type": "gemma4_text",
    }
    text_layer_count = _config_positive_int(text_config, "num_hidden_layers")
    if text_layer_count > 0:
        ext["text_layer_count"] = str(text_layer_count)
        ext["melix.component.text_backbone.layer_count"] = str(text_layer_count)
    if has_vision_component:
        config_payload = config_payload or {}
        vision_config = config_payload.get("vision_config")
        vision_model_type = ""
        if isinstance(vision_config, Mapping):
            vision_model_type = _normalized(str(vision_config.get("model_type", "")))
        ext.update(
            {
                "melix.component.vision_encoder.model_type": vision_model_type or "gemma4_vision",
                "melix.component.vision_encoder.lora_supported": "false",
                "melix.component.vision_encoder.lora_support_contract": "separate_contract",
            }
        )
        if projector_components_available:
            ext.update(
                {
                    "melix.component.multimodal_projector.lora_supported": "false",
                    "melix.component.multimodal_projector.lora_support_contract": "separate_contract",
                }
            )
    return ext


def _config_positive_int(config_payload: Mapping[str, object] | None, key: str) -> int:
    if not isinstance(config_payload, Mapping):
        return 0
    try:
        value = int(config_payload.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _gemma4_index_has_vision_weights(
    model_dir: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> bool:
    evidence = _tensor_index_evidence(model_dir, json_cache=json_cache)
    return "vision" in evidence.modalities


def _gemma4_mtp_assistant_metadata(
    *,
    model_id: str,
    model_dir: Path,
    config_payload: Mapping[str, object] | None,
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] | None = None,
) -> dict[str, str]:
    if not _is_gemma4_vlm_config(config_payload):
        return {}

    readme_text = _read_text_prefix(
        model_dir / "README.md",
        text_prefix_cache=text_prefix_cache,
    ).lower()
    try:
        config_text = json.dumps(dict(config_payload or {})).lower()
    except (TypeError, ValueError):
        config_text = ""
    combined = " ".join((model_id.lower(), readme_text, config_text))
    if "assistant" not in combined and "drafter" not in combined:
        return {}
    if "mtp" not in combined and "speculative-decoding" not in combined:
        return {}
    return {
        "melix.speculative.role": "assistant",
        "melix.speculative.kind": "mtp",
        "melix.speculative.target_family": "gemma4-v1",
        "melix.serving.hidden": "true",
    }


def _gemma4_qat_metadata(
    *,
    model_id: str,
    model_dir: Path,
    config_payload: Mapping[str, object] | None,
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] | None = None,
) -> dict[str, str]:
    if not _is_gemma4_vlm_config(config_payload):
        return {}

    readme_text = _read_text_prefix(
        model_dir / "README.md",
        text_prefix_cache=text_prefix_cache,
    )
    model_id_lower = model_id.lower()
    combined = " ".join((model_id_lower, readme_text)).lower()
    if ("gemma-4" not in combined and "gemma4" not in combined) or "qat" not in combined:
        return {}
    if "mlx" not in combined:
        return {}

    model_size = _gemma4_qat_model_size(combined)
    quantization_family = _gemma4_qat_quantization_family(combined)
    if not model_size or not quantization_family:
        return {}

    organization = _model_id_organization(model_id)
    auto_supported = organization == _GEMMA4_QAT_AUTOMATIC_ORG
    companion = _gemma4_qat_is_draft_companion(
        combined,
        model_id_lower=model_id_lower,
    )
    source_model = _gemma4_qat_source_model(
        readme_text,
        model_size=model_size,
        companion=companion,
    )
    default_policy = "auto_pair_when_available" if auto_supported else "manual_override_only"
    ext = {
        "melix.qat.enabled": "true",
        "melix.qat.family": "gemma4",
        "melix.qat.asset_format": "mlx",
        "melix.qat.hf_organization": organization,
        "melix.qat.auto_supported": "true" if auto_supported else "false",
        "melix.qat.support_scope": (
            _GEMMA4_QAT_AUTOMATIC_SCOPE if auto_supported else "manual_experimental"
        ),
        "melix.qat.model_size": model_size,
        "melix.qat.quantization_family": quantization_family,
        "melix.draft_companion.role": "companion" if companion else "target",
        "melix.draft_companion.default_policy": default_policy,
        "melix.draft_companion.override_supported": "true",
        "melix.draft_companion.auto_pair_key": (
            f"gemma4:{model_size}:qat:{quantization_family}"
        ),
    }
    if source_model:
        ext["melix.qat.source_model"] = source_model
    if not companion:
        ext["melix.draft_companion.missing_policy"] = "baseline_generation"
    return ext


def _apply_gemma4_qat_companion_metadata(
    models: Iterable[common_pb2.ModelSpec],
) -> None:
    companions_by_key: dict[str, list[common_pb2.ModelSpec]] = {}
    targets_by_key: dict[str, list[common_pb2.ModelSpec]] = {}
    for model in models:
        if not _gemma4_qat_auto_supported_model(model):
            continue
        pair_key = _normalized(model.ext.get("melix.draft_companion.auto_pair_key"))
        if not pair_key:
            continue
        role = _normalized(model.ext.get("melix.draft_companion.role")).lower()
        if role == "companion":
            companions_by_key.setdefault(pair_key, []).append(model)
        elif role == "target":
            targets_by_key.setdefault(pair_key, []).append(model)

    target_ids_by_companion: dict[str, set[str]] = {}
    for pair_key, targets in targets_by_key.items():
        companions = sorted(
            companions_by_key.get(pair_key, ()),
            key=lambda model: model.model_id,
        )
        companion_ids = [model.model_id for model in companions]
        for target in targets:
            _merge_csv_ext(
                target,
                "melix.acceleration.supported_modes",
                ("baseline", "speculative_decode"),
            )
            _set_ext_default(
                target,
                "melix.acceleration.target_capability",
                "speculative_decode",
            )
            _set_ext_default(
                target,
                "melix.acceleration.receipt_provenance",
                "model_registry.gemma4_qat",
            )
            if companion_ids:
                _set_ext_default(target, "melix.draft_companion.status", "available")
                _merge_csv_ext(
                    target,
                    "melix.draft_companion.model_ids",
                    companion_ids,
                )
                _merge_csv_ext(
                    target,
                    "melix.acceleration.valid_draft_model_ids",
                    companion_ids,
                )
                _set_ext_default(
                    target,
                    "melix.acceleration.drafter_capability",
                    "speculative_draft",
                )
                for companion_id in companion_ids:
                    target_ids_by_companion.setdefault(companion_id, set()).add(target.model_id)
            else:
                _set_ext_default(target, "melix.draft_companion.status", "missing")
                _set_ext_default(
                    target,
                    "melix.draft_companion.recovery_hint",
                    _GEMMA4_QAT_DRAFT_COMPANION_RECOVERY_HINT,
                )

    for companions in companions_by_key.values():
        for companion in companions:
            target_ids = sorted(target_ids_by_companion.get(companion.model_id, ()))
            _set_ext_default(companion, "melix.draft_companion.status", "available")
            if target_ids:
                _merge_csv_ext(
                    companion,
                    "melix.draft_companion.target_model_ids",
                    target_ids,
                )
            _set_ext_default(
                companion,
                "melix.acceleration.drafter_capability",
                "speculative_draft",
            )
            _set_ext_default(
                companion,
                "melix.acceleration.receipt_provenance",
                "model_registry.gemma4_qat",
            )


def _gemma4_qat_auto_supported_model(model: common_pb2.ModelSpec) -> bool:
    return (
        _normalized(model.ext.get("melix.qat.enabled")).lower() == "true"
        and _normalized(model.ext.get("melix.qat.family")).lower() == "gemma4"
        and _normalized(model.ext.get("melix.qat.asset_format")).lower() == "mlx"
        and _normalized(model.ext.get("melix.qat.auto_supported")).lower() == "true"
    )


def _set_ext_default(model: common_pb2.ModelSpec, key: str, value: str) -> None:
    if not _normalized(model.ext.get(key)):
        model.ext[key] = value


def _merge_csv_ext(
    model: common_pb2.ModelSpec,
    key: str,
    values: Iterable[str],
) -> None:
    merged: list[str] = []
    seen: set[str] = set()
    for raw_value in (*_split_csv(model.ext.get(key)), *values):
        value = _normalized(raw_value)
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    if merged:
        model.ext[key] = ",".join(merged)


def _split_csv(raw_value: str | None) -> tuple[str, ...]:
    return tuple(
        part.strip()
        for part in (raw_value or "").split(",")
        if part.strip()
    )


def _gemma4_qat_fast_candidate(model_id: str) -> bool:
    lowered = model_id.lower()
    return ("gemma-4" in lowered or "gemma4" in lowered) and "qat" in lowered


def _model_id_organization(model_id: str) -> str:
    separator_index = model_id.find("/")
    if separator_index < 0:
        return ""
    return model_id[:separator_index].lower()


def _gemma4_qat_model_size(value: str) -> str:
    for token in ("26b-a4b", "12b", "e4b", "e2b"):
        if token in value:
            return token
    return ""


def _gemma4_qat_quantization_family(value: str) -> str:
    for source, normalized in (
        ("mxfp8", "mxfp8"),
        ("mxfp4", "mxfp4"),
        ("nvfp4", "nvfp4"),
        ("bf16", "bf16"),
        ("8-bit", "8bit"),
        ("8bit", "8bit"),
        ("6-bit", "6bit"),
        ("6bit", "6bit"),
        ("5-bit", "5bit"),
        ("5bit", "5bit"),
        ("4-bit", "4bit"),
        ("4bit", "4bit"),
        ("q4_0", "4bit"),
    ):
        if source in value:
            return normalized
    return ""


def _gemma4_qat_is_draft_companion(value: str, *, model_id_lower: str) -> bool:
    return (
        "assistant" in model_id_lower
        or "draft-model" in value
        or "drafter" in value
        or ("mtp" in value and "speculative" in value)
    )


@lru_cache(maxsize=8)
def _gemma4_qat_source_model(
    readme_text: str,
    *,
    model_size: str,
    companion: bool,
) -> str:
    marker = _GEMMA4_QAT_BASE_MODEL_MARKER
    marker_len = _GEMMA4_QAT_BASE_MODEL_MARKER_LEN
    quoted_marker_index = readme_text.find(_GEMMA4_QAT_QUOTED_BASE_MODEL_MARKER)
    if quoted_marker_index >= 0:
        quoted_marker_start = quoted_marker_index + _GEMMA4_QAT_QUOTED_BASE_MODEL_PREFIX_LEN
        marker_index = readme_text.rfind(marker, 0, quoted_marker_start)
        while marker_index >= 0:
            line_start = readme_text.rfind("\n", 0, marker_index) + 1
            if not readme_text[line_start:marker_index].strip(" \t\r'\""):
                break
            marker_index = readme_text.rfind(marker, 0, marker_index)
        if marker_index >= 0:
            quoted_marker_index = -1
    if quoted_marker_index >= 0:
        value_start = quoted_marker_index + _GEMMA4_QAT_QUOTED_BASE_MODEL_MARKER_LEN
        line_end = readme_text.find("\n", value_start)
        if line_end < 0:
            line_end = len(readme_text)
        value = readme_text[value_start:line_end].strip(_GEMMA4_QAT_BASE_MODEL_STRIP_CHARS)
        if value:
            return value
    search_start = 0
    while True:
        marker_index = readme_text.find(marker, search_start)
        if marker_index < 0:
            break
        line_start = readme_text.rfind("\n", 0, marker_index) + 1
        if readme_text[line_start:marker_index].strip(" \t\r'\""):
            search_start = marker_index + 1
            continue
        line_end = readme_text.find("\n", marker_index)
        if line_end < 0:
            line_end = len(readme_text)
        value = readme_text[marker_index + marker_len : line_end].strip(_GEMMA4_QAT_BASE_MODEL_STRIP_CHARS)
        if value:
            return value
        search_start = marker_index + 1

    size_name = _GEMMA4_QAT_SIZE_NAMES.get(model_size)
    if not size_name:
        return ""
    suffix = "-assistant" if companion else ""
    return f"google/gemma-4-{size_name}-it-qat-q4_0-unquantized{suffix}"


def _multimodal_load_receipt_metadata(
    *,
    model_dir: Path,
    config_payload: Mapping[str, object],
    metadata: Mapping[str, str],
    family_id: str,
    tensor_evidence: _TensorIndexEvidence,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> dict[str, str]:
    processor_metadata = _processor_receipt_metadata(model_dir, json_cache=json_cache)
    aliases = _nested_config_aliases(config_payload)
    placeholder_counts, image_token_budget = _media_placeholder_counts(
        model_dir,
        config_payload,
        json_cache=json_cache,
    )
    projector_evidence = _projector_evidence(
        model_dir=model_dir,
        metadata=metadata,
        family_id=family_id,
        tensor_evidence=tensor_evidence,
        json_cache=json_cache,
    )
    optional_heads = _optional_head_receipt_metadata(config_payload, tensor_evidence)

    ext = {
        **processor_metadata,
        "melix.capability.media_placeholders.counts": _format_media_placeholder_counts(placeholder_counts),
        "melix.capability.media_placeholders.image_token_budget": str(image_token_budget),
        "melix.capability.nested_config.aliases": ",".join(
            f"{component}:{alias}" for component, alias in aliases
        ),
        "melix.capability.projector.status": projector_evidence.status,
        "melix.capability.projector.family_id": projector_evidence.family_id,
        "melix.capability.vision_weight_remap.status": projector_evidence.status,
        **optional_heads,
    }
    if projector_evidence.status == "matched":
        ext["melix.capability.vision_weight_remap.status"] = "matched_projector"
    if not projector_evidence.components_available:
        ext["melix.capability.projector.components_available"] = "false"
    return ext


def _processor_receipt_metadata(
    model_dir: Path,
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> dict[str, str]:
    processor_path, processor_payload = _first_json_sidecar(
        model_dir,
        ("processor_config.json", "preprocessor_config.json"),
        json_cache=json_cache,
    )
    if processor_path is None:
        return {
            "melix.capability.processor.status": "missing",
            "melix.capability.processor.source": "",
            "melix.capability.processor.class": "",
            "melix.capability.image_processor.class": "",
        }

    image_processor = processor_payload.get("image_processor")
    image_processor_class = ""
    if isinstance(image_processor, Mapping):
        image_processor_class = _first_normalized_value(
            image_processor,
            ("image_processor_type", "processor_class", "image_processor_class"),
        )
    if not image_processor_class:
        image_processor_class = _first_normalized_value(
            processor_payload,
            ("image_processor_type", "image_processor_class"),
        )

    return {
        "melix.capability.processor.status": "present",
        "melix.capability.processor.source": str(processor_path),
        "melix.capability.processor.class": _first_normalized_value(
            processor_payload,
            ("processor_class", "feature_extractor_type"),
        ),
        "melix.capability.image_processor.class": image_processor_class,
    }


def _first_json_sidecar(
    model_dir: Path,
    filenames: tuple[str, ...],
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> tuple[Path | None, dict[str, object]]:
    for filename in filenames:
        path = model_dir / filename
        try:
            stat_result = path.stat()
        except OSError:
            if json_cache is not None:
                json_cache.pop(path, None)
            continue
        if not stat.S_ISREG(stat_result.st_mode):
            if json_cache is not None:
                json_cache.pop(path, None)
            continue
        return path, _load_json_dict_file(path, json_cache=json_cache)
    return None, {}


def _first_normalized_value(payload: Mapping[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = _normalized(value)
            if normalized:
                return normalized
    return ""


def _nested_config_aliases(config_payload: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    alias_groups = {
        "text": ("text_config", "language_config", "llm_config"),
        "vision": ("vision_config", "visual_config", "image_config"),
        "audio": ("audio_config", "speech_config"),
        "video": ("video_config",),
        "projector": ("projector_config", "multi_modal_projector", "multimodal_projector", "mm_projector"),
        "draft": ("draft_config", "draft_model", "dflash_config", "mtp_config"),
    }
    aliases: list[tuple[str, str]] = []
    for component in ("audio", "draft", "projector", "text", "video", "vision"):
        for alias in alias_groups[component]:
            value = config_payload.get(alias)
            if isinstance(value, Mapping) and len(value) > 0:
                aliases.append((component, alias))
                break
    return tuple(sorted(aliases))


def _media_placeholder_counts(
    model_dir: Path,
    config_payload: Mapping[str, object],
    *,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> tuple[dict[str, int], int]:
    payloads = [config_payload]
    for filename in ("processor_config.json", "preprocessor_config.json", "tokenizer_config.json"):
        sidecar = _load_json_dict_file(model_dir / filename, json_cache=json_cache)
        if sidecar:
            payloads.append(sidecar)

    counts = {"image": 0, "audio": 0, "video": 0}
    image_token_budget = 0
    for payload in payloads:
        counts["image"] += _count_media_placeholder_keys(payload, ("image", "boi", "eoi"))
        counts["audio"] += _count_media_placeholder_keys(payload, ("audio",))
        counts["video"] += _count_media_placeholder_keys(payload, ("video",))
        image_token_budget = max(image_token_budget, _positive_int_value(payload.get("num_image_tokens")))
        image_processor = payload.get("image_processor")
        if isinstance(image_processor, Mapping):
            counts["image"] += _count_media_placeholder_keys(image_processor, ("image",))
            image_token_budget = max(image_token_budget, _positive_int_value(image_processor.get("num_image_tokens")))
        video_processor = payload.get("video_processor")
        if isinstance(video_processor, Mapping):
            counts["video"] += _count_media_placeholder_keys(video_processor, ("video",))
    return counts, image_token_budget


def _count_media_placeholder_keys(payload: Mapping[str, object], prefixes: tuple[str, ...]) -> int:
    count = 0
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        normalized_key = str(key).lower()
        if normalized_key.startswith(prefixes) and normalized_key.endswith(("_token", "_token_id", "_token_ids")):
            count += 1
    return count


def _positive_int_value(value: object) -> int:
    try:
        candidate = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return candidate if candidate > 0 else 0


def _format_media_placeholder_counts(counts: Mapping[str, int]) -> str:
    return ",".join(f"{modality}:{int(counts.get(modality, 0))}" for modality in ("image", "audio", "video"))


def _projector_evidence(
    *,
    model_dir: Path,
    metadata: Mapping[str, str],
    family_id: str,
    tensor_evidence: _TensorIndexEvidence,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> _ProjectorEvidence:
    projector_family_id = _normalized(metadata.get("melix.projector.family_id", ""))
    if projector_family_id and projector_family_id != family_id:
        return _ProjectorEvidence(
            status="cross_family_rejected",
            family_id=projector_family_id,
            components_available=False,
        )
    if "projector" in tensor_evidence.modalities:
        return _ProjectorEvidence(status="matched", family_id=projector_family_id or family_id)
    if "vision" not in tensor_evidence.modalities:
        return _ProjectorEvidence(status="no_projector", family_id=projector_family_id)
    if family_id == "gemma4-v1" and _has_gemma4_vision_weight_remap_tensor(
        model_dir,
        tensor_evidence=tensor_evidence,
        json_cache=json_cache,
    ):
        return _ProjectorEvidence(status="gemma4_embed_vision_projection", family_id=projector_family_id or family_id)
    if projector_family_id == family_id and _has_renamed_projector_tensor(
        model_dir,
        tensor_evidence=tensor_evidence,
        json_cache=json_cache,
    ):
        return _ProjectorEvidence(status="renamed_metadata_matched", family_id=projector_family_id)
    return _ProjectorEvidence(status="missing", family_id=projector_family_id, components_available=False)


def _has_renamed_projector_tensor(
    model_dir: Path,
    *,
    tensor_evidence: _TensorIndexEvidence,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> bool:
    if tensor_evidence.status != "ok":
        return False
    for name in _weight_map_tensor_names(model_dir, json_cache=json_cache):
        if (
            _tensor_name_is_text(name)
            or _tensor_name_is_vision(name)
            or _tensor_name_is_audio(name)
            or _tensor_name_is_video(name)
        ):
            continue
        # Reuse a single lowercase form across the projector/draft helpers and the
        # connector/projector substring check below.
        lowered = name.lower()
        if _tensor_name_is_projector(name, lowered) or _tensor_name_is_draft(name, lowered):
            continue
        if "connector" in lowered or "projector" in lowered:
            return True
    return False


def _has_gemma4_vision_weight_remap_tensor(
    model_dir: Path,
    *,
    tensor_evidence: _TensorIndexEvidence,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> bool:
    if tensor_evidence.status != "ok":
        return False
    for name in _weight_map_tensor_names(model_dir, json_cache=json_cache):
        if _tensor_name_is_gemma4_vision_weight_remap(name):
            return True
    return False


def _optional_head_receipt_metadata(
    config_payload: Mapping[str, object],
    tensor_evidence: _TensorIndexEvidence,
) -> dict[str, str]:
    components: list[str] = []
    declared: list[str] = []
    draft_model_type = _normalized(str(config_payload.get("draft_model_type", "")))
    if draft_model_type or any(
        _config_declares_component(config_payload, key)
        for key in ("draft_config", "draft_model", "dflash_config", "mtp_config")
    ):
        declared.append("draft")
    if "draft" in tensor_evidence.modalities:
        components.append("draft")
    load_attached = bool(components)
    return {
        "melix.capability.optional_heads.declared": ",".join(declared),
        "melix.capability.optional_heads.draft_model_type": draft_model_type,
        "melix.capability.optional_heads.load_attached": "true" if load_attached else "false",
        "melix.capability.optional_heads.acceleration_enabled": "false",
        "melix.capability.optional_heads.components": ",".join(components or declared),
    }


def _vlm_capability_metadata(
    *,
    model_path: str,
    model_dir: Path,
    metadata: dict[str, str] | None = None,
    config_payload: Mapping[str, object] | None = None,
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
) -> dict[str, str]:
    metadata = dict(metadata or {})
    config_payload = dict(config_payload or {})
    tensor_evidence = _tensor_index_evidence(model_dir, json_cache=json_cache)
    family_id = _normalized(metadata.get("vision_family_id", ""))
    if not family_id and _is_gemma4_vlm_config(config_payload):
        family_id = "gemma4-v1"
    family_id = family_id or "llava-v1"

    resolved_family = resolve_vision_family_config(
        {
            **metadata,
            "vision_family_id": family_id,
        }
    )
    ext = {
        **_vision_capability_metadata(family_id),
        **resolved_family.capability_metadata(),
        "melix.vlm.backend_id": _normalized(metadata.get("melix.vlm.backend_id", "")) or "mlx_vlm",
        "melix.vlm.text_only_step_cooperative": _normalized(
            metadata.get("melix.vlm.text_only_step_cooperative", "")
        ) or "false",
        "melix.vlm.text_only_batch_generator": _normalized(
            metadata.get("melix.vlm.text_only_batch_generator", "")
        ) or "false",
        "melix.multimodal_adapter_hash": (
            _normalized(metadata.get("melix.multimodal_adapter_hash", ""))
            or resolved_family.multimodal_adapter_hash
        ),
    }
    ext.update(_tensor_index_receipt_metadata(tensor_evidence, config_payload))
    load_receipts = _multimodal_load_receipt_metadata(
        model_dir=model_dir,
        config_payload=config_payload,
        metadata=metadata,
        family_id=family_id,
        tensor_evidence=tensor_evidence,
        json_cache=json_cache,
    )
    ext.update(load_receipts)
    supported_modalities = _supported_vlm_modalities_from_tensor_index(tensor_evidence, config_payload)
    projector_status = load_receipts.get("melix.capability.projector.status")
    if projector_status in {"cross_family_rejected", "missing"}:
        supported_modalities = ("text",)
        ext["melix.capability.tensor_index.warning_code"] = (
            "projector_cross_family" if projector_status == "cross_family_rejected" else "projector_missing"
        )
        ext["melix.capability.tensor_index.warning_modalities"] = "projector"
        ext["melix.capability.tensor_index.warning_source"] = tensor_evidence.source_path
    ext[_CAPABILITY_SUPPORTED_MODALITIES_KEY] = ",".join(supported_modalities)
    execution_mode = (
        _gemma4_execution_mode(
            model_dir,
            config_payload,
            json_cache=json_cache,
            tensor_evidence=tensor_evidence,
        )
        if family_id == "gemma4-v1"
        else ""
    )
    if projector_status in {"cross_family_rejected", "missing"}:
        execution_mode = "text_backed"
    if execution_mode:
        ext["melix.vlm.execution_mode"] = execution_mode
    ext.update(
        _gemma4_component_lora_metadata(
            model_path=model_path,
            model_dir=model_dir,
            config_payload=config_payload,
            json_cache=json_cache,
            tensor_evidence=tensor_evidence,
            projector_components_available=load_receipts.get(
                "melix.capability.projector.components_available"
            ) != "false",
        )
    )
    return ext


def _supported_vlm_modalities_from_tensor_index(
    tensor_evidence: _TensorIndexEvidence,
    config_payload: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    if tensor_evidence.status != "ok":
        return ("text",)
    if _tensor_index_missing_declared_modalities(tensor_evidence, config_payload):
        return ("text",)
    modalities = ["text"]
    if "vision" in tensor_evidence.modalities:
        modalities.append("image")
    if "audio" in tensor_evidence.modalities:
        modalities.append("audio")
    if "video" in tensor_evidence.modalities:
        modalities.append("video")
    return tuple(modalities)


def _tensor_index_receipt_metadata(
    tensor_evidence: _TensorIndexEvidence,
    config_payload: Mapping[str, object] | None,
) -> dict[str, str]:
    metadata = {
        "melix.capability.tensor_index.source": tensor_evidence.source_path,
        "melix.capability.tensor_index.status": tensor_evidence.status,
        "melix.capability.tensor_index.modalities": ",".join(tensor_evidence.modalities),
        "melix.capability.tensor_index.warning_code": "",
        "melix.capability.tensor_index.warning_modalities": "",
        "melix.capability.tensor_index.warning_source": "",
    }
    if tensor_evidence.tensor_counts:
        metadata["melix.capability.tensor_index.tensor_counts"] = ",".join(
            f"{modality}:{tensor_evidence.tensor_counts[modality]}"
            for modality in ("text", "vision", "audio", "video", "projector", "draft")
            if tensor_evidence.tensor_counts.get(modality, 0) > 0
        )

    if tensor_evidence.status != "ok":
        metadata["melix.capability.tensor_index.warning_code"] = tensor_evidence.status
        metadata["melix.capability.tensor_index.warning_source"] = tensor_evidence.source_path
        return metadata

    missing_declared = _tensor_index_missing_declared_modalities(tensor_evidence, config_payload)
    if missing_declared:
        metadata["melix.capability.tensor_index.warning_code"] = "config_declared_missing_tensor_evidence"
        metadata["melix.capability.tensor_index.warning_modalities"] = ",".join(
            modality for modality in ("vision", "audio", "video", "projector", "draft") if modality in missing_declared
        )
    return metadata


def _tensor_index_missing_declared_modalities(
    tensor_evidence: _TensorIndexEvidence,
    config_payload: Mapping[str, object] | None,
) -> set[str]:
    if tensor_evidence.status != "ok":
        return set()
    missing_declared = _config_declared_modalities(config_payload) - set(tensor_evidence.modalities)
    missing_declared.discard("text")
    return missing_declared


def _config_declared_modalities(config_payload: Mapping[str, object] | None) -> set[str]:
    if not isinstance(config_payload, Mapping):
        return set()
    modalities = {"text"}
    if _config_declares_component(config_payload, "vision_config") or any(
        key in config_payload and config_payload.get(key) not in (None, "", [], {})
        for key in ("image_token_id", "boi_token_id", "eoi_token_id")
    ):
        modalities.add("vision")
    if _config_declares_component(config_payload, "audio_config") or (
        "audio_token_id" in config_payload and config_payload.get("audio_token_id") not in (None, "", [], {})
    ):
        modalities.add("audio")
    if _config_declares_component(config_payload, "video_config") or (
        "video_token_id" in config_payload and config_payload.get("video_token_id") not in (None, "", [], {})
    ):
        modalities.add("video")
    if _config_declares_component(config_payload, "projector_config"):
        modalities.add("projector")
    if _config_declares_component(config_payload, "draft_config") or _normalized(str(config_payload.get("draft_model_type", ""))):
        modalities.add("draft")
    return modalities


def _config_declares_component(config_payload: Mapping[str, object], key: str) -> bool:
    value = config_payload.get(key)
    return isinstance(value, Mapping) and len(value) > 0


def _audio_capability_metadata(
    *,
    family_id: str,
    model_kind: str,
) -> dict[str, str]:
    if model_kind == "transcription":
        route_kind = "python_transcription"
        capability_class = "transcription"
        supported_modalities = ("audio", "text")
        supported_tasks = ("transcribe",)
    else:
        route_kind = "python_speech"
        capability_class = "speech"
        supported_modalities = ("text", "audio")
        supported_tasks = ("speak",)
    return _capability_metadata(
        adapter_set_hash=f"audio-family-{family_id}",
        route_kind=route_kind,
        capability_class=capability_class,
        supported_modalities=supported_modalities,
        supported_tasks=supported_tasks,
        supported_parsers=("text",),
    )


def _audio_metadata(
    *,
    backend_id: str,
    family_id: str,
    install_profile: str,
    languages: tuple[str, ...] = (),
    voice_mode: str = "",
    output_formats: tuple[str, ...] = (),
    supports_instructions: bool = False,
    voice_catalog_summary: str = "",
    voice_locales: tuple[str, ...] = (),
    default_locale: str = "",
    packaged_default_locale: str = "",
    locale_policy: str = "",
) -> dict[str, str]:
    return {
        _AUDIO_BACKEND_ID_KEY: backend_id,
        _AUDIO_FAMILY_ID_KEY: family_id,
        _AUDIO_INSTALL_PROFILE_KEY: install_profile,
        _AUDIO_LANGUAGES_KEY: ",".join(languages),
        _AUDIO_VOICE_MODE_KEY: voice_mode,
        _AUDIO_OUTPUT_FORMATS_KEY: ",".join(output_formats),
        _AUDIO_SUPPORTS_INSTRUCTIONS_KEY: "true" if supports_instructions else "false",
        _AUDIO_VOICE_CATALOG_SUMMARY_KEY: voice_catalog_summary,
        _AUDIO_VOICE_LOCALES_KEY: ",".join(voice_locales),
        _AUDIO_DEFAULT_LOCALE_KEY: default_locale,
        _AUDIO_PACKAGED_DEFAULT_LOCALE_KEY: packaged_default_locale,
        _AUDIO_LOCALE_POLICY_KEY: locale_policy,
    }


def _audio_setup_metadata(*, capability: str, role: str, priority: int) -> dict[str, str]:
    return {
        "melix.audio.capability": capability,
        "melix.audio.setup_role": role,
        "melix.audio.setup_priority": str(priority),
    }


class WorkerModelCatalog:
    def __init__(self, environment: dict[str, str] | None = None) -> None:
        self._uses_explicit_environment = environment is not None
        self._environment = dict(environment or os.environ)
        self._seed_models = {
            "melix-dev-text": self.dev_text_model(environment=self._environment),
            "melix-dev-embed": self.dev_embedding_model(environment=self._environment),
            "melix-dev-rerank": self.dev_rerank_model(environment=self._environment),
            "melix-dev-ocr": self.dev_ocr_model(environment=self._environment),
            "melix-dev-vlm": self.dev_vlm_model(environment=self._environment),
            "melix-dev-transcribe": self.dev_transcription_model(environment=self._environment),
            "melix-dev-speech": self.dev_speech_model(environment=self._environment),
            "melix-dev-image": self.dev_image_model(environment=self._environment),
        }
        for helper in (
            self.mlx_whisper_model,
            self.mlx_parakeet_model,
            self.mlx_kokoro_model,
            self.mlx_qwen3_tts_model,
        ):
            model = helper(environment=self._environment)
            if model is not None:
                self._seed_models[model.model_id] = model
        self._models = dict(self._seed_models)
        self._overlay_models: dict[str, common_pb2.ModelSpec] = {}
        self._registry_lock = threading.RLock()
        self._json_file_cache: dict[Path, tuple[int, int, dict[str, object]]] = {}
        self._text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] = {}
        self._registry_snapshot_cache: dict[tuple[str, ...], RegistrySnapshot] = {}
        self._source_requested_root_sets_cache: dict[str, set[str]] = {}
        self._runtime_models_snapshot: RegistrySnapshot | None = None
        self._runtime_models_overlay_revision = 0
        self._overlay_revision = 0
        self._active_registry_roots = tuple(self._configured_registry_roots())
        self._last_registry_snapshot = self._refresh_registry_snapshot(self._active_registry_roots)
        self._registry_snapshot_cache[self._active_registry_roots] = self._last_registry_snapshot

    def get(self, model_id: str) -> common_pb2.ModelSpec | None:
        with self._registry_lock:
            return self._models.get(model_id)

    def all_models(self) -> list[common_pb2.ModelSpec]:
        with self._registry_lock:
            return [self._models[model_id] for model_id in sorted(self._models)]

    def register_model(self, model: common_pb2.ModelSpec) -> common_pb2.ModelSpec:
        registered = common_pb2.ModelSpec()
        registered.CopyFrom(model)
        with self._registry_lock:
            self._overlay_models[registered.model_id] = registered
            self._overlay_revision += 1
            self._rebuild_runtime_models()
            return self._models[registered.model_id]

    def remove_model(self, model_id: str) -> bool:
        with self._registry_lock:
            removed = self._overlay_models.pop(model_id, None)
            if removed is None:
                return False
            self._overlay_revision += 1
            self._rebuild_runtime_models()
            return True

    def registry_snapshot(
        self,
        *,
        rescan: bool = False,
        registry_roots: Iterable[str] | None = None,
    ) -> RegistrySnapshot:
        roots_key = tuple(self._resolved_registry_roots(registry_roots))
        with self._registry_lock:
            if rescan or roots_key not in self._registry_snapshot_cache:
                self._registry_snapshot_cache[roots_key] = self._refresh_registry_snapshot(roots_key)
            snapshot = self._registry_snapshot_cache[roots_key]
            self._active_registry_roots = roots_key
            self._last_registry_snapshot = snapshot
            if not self._runtime_models_current(snapshot):
                self._rebuild_runtime_models(snapshot=snapshot)
            return snapshot

    def _runtime_models_current(self, snapshot: RegistrySnapshot) -> bool:
        return (
            self._runtime_models_snapshot is snapshot
            and self._runtime_models_overlay_revision == self._overlay_revision
        )

    def _rebuild_runtime_models(self, snapshot: RegistrySnapshot | None = None) -> None:
        active_snapshot = snapshot or self._last_registry_snapshot
        new_models = dict(self._seed_models)
        for model in active_snapshot.models:
            new_models.setdefault(model.model_id, model)
        for model_id, model in self._overlay_models.items():
            new_models[model_id] = model
        self._models = new_models
        self._runtime_models_snapshot = active_snapshot
        self._runtime_models_overlay_revision = self._overlay_revision

    def registry_snapshot_payload(
        self,
        *,
        rescan: bool = False,
        registry_roots: Iterable[str] | None = None,
    ) -> dict[str, object]:
        snapshot = self.registry_snapshot(rescan=rescan, registry_roots=registry_roots)
        discovered_models = {model.model_id: model for model in snapshot.models}
        model_classifications = (
            snapshot.model_classifications
            or {
                model_id: _classification_for_admitted_model(model)
                for model_id, model in discovered_models.items()
            }
        )
        scan_receipt = snapshot.scan_receipt or self._build_scan_receipt(
            scan_id=snapshot.scan_id,
            started_at_unix_ms=snapshot.scan_started_at_unix_ms,
            completed_at_unix_ms=snapshot.scanned_at_unix_ms,
            source_descriptors=snapshot.source_descriptors,
            roots=snapshot.roots,
            discovered_models=discovered_models,
            model_classifications=model_classifications,
            candidate_findings=snapshot.candidate_findings,
            aggregated_invalid_entry_counts=snapshot.aggregated_invalid_entry_counts,
            hf_cache_roots=snapshot.hf_cache_roots,
            root_scan_latency_ms=snapshot.root_scan_latency_ms,
        )
        return {
            "scanned_at_unix_ms": snapshot.scanned_at_unix_ms,
            "source_descriptors": [
                descriptor.to_payload()
                for descriptor in snapshot.source_descriptors
            ],
            "scan_receipt": scan_receipt.to_payload(),
            "roots": [
                {
                    "root_id": root.root_id,
                    "root_path": root.root_path,
                    "root_order": root.root_order,
                    "accessible": root.accessible,
                    "error_code": root.error_code,
                    "error_message": root.error_message,
                    "discovered_model_ids": list(root.discovered_model_ids),
                }
                for root in snapshot.roots
            ],
            "models": [
                self._registry_model_payload(model, model_classifications=model_classifications)
                for model in snapshot.models
            ],
        }

    def _registry_model_payload(
        self,
        model: common_pb2.ModelSpec,
        *,
        model_classifications: Mapping[str, ModelInventoryClassification],
    ) -> dict[str, object]:
        payload = {
            "model_id": model.model_id,
            "model_path": model.model_path,
            "model_kind": model.model_kind,
            "revision": model.revision,
            "tokenizer_hash": model.tokenizer_hash,
            "quant_profile_id": model.quant_profile_id,
            "parser_mode": model.parser_mode,
            "reasoning_mode": model.reasoning_mode,
            "max_context": model.max_context,
            "ext": dict(model.ext),
        }
        classification = model_classifications.get(model.model_id)
        if classification is not None:
            payload["classification"] = classification.to_payload()
        return payload

    def _refresh_registry_snapshot(self, registry_roots: tuple[str, ...]) -> RegistrySnapshot:
        self._prune_text_prefix_cache()
        started_at_unix_ms = int(time.time() * 1000)
        scan_result = self._scan_registry_roots(registry_roots)
        roots = scan_result.roots
        discovered_models = scan_result.discovered_models
        hf_cache_roots = scan_result.hf_cache_roots
        _apply_gemma4_qat_companion_metadata(discovered_models.values())
        source_descriptors = self._source_descriptors_for_registry_roots(
            registry_roots,
            hf_cache_roots=hf_cache_roots,
        )
        completed_at_unix_ms = int(time.time() * 1000)
        return RegistrySnapshot(
            roots=tuple(roots),
            models=tuple(discovered_models[model_id] for model_id in sorted(discovered_models)),
            scanned_at_unix_ms=completed_at_unix_ms,
            source_descriptors=source_descriptors,
            scan_started_at_unix_ms=started_at_unix_ms,
            scan_id=_stable_inventory_scan_id(
                registry_roots=registry_roots,
                started_at_unix_ms=started_at_unix_ms,
            ),
            hf_cache_roots=hf_cache_roots,
            candidate_findings=tuple(scan_result.candidate_findings),
            aggregated_invalid_entry_counts=scan_result.aggregated_invalid_entry_counts,
            root_scan_latency_ms=scan_result.root_scan_latency_ms,
        )

    def _source_descriptors_for_registry_roots(
        self,
        registry_roots: tuple[str, ...],
        *,
        hf_cache_roots: frozenset[str] = frozenset(),
    ) -> tuple[ModelInventorySourceDescriptor, ...]:
        effective_roots_by_kind: dict[str, list[str]] = {
            source_kind: []
            for source_kind in _MODEL_INVENTORY_SOURCE_KINDS
        }
        for root in registry_roots:
            effective_roots_by_kind[
                self._source_kind_for_registry_root(root, hf_cache_roots=hf_cache_roots)
            ].append(root)

        requested_roots_by_kind = self._requested_roots_by_source_kind(
            effective_roots_by_kind=effective_roots_by_kind,
            hf_cache_roots=hf_cache_roots,
        )
        return (
            self._melix_managed_root_source_descriptor(
                requested_roots=tuple(requested_roots_by_kind[_SOURCE_KIND_MELIX_MANAGED_ROOT]),
                effective_roots=tuple(effective_roots_by_kind[_SOURCE_KIND_MELIX_MANAGED_ROOT]),
            ),
            self._huggingface_cache_source_descriptor(
                requested_roots=tuple(requested_roots_by_kind[_SOURCE_KIND_HUGGINGFACE_CACHE]),
                effective_roots=tuple(effective_roots_by_kind[_SOURCE_KIND_HUGGINGFACE_CACHE]),
            ),
            self._external_runtime_source_descriptor(
                descriptor_id="modelscope-cache",
                source_kind=_SOURCE_KIND_MODELSCOPE_CACHE,
                display_name="ModelScope cache snapshots",
                env_vars=("MODELSCOPE_CACHE", "MODELSCOPE_HOME"),
                requested_roots=tuple(requested_roots_by_kind[_SOURCE_KIND_MODELSCOPE_CACHE]),
                effective_roots=tuple(effective_roots_by_kind[_SOURCE_KIND_MODELSCOPE_CACHE]),
                store_layout="ModelScope cache snapshot directories",
            ),
            self._external_runtime_source_descriptor(
                descriptor_id="ollama-store",
                source_kind=_SOURCE_KIND_OLLAMA_STORE,
                display_name="Ollama model store",
                env_vars=("OLLAMA_MODELS",),
                requested_roots=tuple(requested_roots_by_kind[_SOURCE_KIND_OLLAMA_STORE]),
                effective_roots=tuple(effective_roots_by_kind[_SOURCE_KIND_OLLAMA_STORE]),
                store_layout="Ollama manifest and blob store",
            ),
            self._external_runtime_source_descriptor(
                descriptor_id="lm-studio-store",
                source_kind=_SOURCE_KIND_LM_STUDIO_STORE,
                display_name="LM Studio model store",
                env_vars=("LM_STUDIO_MODELS", "LMSTUDIO_MODELS", "LM_STUDIO_HOME"),
                requested_roots=tuple(requested_roots_by_kind[_SOURCE_KIND_LM_STUDIO_STORE]),
                effective_roots=tuple(effective_roots_by_kind[_SOURCE_KIND_LM_STUDIO_STORE]),
                store_layout="LM Studio local model directories",
            ),
        )

    def _build_scan_receipt(
        self,
        *,
        scan_id: str,
        started_at_unix_ms: int,
        completed_at_unix_ms: int,
        source_descriptors: tuple[ModelInventorySourceDescriptor, ...],
        roots: tuple[RegistryRootSnapshot, ...],
        discovered_models: Mapping[str, common_pb2.ModelSpec],
        model_classifications: Mapping[str, ModelInventoryClassification],
        candidate_findings: tuple[_InventoryScanCandidate, ...],
        aggregated_invalid_entry_counts: Mapping[str, int],
        hf_cache_roots: frozenset[str],
        root_scan_latency_ms: Mapping[str, float],
    ) -> ModelInventoryScanReceipt:
        records: list[_InventoryClassificationRecord] = [
            _InventoryClassificationRecord(
                root_path=_normalized(model.ext.get("melix.registry_root_path")),
                invalid_entry=False,
                classification=classification,
            )
            for model_id, classification in model_classifications.items()
            for model in (discovered_models.get(model_id),)
            if model is not None
        ]
        for candidate in candidate_findings:
            source_kind = self._source_kind_for_registry_root(
                candidate.root_path,
                hf_cache_roots=hf_cache_roots,
            )
            records.append(
                _classification_record_from_candidate(
                    candidate,
                    source_kind=source_kind,
                    invalid_entry=bool(candidate.metrics.get("invalid_entry")),
                )
            )

        records_by_root: dict[str, list[_InventoryClassificationRecord]] = {}
        for record in records:
            canonical_record_root = (
                _canonical_registry_root_path(record.root_path)
                if record.root_path.strip()
                else ""
            )
            records_by_root.setdefault(canonical_record_root, []).append(record)

        source_receipts: list[ModelInventorySourceScanReceipt] = []
        source_receipt_keys: set[tuple[str, str]] = set()
        redaction_count = 0
        for root in roots:
            source_kind = self._source_kind_for_registry_root(
                root.root_path,
                hf_cache_roots=hf_cache_roots,
            )
            root_records = records_by_root.get(_canonical_registry_root_path(root.root_path), [])
            source_receipt, receipt_redaction_count = self._source_receipt_for_root(
                root,
                source_kind=source_kind,
                root_records=root_records,
                aggregated_invalid_entry_count=aggregated_invalid_entry_counts.get(
                    _canonical_registry_root_path(root.root_path),
                    0,
                ),
                scan_latency_ms=root_scan_latency_ms.get(root.root_path, 0.0),
            )
            redaction_count += receipt_redaction_count
            source_receipt_keys.add((source_kind, _canonical_registry_root_path(root.root_path)))
            source_receipts.append(source_receipt)

        for descriptor in source_descriptors:
            for requested_root in descriptor.requested_roots:
                root_key = (descriptor.source_kind, _canonical_registry_root_path(requested_root))
                if root_key in source_receipt_keys:
                    continue
                source_receipt, receipt_redaction_count = self._source_receipt_for_requested_only_root(
                    descriptor,
                    requested_root=requested_root,
                )
                redaction_count += receipt_redaction_count
                source_receipt_keys.add(root_key)
                source_receipts.append(source_receipt)

        classifications = tuple(record.classification for record in records)
        classification_redaction_count = sum(
            int(classification.metrics.get("redaction_count", 0) or 0)
            for classification in classifications
        )
        redaction_count += classification_redaction_count
        usable_count = sum(1 for record in records if record.classification.usable_state == "usable")
        unsupported_count = sum(1 for record in records if record.classification.usable_state == "unsupported")
        incomplete_count = sum(1 for record in records if record.classification.usable_state == "incomplete")
        ambiguous_count = sum(1 for record in records if record.classification.usable_state == "ambiguous")
        sampled_invalid_entry_count = sum(1 for record in records if record.invalid_entry)
        aggregated_invalid_entry_count = sum(max(0, int(count)) for count in aggregated_invalid_entry_counts.values())
        invalid_entry_count = sampled_invalid_entry_count + aggregated_invalid_entry_count
        requested_source_count = sum(len(descriptor.requested_roots) for descriptor in source_descriptors)
        effective_source_count = sum(len(descriptor.effective_roots) for descriptor in source_descriptors)
        payload_probe = {
            "scan_id": scan_id,
            "source_receipts": [receipt.to_payload() for receipt in source_receipts],
            "discovered_models": [classification.to_payload() for classification in classifications],
        }
        scan_payload_byte_size = _payload_size_bytes(payload_probe)
        summary = {
            "scan_status": (
                "completed_with_warnings"
                if unsupported_count or incomplete_count or ambiguous_count or invalid_entry_count
                else "completed"
            ),
            "source_count": len(source_descriptors),
            "requested_source_count": requested_source_count,
            "effective_source_count": effective_source_count,
            "invalid_source_count": sum(
                1
                for receipt in source_receipts
                if not receipt.accessible and receipt.failure_code != "scanner_not_implemented"
            ),
            "discovered_model_count": len(records) + aggregated_invalid_entry_count,
            "usable_model_count": usable_count,
            "unsupported_model_count": unsupported_count,
            "incomplete_model_count": incomplete_count,
            "ambiguous_model_count": ambiguous_count + aggregated_invalid_entry_count,
            "invalid_entry_count": invalid_entry_count,
        }
        metrics = {
            "inventory_scan_latency_ms": float(max(0, completed_at_unix_ms - started_at_unix_ms)),
            "scan_payload_byte_size": scan_payload_byte_size,
            "source_count": len(source_descriptors),
            "requested_source_count": requested_source_count,
            "effective_source_count": effective_source_count,
            "invalid_source_count": summary["invalid_source_count"],
            "discovered_model_count": len(records) + aggregated_invalid_entry_count,
            "usable_model_count": usable_count,
            "unsupported_model_count": unsupported_count,
            "incomplete_model_count": incomplete_count,
            "ambiguous_model_count": ambiguous_count + aggregated_invalid_entry_count,
            "classification_latency_ms": 0.0,
            "redaction_count": redaction_count,
            "catalog_scan_latency_ms": 0.0,
            "catalog_result_count": 0,
            "pull_cancel_latency_ms": 0.0,
            "partial_artifact_cleanup_latency_ms": 0.0,
        }
        return ModelInventoryScanReceipt(
            scan_id=scan_id,
            started_at_unix_ms=started_at_unix_ms,
            completed_at_unix_ms=completed_at_unix_ms,
            requested_sources=tuple(
                self._receipt_source_roots(descriptor, roots_attr="requested_roots")
                for descriptor in source_descriptors
            ),
            effective_sources=tuple(
                self._receipt_source_roots(descriptor, roots_attr="effective_roots")
                for descriptor in source_descriptors
            ),
            source_receipts=tuple(source_receipts),
            discovered_models=classifications,
            summary=summary,
            redaction_summary={
                "strategy": "basename_sha256_16",
                "redaction_count": redaction_count,
                "path_fields": [
                    "requested_root",
                    "effective_root",
                    "model_path",
                    "source_model_id",
                ],
                "secret_like_values_redacted": redaction_count,
            },
            metrics=metrics,
        )

    def _receipt_source_roots(
        self,
        descriptor: ModelInventorySourceDescriptor,
        *,
        roots_attr: str,
    ) -> dict[str, object]:
        roots = getattr(descriptor, roots_attr)
        redacted_roots = [_inventory_redacted_value(root)[0] for root in roots]
        return {
            "descriptor_id": descriptor.descriptor_id,
            "source_kind": descriptor.source_kind,
            "roots": redacted_roots,
            "root_count": len(redacted_roots),
        }

    def _source_receipt_for_root(
        self,
        root: RegistryRootSnapshot,
        *,
        source_kind: str,
        root_records: list[_InventoryClassificationRecord],
        aggregated_invalid_entry_count: int,
        scan_latency_ms: float,
    ) -> tuple[ModelInventorySourceScanReceipt, int]:
        root_redaction, root_redaction_count, root_digest = _redacted_inventory_path(root.root_path)
        redacted_effective_root = str(root_redaction["display"])
        effective_redaction_count = root_redaction_count
        usable_count = sum(1 for record in root_records if record.classification.usable_state == "usable")
        unsupported_count = sum(1 for record in root_records if record.classification.usable_state == "unsupported")
        incomplete_count = sum(1 for record in root_records if record.classification.usable_state == "incomplete")
        ambiguous_count = (
            sum(1 for record in root_records if record.classification.usable_state == "ambiguous")
            + max(0, aggregated_invalid_entry_count)
        )
        invalid_entry_count = (
            sum(1 for record in root_records if record.invalid_entry)
            + max(0, aggregated_invalid_entry_count)
        )
        receipt = ModelInventorySourceScanReceipt(
            descriptor_id=_source_descriptor_id_for_kind(source_kind),
            source_kind=source_kind,
            requested_root=redacted_effective_root,
            effective_root=redacted_effective_root,
            root_redaction=root_redaction,
            root_path_digest=root_digest,
            accessible=root.accessible,
            scan_status=_scan_status_for_counts(
                accessible=root.accessible,
                failure_code=root.error_code,
                unsupported_model_count=unsupported_count,
                incomplete_model_count=incomplete_count,
                ambiguous_model_count=ambiguous_count,
                invalid_entry_count=invalid_entry_count,
            ),
            failure_code=root.error_code,
            failure_message=_redacted_inventory_path(root.error_message)[0]["display"] if root.error_message else "",
            discovered_model_count=len(root_records) + max(0, aggregated_invalid_entry_count),
            usable_model_count=usable_count,
            unsupported_model_count=unsupported_count,
            incomplete_model_count=incomplete_count,
            ambiguous_model_count=ambiguous_count,
            invalid_entry_count=invalid_entry_count,
            redaction_count=effective_redaction_count + root_redaction_count,
            scan_latency_ms=scan_latency_ms,
        )
        receipt = replace(receipt, payload_byte_size=_payload_size_bytes(receipt.to_payload()))
        return receipt, receipt.redaction_count

    def _source_receipt_for_requested_only_root(
        self,
        descriptor: ModelInventorySourceDescriptor,
        *,
        requested_root: str,
    ) -> tuple[ModelInventorySourceScanReceipt, int]:
        root_redaction, root_redaction_count, root_digest = _redacted_inventory_path(requested_root)
        redacted_requested_root = str(root_redaction["display"])
        requested_redaction_count = root_redaction_count
        failure_code = (
            "scanner_not_implemented"
            if descriptor.discovery_policy.get("scanner") == "descriptor_only_until_source_specific_scanner_lands"
            else "not_found"
        )
        failure_message = (
            "Source scanner is descriptor-only in this implementation slice."
            if failure_code == "scanner_not_implemented"
            else "Requested source root was not scanned."
        )
        receipt = ModelInventorySourceScanReceipt(
            descriptor_id=descriptor.descriptor_id,
            source_kind=descriptor.source_kind,
            requested_root=redacted_requested_root,
            effective_root="",
            root_redaction=root_redaction,
            root_path_digest=root_digest,
            accessible=False,
            scan_status="skipped",
            failure_code=failure_code,
            failure_message=failure_message,
            discovered_model_count=0,
            usable_model_count=0,
            unsupported_model_count=0,
            incomplete_model_count=0,
            ambiguous_model_count=0,
            invalid_entry_count=0,
            redaction_count=requested_redaction_count + root_redaction_count,
            scan_latency_ms=0.0,
        )
        receipt = replace(receipt, payload_byte_size=_payload_size_bytes(receipt.to_payload()))
        return receipt, receipt.redaction_count

    def _source_kind_for_registry_root(
        self,
        root_path: str,
        *,
        hf_cache_roots: frozenset[str] = frozenset(),
    ) -> str:
        root = _canonical_registry_root_path(root_path)
        if root in self._source_requested_root_set(_SOURCE_KIND_HUGGINGFACE_CACHE):
            return _SOURCE_KIND_HUGGINGFACE_CACHE
        if root in self._source_requested_root_set(_SOURCE_KIND_MODELSCOPE_CACHE):
            return _SOURCE_KIND_MODELSCOPE_CACHE
        if root in self._source_requested_root_set(_SOURCE_KIND_OLLAMA_STORE):
            return _SOURCE_KIND_OLLAMA_STORE
        if root in self._source_requested_root_set(_SOURCE_KIND_LM_STUDIO_STORE):
            return _SOURCE_KIND_LM_STUDIO_STORE
        if root in hf_cache_roots:
            return _SOURCE_KIND_HUGGINGFACE_CACHE
        return _SOURCE_KIND_MELIX_MANAGED_ROOT

    def _requested_roots_by_source_kind(
        self,
        *,
        effective_roots_by_kind: Mapping[str, list[str]],
        hf_cache_roots: frozenset[str],
    ) -> dict[str, list[str]]:
        requested: dict[str, list[str]] = {
            source_kind: []
            for source_kind in _MODEL_INVENTORY_SOURCE_KINDS
        }
        for root in self._split_env_paths(_REGISTRY_ROOTS_ENV_KEY):
            requested[
                self._source_kind_for_registry_root(root, hf_cache_roots=hf_cache_roots)
            ].append(root)
        managed_root = (self._environment.get(_MANAGED_MODEL_ROOT_ENV_KEY) or "").strip()
        if managed_root:
            requested[_SOURCE_KIND_MELIX_MANAGED_ROOT].append(managed_root)
        else:
            default_managed_root = self._default_managed_model_root()
            if default_managed_root is not None:
                requested[_SOURCE_KIND_MELIX_MANAGED_ROOT].append(os.fspath(default_managed_root))

        requested[_SOURCE_KIND_HUGGINGFACE_CACHE].extend(
            self._requested_huggingface_cache_roots()
        )

        for key in ("MODELSCOPE_CACHE", "MODELSCOPE_HOME"):
            requested[_SOURCE_KIND_MODELSCOPE_CACHE].extend(self._split_env_paths(key))
        requested[_SOURCE_KIND_OLLAMA_STORE].extend(self._split_env_paths("OLLAMA_MODELS"))
        for key in ("LM_STUDIO_MODELS", "LMSTUDIO_MODELS", "LM_STUDIO_HOME"):
            requested[_SOURCE_KIND_LM_STUDIO_STORE].extend(self._split_env_paths(key))

        for source_kind, effective_roots in effective_roots_by_kind.items():
            requested[source_kind].extend(effective_roots)

        return {
            source_kind: self._dedupe_requested_roots(roots)
            for source_kind, roots in requested.items()
        }

    def _source_requested_root_set(self, source_kind: str) -> set[str]:
        cached = self._source_requested_root_sets_cache.get(source_kind)
        if cached is not None:
            return cached
        if source_kind == _SOURCE_KIND_HUGGINGFACE_CACHE:
            root_set = {
                _canonical_registry_root_path(root)
                for root in self._requested_huggingface_cache_roots()
                if root.strip()
            }
        elif source_kind == _SOURCE_KIND_MODELSCOPE_CACHE:
            keys = ("MODELSCOPE_CACHE", "MODELSCOPE_HOME")
        elif source_kind == _SOURCE_KIND_OLLAMA_STORE:
            keys = ("OLLAMA_MODELS",)
        elif source_kind == _SOURCE_KIND_LM_STUDIO_STORE:
            keys = ("LM_STUDIO_MODELS", "LMSTUDIO_MODELS", "LM_STUDIO_HOME")
        else:
            keys = ()
        if source_kind != _SOURCE_KIND_HUGGINGFACE_CACHE:
            root_set = {
                _canonical_registry_root_path(root)
                for key in keys
                for root in self._split_env_paths(key)
            }
        self._source_requested_root_sets_cache[source_kind] = root_set
        return root_set

    def _requested_huggingface_cache_roots(self) -> list[str]:
        env_hf_cache = (self._environment.get("HUGGINGFACE_HUB_CACHE") or "").strip()
        if env_hf_cache:
            return [env_hf_cache]

        env_hf_home = (self._environment.get("HF_HOME") or "").strip()
        if env_hf_home:
            return [os.fspath(Path(env_hf_home).expanduser() / "hub")]

        default_hf_cache = self._default_huggingface_cache_root()
        if default_hf_cache is not None:
            return [os.fspath(default_hf_cache)]
        return []

    def _split_env_paths(self, key: str) -> list[str]:
        raw = self._environment.get(key) or ""
        if not raw.strip():
            return []
        return [
            part.strip()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]

    def _dedupe_requested_roots(self, roots: Iterable[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for root in roots:
            normalized = root.strip()
            if not normalized:
                continue
            canonical = _canonical_registry_root_path(normalized)
            if canonical in seen:
                continue
            seen.add(canonical)
            deduped.append(normalized)
        return deduped

    def _melix_managed_root_source_descriptor(
        self,
        *,
        requested_roots: tuple[str, ...],
        effective_roots: tuple[str, ...],
    ) -> ModelInventorySourceDescriptor:
        return ModelInventorySourceDescriptor(
            descriptor_id="melix-managed-root",
            source_kind=_SOURCE_KIND_MELIX_MANAGED_ROOT,
            display_name="Melix-managed model roots",
            ownership="melix_owned",
            requested_roots=requested_roots,
            effective_roots=effective_roots,
            path_policy={
                "configured_by": [
                    _REGISTRY_ROOTS_ENV_KEY,
                    _MANAGED_MODEL_ROOT_ENV_KEY,
                    "MELIX_HOME",
                    "HOME",
                ],
                "resolution": "expanduser.resolve(strict=false)",
                "dedupe": "canonical_path_first_wins",
                "scan_scope": "recursive_manifest_and_mlx_directory_scan",
                "writable": True,
            },
            discovery_policy={
                "scanner": "WorkerModelCatalog.registry_snapshot",
                "admission": "manifest_or_mlx_directory",
                "invalid_source_isolation": "per_root",
                "missing_roots": "reported_in_roots_without_poisoning_valid_roots",
            },
            receipt_policy=_inventory_receipt_policy(
                source_kind=_SOURCE_KIND_MELIX_MANAGED_ROOT,
            ),
            redaction_policy=_inventory_redaction_policy(),
            failure_modes=(
                "not_found",
                "permission_denied",
                "manifest_invalid",
                "invalid_layout",
                "scan_io_error",
            ),
            catalog_policy={
                "searchable": False,
                "browse_surface": "local_filesystem",
            },
            pull_policy={
                "supports_pull": False,
                "admission": "managed_downloads_recorded_after_fetch",
            },
            metrics_policy=_inventory_metrics_policy(),
        )

    def _huggingface_cache_source_descriptor(
        self,
        *,
        requested_roots: tuple[str, ...],
        effective_roots: tuple[str, ...],
    ) -> ModelInventorySourceDescriptor:
        return ModelInventorySourceDescriptor(
            descriptor_id="huggingface-cache",
            source_kind=_SOURCE_KIND_HUGGINGFACE_CACHE,
            display_name="Hugging Face cache snapshots",
            ownership="external_read_only",
            requested_roots=requested_roots,
            effective_roots=effective_roots,
            path_policy={
                "configured_by": [
                    "HUGGINGFACE_HUB_CACHE",
                    "HF_HOME",
                    "HOME",
                    _REGISTRY_ROOTS_ENV_KEY,
                ],
                "resolution": "expanduser.resolve(strict=false)",
                "dedupe": "canonical_path_first_wins",
                "layout": "models--<org>--<name>/snapshots/<revision>",
                "writable": False,
            },
            discovery_policy={
                "scanner": "WorkerModelCatalog._scan_huggingface_cache_models",
                "admission": "config_plus_weight_files_plus_mlx_signal",
                "revision_receipt": "refs/<name> mapped to snapshot id when available",
                "invalid_source_isolation": "per_root",
                "missing_roots": "reported_in_roots_without_poisoning_valid_roots",
            },
            receipt_policy=_inventory_receipt_policy(
                source_kind=_SOURCE_KIND_HUGGINGFACE_CACHE,
            ),
            redaction_policy=_inventory_redaction_policy(),
            failure_modes=(
                "not_found",
                "permission_denied",
                "invalid_cache_repo",
                "snapshot_incomplete",
                "metadata_not_mlx",
                "scan_io_error",
            ),
            catalog_policy={
                "searchable": True,
                "discovery_backend": "huggingface_hub",
                "search_method": "HubCatalog.search_models",
                "card_method": "HubCatalog.get_model_card",
                "mlx_filter": "filter=mlx",
            },
            pull_policy={
                "supports_pull": True,
                "states": [
                    "queued",
                    "resolving",
                    "downloading",
                    "verifying",
                    "admitted",
                    "cancel_requested",
                    "cancelled",
                    "failed",
                    "partial_cleanup_pending",
                    "partial_cleanup_done",
                ],
                "cancel_semantics": "best_effort_transport_cancel_then_partial_cleanup",
                "partial_artifacts": "receipt_records_bytes_and_cleanup_state",
            },
            metrics_policy=_inventory_metrics_policy(),
        )

    def _external_runtime_source_descriptor(
        self,
        *,
        descriptor_id: str,
        source_kind: str,
        display_name: str,
        env_vars: tuple[str, ...],
        requested_roots: tuple[str, ...],
        effective_roots: tuple[str, ...],
        store_layout: str,
    ) -> ModelInventorySourceDescriptor:
        return ModelInventorySourceDescriptor(
            descriptor_id=descriptor_id,
            source_kind=source_kind,
            display_name=display_name,
            ownership="external_read_only",
            requested_roots=requested_roots,
            effective_roots=effective_roots,
            path_policy={
                "configured_by": list(env_vars) + [_REGISTRY_ROOTS_ENV_KEY],
                "resolution": "expanduser.resolve(strict=false)",
                "dedupe": "canonical_path_first_wins",
                "layout": store_layout,
                "writable": False,
            },
            discovery_policy={
                "scanner": "descriptor_only_until_source_specific_scanner_lands",
                "admission": "reported_as_requested_and_effective_roots_only",
                "invalid_source_isolation": "per_source",
                "missing_roots": "kept_out_of_model_admission_for_other_sources",
            },
            receipt_policy=_inventory_receipt_policy(source_kind=source_kind),
            redaction_policy=_inventory_redaction_policy(),
            failure_modes=(
                "not_found",
                "permission_denied",
                "invalid_layout",
                "unsupported_manifest",
                "scan_io_error",
            ),
            catalog_policy={
                "searchable": False,
                "browse_surface": "external_runtime_store",
            },
            pull_policy={
                "supports_pull": False,
                "admission": "external_runtime_owned_artifacts_are_read_only",
            },
            metrics_policy=_inventory_metrics_policy(),
        )

    def _prune_text_prefix_cache(self) -> None:
        for path in tuple(self._text_prefix_cache):
            if not path.exists():
                self._text_prefix_cache.pop(path, None)

    def _scan_registry_roots(
        self,
        registry_roots: tuple[str, ...],
    ) -> _RegistryScanResult:
        roots: list[RegistryRootSnapshot] = []
        discovered_models: dict[str, common_pb2.ModelSpec] = {}
        hf_cache_roots: set[str] = set()
        candidate_findings: list[_InventoryScanCandidate] = []
        aggregated_invalid_entry_counts: dict[str, int] = {}
        root_scan_latency_ms: dict[str, float] = {}

        for index, root_path in enumerate(registry_roots, start=1):
            root_id = _stable_registry_root_id(root_path)
            root = Path(root_path)
            if not root.is_dir():
                roots.append(
                    RegistryRootSnapshot(
                        root_id=root_id,
                        root_path=str(root),
                        root_order=index,
                        accessible=False,
                        error_code="not_found",
                        error_message="Registry root does not exist.",
                    )
                )
                continue

            accepted_model_ids: list[str] = []
            manifest_paths, plain_local_model_dirs, hf_cache_repo_dirs = WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(root)
            if hf_cache_repo_dirs:
                hf_cache_roots.add(root_path)
            root_key = _canonical_registry_root_path(root_path)
            for manifest_path in manifest_paths:
                relative_path = manifest_path.parent.relative_to(root)
                if _path_derived_registry_identity(relative_path.parts) is None:
                    aggregated_invalid_entry_counts[root_key] = (
                        aggregated_invalid_entry_counts.get(root_key, 0) + 1
                    )
                    continue
                parsed = self._parse_registry_manifest(manifest_path)
                if parsed is None:
                    candidate_findings.append(
                        _inventory_candidate_for_path(
                            root_path=root_path,
                            model_id=relative_path.name or os.fspath(relative_path),
                            source_model_id=os.fspath(relative_path),
                            model_path=manifest_path.parent,
                            file_layout="melix_manifest",
                            config_payload={},
                            mlx_compatibility="unknown",
                            missing_file_state="unknown",
                            artifact_state="incomplete",
                            usable_state="ambiguous",
                            operator_message="Registry manifest is invalid or missing a model id.",
                            remediation="Repair or remove the manifest before using this model.",
                            invalid_entry=True,
                        )
                    )
                    continue
                model_id, model = parsed
                if model_id in discovered_models or model_id in self._seed_models:
                    continue
                if not _apply_registry_identity_metadata(
                    model,
                    relative_parts=relative_path.parts,
                ):
                    candidate_findings.append(
                        _inventory_candidate_for_path(
                            root_path=root_path,
                            model_id=model_id,
                            source_model_id=os.fspath(relative_path),
                            model_path=manifest_path.parent,
                            file_layout="melix_manifest",
                            config_payload={},
                            mlx_compatibility="unknown",
                            missing_file_state="unknown",
                            artifact_state="ready",
                            usable_state="ambiguous",
                            operator_message="Registry manifest path does not provide a stable Melix identity.",
                            remediation="Move the manifest under <provider>/<organization>/<model>/<variant> or add identity metadata.",
                        )
                    )
                    continue
                model.ext["melix.registry_root_id"] = root_id
                model.ext["melix.registry_root_path"] = str(root)
                model.ext["melix.registry_root_order"] = str(index)
                model.ext["melix.registry_relative_path"] = os.fspath(relative_path)
                model.ext["melix.registry_descriptor_path"] = str(manifest_path.parent)
                discovered_models[model_id] = model
                accepted_model_ids.append(model_id)

            self._scan_raw_model_directories(
                root=root,
                root_id=root_id,
                root_order=index,
                plain_local_model_dirs=plain_local_model_dirs,
                hf_cache_repo_dirs=hf_cache_repo_dirs,
                discovered_models=discovered_models,
                accepted_model_ids=accepted_model_ids,
                candidate_findings=candidate_findings,
            )

            roots.append(
                RegistryRootSnapshot(
                    root_id=root_id,
                    root_path=str(root),
                    root_order=index,
                    accessible=True,
                    discovered_model_ids=tuple(accepted_model_ids),
                )
            )

        return _RegistryScanResult(
            roots=roots,
            discovered_models=discovered_models,
            hf_cache_roots=frozenset(hf_cache_roots),
            candidate_findings=candidate_findings,
            aggregated_invalid_entry_counts=aggregated_invalid_entry_counts,
            root_scan_latency_ms=root_scan_latency_ms,
        )

    def _configured_registry_roots(self) -> list[str]:
        configured: list[str] = []
        raw = self._environment.get(_REGISTRY_ROOTS_ENV_KEY) or ""
        if raw.strip():
            configured.extend(raw.split(os.pathsep))

        managed_root = (self._environment.get(_MANAGED_MODEL_ROOT_ENV_KEY) or "").strip()
        if managed_root:
            configured.append(managed_root)
        else:
            default_managed_root = self._default_managed_model_root()
            if default_managed_root is not None:
                configured.append(os.fspath(default_managed_root))
        default_hf_cache = self._default_huggingface_cache_root()
        if default_hf_cache is not None:
            configured.append(os.fspath(default_hf_cache))

        return self._normalized_registry_roots(configured)

    def _resolved_registry_roots(self, registry_roots: Iterable[str] | None) -> list[str]:
        if registry_roots is None:
            return self._configured_registry_roots()

        requested_roots = list(registry_roots)
        managed_root = (self._environment.get(_MANAGED_MODEL_ROOT_ENV_KEY) or "").strip()
        if managed_root:
            requested_roots.append(managed_root)
        else:
            default_managed_root = self._default_managed_model_root()
            if default_managed_root is not None:
                requested_roots.append(os.fspath(default_managed_root))
        default_hf_cache = self._default_huggingface_cache_root()
        if default_hf_cache is not None:
            requested_roots.append(os.fspath(default_hf_cache))
        return self._normalized_registry_roots(requested_roots)

    def _default_huggingface_cache_root(self) -> Path | None:
        env_cache = (self._environment.get("HUGGINGFACE_HUB_CACHE") or "").strip()
        if env_cache:
            return Path(env_cache).expanduser().resolve()

        env_hf_home = (self._environment.get("HF_HOME") or "").strip()
        if env_hf_home:
            return (Path(env_hf_home).expanduser() / "hub").resolve()

        if self._uses_explicit_environment and "HOME" not in self._environment:
            return None
        home = (self._environment.get("HOME") or "").strip()
        root = (Path(home).expanduser() if home else Path.home()) / ".cache" / "huggingface" / "hub"
        resolved = root.resolve()
        return resolved if resolved.is_dir() else None

    def _default_managed_model_root(self) -> Path | None:
        if (
            self._uses_explicit_environment
            and "MELIX_HOME" not in self._environment
            and "HOME" not in self._environment
        ):
            return None
        home = (self._environment.get("MELIX_HOME") or "").strip()
        if not home:
            home = (self._environment.get("HOME") or "").strip()
            root = (Path(home).expanduser() if home else Path.home()) / ".melix"
        else:
            root = Path(home).expanduser()
        resolved = (root / "models" / "default-managed").resolve()
        return resolved if resolved.is_dir() else None

    def _normalized_registry_roots(self, raw_roots: Iterable[str]) -> list[str]:
        roots: list[str] = []
        seen: set[str] = set()
        for part in raw_roots:
            normalized = part.strip()
            if not normalized:
                continue
            canonical = _canonical_registry_root_path(normalized)
            if canonical in seen:
                continue
            seen.add(canonical)
            roots.append(canonical)
        return roots

    def _scan_raw_model_directories(
        self,
        *,
        root: Path,
        root_id: str,
        root_order: int,
        plain_local_model_dirs: Iterable[_PlainLocalModelScan],
        discovered_models: dict[str, common_pb2.ModelSpec],
        accepted_model_ids: list[str],
        candidate_findings: list[_InventoryScanCandidate],
        hf_cache_repo_dirs: Iterable[Path] | None = None,
    ) -> None:
        root_resolved = root.resolve()
        seen_paths: set[Path] = set()
        json_cache = self._json_file_cache
        for model in self._scan_huggingface_cache_models(root=root, cache_repo_dirs=hf_cache_repo_dirs):
            resolved_path = Path(model.model_path)
            seen_paths.add(resolved_path)
            if model.model_id in discovered_models or model.model_id in self._seed_models:
                continue
            self._apply_root_metadata(
                model,
                resolved_root=root_resolved,
                root_id=root_id,
                root_order=root_order,
                relative_path=resolved_path.relative_to(root_resolved),
            )
            discovered_models[model.model_id] = model
            accepted_model_ids.append(model.model_id)

        if hf_cache_repo_dirs:
            self._record_huggingface_cache_findings(
                root=root_resolved,
                cache_repo_dirs=hf_cache_repo_dirs,
                admitted_model_paths=seen_paths,
                candidate_findings=candidate_findings,
            )

        for plain_local_model in plain_local_model_dirs:
            resolved_path = plain_local_model.model_dir
            if resolved_path in seen_paths or _is_hf_cache_snapshot_dir(root_resolved, resolved_path):
                continue
            model_id = _local_model_id(root_resolved, resolved_path)
            if model_id in discovered_models or model_id in self._seed_models:
                continue
            if not plain_local_model.has_model_weight_files:
                candidate_findings.append(
                    _inventory_candidate_for_path(
                        root_path=os.fspath(root),
                        model_id=model_id,
                        source_model_id=model_id,
                        model_path=resolved_path,
                        file_layout="plain_mlx_directory",
                        config_payload={},
                        mlx_compatibility="unknown",
                        missing_file_state="missing_weights",
                        artifact_state="incomplete",
                        usable_state="incomplete",
                        operator_message="Local model directory has config metadata but no complete model weights.",
                        remediation="Add model weights or remove the incomplete directory.",
                        estimated_size_bytes=plain_local_model.estimated_size_bytes,
                    )
                )
                continue
            config_payload = _load_model_config_payload(resolved_path, json_cache=json_cache)
            if not _has_mlx_signal(
                model_dir=resolved_path,
                repo_id=model_id,
                text_prefix_cache=self._text_prefix_cache,
                config_payload=config_payload,
            ):
                family_signal = _family_signal_from_config(config_payload)
                candidate_findings.append(
                    _inventory_candidate_for_path(
                        root_path=os.fspath(root),
                        model_id=model_id,
                        source_model_id=model_id,
                        model_path=resolved_path,
                        file_layout="plain_mlx_directory",
                        config_payload=config_payload,
                        mlx_compatibility="incompatible" if family_signal != "unknown" else "unknown",
                        missing_file_state="complete",
                        artifact_state="external_runtime_only",
                        usable_state="unsupported" if family_signal != "unknown" else "ambiguous",
                        operator_message=(
                            "Local model directory does not advertise an MLX-compatible signal."
                            if family_signal != "unknown"
                            else "Local model directory has weights but no stable family or MLX signal."
                        ),
                        remediation=(
                            "Import or convert the model into an MLX-compatible layout."
                            if family_signal != "unknown"
                            else "Add model metadata that identifies the family and MLX compatibility."
                        ),
                        estimated_size_bytes=plain_local_model.estimated_size_bytes,
                    )
                )
                continue
            model = self._raw_model_spec(
                model_id=model_id,
                model_dir=resolved_path,
                revision="local",
                source_kind="local_mlx_directory",
                metadata={},
                config_payload=config_payload,
                has_generation_config=plain_local_model.has_generation_config,
                has_tokenizer_config=plain_local_model.has_tokenizer_config,
            )
            self._apply_root_metadata(
                model,
                resolved_root=root_resolved,
                root_id=root_id,
                root_order=root_order,
                relative_path=resolved_path.relative_to(root_resolved),
            )
            discovered_models[model_id] = model
            accepted_model_ids.append(model_id)

    def _scan_huggingface_cache_models(
        self,
        *,
        root: Path,
        cache_repo_dirs: Iterable[Path] | None = None,
    ) -> Iterable[common_pb2.ModelSpec]:
        json_cache = getattr(self, "_json_file_cache", None)
        if json_cache is None:
            json_cache = {}
            self._json_file_cache = json_cache
        resolved_cache_repo_dirs = (
            tuple(cache_repo_dirs)
            if cache_repo_dirs is not None
            else _sorted_child_directories(root, name_prefix="models--")
        )
        for cache_repo_dir in resolved_cache_repo_dirs:
            repo_id = _hf_cache_repo_id(cache_repo_dir)
            if repo_id is None:
                continue
            snapshots_dir = cache_repo_dir / "snapshots"
            if not snapshots_dir.is_dir():
                continue
            snapshot_dirs = tuple(_sorted_child_directories(snapshots_dir))
            revision_map = _hf_cache_revision_map(
                cache_repo_dir,
                snapshot_ids={snapshot_dir.name for snapshot_dir in snapshot_dirs},
            )
            for snapshot_dir in snapshot_dirs:
                if not (snapshot_dir / "config.json").is_file() or not _has_model_weight_files(snapshot_dir):
                    continue
                config_payload = _load_model_config_payload(snapshot_dir, json_cache=json_cache)
                if not _has_mlx_signal(
                    model_dir=snapshot_dir,
                    repo_id=repo_id,
                    text_prefix_cache=self._text_prefix_cache,
                    config_payload=config_payload,
                ):
                    continue
                revision = _hf_cache_revision(cache_repo_dir, snapshot_dir.name, revision_map=revision_map)
                yield self._raw_model_spec(
                    model_id=repo_id,
                    model_dir=snapshot_dir.resolve(),
                    revision=revision,
                    source_kind="hf_cache_snapshot",
                    metadata={
                        "melix.hf_repo_id": repo_id,
                        "melix.hf_revision": revision,
                    },
                    config_payload=config_payload,
                )

    def _record_huggingface_cache_findings(
        self,
        *,
        root: Path,
        cache_repo_dirs: Iterable[Path] | None,
        admitted_model_paths: set[Path],
        candidate_findings: list[_InventoryScanCandidate],
    ) -> None:
        json_cache = getattr(self, "_json_file_cache", None)
        if json_cache is None:
            json_cache = {}
            self._json_file_cache = json_cache
        resolved_cache_repo_dirs = (
            tuple(cache_repo_dirs)
            if cache_repo_dirs is not None
            else _sorted_child_directories(root, name_prefix="models--")
        )
        for cache_repo_dir in resolved_cache_repo_dirs:
            repo_id = _hf_cache_repo_id(cache_repo_dir)
            if repo_id is None:
                continue
            snapshots_dir = cache_repo_dir / "snapshots"
            if not snapshots_dir.is_dir():
                candidate_findings.append(
                    _inventory_candidate_for_path(
                        root_path=os.fspath(root),
                        model_id=repo_id,
                        source_model_id=repo_id,
                        model_path=cache_repo_dir,
                        file_layout="huggingface_snapshot",
                        config_payload={},
                        mlx_compatibility="unknown",
                        missing_file_state="missing_companion",
                        artifact_state="incomplete",
                        usable_state="incomplete",
                        operator_message="Hugging Face cache repo has no snapshots directory.",
                        remediation="Re-download the model or remove the incomplete cache entry.",
                    )
                )
                continue
            snapshot_dirs = tuple(_sorted_child_directories(snapshots_dir))
            revision_map = _hf_cache_revision_map(
                cache_repo_dir,
                snapshot_ids={snapshot_dir.name for snapshot_dir in snapshot_dirs},
            )
            if not snapshot_dirs:
                candidate_findings.append(
                    _inventory_candidate_for_path(
                        root_path=os.fspath(root),
                        model_id=repo_id,
                        source_model_id=repo_id,
                        model_path=snapshots_dir,
                        file_layout="huggingface_snapshot",
                        config_payload={},
                        mlx_compatibility="unknown",
                        missing_file_state="missing_companion",
                        artifact_state="incomplete",
                        usable_state="incomplete",
                        operator_message="Hugging Face cache repo has no snapshot payloads.",
                        remediation="Re-download the model or remove the empty cache entry.",
                    )
                )
                continue
            for snapshot_dir in snapshot_dirs:
                resolved_snapshot = snapshot_dir.resolve()
                if resolved_snapshot in admitted_model_paths:
                    continue
                revision = _hf_cache_revision(cache_repo_dir, snapshot_dir.name, revision_map=revision_map)
                has_config = (snapshot_dir / "config.json").is_file()
                has_weights = _has_model_weight_files(snapshot_dir)
                config_payload = _load_model_config_payload(snapshot_dir, json_cache=json_cache) if has_config else {}
                if not has_config:
                    missing_file_state = "missing_config"
                    usable_state = "incomplete"
                    artifact_state = "incomplete"
                    mlx_compatibility = "unknown"
                    message = "Hugging Face snapshot is missing config.json."
                    remediation = "Re-download or repair the snapshot before using it."
                elif not has_weights:
                    missing_file_state = "missing_weights"
                    usable_state = "incomplete"
                    artifact_state = "incomplete"
                    mlx_compatibility = "unknown"
                    message = "Hugging Face snapshot has no complete model weights."
                    remediation = "Re-download or repair the snapshot before using it."
                else:
                    family_signal = _family_signal_from_config(config_payload)
                    missing_file_state = "complete"
                    artifact_state = "external_runtime_only"
                    usable_state = "unsupported" if family_signal != "unknown" else "ambiguous"
                    mlx_compatibility = "incompatible" if family_signal != "unknown" else "unknown"
                    message = (
                        "Hugging Face snapshot does not advertise an MLX-compatible signal."
                        if family_signal != "unknown"
                        else "Hugging Face snapshot has weights but no stable family or MLX signal."
                    )
                    remediation = (
                        "Choose an MLX-compatible revision or import the model through a conversion flow."
                        if family_signal != "unknown"
                        else "Add metadata that identifies the family and MLX compatibility."
                    )
                candidate_findings.append(
                    _inventory_candidate_for_path(
                        root_path=os.fspath(root),
                        model_id=repo_id,
                        source_model_id=f"{repo_id}@{revision}",
                        model_path=resolved_snapshot,
                        file_layout="huggingface_snapshot",
                        config_payload=config_payload,
                        mlx_compatibility=mlx_compatibility,
                        missing_file_state=missing_file_state,
                        artifact_state=artifact_state,
                        usable_state=usable_state,
                        operator_message=message,
                        remediation=remediation,
                    )
                )

    @staticmethod
    def _scan_registry_root_tree(root: Path) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
        manifest_paths, plain_local_model_dirs, _ = WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(root)
        return manifest_paths, tuple(scan.model_dir for scan in plain_local_model_dirs)

    @staticmethod
    def _scan_registry_root_tree_with_hf_repos(root: Path) -> tuple[tuple[Path, ...], tuple[_PlainLocalModelScan, ...], tuple[Path, ...]]:
        manifest_paths: list[Path] = []
        plain_local_model_dirs: list[_PlainLocalModelScan] = []
        hf_cache_repo_dirs: list[Path] = []
        resolved_root = root.resolve()
        stack = [resolved_root]
        while stack:
            current = stack.pop()
            current_name = current.name
            if current_name in _REGISTRY_SCAN_PRUNED_DIR_NAMES:
                continue
            if current_name in _HF_CACHE_PRUNED_SUBTREE_NAMES and _is_hf_cache_pruned_subtree(resolved_root, current):
                continue
            try:
                with os.scandir(os.fspath(current)) as entries:
                    child_entries: list[tuple[str, str]] = []
                    has_manifest = False
                    has_config = False
                    has_generation_config = False
                    has_tokenizer_config = False
                    has_model_weight_files = False
                    for entry in entries:
                        entry_name = entry.name
                        try:
                            if entry_name in _REGISTRY_SCAN_SENTINEL_FILENAMES and entry.is_file():
                                if entry_name == "manifest.json":
                                    has_manifest = True
                                elif entry_name == "config.json":
                                    has_config = True
                                elif entry_name == "generation_config.json":
                                    has_generation_config = True
                                elif entry_name == "tokenizer_config.json":
                                    has_tokenizer_config = True
                                else:
                                    has_model_weight_files = True
                                continue
                            if (
                                entry_name
                                and entry_name[-1] in _MODEL_WEIGHT_FILE_SUFFIX_LAST_CHARS
                                and entry_name.endswith(_MODEL_WEIGHT_FILE_SUFFIXES)
                                and entry.is_file()
                            ):
                                has_model_weight_files = True
                                continue
                            if entry.is_dir():
                                entry_path = entry.path
                                if current is resolved_root and entry_name.startswith("models--"):
                                    child_path = Path(entry_path)
                                    if _hf_cache_repo_id(child_path) is not None:
                                        hf_cache_repo_dirs.append(child_path)
                                        continue
                                child_entries.append((entry_name, entry_path))
                        except OSError:
                            continue
            except OSError:
                continue
            if has_manifest:
                manifest_paths.append(current / "manifest.json")
                continue
            if has_config:
                plain_local_model_dirs.append(
                    _PlainLocalModelScan(
                        model_dir=current,
                        has_model_weight_files=has_model_weight_files,
                        has_generation_config=has_generation_config,
                        has_tokenizer_config=has_tokenizer_config,
                    )
                )
                continue
            child_entries.sort(reverse=True)
            stack.extend(Path(entry_path) for _name, entry_path in child_entries)
        return tuple(manifest_paths), tuple(plain_local_model_dirs), tuple(sorted(hf_cache_repo_dirs))

    @staticmethod
    def _iter_plain_local_model_dirs(root: Path) -> Iterable[Path]:
        _, plain_local_model_dirs = WorkerModelCatalog._scan_registry_root_tree(root)
        yield from plain_local_model_dirs

    @staticmethod
    def _iter_registry_manifest_paths(root: Path) -> Iterable[Path]:
        manifest_paths, _ = WorkerModelCatalog._scan_registry_root_tree(root)
        yield from manifest_paths

    @staticmethod
    def _apply_root_metadata(
        model: common_pb2.ModelSpec,
        *,
        resolved_root: Path,
        root_id: str,
        root_order: int,
        relative_path: Path,
    ) -> None:
        model.ext["melix.registry_root_id"] = root_id
        model.ext["melix.registry_root_path"] = str(resolved_root)
        model.ext["melix.registry_root_order"] = str(root_order)
        model.ext["melix.registry_relative_path"] = os.fspath(relative_path)

    def _raw_model_spec(
        self,
        *,
        model_id: str,
        model_dir: Path,
        revision: str,
        source_kind: str,
        metadata: dict[str, str],
        config_payload: Mapping[str, object] | None = None,
        has_generation_config: bool | None = None,
        has_tokenizer_config: bool | None = None,
        estimated_size_bytes: int | None = None,
    ) -> common_pb2.ModelSpec:
        json_cache = getattr(self, "_json_file_cache", None)
        if json_cache is None:
            json_cache = {}
            self._json_file_cache = json_cache
        runtime_model_path = str(model_dir)
        ext = {
            **metadata,
            "melix.source_kind": source_kind,
            "melix.model_path": runtime_model_path,
        }
        if estimated_size_bytes is not None:
            ext["melix.estimated_size_bytes"] = str(max(0, estimated_size_bytes))
        if config_payload is None:
            config_payload = _load_model_config_payload(model_dir, json_cache=json_cache)
        max_context, max_context_source = _model_context_window(
            model_dir,
            config_payload,
            json_cache=json_cache,
            has_tokenizer_config=has_tokenizer_config,
        )
        if max_context <= 0:
            max_context = 8192
            max_context_source = "default.8192"
        ext["melix.context_window.source"] = max_context_source
        ext.update(dflash_draft_metadata(config_payload))
        embedding_metadata = _artifact_embedding_metadata(
            model_dir,
            config_payload,
            json_cache=json_cache,
        )
        if embedding_metadata is not None:
            model_kind = "embedding"
            ext.update(embedding_metadata)
        else:
            model_kind = "vlm" if _is_gemma4_vlm_config(config_payload) else "text"
        if model_kind == "text":
            ext.update(
                _text_capability_metadata(
                    model_path=runtime_model_path,
                    metadata=ext,
                    config_payload=config_payload,
                    default_route_kind="python_text_compatibility",
                )
            )
            _merge_text_layer_count_metadata(ext, config_payload)
        elif model_kind == "vlm":
            ext.update(
                _vlm_capability_metadata(
                    model_path=runtime_model_path,
                    model_dir=model_dir,
                    metadata=ext,
                    config_payload=config_payload,
                    json_cache=json_cache,
                )
            )
        ext.update(
            _gemma4_mtp_assistant_metadata(
                model_id=model_id,
                model_dir=model_dir,
                config_payload=config_payload,
                text_prefix_cache=self._text_prefix_cache,
            )
        )
        if _gemma4_qat_fast_candidate(model_id):
            ext.update(
                _gemma4_qat_metadata(
                    model_id=model_id,
                    model_dir=model_dir,
                    config_payload=config_payload,
                    text_prefix_cache=self._text_prefix_cache,
                )
            )
        _merge_generation_config_metadata(
            model_dir,
            ext=ext,
            json_cache=json_cache,
            known_present=has_generation_config,
        )
        return common_pb2.ModelSpec(
            model_id=model_id,
            model_path=runtime_model_path,
            model_kind=model_kind,
            revision=revision,
            tokenizer_hash=f"hf.{model_id.replace('/', '.')}" if source_kind == "hf_cache_snapshot" else "tok-local",
            quant_profile_id="",
            parser_mode="text",
            reasoning_mode="off",
            max_context=max_context,
            ext=ext,
        )

    def _parse_registry_manifest(
        self,
        manifest_path: Path,
    ) -> tuple[str, common_pb2.ModelSpec] | None:
        json_cache = getattr(self, "_json_file_cache", None)
        if json_cache is None:
            json_cache = {}
            self._json_file_cache = json_cache
        payload = _load_json_dict_file(manifest_path, json_cache=json_cache)
        if not payload:
            return None

        model_id = _normalized(str(payload.get("model_id", "")))
        if not model_id:
            return None

        ext = payload.get("ext", {})
        if not isinstance(ext, dict):
            ext = {}
        normalized_ext = {
            str(key): str(value)
            for key, value in ext.items()
            if str(key).strip()
        }
        raw_manifest_runtime_path = ext.get("melix.model_path")
        if not isinstance(raw_manifest_runtime_path, str):
            normalized_ext.pop("melix.model_path", None)
        for payload_key, ext_key in (
            ("provider_id", _REGISTRY_PROVIDER_ID_KEY),
            ("organization_id", _REGISTRY_ORGANIZATION_ID_KEY),
            ("model_name", _REGISTRY_MODEL_NAME_KEY),
            ("variant_id", _REGISTRY_VARIANT_ID_KEY),
        ):
            override_value = _normalized(str(payload.get(payload_key, "")))
            if override_value:
                normalized_ext[ext_key] = override_value

        requested_model_kind = _normalized(str(payload.get("model_kind", "text"))) or "text"
        quant_profile_id = _normalized(str(payload.get("quant_profile_id", "")))
        revision = _normalized(str(payload.get("revision", "registry"))) or "registry"
        tokenizer_hash = _normalized(str(payload.get("tokenizer_hash", "tok-registry"))) or "tok-registry"
        parser_mode = _normalized(str(payload.get("parser_mode", "text"))) or "text"
        reasoning_mode = _normalized(str(payload.get("reasoning_mode", "off"))) or "off"
        max_context = int(payload.get("max_context", 8192) or 8192)
        manifest_runtime_path = _normalized(raw_manifest_runtime_path) if isinstance(raw_manifest_runtime_path, str) else ""
        if manifest_runtime_path:
            runtime_model_dir = Path(manifest_runtime_path).expanduser().resolve()
        else:
            runtime_model_dir = manifest_path.parent
        runtime_model_path = str(runtime_model_dir)
        normalized_ext["melix.model_path"] = runtime_model_path
        if manifest_runtime_path and not runtime_model_dir.is_dir():
            normalized_ext["melix.model_path_missing"] = "true"
        else:
            normalized_ext.pop("melix.model_path_missing", None)
        config_payload = _load_model_config_payload(runtime_model_dir, json_cache=json_cache)
        normalized_ext.update(dflash_draft_metadata(config_payload))
        model_kind = (
            "vlm"
            if requested_model_kind == "text" and _is_gemma4_vlm_config(config_payload)
            else requested_model_kind
        )
        if model_kind == "text":
            normalized_ext.update(
                _text_capability_metadata(
                    model_path=runtime_model_path,
                    metadata=normalized_ext,
                    config_payload=config_payload,
                    default_route_kind="python_text_compatibility",
                )
            )
            _merge_text_layer_count_metadata(normalized_ext, config_payload)
        if model_kind == "vlm":
            normalized_ext.update(
                _vlm_capability_metadata(
                    model_path=runtime_model_path,
                    model_dir=runtime_model_dir,
                    metadata=normalized_ext,
                    config_payload=config_payload,
                    json_cache=json_cache,
                )
            )
        normalized_ext.update(
            _gemma4_mtp_assistant_metadata(
                model_id=model_id,
                model_dir=runtime_model_dir,
                config_payload=config_payload,
                text_prefix_cache=self._text_prefix_cache,
            )
        )
        if _gemma4_qat_fast_candidate(model_id):
            normalized_ext.update(
                _gemma4_qat_metadata(
                    model_id=model_id,
                    model_dir=runtime_model_dir,
                    config_payload=config_payload,
                    text_prefix_cache=self._text_prefix_cache,
                )
            )
        if model_kind == "image":
            normalized_ext.update(
                _image_capability_metadata(
                    model_path=runtime_model_path,
                    metadata=normalized_ext,
                    default_task_kind=normalized_ext.get("melix.image.task_kind", "text-to-image"),
                )
            )
        _merge_generation_config_metadata(
            runtime_model_dir,
            ext=normalized_ext,
            json_cache=json_cache,
        )

        return model_id, common_pb2.ModelSpec(
            model_id=model_id,
            model_path=runtime_model_path,
            model_kind=model_kind,
            revision=revision,
            tokenizer_hash=tokenizer_hash,
            quant_profile_id=quant_profile_id,
            parser_mode=parser_mode,
            reasoning_mode=reasoning_mode,
            max_context=max_context,
            ext=normalized_ext,
        )

    @staticmethod
    def dev_text_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        model_path = environment.get("MELIX_DEV_TEXT_MODEL_PATH", "models/melix-dev-text")
        configured_family_id = _normalized(environment.get("MELIX_DEV_TEXT_FAMILY_ID"))
        configured_route_kind = _normalized(environment.get("MELIX_DEV_TEXT_ROUTE_KIND"))
        metadata: dict[str, str] = {}
        if configured_family_id:
            metadata["text_family_id"] = configured_family_id
        if configured_route_kind:
            metadata["melix.capability.route_kind"] = configured_route_kind
        text_metadata = _text_capability_metadata(
            model_path=model_path,
            metadata=metadata,
            default_route_kind="swift_text",
        )
        return common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=model_path,
            model_kind="text",
            revision="dev",
            tokenizer_hash="tok-dev",
            quant_profile_id="q4",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
            ext=text_metadata,
        )

    @staticmethod
    def dev_embedding_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        model_path = environment.get("MELIX_DEV_EMBED_MODEL_PATH", "models/melix-dev-embed")
        detected = _infer_embedding_identity(model_path)
        configured_family_id = _normalized(environment.get("MELIX_DEV_EMBED_FAMILY_ID"))
        configured_backend_id = _normalized(environment.get("MELIX_DEV_EMBED_BACKEND_ID"))

        if configured_family_id:
            family_id = configured_family_id
            backend_id = configured_backend_id or _embedding_backend_for_family(family_id)
        else:
            backend_id = configured_backend_id or "deterministic-fixture-v1"
            family_id = _default_embedding_family_for_backend(backend_id, detected["family_id"])

        architecture = _embedding_architecture_for_family(family_id)
        default_pooling_mode = _default_embedding_pooling_mode(family_id)
        pooling_mode = environment.get(
            "MELIX_DEV_EMBED_POOLING_MODE",
            default_pooling_mode,
        ).strip() or default_pooling_mode
        normalization = environment.get("MELIX_DEV_EMBED_NORMALIZATION", "l2").strip() or "l2"
        default_dimensions = _default_embedding_dimensions(family_id)
        dimensions = environment.get("MELIX_DEV_EMBED_DIMENSIONS", default_dimensions).strip() or default_dimensions
        identity_override = (
            family_id != detected["family_id"] or architecture != detected["architecture"]
        )
        return common_pb2.ModelSpec(
            model_id="melix-dev-embed",
            model_path=model_path,
            model_kind="embedding",
            revision="dev",
            tokenizer_hash="tok-embed-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
            ext={
                **_embedding_capability_metadata(family_id),
                **_embedding_lora_support_metadata(family_id),
                "embedding_backend_id": backend_id,
                "embedding_family_id": family_id,
                "embedding_pooling_mode": pooling_mode,
                "embedding_normalization": normalization,
                "embedding_dimensions": dimensions,
                "embedding_execution_kind": (
                    "artifact" if backend_id in {"mlx-bert-v1", "mlx-xlmr-v1"} else "fixture"
                ),
                "model_architecture": architecture,
                "detected_architecture": detected["architecture"],
                "detected_family_id": detected["family_id"],
                "detected_identity_source": detected["source"],
                "identity_override": "true" if identity_override else "false",
            },
        )

    @staticmethod
    def dev_rerank_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        model_path = environment.get("MELIX_DEV_RERANK_MODEL_PATH", "models/melix-dev-rerank")
        detected = _infer_rerank_identity(model_path)
        backend_id = environment.get("MELIX_DEV_RERANK_BACKEND_ID", "token-overlap-v1").strip() or "token-overlap-v1"
        family_id = environment.get("MELIX_DEV_RERANK_FAMILY_ID", detected["family_id"]).strip() or detected["family_id"]
        architecture = _rerank_architecture_for_family(family_id)
        default_scoring_mode = _default_rerank_scoring_mode(family_id)
        scoring_mode = environment.get("MELIX_DEV_RERANK_SCORING_MODE", default_scoring_mode).strip() or default_scoring_mode
        identity_override = (
            family_id != detected["family_id"] or architecture != detected["architecture"]
        )
        ext = {
            **_rerank_capability_metadata(family_id),
            "rerank_backend_id": backend_id,
            "rerank_family_id": family_id,
            "rerank_scoring_mode": scoring_mode,
            "model_architecture": architecture,
            "detected_architecture": detected["architecture"],
            "detected_family_id": detected["family_id"],
            "detected_identity_source": detected["source"],
            "identity_override": "true" if identity_override else "false",
        }
        if family_id == "causal-lm":
            yes_no_labels = environment.get("MELIX_DEV_RERANK_YES_NO_LABELS", "yes,no").strip() or "yes,no"
            ext["rerank_yes_no_labels"] = yes_no_labels
        return common_pb2.ModelSpec(
            model_id="melix-dev-rerank",
            model_path=model_path,
            model_kind="rerank",
            revision="dev",
            tokenizer_hash="tok-rerank-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
            ext=ext,
        )

    @staticmethod
    def dev_ocr_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-ocr",
            model_path=environment.get("MELIX_DEV_OCR_MODEL_PATH", "models/melix-dev-ocr"),
            model_kind="ocr",
            revision="dev",
            tokenizer_hash="tok-ocr-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                "ocr_prompt_profile_id": "ocr-default-v1",
                "ocr_prompt_template": "OCR instruction: {prompt}",
                "ocr_auto_prompt": "Extract the text from the image exactly as written.",
                "ocr_stop_sequences": "<ocr:end>",
                "ocr_sampling_profile_id": "ocr-deterministic",
                "ocr_default_temperature": "0.0",
                "ocr_default_top_p": "1.0",
                "ocr_default_max_tokens": "256",
            },
        )

    @staticmethod
    def dev_vlm_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        family_id = environment.get("MELIX_DEV_VLM_FAMILY_ID", "llava-v1").strip() or "llava-v1"
        return common_pb2.ModelSpec(
            model_id="melix-dev-vlm",
            model_path=environment.get("MELIX_DEV_VLM_MODEL_PATH", "models/melix-dev-vlm"),
            model_kind="vlm",
            revision="dev",
            tokenizer_hash="tok-vlm-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                **_vision_capability_metadata(family_id),
                "melix.vlm.backend_id": "deterministic",
                "vision_family_id": family_id,
                "vision_prompt_profile_id": (
                    "paligemma-caption-v1" if family_id == "paligemma-v1" else "llava-chatml-v1"
                ),
                "vision_tokenization_mode": (
                    "prefix" if family_id == "paligemma-v1" else "interleaved"
                ),
                "vision_max_images_per_prompt": "1" if family_id == "paligemma-v1" else "8",
                "vision_supports_tool_calls": "false" if family_id == "paligemma-v1" else "true",
                "melix.multimodal_adapter_hash": f"vision-family-{family_id}",
            },
        )

    @staticmethod
    def dev_transcription_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        family_id = "deterministic-transcription"
        return common_pb2.ModelSpec(
            model_id="melix-dev-transcribe",
            model_path=environment.get("MELIX_DEV_TRANSCRIBE_MODEL_PATH", "models/melix-dev-transcribe"),
            model_kind="transcription",
            revision="dev",
            tokenizer_hash="tok-transcribe-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                **_audio_capability_metadata(family_id=family_id, model_kind="transcription"),
                **_audio_metadata(
                    backend_id="deterministic",
                    family_id=family_id,
                    install_profile="",
                    languages=("und",),
                ),
            },
        )

    @staticmethod
    def dev_speech_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        family_id = "deterministic-speech"
        return common_pb2.ModelSpec(
            model_id="melix-dev-speech",
            model_path=environment.get("MELIX_DEV_SPEECH_MODEL_PATH", "models/melix-dev-speech"),
            model_kind="speech",
            revision="dev",
            tokenizer_hash="tok-speech-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                **_audio_capability_metadata(family_id=family_id, model_kind="speech"),
                **_audio_metadata(
                    backend_id="deterministic",
                    family_id=family_id,
                    install_profile="",
                    languages=("und",),
                    voice_mode="named",
                    output_formats=("wav", "mp3"),
                    supports_instructions=False,
                    voice_catalog_summary="Deterministic synthetic default voice.",
                    voice_locales=("und",),
                    default_locale="und",
                    packaged_default_locale="und",
                    locale_policy="request>model_default>packaged_default",
                ),
            },
        )

    @staticmethod
    def dev_image_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        model_path = environment.get("MELIX_DEV_IMAGE_MODEL_PATH", "models/melix-dev-image")
        configured_family_id = _normalized(environment.get("MELIX_DEV_IMAGE_FAMILY_ID"))
        configured_task_kind = _normalized(environment.get("MELIX_DEV_IMAGE_TASK_KIND"))
        metadata: dict[str, str] = {}
        if configured_family_id:
            metadata["melix.image.family_id"] = configured_family_id
        if configured_task_kind:
            metadata["melix.image.task_kind"] = configured_task_kind
        image_metadata = _image_capability_metadata(
            model_path=model_path,
            metadata=metadata,
            default_task_kind=configured_task_kind or "text-to-image",
        )
        return common_pb2.ModelSpec(
            model_id="melix-dev-image",
            model_path=model_path,
            model_kind="image",
            revision="dev",
            tokenizer_hash="tok-image-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext=image_metadata,
        )

    @staticmethod
    def mlx_whisper_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec | None:
        environment = dict(environment or os.environ)
        model_path = environment.get(
            "MELIX_MLX_AUDIO_WHISPER_MODEL_PATH",
            "mlx-community/whisper-large-v3-turbo-asr-fp16",
        ).strip() or "mlx-community/whisper-large-v3-turbo-asr-fp16"
        family_id = "whisper"
        return common_pb2.ModelSpec(
            model_id="melix-whisper-mlx",
            model_path=model_path,
            model_kind="transcription",
            revision="mlx-audio",
            tokenizer_hash="tok-whisper-mlx",
            quant_profile_id="fp16",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                **_audio_capability_metadata(family_id=family_id, model_kind="transcription"),
                **_audio_metadata(
                    backend_id="mlx_audio.stt",
                    family_id=family_id,
                    install_profile="audio-stt",
                    languages=("auto",),
                ),
                **_audio_setup_metadata(capability="stt", role="recommended", priority=0),
            },
        )

    @staticmethod
    def mlx_parakeet_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec | None:
        environment = dict(environment or os.environ)
        model_path = environment.get(
            "MELIX_MLX_AUDIO_PARAKEET_MODEL_PATH",
            "mlx-community/parakeet-tdt-0.6b-v2",
        ).strip() or "mlx-community/parakeet-tdt-0.6b-v2"
        family_id = "parakeet"
        return common_pb2.ModelSpec(
            model_id="melix-parakeet-mlx",
            model_path=model_path,
            model_kind="transcription",
            revision="mlx-audio",
            tokenizer_hash="tok-parakeet-mlx",
            quant_profile_id="fp16",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                **_audio_capability_metadata(family_id=family_id, model_kind="transcription"),
                **_audio_metadata(
                    backend_id="mlx_audio.stt",
                    family_id=family_id,
                    install_profile="audio-stt",
                    languages=("auto",),
                ),
                **_audio_setup_metadata(capability="stt", role="optional", priority=20),
            },
        )

    @staticmethod
    def mlx_kokoro_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec | None:
        environment = dict(environment or os.environ)
        model_path = environment.get(
            "MELIX_MLX_AUDIO_KOKORO_MODEL_PATH",
            "mlx-community/Kokoro-82M-bf16",
        ).strip() or "mlx-community/Kokoro-82M-bf16"
        family_id = "kokoro"
        return common_pb2.ModelSpec(
            model_id="melix-kokoro-mlx",
            model_path=model_path,
            model_kind="speech",
            revision="mlx-audio",
            tokenizer_hash="tok-kokoro-mlx",
            quant_profile_id="bf16",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                **_audio_capability_metadata(family_id=family_id, model_kind="speech"),
                **_audio_metadata(
                    backend_id="mlx_audio.tts",
                    family_id=family_id,
                    install_profile="audio-tts",
                    languages=("en",),
                    voice_mode="named",
                    output_formats=("wav",),
                    supports_instructions=False,
                    voice_catalog_summary="Named English voices exposed by the Kokoro speaker catalog.",
                    voice_locales=("en",),
                    default_locale="en",
                    packaged_default_locale="en",
                    locale_policy="request>model_default>packaged_default",
                ),
                **_audio_setup_metadata(capability="tts", role="recommended", priority=0),
            },
        )

    @staticmethod
    def mlx_qwen3_tts_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        model_path = environment.get(
            "MELIX_MLX_AUDIO_QWEN3_TTS_MODEL_PATH",
            "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit",
        ).strip() or "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit"
        family_id = "qwen3-tts"
        return common_pb2.ModelSpec(
            model_id="melix-qwen3-tts-mlx",
            model_path=model_path,
            model_kind="speech",
            revision="mlx-audio",
            tokenizer_hash="tok-qwen3-tts-mlx",
            quant_profile_id="4bit",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                **_audio_capability_metadata(family_id=family_id, model_kind="speech"),
                **_audio_metadata(
                    backend_id="mlx_audio.tts",
                    family_id=family_id,
                    install_profile="audio-tts",
                    languages=("zh", "en"),
                    voice_mode="hybrid",
                    output_formats=("wav",),
                    supports_instructions=True,
                    voice_catalog_summary=(
                        "Hybrid named and instruction-conditioned multilingual voices "
                        "for Chinese and English synthesis."
                    ),
                    voice_locales=("zh", "en"),
                    default_locale="zh",
                    packaged_default_locale="zh",
                    locale_policy="request>model_default>packaged_default",
                ),
                **_audio_setup_metadata(capability="tts", role="optional", priority=20),
            },
        )


def _canonical_registry_root_path(raw_path: str) -> str:
    return os.fspath(Path(raw_path).expanduser().resolve(strict=False))


def _stable_registry_root_id(root_path: str) -> str:
    digest = hashlib.sha1(root_path.encode("utf-8")).hexdigest()[:12]
    return f"root-{digest}"


def _stable_inventory_scan_id(
    *,
    registry_roots: tuple[str, ...],
    started_at_unix_ms: int,
) -> str:
    digest = hashlib.sha1(
        ("\0".join(registry_roots) + f"\0{started_at_unix_ms}").encode("utf-8")
    ).hexdigest()[:16]
    return f"scan-{digest}"


def _inventory_candidate_for_path(
    *,
    root_path: str,
    model_id: str,
    source_model_id: str,
    model_path: Path,
    file_layout: str,
    config_payload: Mapping[str, object] | None,
    mlx_compatibility: str,
    missing_file_state: str,
    artifact_state: str,
    usable_state: str,
    operator_message: str,
    remediation: str,
    estimated_size_bytes: int = 0,
    invalid_entry: bool = False,
) -> _InventoryScanCandidate:
    family_signal = _family_signal_from_config(config_payload)
    if usable_state == "usable":
        trainability = "adapter_only"
        exportability = "exportable"
    elif mlx_compatibility == "incompatible":
        trainability = "not_trainable"
        exportability = "not_exportable"
    else:
        trainability = "unknown"
        exportability = "unknown"
    return _InventoryScanCandidate(
        root_path=root_path,
        model_id=model_id,
        source_model_id=source_model_id,
        model_path=os.fspath(model_path),
        file_layout=file_layout,
        family_signal=family_signal,
        mlx_compatibility=mlx_compatibility,
        trainability=trainability,
        exportability=exportability,
        missing_file_state=missing_file_state,
        estimated_size_bytes=max(0, estimated_size_bytes),
        artifact_state=artifact_state,
        usable_state=usable_state,
        operator_message=operator_message,
        remediation=remediation,
        metrics={
            "classification_latency_ms": 0.0,
            "invalid_entry": invalid_entry,
        },
    )
