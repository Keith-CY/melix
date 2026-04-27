from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import importlib.util
import time
from pathlib import Path
from threading import Event
from typing import Any, Callable

from worker.runtime.deterministic_vlm_runtime import VisionProbeSnapshot
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent
from worker.runtime.multimodal_fast_paths import MultimodalFastPathController
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest, prepare_vision_request, rebuild_multimodal_hash
from worker.runtime.temp_media_lifecycle import TempMediaSession
from worker.runtime.vision_family_adapters import resolve_vision_family_config


class RuntimeUnavailableError(RuntimeError):
    pass


def _gemma4_multimodal_weight_presence(weight_names: list[str] | tuple[str, ...] | set[str]) -> tuple[bool, bool]:
    has_vision = any(
        name.startswith("vision_tower.") or name.startswith("embed_vision.")
        for name in weight_names
    )
    has_audio = any(
        name.startswith("audio_tower.") or name.startswith("embed_audio.")
        for name in weight_names
    )
    return has_vision, has_audio


def _gemma4_loaded_execution_mode(model: Any, processor: Any) -> str:
    if getattr(model, "vision_tower", None) is not None or getattr(model, "embed_vision", None) is not None:
        return "multimodal"
    if getattr(processor, "image_processor", None) is not None:
        return "multimodal"
    return "text_backed"


def _patch_gemma4_scaled_linear_quantization() -> None:
    import mlx.nn as nn
    import mlx_vlm.models.gemma4.language as gemma4_language

    if hasattr(gemma4_language.ScaledLinear, "to_quantized"):
        return

    class QuantizedScaledLinear(nn.QuantizedLinear):
        def __init__(
            self,
            in_features: int,
            out_features: int,
            scalar: float,
            *,
            group_size: int | None = None,
            bits: int | None = None,
            mode: str = "affine",
        ) -> None:
            super().__init__(
                in_features,
                out_features,
                bias=False,
                group_size=group_size,
                bits=bits,
                mode=mode,
            )
            self.scalar = scalar

        def __call__(self, x):
            return super().__call__(x) * self.scalar

    def to_quantized(
        self,
        group_size: int | None = None,
        bits: int | None = None,
        mode: str = "affine",
        quantize_input: bool = False,
    ):
        _ = quantize_input
        return QuantizedScaledLinear(
            self.weight.shape[1],
            self.weight.shape[0],
            self.scalar,
            group_size=group_size,
            bits=bits,
            mode=mode,
        )

    gemma4_language.ScaledLinear.to_quantized = to_quantized


