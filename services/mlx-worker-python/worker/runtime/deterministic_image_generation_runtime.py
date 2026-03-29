from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from packages.protocol.python.worker.v1 import common_pb2

from worker.runtime.deterministic_delay import sleep_if_configured


class ImageGenerationCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageGenerationProbeSnapshot:
    job_latency_ms: float
    artifact_publish_ms: float
    output_bytes: int
    peak_memory_bytes: int


@dataclass(frozen=True)
class DeterministicImageGenerationResult:
    images: list[bytes]
    artifacts: list[common_pb2.ImageArtifactMetadata]
    progress: common_pb2.ImageJobProgress


class DeterministicImageGenerationRuntime:
    runtime_name = "deterministic-image"

    def __init__(self) -> None:
        self._last_probe = ImageGenerationProbeSnapshot(0.0, 0.0, 0, 0)

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_kind": model_spec.model_kind}

    def estimate_resident_bytes(self, model_spec):
        return 8192

    def generate_images(
        self,
        loaded_model,
        request,
        *,
        job_id: str,
        images_root: Path,
        cancel_event: Event,
    ) -> DeterministicImageGenerationResult:
        started = time.monotonic()
        width, height = self._parse_size(request.size or "1024x1024")
        image_count = max(1, int(request.n or 1))
        image_format = self._normalized_format(request.response_format)
        mime_type = self._mime_type_for_format(image_format)
        output_dir = self._output_dir(images_root, request.artifact_namespace, job_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        images: list[bytes] = []
        artifacts: list[common_pb2.ImageArtifactMetadata] = []
        artifact_publish_ms = 0.0

        for index in range(image_count):
            if cancel_event.is_set():
                raise ImageGenerationCancelled("Image generation was canceled.")

            sleep_if_configured("image")
            payload = self._render_payload(
                prompt=request.prompt,
                width=width,
                height=height,
                variant=index,
                model_id=str(loaded_model.get("model_id", "image-model")),
            )
            artifact_path = output_dir / f"output-{index}.{image_format}"
            artifact_started = time.monotonic()
            artifact_path.write_bytes(payload)
            artifact_publish_ms += (time.monotonic() - artifact_started) * 1000.0

            digest = hashlib.sha256(payload).hexdigest()
            artifact = common_pb2.ImageArtifactMetadata(
                artifact_id=f"{job_id}::artifact-{index}",
                job_id=job_id,
                role=common_pb2.IMAGE_ARTIFACT_GENERATED,
                mime_type=mime_type,
                format=image_format,
                width=width,
                height=height,
                byte_length=len(payload),
                storage_uri=str(artifact_path),
                sha256=digest,
                variant_index=index,
            )
            images.append(payload)
            artifacts.append(artifact)

        total_output_bytes = sum(len(item) for item in images)
        peak_memory_bytes = max(total_output_bytes, width * height)
        self._last_probe = ImageGenerationProbeSnapshot(
            job_latency_ms=(time.monotonic() - started) * 1000.0,
            artifact_publish_ms=artifact_publish_ms,
            output_bytes=total_output_bytes,
            peak_memory_bytes=peak_memory_bytes,
        )

        return DeterministicImageGenerationResult(
            images=images,
            artifacts=artifacts,
            progress=common_pb2.ImageJobProgress(
                stage="completed",
                pct=1.0,
                completed_steps=image_count,
                total_steps=image_count,
            ),
        )

    def last_probe_snapshot(self) -> ImageGenerationProbeSnapshot:
        return self._last_probe

    @staticmethod
    def _parse_size(raw_size: str) -> tuple[int, int]:
        width_raw, separator, height_raw = raw_size.lower().partition("x")
        if separator != "x":
            raise ValueError(f"Unsupported image size: {raw_size}")
        try:
            width = int(width_raw)
            height = int(height_raw)
        except ValueError as exc:
            raise ValueError(f"Unsupported image size: {raw_size}") from exc
        if width <= 0 or height <= 0:
            raise ValueError(f"Unsupported image size: {raw_size}")
        return width, height

    @staticmethod
    def _normalized_format(response_format: str) -> str:
        normalized = (response_format or "png").strip().lower()
        if normalized in {"png", "jpeg", "jpg", "webp"}:
            return "jpeg" if normalized == "jpg" else normalized
        raise ValueError(f"Unsupported image response format: {response_format}")

    @staticmethod
    def _mime_type_for_format(image_format: str) -> str:
        return {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }[image_format]

    @staticmethod
    def _output_dir(images_root: Path, artifact_namespace: str, job_id: str) -> Path:
        namespace = (artifact_namespace or "generated").strip() or "generated"
        return images_root / namespace / job_id

    @staticmethod
    def _render_payload(
        *,
        prompt: str,
        width: int,
        height: int,
        variant: int,
        model_id: str,
    ) -> bytes:
        payload = (
            f"MELIX_IMAGE\n"
            f"MODEL={model_id}\n"
            f"PROMPT={prompt or '<empty>'}\n"
            f"SIZE={width}x{height}\n"
            f"VARIANT={variant}\n"
        ).encode("utf-8")
        return b"\x89PNG\r\n\x1a\n" + payload
