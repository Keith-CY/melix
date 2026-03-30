from __future__ import annotations

from dataclasses import dataclass
from threading import Event

from worker.runtime.deterministic_delay import sleep_if_configured
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest, prepare_vision_request


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
        return {"model_id": model_spec.model_id, "model_kind": model_spec.model_kind}

    def estimate_resident_bytes(self, model_spec):
        return 3072

    def render_prompt(self, messages, loaded_model=None, template_kwargs=None) -> PreparedVisionRequest:
        _ = template_kwargs
        prepared = prepare_vision_request(messages)
        self._last_probe = VisionProbeSnapshot(
            preprocess_latency_ms=prepared.preprocess_latency_ms,
            preprocess_input_bytes=prepared.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
            first_token_latency_ms=0.0,
        )
        return prepared

    def prompt_token_count(self, prepared_request: PreparedVisionRequest) -> int:
        prompt_tokens = len(prepared_request.prompt_text.split())
        image_tokens = sum(max(1, image.byte_length // 8) for image in prepared_request.images)
        return max(1, prompt_tokens + image_tokens)

    def generate_tokens(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
    ):
        extracted_text = prepared_request.images[0].decoded_text()
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
            text=extracted_text,
            prompt_tokens=self.prompt_token_count(prepared_request),
            completion_tokens=max(1, len(extracted_text.split())),
            finish_reason="stop",
        )

    def last_probe_snapshot(self) -> VisionProbeSnapshot:
        return self._last_probe