@dataclass
class AutoMLXVLMBackend:
    load_fn: Any | None = None
    stream_generate_fn: Any | None = None
    apply_chat_template_fn: Any | None = None
    runtime_name: str = "mlx-vlm-unavailable"

    def __post_init__(self) -> None:
        if self.load_fn is not None and self.stream_generate_fn is not None and self.apply_chat_template_fn is not None:
            self.runtime_name = "mlx-vlm"
            self._available = True
            self._error = None
            return
        self._available = importlib.util.find_spec("mlx_vlm") is not None
        self._error = None if self._available else ModuleNotFoundError("mlx_vlm is not installed")
        if self._available:
            self.runtime_name = "mlx-vlm"

    def _ensure_runtime(self) -> None:
        if self.load_fn is not None and self.stream_generate_fn is not None and self.apply_chat_template_fn is not None:
            return
        try:
            from mlx_vlm import apply_chat_template, load, stream_generate
        except ModuleNotFoundError as exc:
            self._available = False
            self._error = exc
            self.runtime_name = "mlx-vlm-unavailable"
            raise RuntimeUnavailableError("mlx-vlm is not installed") from exc
        self._available = True
        self._error = None
        self.runtime_name = "mlx-vlm"
        self.load_fn = load
        self.stream_generate_fn = stream_generate
        self.apply_chat_template_fn = apply_chat_template

    def load_model(self, model_spec):
        if not self._available:
            raise RuntimeUnavailableError("mlx-vlm is not installed") from self._error
        self._ensure_runtime()
        metadata = dict(model_spec.ext)
        execution_mode = metadata.get("melix.vlm.execution_mode", "").strip() or "multimodal"
        try:
            model, processor = self.load_fn(
                model_spec.model_path,
                revision=model_spec.revision or "main",
            )
            if self._should_attempt_gemma4_text_backed_fallback(model_spec):
                execution_mode = _gemma4_loaded_execution_mode(model, processor)
        except Exception as exc:
            if not self._should_attempt_gemma4_text_backed_fallback(model_spec):
                raise
            model, processor, execution_mode = self._load_gemma4_text_backed_model(
                model_spec=model_spec,
                original_error=exc,
            )
        metadata["melix.vlm.execution_mode"] = execution_mode
        return {
            "model_id": model_spec.model_id,
            "model_kind": model_spec.model_kind,
            "model_path": model_spec.model_path,
            "revision": model_spec.revision,
            "tokenizer_hash": model_spec.tokenizer_hash,
            "quant_profile_id": model_spec.quant_profile_id,
            "parser_mode": model_spec.parser_mode,
            "reasoning_mode": model_spec.reasoning_mode,
            "model": model,
            "processor": processor,
            "metadata": metadata,
            **resolve_vision_family_config(dict(model_spec.ext)).capability_metadata(),
        }

    @staticmethod
    def estimate_resident_bytes(model_spec) -> int:
        _ = model_spec
        return 0

    @staticmethod
    def _should_attempt_gemma4_text_backed_fallback(model_spec) -> bool:
        metadata = dict(getattr(model_spec, "ext", {}))
        if metadata.get("vision_family_id", "").strip() == "gemma4-v1":
            return True
        model_path = str(getattr(model_spec, "model_path", "") or "").lower()
        return "gemma-4" in model_path or "gemma4" in model_path

    @staticmethod
    def _load_gemma4_text_backed_model(model_spec, original_error: Exception):
        import mlx.core as mx
        import mlx.nn as nn
        from mlx_vlm.utils import (
            get_model_and_args,
            get_model_path,
            load_config,
            load_processor,
            update_module_configs,
        )

        _patch_gemma4_scaled_linear_quantization()

        model_path = get_model_path(model_spec.model_path, revision=model_spec.revision or "main")
        config = load_config(model_path)
        weights: dict[str, Any] = {}
        for weight_file in model_path.glob("*.safetensors"):
            weights.update(mx.load(str(weight_file)))

        has_vision_weights, has_audio_weights = _gemma4_multimodal_weight_presence(list(weights))
        if has_vision_weights:
            raise original_error

        model_class, _ = get_model_and_args(config=config)
        config.setdefault("text_config", config.pop("llm_config", {}))
        config.setdefault("vision_config", {})
        config.setdefault("audio_config", {})

        model_config = model_class.ModelConfig.from_dict(config)
        model_config = update_module_configs(
            model_config,
            model_class,
            config,
            ["text", "vision", "perceiver", "projector", "audio"],
        )
        model = model_class.Model(model_config)
        model.vision_tower = None
        model.embed_vision = None
        if not has_audio_weights:
            model.audio_tower = None
            model.embed_audio = None

        quantization = config.get("quantization")
        if quantization is not None:
            def get_class_predicate(path: str, module: Any):
                if path.startswith(("vision_tower", "embed_vision")):
                    return False
                if path.startswith(("audio_tower", "embed_audio")) and not has_audio_weights:
                    return False
                if path in quantization:
                    return quantization[path]
                if not hasattr(module, "to_quantized"):
                    return False
                if hasattr(module, "weight") and module.weight.size % 64 != 0:
                    return False
                return f"{path}.scales" in weights

            nn.quantize(
                model,
                group_size=quantization["group_size"],
                bits=quantization["bits"],
                mode=quantization.get("mode", "affine"),
                class_predicate=get_class_predicate,
            )

        filtered_weights = [
            (key, value)
            for key, value in weights.items()
            if not key.startswith(("vision_tower.", "embed_vision."))
            and (has_audio_weights or not key.startswith(("audio_tower.", "embed_audio.")))
        ]
        model.load_weights(filtered_weights)

        processor = load_processor(
            model_path,
            True,
            eos_token_ids=getattr(model.config, "eos_token_id", None),
        )
        execution_mode = "text_backed"
        return model, processor, execution_mode


