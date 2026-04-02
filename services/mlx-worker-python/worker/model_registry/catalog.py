from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time

from packages.protocol.python.worker.v1 import common_pb2

_ADAPTER_SET_HASH_KEY = "melix.adapter_set_hash"
_CAPABILITY_ROUTE_KIND_KEY = "melix.capability.route_kind"
_CAPABILITY_CLASS_KEY = "melix.capability.class"
_CAPABILITY_SUPPORTED_MODALITIES_KEY = "melix.capability.supported_modalities"
_CAPABILITY_SUPPORTED_TASKS_KEY = "melix.capability.supported_tasks"
_CAPABILITY_SUPPORTED_PARSERS_KEY = "melix.capability.supported_parsers"
_REGISTRY_ROOTS_ENV_KEY = "MELIX_MODEL_ROOTS"
_REGISTRY_PROVIDER_ID_KEY = "melix.registry_provider_id"
_REGISTRY_ORGANIZATION_ID_KEY = "melix.registry_organization_id"
_REGISTRY_MODEL_NAME_KEY = "melix.registry_model_name"
_REGISTRY_VARIANT_ID_KEY = "melix.registry_variant_id"
_AUDIO_BACKEND_ID_KEY = "melix.audio.backend_id"
_AUDIO_FAMILY_ID_KEY = "melix.audio.family_id"
_AUDIO_INSTALL_PROFILE_KEY = "melix.audio.install_profile"
_AUDIO_LANGUAGES_KEY = "melix.audio.languages"
_AUDIO_VOICE_MODE_KEY = "melix.audio.voice_mode"
_AUDIO_OUTPUT_FORMATS_KEY = "melix.audio.output_formats"
_AUDIO_SUPPORTS_INSTRUCTIONS_KEY = "melix.audio.supports_instructions"


@dataclass(frozen=True)
class RegistryRootSnapshot:
    root_id: str
    root_path: str
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
        adapter_set_hash="vision-family-llava-v1",
        route_kind="python_vlm",
        capability_class="vlm",
        supported_modalities=("text", "image"),
        supported_tasks=("vlm", "generate"),
        supported_parsers=("text", "qwen"),
        tool_parser_mode="qwen",
        tool_parser_namespaces=("tools.vision",),
        tool_parser_xml_fallback=True,
    )


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
) -> dict[str, str]:
    return {
        _AUDIO_BACKEND_ID_KEY: backend_id,
        _AUDIO_FAMILY_ID_KEY: family_id,
        _AUDIO_INSTALL_PROFILE_KEY: install_profile,
        _AUDIO_LANGUAGES_KEY: ",".join(languages),
        _AUDIO_VOICE_MODE_KEY: voice_mode,
        _AUDIO_OUTPUT_FORMATS_KEY: ",".join(output_formats),
        _AUDIO_SUPPORTS_INSTRUCTIONS_KEY: "true" if supports_instructions else "false",
    }


class WorkerModelCatalog:
    def __init__(self, environment: dict[str, str] | None = None) -> None:
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
        self._last_registry_snapshot = self._refresh_registry_snapshot()

    def get(self, model_id: str) -> common_pb2.ModelSpec | None:
        return self._models.get(model_id)

    def all_models(self) -> list[common_pb2.ModelSpec]:
        return [self._models[model_id] for model_id in sorted(self._models)]

    def registry_snapshot(self, *, rescan: bool = False) -> RegistrySnapshot:
        if rescan:
            self._last_registry_snapshot = self._refresh_registry_snapshot()
        return self._last_registry_snapshot

    def registry_snapshot_payload(self, *, rescan: bool = False) -> dict[str, object]:
        snapshot = self.registry_snapshot(rescan=rescan)
        return {
            "scanned_at_unix_ms": snapshot.scanned_at_unix_ms,
            "roots": [
                {
                    "root_id": root.root_id,
                    "root_path": root.root_path,
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

    def _refresh_registry_snapshot(self) -> RegistrySnapshot:
        roots, discovered_models = self._scan_registry_roots()
        self._models = dict(self._seed_models)
        for model_id, model in discovered_models.items():
            self._models.setdefault(model_id, model)
        return RegistrySnapshot(
            roots=tuple(roots),
            models=tuple(discovered_models[model_id] for model_id in sorted(discovered_models)),
            scanned_at_unix_ms=int(time.time() * 1000),
        )

    def _scan_registry_roots(self) -> tuple[list[RegistryRootSnapshot], dict[str, common_pb2.ModelSpec]]:
        roots: list[RegistryRootSnapshot] = []
        discovered_models: dict[str, common_pb2.ModelSpec] = {}

        for index, root_path in enumerate(self._configured_registry_roots(), start=1):
            root_id = f"root-{index}"
            root = Path(root_path)
            if not root.is_dir():
                roots.append(
                    RegistryRootSnapshot(
                        root_id=root_id,
                        root_path=str(root),
                        accessible=False,
                        error_code="not_found",
                        error_message="Registry root does not exist.",
                    )
                )
                continue

            accepted_model_ids: list[str] = []
            for manifest_path in sorted(root.rglob("manifest.json")):
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
                model.ext["melix.registry_relative_path"] = os.fspath(relative_path)
                model.ext["melix.model_path"] = str(manifest_path.parent)
                discovered_models[model_id] = model
                accepted_model_ids.append(model_id)

            roots.append(
                RegistryRootSnapshot(
                    root_id=root_id,
                    root_path=str(root),
                    accessible=True,
                    discovered_model_ids=tuple(accepted_model_ids),
                )
            )

        return roots, discovered_models

    def _configured_registry_roots(self) -> list[str]:
        raw = self._environment.get(_REGISTRY_ROOTS_ENV_KEY, "")
        if not raw.strip():
            return []

        roots: list[str] = []
        seen: set[str] = set()
        for part in raw.split(os.pathsep):
            normalized = part.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            roots.append(normalized)
        return roots

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
        for payload_key, ext_key in (
            ("provider_id", _REGISTRY_PROVIDER_ID_KEY),
            ("organization_id", _REGISTRY_ORGANIZATION_ID_KEY),
            ("model_name", _REGISTRY_MODEL_NAME_KEY),
            ("variant_id", _REGISTRY_VARIANT_ID_KEY),
        ):
            override_value = _normalized(str(payload.get(payload_key, "")))
            if override_value:
                normalized_ext[ext_key] = override_value

        model_kind = _normalized(str(payload.get("model_kind", "text"))) or "text"
        quant_profile_id = _normalized(str(payload.get("quant_profile_id", "")))
        revision = _normalized(str(payload.get("revision", "registry"))) or "registry"
        tokenizer_hash = _normalized(str(payload.get("tokenizer_hash", "tok-registry"))) or "tok-registry"
        parser_mode = _normalized(str(payload.get("parser_mode", "text"))) or "text"
        reasoning_mode = _normalized(str(payload.get("reasoning_mode", "off"))) or "off"
        max_context = int(payload.get("max_context", 8192) or 8192)

        return model_id, common_pb2.ModelSpec(
            model_id=model_id,
            model_path=str(manifest_path.parent),
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
        return common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=environment.get("MELIX_DEV_TEXT_MODEL_PATH", "models/melix-dev-text"),
            model_kind="text",
            revision="dev",
            tokenizer_hash="tok-dev",
            quant_profile_id="q4",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
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
                ),
            },
        )

    @staticmethod
    def dev_image_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-image",
            model_path=environment.get("MELIX_DEV_IMAGE_MODEL_PATH", "models/melix-dev-image"),
            model_kind="image",
            revision="dev",
            tokenizer_hash="tok-image-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
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
                ),
            },
        )
