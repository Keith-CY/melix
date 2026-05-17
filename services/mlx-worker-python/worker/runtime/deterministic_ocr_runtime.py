from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from threading import Event

from worker.runtime.deterministic_delay import sleep_if_configured
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent
from worker.runtime.multimodal_preprocessing import (
    MultimodalPreprocessError,
    PreparedVisionRequest,
    prepare_vision_request,
)
from worker.runtime.token_counting import whitespace_token_count as _whitespace_token_count


@dataclass(frozen=True)
class VisionProbeSnapshot:
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    first_token_latency_ms: float


class DeterministicOCRRuntime:
    runtime_name = "deterministic-ocr"

    def __init__(self) -> None:
        self._last_probe = VisionProbeSnapshot(0.0, 0, 0, 0.0)

    def load_model(self, model_spec):
        return {
            "model_id": model_spec.model_id,
            "model_kind": model_spec.model_kind,
            "metadata": dict(model_spec.ext),
        }

    def estimate_resident_bytes(self, model_spec):
        return 3072

    def render_prompt(
        self,
        messages,
        loaded_model=None,
        template_kwargs=None,
        execution_ext=None,
    ) -> PreparedVisionRequest:
        _ = template_kwargs
        prepared = prepare_vision_request(messages)
        if len(prepared.images) != 1:
            raise MultimodalPreprocessError("OCR only supports single-image requests.")
        effective_prompt = self._effective_prompt(
            prepared.prompt_text,
            loaded_model=loaded_model,
            execution_ext=execution_ext,
        )
        if effective_prompt != prepared.prompt_text:
            prepared = self._with_prompt_text(prepared, effective_prompt)
        self._last_probe = VisionProbeSnapshot(
            preprocess_latency_ms=prepared.preprocess_latency_ms,
            preprocess_input_bytes=prepared.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
            first_token_latency_ms=0.0,
        )
        return prepared

    def prompt_token_count(self, prepared_request: PreparedVisionRequest) -> int:
        images = prepared_request.images
        prompt_tokens = _whitespace_token_count(prepared_request.prompt_text)
        if len(images) == 1 and not prepared_request.videos:
            return max(
                1,
                prompt_tokens + max(1, prepared_request.preprocess_input_bytes // 8),
            )
        image_tokens = sum(max(1, image.byte_length // 8) for image in images)
        return max(1, prompt_tokens + image_tokens)

    def generate_tokens(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        execution_ext=None,
    ):
        extracted_text = prepared_request.images[0].decoded_text()
        output_text = self._apply_stop_sequences(
            extracted_text,
            sampling=sampling,
            loaded_model=loaded_model,
            execution_ext=execution_ext,
        )
        self._last_probe = VisionProbeSnapshot(
            preprocess_latency_ms=prepared_request.preprocess_latency_ms,
            preprocess_input_bytes=prepared_request.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
            first_token_latency_ms=max(0.0, prepared_request.preprocess_latency_ms / 2.0),
        )
        sleep_if_configured("ocr")
        if cancel_event.is_set():
            return
        yield RuntimeTokenEvent(
            text=output_text,
            prompt_tokens=self.prompt_token_count(prepared_request),
            completion_tokens=max(1, _whitespace_token_count(output_text)),
            finish_reason="stop_sequence" if output_text != extracted_text else "stop",
        )

    def last_probe_snapshot(self) -> VisionProbeSnapshot:
        return self._last_probe

    def _effective_prompt(
        self,
        prompt_text: str,
        *,
        loaded_model,
        execution_ext,
    ) -> str:
        metadata = self._metadata(loaded_model)
        template = (execution_ext or {}).get("melix.ocr.prompt_template") or metadata.get("ocr_prompt_template", "")
        auto_prompt = (execution_ext or {}).get("melix.ocr.auto_prompt") or metadata.get(
            "ocr_auto_prompt",
            "",
        )
        effective_instruction = prompt_text.strip() or auto_prompt.strip()
        if not effective_instruction:
            return prompt_text
        if "{prompt}" in template:
            return template.replace("{prompt}", effective_instruction)
        return effective_instruction

    def _apply_stop_sequences(
        self,
        text: str,
        *,
        sampling,
        loaded_model,
        execution_ext,
    ) -> str:
        stop_sequences = self._stop_sequences(
            sampling=sampling,
            loaded_model=loaded_model,
            execution_ext=execution_ext,
        )
        if not stop_sequences:
            return text

        stop_index: int | None = None
        for stop_sequence in stop_sequences:
            if not stop_sequence:
                continue
            index = text.find(stop_sequence)
            if index == -1:
                continue
            if stop_index is None or index < stop_index:
                stop_index = index
        if stop_index is None:
            return text
        return text[:stop_index]

    def _stop_sequences(
        self,
        *,
        sampling,
        loaded_model,
        execution_ext,
    ) -> list[str]:
        configured = getattr(sampling, "stop", None)
        if configured:
            return [str(item) for item in configured if str(item)]

        raw_value = (execution_ext or {}).get("melix.ocr.stop_sequences")
        if raw_value is None:
            raw_value = self._metadata(loaded_model).get("ocr_stop_sequences", "")
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    @staticmethod
    def _metadata(loaded_model) -> dict[str, str]:
        if isinstance(loaded_model, dict):
            metadata = loaded_model.get("metadata")
            if isinstance(metadata, dict):
                return metadata
        return {}

    @staticmethod
    def _with_prompt_text(
        prepared_request: PreparedVisionRequest,
        prompt_text: str,
    ) -> PreparedVisionRequest:
        prompt_hash_hex = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        digest = hashlib.sha256()
        digest.update(prompt_hash_hex.encode("ascii"))
        for image in prepared_request.images:
            digest.update(image.sha256_hex.encode("ascii"))
        return replace(
            prepared_request,
            prompt_text=prompt_text,
            prompt_hash_hex=prompt_hash_hex,
            multimodal_hash_hex=digest.hexdigest(),
        )