class MLXVLMRuntime:
    def __init__(
        self,
        backend: AutoMLXVLMBackend | None = None,
        temp_root: Path | str | None = None,
        temp_media_session_factory: Callable[..., TempMediaSession] | None = None,
        fast_path_controller: MultimodalFastPathController | None = None,
    ) -> None:
        self._backend = backend or AutoMLXVLMBackend()
        self._temp_root = Path(temp_root) if temp_root is not None else None
        self._temp_media_session_factory = temp_media_session_factory or TempMediaSession
        self._fast_path_controller = fast_path_controller or MultimodalFastPathController()
        self._last_probe = VisionProbeSnapshot(0.0, 0, 0, 0.0)
        self._last_fast_path_signature: tuple[str, ...] | None = None

    @property
    def runtime_name(self) -> str:
        return getattr(self._backend, "runtime_name", "mlx-vlm-unavailable")

    def load_model(self, model_spec):
        return self._backend.load_model(model_spec)

    def estimate_resident_bytes(self, model_spec) -> int:
        return int(self._backend.estimate_resident_bytes(model_spec))

    def render_prompt(
        self,
        messages,
        loaded_model=None,
        template_kwargs=None,
        execution_ext: dict[str, str] | None = None,
    ) -> PreparedVisionRequest:
        _ = template_kwargs
        started_at = time.perf_counter()
        metadata = loaded_model.get("metadata", {}) if isinstance(loaded_model, dict) else {}
        execution_mode = str(metadata.get("melix.vlm.execution_mode", "") or "").strip() or "multimodal"
        family_config = self._family_config(loaded_model)
        has_non_text_media = self._contains_non_text_media(messages)
        if execution_mode == "text_backed":
            if has_non_text_media:
                prepared = family_config.shape_request(prepare_vision_request(messages))
                if prepared.videos and not prepared.images:
                    prepared = self._replace_prompt_text(
                        prepared,
                        prompt_text=self._text_backed_video_prompt(prepared),
                    )
                prepared = replace(
                    prepared,
                    preprocess_latency_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
                    preprocess_input_bytes=prepared.preprocess_input_bytes,
                    preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
                )
            else:
                prepared = self._prompt_only_request(
                    messages,
                    family_config=family_config,
                    started_at=started_at,
                )
        else:
            if has_non_text_media:
                prepared = family_config.shape_request(prepare_vision_request(messages))
            else:
                prepared = self._prompt_only_request(
                    messages,
                    family_config=family_config,
                    started_at=started_at,
                )
        self._record_fast_path_probe(loaded_model, prepared)
        return prepared

    def prompt_token_count(
        self,
        prepared_request: PreparedVisionRequest,
        loaded_model=None,
    ) -> int:
        return self._family_config(loaded_model).prompt_token_count(prepared_request)

    def generate_tokens(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        execution_ext: dict[str, str] | None = None,
    ):
        _ = execution_ext
        metadata = loaded_model.get("metadata", {}) if isinstance(loaded_model, dict) else {}
        execution_mode = str(metadata.get("melix.vlm.execution_mode", "") or "").strip() or "multimodal"
        if execution_mode == "text_backed" and prepared_request.images:
            raise RuntimeError(
                "The loaded Gemma 4 MLX package does not include vision weights, so image inputs are unavailable."
            )
        self._ensure_fast_path_probe(loaded_model, prepared_request)
        self._backend._ensure_runtime()
        if cancel_event.is_set():
            return

        prompt_tokens = self.prompt_token_count(prepared_request, loaded_model=loaded_model)
        temp_media_session = self._temp_media_session_factory(
            temp_root=self._temp_root,
            prefix="melix-vlm-",
        )
        try:
            image_paths = self._materialize_media(prepared_request, temp_media_session)
            formatted_prompt = self._backend.apply_chat_template_fn(
                loaded_model["processor"],
                loaded_model["model"].config,
                prepared_request.prompt_text,
                num_images=len(image_paths),
            )
            image_argument = image_paths if image_paths else None

            started_at = time.perf_counter()
            first_token_at: float | None = None
            completion_tokens = 0
            for response in self._backend.stream_generate_fn(
                loaded_model["model"],
                loaded_model["processor"],
                formatted_prompt,
                image=image_argument,
                max_tokens=int(getattr(sampling, "max_output_tokens", 0) or 64),
                temperature=float(getattr(sampling, "temperature", 0.0)),
                top_p=float(getattr(sampling, "top_p", 1.0)),
                top_k=int(getattr(sampling, "top_k", 0)),
                verbose=False,
            ):
                if cancel_event.is_set():
                    return
                text = str(getattr(response, "text", "") or "")
                if not text:
                    continue
                now = time.perf_counter()
                if first_token_at is None:
                    first_token_at = now
                    self._last_probe = replace(
                        self._last_probe,
                        preprocess_latency_ms=prepared_request.preprocess_latency_ms,
                        preprocess_input_bytes=prepared_request.preprocess_input_bytes,
                        preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
                        first_token_latency_ms=max(0.0, (first_token_at - started_at) * 1000.0),
                        video_effective_frame_count=prepared_request.effective_video_frame_count,
                        video_requested_frame_budget=prepared_request.requested_video_frame_budget,
                        video_window_ms=prepared_request.effective_video_window_ms,
                        cache_identity="",
                        cache_scope_id="",
                        cache_hit=False,
                    )
                completion_tokens = max(
                    completion_tokens,
                    int(getattr(response, "generation_tokens", 0) or (completion_tokens + 1)),
                )
                yield RuntimeTokenEvent(
                    text=text,
                    prompt_tokens=int(getattr(response, "prompt_tokens", 0) or prompt_tokens),
                    completion_tokens=completion_tokens,
                    prompt_tps=float(getattr(response, "prompt_tps", 0.0) or 0.0),
                    generation_tps=float(getattr(response, "generation_tps", 0.0) or 0.0),
                    peak_memory=float(getattr(response, "peak_memory", 0.0) or 0.0),
                    finish_reason="stop",
                )
        finally:
            cleanup_report = temp_media_session.cleanup()
            self._last_probe = replace(
                self._last_probe,
                temp_media_artifact_count=cleanup_report.artifact_count,
                temp_media_artifact_bytes=cleanup_report.artifact_bytes,
                temp_media_cleanup_latency_ms=cleanup_report.cleanup_latency_ms,
                temp_media_cleanup_failure_count=cleanup_report.cleanup_failure_count,
            )

    def last_probe_snapshot(self) -> VisionProbeSnapshot:
        return self._last_probe

    def _ensure_fast_path_probe(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
    ) -> None:
        signature = self._fast_path_probe_signature(loaded_model, prepared_request)
        if self._last_fast_path_signature == signature:
            return
        self._record_fast_path_probe(loaded_model, prepared_request, signature=signature)

    def _record_fast_path_probe(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        *,
        signature: tuple[str, ...] | None = None,
    ) -> None:
        fast_path = self._fast_path_controller.plan(loaded_model, prepared_request)
        self._last_fast_path_signature = signature or self._fast_path_probe_signature(
            loaded_model,
            prepared_request,
        )
        self._last_probe = VisionProbeSnapshot(
            preprocess_latency_ms=prepared_request.preprocess_latency_ms,
            preprocess_input_bytes=prepared_request.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
            first_token_latency_ms=0.0,
            video_effective_frame_count=prepared_request.effective_video_frame_count,
            video_requested_frame_budget=prepared_request.requested_video_frame_budget,
            video_window_ms=prepared_request.effective_video_window_ms,
            cache_identity="",
            cache_scope_id="",
            cache_hit=False,
            image_feature_cache_hits=fast_path.image_feature_cache_hits,
            image_feature_cache_misses=fast_path.image_feature_cache_misses,
            multimodal_decode_mode=fast_path.multimodal_decode_mode,
            multimodal_fallback_reason=fast_path.multimodal_fallback_reason,
            multimodal_decode_sync_mode=fast_path.multimodal_decode_sync_mode,
            multi_image_scatter_mode=fast_path.multi_image_scatter_mode,
            quantized_load_mode=fast_path.quantized_load_mode,
            quantized_load_fallback_reason=fast_path.quantized_load_fallback_reason,
        )

    @staticmethod
    def _fast_path_probe_signature(
        loaded_model,
        prepared_request: PreparedVisionRequest,
    ) -> tuple[str, ...]:
        metadata = loaded_model.get("metadata", {}) if isinstance(loaded_model, dict) else {}
        metadata_items: tuple[tuple[str, str], ...] = ()
        if isinstance(metadata, dict):
            metadata_items = tuple(
                sorted(
                    (str(key), str(value))
                    for key, value in metadata.items()
                    if key in {
                        "melix.vlm.execution_mode",
                        "vision_family_id",
                        "vision_prompt_profile_id",
                        "vision_tokenization_mode",
                        "vision_max_images_per_prompt",
                        "melix.multimodal_adapter_hash",
                        "multimodal_adapter_hash",
                    }
                )
            )
        top_level_items: tuple[tuple[str, str], ...] = ()
        if isinstance(loaded_model, dict):
            top_level_items = tuple(
                sorted(
                    (key, str(loaded_model.get(key, "")))
                    for key in ("model_id", "revision", "tokenizer_hash", "quant_profile_id")
                )
            )
        return (
            prepared_request.multimodal_hash_hex,
            repr(top_level_items),
            repr(metadata_items),
        )

    @staticmethod
    def _materialize_media(
        prepared_request: PreparedVisionRequest,
        temp_media_session: TempMediaSession,
    ) -> list[str]:
        image_paths: list[str] = []
        for index, image in enumerate(prepared_request.images):
            suffix = MLXVLMRuntime._media_suffix(image.filename, image.format)
            image_path = temp_media_session.write_bytes(f"image-{index}.{suffix}", image.bytes_data)
            image_paths.append(str(image_path))
        for index, video in enumerate(prepared_request.videos):
            if not video.bytes_data:
                continue
            suffix = MLXVLMRuntime._media_suffix(video.filename, video.format)
            temp_media_session.write_bytes(f"video-{index}.{suffix}", video.bytes_data)
        return image_paths

    @staticmethod
    def _media_suffix(filename: str, format_name: str) -> str:
        if format_name:
            return format_name
        if "." in filename:
            return filename.rsplit(".", 1)[-1]
        return "bin"

    @staticmethod
    def _family_config(loaded_model) -> Any:
        metadata: dict[str, str] = {}
        if isinstance(loaded_model, dict):
            raw_metadata = loaded_model.get("metadata")
            if isinstance(raw_metadata, dict):
                metadata = {
                    str(key): str(value)
                    for key, value in raw_metadata.items()
                }
        return resolve_vision_family_config(metadata)

    @staticmethod
    def _prompt_text_from_messages(messages) -> str:
        prompt_segments: list[str] = []
        for message in messages:
            for part in message.parts:
                text = str(getattr(part, "text", "") or "").strip()
                if text:
                    prompt_segments.append(text)
        return "\n".join(prompt_segments).strip()

    @staticmethod
    def _contains_non_text_media(messages) -> bool:
        for message in messages:
            for part in message.parts:
                if getattr(part, "image_bytes", b"") or getattr(part, "image_uri", ""):
                    return True
                if getattr(part, "video_bytes", b"") or getattr(part, "video_uri", ""):
                    return True
        return False

    @staticmethod
    def _replace_prompt_text(
        prepared_request: PreparedVisionRequest,
        *,
        prompt_text: str,
    ) -> PreparedVisionRequest:
        normalized_prompt_text = prompt_text.strip()
        prompt_hash_hex = hashlib.sha256(normalized_prompt_text.encode("utf-8")).hexdigest()
        return replace(
            prepared_request,
            prompt_text=normalized_prompt_text,
            prompt_hash_hex=prompt_hash_hex,
            multimodal_hash_hex=rebuild_multimodal_hash(prepared_request, prompt_hash_hex),
        )

    @staticmethod
    def _prompt_only_request(
        messages,
        *,
        family_config,
        started_at: float,
    ) -> PreparedVisionRequest:
        prompt_text = MLXVLMRuntime._prompt_text_from_messages(messages)
        prepared = PreparedVisionRequest(
            prompt_text=prompt_text,
            images=[],
            videos=[],
            video_frame_policies=[],
            preprocess_latency_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
            preprocess_input_bytes=len(prompt_text.encode("utf-8")),
            preprocess_peak_memory_bytes=0,
        )
        prepared = family_config.shape_request(prepared)
        prompt_hash_hex = hashlib.sha256(prepared.prompt_text.encode("utf-8")).hexdigest()
        return replace(
            prepared,
            prompt_hash_hex=prompt_hash_hex,
            multimodal_hash_hex=prompt_hash_hex,
        )

    @staticmethod
    def _text_backed_video_prompt(prepared_request: PreparedVisionRequest) -> str:
        prompt_text = prepared_request.prompt_text or "Describe the video."
        video_lines = [
            (
                f"Video {index + 1}: {video.filename};"
                f" format={video.format};"
                f" frames={policy.effective_frame_count};"
                f" start_ms={policy.clip_start_ms};"
                f" end_ms={policy.clip_end_ms}"
            )
            for index, (video, policy) in enumerate(
                zip(prepared_request.videos, prepared_request.video_frame_policies, strict=False)
            )
        ]
        video_lines.append(f"Prompt: {prompt_text}")
        return "\n".join(video_lines)
