from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Iterable, Mapping

from packages.protocol.python.worker.v1 import common_pb2
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
_GENERATION_CONFIG_MAX_TOKENS_KEY = "melix.generation_config.max_tokens"
_GENERATION_CONFIG_DO_SAMPLE_KEY = "melix.generation_config.do_sample"


@dataclass(frozen=True)
class RegistryRootSnapshot:
    root_id: str
    root_path: str
    root_order: int
    accessible: bool
    error_code: str = ""
    error_message: str = ""
    discovered_model_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegistrySnapshot:
    roots: tuple[RegistryRootSnapshot, ...]
    models: tuple[common_pb2.ModelSpec, ...]
    scanned_at_unix_ms: int


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


def _merge_generation_config_metadata(
    model_dir: Path,
    *,
    ext: dict[str, str],
) -> None:
    generation_config_path = model_dir / "generation_config.json"
    if not generation_config_path.is_file():
        return

    try:
        payload = json.loads(generation_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(payload, dict):
        return

    recognized_values = {
        _GENERATION_CONFIG_TEMPERATURE_KEY: payload.get("temperature"),
        _GENERATION_CONFIG_TOP_P_KEY: payload.get("top_p"),
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


def _load_model_config_payload(model_dir: Path) -> dict[str, object]:
    config_path = model_dir / "config.json"
    if not config_path.is_file():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_model_weight_files(model_dir: Path) -> bool:
    if (model_dir / "model.safetensors.index.json").is_file():
        return True
    return any(path.is_file() for path in model_dir.glob("*.safetensors")) or any(
        path.is_file() for path in model_dir.glob("*.npz")
    )


def _read_text_prefix(path: Path, *, max_chars: int = 16_384) -> str:
    if not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return handle.read(max_chars)
    except OSError:
        return ""


def _has_mlx_signal(*, model_dir: Path, repo_id: str = "") -> bool:
    lowered_repo_id = repo_id.lower()
    lowered_path = model_dir.name.lower()
    if repo_id.startswith("mlx-community/") or "mlx" in lowered_repo_id or "mlx" in lowered_path:
        return True

    metadata_text = "\n".join(
        filter(
            None,
            (
                _read_text_prefix(model_dir / "README.md"),
                _read_text_prefix(model_dir / "config.json"),
                _read_text_prefix(model_dir / "model_index.json"),
            ),
        )
    ).lower()
    if not metadata_text:
        return False
    return (
        "library_name: mlx" in metadata_text
        or '"library_name": "mlx"' in metadata_text
        or "\n- mlx" in metadata_text
        or "\n  - mlx" in metadata_text
        or '"mlx"' in metadata_text and '"tags"' in metadata_text
    )


def _hf_cache_repo_id(cache_repo_dir: Path) -> str | None:
    name = cache_repo_dir.name
    if not name.startswith("models--"):
        return None
    parts = name.removeprefix("models--").split("--", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


def _hf_cache_revision_map(cache_repo_dir: Path) -> dict[str, str]:
    refs_dir = cache_repo_dir / "refs"
    revisions: dict[str, str] = {}
    if refs_dir.is_dir():
        try:
            ref_paths = sorted(path for path in refs_dir.rglob("*") if path.is_file())
        except OSError:
            return revisions
        for ref_path in ref_paths:
            try:
                snapshot_id = ref_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not snapshot_id:
                continue
            revisions.setdefault(snapshot_id, os.fspath(ref_path.relative_to(refs_dir)))
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
    return len(relative_parts) >= 3 and relative_parts[0].startswith("models--") and relative_parts[1] == "snapshots"


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
            "backend_id": "bert-v1",
            "source": "directory_name",
        }
    if "bge" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "bge-m3",
            "backend_id": "bert-v1",
            "source": "directory_name",
        }
    if "xlmr" in normalized_path or "xlm-r" in normalized_path:
        return {
            "architecture": "xlmr",
            "family_id": "xlmr",
            "backend_id": "xlmr-v1",
            "source": "directory_name",
        }
    if "bert" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "bert",
            "backend_id": "bert-v1",
            "source": "directory_name",
        }
    return {
        "architecture": "bert",
        "family_id": "bert",
        "backend_id": "bert-v1",
        "source": "default",
    }


def _embedding_backend_for_family(family_id: str) -> str:
    return "xlmr-v1" if family_id == "xlmr" else "bert-v1"


def _embedding_architecture_for_family(family_id: str) -> str:
    return "xlmr" if family_id == "xlmr" else "bert"


def _default_embedding_family_for_backend(backend_id: str, detected_family_id: str) -> str:
    if backend_id == "xlmr-v1":
        return "xlmr"
    if detected_family_id in {"bert", "bge-m3", "mxbai-embed"}:
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
    return _capability_metadata(
        adapter_set_hash=f"vision-family-{family_id}",
        route_kind="python_vlm",
        capability_class="vlm",
        supported_modalities=("text", "image"),
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


def _gemma4_execution_mode(model_dir: Path, config_payload: Mapping[str, object] | None) -> str:
    config_payload = dict(config_payload or {})
    vision_config = config_payload.get("vision_config")
    if isinstance(vision_config, Mapping) and len(vision_config) > 0:
        return ""
    if (model_dir / "processor_config.json").is_file() or (model_dir / "preprocessor_config.json").is_file():
        return ""
    has_multimodal_marker = any(
        key in config_payload and config_payload.get(key) not in (None, "", [], {})
        for key in ("image_token_id", "boi_token_id", "eoi_token_id")
    )
    if has_multimodal_marker and _gemma4_index_has_vision_weights(model_dir):
        return ""
    return "text_backed"


def _gemma4_index_has_vision_weights(model_dir: Path) -> bool:
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.is_file():
        return False
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    weight_map = payload.get("weight_map")
    if not isinstance(weight_map, dict):
        return False
    return any(
        str(name).startswith("vision_tower.") or str(name).startswith("embed_vision.")
        for name in weight_map
    )


def _vlm_capability_metadata(
    *,
    model_path: str,
    model_dir: Path,
    metadata: dict[str, str] | None = None,
    config_payload: Mapping[str, object] | None = None,
) -> dict[str, str]:
    metadata = dict(metadata or {})
    config_payload = dict(config_payload or {})
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
        "melix.multimodal_adapter_hash": (
            _normalized(metadata.get("melix.multimodal_adapter_hash", ""))
            or resolved_family.multimodal_adapter_hash
        ),
    }
    execution_mode = _gemma4_execution_mode(model_dir, config_payload) if family_id == "gemma4-v1" else ""
    if execution_mode:
        ext["melix.vlm.execution_mode"] = execution_mode
    return ext


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
        self._registry_snapshot_cache: dict[tuple[str, ...], RegistrySnapshot] = {}
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
            self._rebuild_runtime_models()
            return self._models[registered.model_id]

    def remove_model(self, model_id: str) -> bool:
        with self._registry_lock:
            removed = self._overlay_models.pop(model_id, None)
            if removed is None:
                return False
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
            self._rebuild_runtime_models(snapshot=snapshot)
            return snapshot

    def _rebuild_runtime_models(self, snapshot: RegistrySnapshot | None = None) -> None:
        active_snapshot = snapshot or self._last_registry_snapshot
        new_models = dict(self._seed_models)
        for model in active_snapshot.models:
            new_models.setdefault(model.model_id, model)
        for model_id, model in self._overlay_models.items():
            new_models[model_id] = model
        self._models = new_models

    def registry_snapshot_payload(
        self,
        *,
        rescan: bool = False,
        registry_roots: Iterable[str] | None = None,
    ) -> dict[str, object]:
        snapshot = self.registry_snapshot(rescan=rescan, registry_roots=registry_roots)
        return {
            "scanned_at_unix_ms": snapshot.scanned_at_unix_ms,
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
                {
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
                for model in snapshot.models
            ],
        }

    def _refresh_registry_snapshot(self, registry_roots: tuple[str, ...]) -> RegistrySnapshot:
        roots, discovered_models = self._scan_registry_roots(registry_roots)
        return RegistrySnapshot(
            roots=tuple(roots),
            models=tuple(discovered_models[model_id] for model_id in sorted(discovered_models)),
            scanned_at_unix_ms=int(time.time() * 1000),
        )

    def _scan_registry_roots(
        self,
        registry_roots: tuple[str, ...],
    ) -> tuple[list[RegistryRootSnapshot], dict[str, common_pb2.ModelSpec]]:
        roots: list[RegistryRootSnapshot] = []
        discovered_models: dict[str, common_pb2.ModelSpec] = {}

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
            for manifest_path in self._iter_registry_manifest_paths(root):
                parsed = self._parse_registry_manifest(manifest_path)
                if parsed is None:
                    continue
                model_id, model = parsed
                if model_id in discovered_models or model_id in self._seed_models:
                    continue
                relative_path = manifest_path.parent.relative_to(root)
                if not _apply_registry_identity_metadata(
                    model,
                    relative_parts=relative_path.parts,
                ):
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
                discovered_models=discovered_models,
                accepted_model_ids=accepted_model_ids,
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

        return roots, discovered_models

    def _configured_registry_roots(self) -> list[str]:
        configured: list[str] = []
        raw = self._environment.get(_REGISTRY_ROOTS_ENV_KEY, "")
        if raw.strip():
            configured.extend(raw.split(os.pathsep))

        managed_root = self._environment.get(_MANAGED_MODEL_ROOT_ENV_KEY, "").strip()
        if managed_root:
            configured.append(managed_root)
        default_hf_cache = self._default_huggingface_cache_root()
        if default_hf_cache is not None:
            configured.append(os.fspath(default_hf_cache))

        return self._normalized_registry_roots(configured)

    def _resolved_registry_roots(self, registry_roots: Iterable[str] | None) -> list[str]:
        if registry_roots is None:
            return self._configured_registry_roots()

        requested_roots = list(registry_roots)
        managed_root = self._environment.get(_MANAGED_MODEL_ROOT_ENV_KEY, "").strip()
        if managed_root:
            requested_roots.append(managed_root)
        default_hf_cache = self._default_huggingface_cache_root()
        if default_hf_cache is not None:
            requested_roots.append(os.fspath(default_hf_cache))
        return self._normalized_registry_roots(requested_roots)

    def _default_huggingface_cache_root(self) -> Path | None:
        if self._uses_explicit_environment and "HOME" not in self._environment:
            return None
        home = self._environment.get("HOME", "").strip()
        root = (Path(home).expanduser() if home else Path.home()) / ".cache" / "huggingface" / "hub"
        resolved = root.resolve()
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
        discovered_models: dict[str, common_pb2.ModelSpec],
        accepted_model_ids: list[str],
    ) -> None:
        seen_paths: set[Path] = set()
        for model in self._scan_huggingface_cache_models(root=root):
            resolved_path = Path(model.model_path).resolve()
            seen_paths.add(resolved_path)
            if model.model_id in discovered_models or model.model_id in self._seed_models:
                continue
            self._apply_root_metadata(
                model,
                root=root,
                root_id=root_id,
                root_order=root_order,
                relative_path=resolved_path.relative_to(root.resolve()),
            )
            discovered_models[model.model_id] = model
            accepted_model_ids.append(model.model_id)

        for model_dir in self._iter_plain_local_model_dirs(root):
            resolved_path = model_dir.resolve()
            if resolved_path in seen_paths or _is_hf_cache_snapshot_dir(root.resolve(), resolved_path):
                continue
            if (resolved_path / "manifest.json").is_file():
                continue
            model_id = _local_model_id(root.resolve(), resolved_path)
            if model_id in discovered_models or model_id in self._seed_models:
                continue
            if not _has_model_weight_files(resolved_path) or not _has_mlx_signal(model_dir=resolved_path, repo_id=model_id):
                continue
            model = self._raw_model_spec(
                model_id=model_id,
                model_dir=resolved_path,
                revision="local",
                source_kind="local_mlx_directory",
                metadata={},
            )
            self._apply_root_metadata(
                model,
                root=root,
                root_id=root_id,
                root_order=root_order,
                relative_path=resolved_path.relative_to(root.resolve()),
            )
            discovered_models[model_id] = model
            accepted_model_ids.append(model_id)

    def _scan_huggingface_cache_models(self, *, root: Path) -> list[common_pb2.ModelSpec]:
        models: list[common_pb2.ModelSpec] = []
        for cache_repo_dir in sorted(root.glob("models--*")):
            if not cache_repo_dir.is_dir():
                continue
            repo_id = _hf_cache_repo_id(cache_repo_dir)
            if repo_id is None:
                continue
            snapshots_dir = cache_repo_dir / "snapshots"
            if not snapshots_dir.is_dir():
                continue
            revision_map = _hf_cache_revision_map(cache_repo_dir)
            for snapshot_dir in sorted(path for path in snapshots_dir.iterdir() if path.is_dir()):
                if not (snapshot_dir / "config.json").is_file() or not _has_model_weight_files(snapshot_dir):
                    continue
                if not _has_mlx_signal(model_dir=snapshot_dir, repo_id=repo_id):
                    continue
                revision = _hf_cache_revision(cache_repo_dir, snapshot_dir.name, revision_map=revision_map)
                models.append(
                    self._raw_model_spec(
                        model_id=repo_id,
                        model_dir=snapshot_dir.resolve(),
                        revision=revision,
                        source_kind="hf_cache_snapshot",
                        metadata={
                            "melix.hf_repo_id": repo_id,
                            "melix.hf_revision": revision,
                        },
                    )
                )
        return models

    @staticmethod
    def _iter_plain_local_model_dirs(root: Path) -> list[Path]:
        model_dirs: list[Path] = []
        stack = [root.resolve()]
        while stack:
            current = stack.pop()
            if current.name in {"blobs", ".git", "__pycache__"}:
                continue
            if (current / "config.json").is_file():
                model_dirs.append(current)
                continue
            try:
                children = sorted(path for path in current.iterdir() if path.is_dir())
            except OSError:
                continue
            stack.extend(reversed(children))
        return model_dirs

    @staticmethod
    def _iter_registry_manifest_paths(root: Path) -> list[Path]:
        manifest_paths: list[Path] = []
        stack = [root.resolve()]
        while stack:
            current = stack.pop()
            if current.name in {"blobs", ".git", "__pycache__"}:
                continue
            manifest_path = current / "manifest.json"
            if manifest_path.is_file():
                manifest_paths.append(manifest_path)
                continue
            try:
                children = sorted(path for path in current.iterdir() if path.is_dir())
            except OSError:
                continue
            stack.extend(reversed(children))
        return sorted(manifest_paths)

    @staticmethod
    def _apply_root_metadata(
        model: common_pb2.ModelSpec,
        *,
        root: Path,
        root_id: str,
        root_order: int,
        relative_path: Path,
    ) -> None:
        model.ext["melix.registry_root_id"] = root_id
        model.ext["melix.registry_root_path"] = str(root.resolve())
        model.ext["melix.registry_root_order"] = str(root_order)
        model.ext["melix.registry_relative_path"] = os.fspath(relative_path)

    @staticmethod
    def _raw_model_spec(
        *,
        model_id: str,
        model_dir: Path,
        revision: str,
        source_kind: str,
        metadata: dict[str, str],
    ) -> common_pb2.ModelSpec:
        runtime_model_path = str(model_dir)
        ext = {
            **metadata,
            "melix.source_kind": source_kind,
            "melix.model_path": runtime_model_path,
        }
        config_payload = _load_model_config_payload(model_dir)
        ext.update(dflash_draft_metadata(config_payload))
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
        else:
            ext.update(
                _vlm_capability_metadata(
                    model_path=runtime_model_path,
                    model_dir=model_dir,
                    metadata=ext,
                    config_payload=config_payload,
                )
            )
        _merge_generation_config_metadata(model_dir, ext=ext)
        return common_pb2.ModelSpec(
            model_id=model_id,
            model_path=runtime_model_path,
            model_kind=model_kind,
            revision=revision,
            tokenizer_hash=f"hf.{model_id.replace('/', '.')}" if source_kind == "hf_cache_snapshot" else "tok-local",
            quant_profile_id="",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
            ext=ext,
        )

    @staticmethod
    def _parse_registry_manifest(
        manifest_path: Path,
    ) -> tuple[str, common_pb2.ModelSpec] | None:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(payload, dict):
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
        config_payload = _load_model_config_payload(runtime_model_dir)
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
        if model_kind == "vlm":
            normalized_ext.update(
                _vlm_capability_metadata(
                    model_path=runtime_model_path,
                    model_dir=runtime_model_dir,
                    metadata=normalized_ext,
                    config_payload=config_payload,
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
        _merge_generation_config_metadata(runtime_model_dir, ext=normalized_ext)

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
            backend_id = configured_backend_id or detected["backend_id"]
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
            },
        )


def _canonical_registry_root_path(raw_path: str) -> str:
    return os.fspath(Path(raw_path).expanduser().resolve(strict=False))


def _stable_registry_root_id(root_path: str) -> str:
    digest = hashlib.sha1(root_path.encode("utf-8")).hexdigest()[:12]
    return f"root-{digest}"
