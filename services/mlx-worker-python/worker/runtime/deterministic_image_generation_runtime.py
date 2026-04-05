from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from urllib.parse import unquote, urlparse

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

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

    def edit_image(
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
        output_dir = self._output_dir(images_root, "edited", job_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        if cancel_event.is_set():
            raise ImageGenerationCancelled("Image edit was canceled.")

        source_bytes, source_format = self._resolve_edit_input(
            inline_bytes=bytes(request.image),
            uri=request.image_uri,
            label="image edit source",
        )
        mask_bytes, mask_format = self._resolve_optional_edit_input(
            inline_bytes=bytes(request.mask),
            uri=request.mask_uri,
            label="image edit mask",
        )

        artifacts: list[common_pb2.ImageArtifactMetadata] = []
        artifact_publish_ms = 0.0
        lineage_ext = self._lineage_ext(
            request,
            source_job_id=request.ext.get("melix.image.source_job_id", ""),
        )

        source_path = output_dir / f"source.{source_format}"
        artifact_publish_ms += self._write_bytes(source_path, source_bytes)
        artifacts.append(
            self._artifact_metadata(
                job_id=job_id,
                artifact_id=f"{job_id}::source",
                role=common_pb2.IMAGE_ARTIFACT_EDIT_SOURCE,
                mime_type=self._mime_type_for_format(source_format),
                image_format=source_format,
                width=width,
                height=height,
                payload=source_bytes,
                storage_path=source_path,
                variant_index=0,
                parent_artifact_id=request.source_artifact_id,
                ext=lineage_ext,
            )
        )

        if mask_bytes is not None:
            mask_path = output_dir / f"mask.{mask_format}"
            artifact_publish_ms += self._write_bytes(mask_path, mask_bytes)
            artifacts.append(
                self._artifact_metadata(
                    job_id=job_id,
                    artifact_id=f"{job_id}::mask",
                    role=common_pb2.IMAGE_ARTIFACT_MASK,
                    mime_type=self._mime_type_for_format(mask_format),
                    image_format=mask_format,
                    width=width,
                    height=height,
                    payload=mask_bytes,
                    storage_path=mask_path,
                    variant_index=0,
                    parent_artifact_id=request.source_artifact_id,
                    ext=lineage_ext,
                )
            )

        images: list[bytes] = []
        for index in range(image_count):
            if cancel_event.is_set():
                raise ImageGenerationCancelled("Image edit was canceled.")

            sleep_if_configured("image")
            payload = self._render_edit_payload(
                prompt=request.prompt,
                width=width,
                height=height,
                variant=index,
                model_id=str(loaded_model.get("model_id", "image-model")),
                strength=float(request.strength or 0.0),
                source_bytes=source_bytes,
                mask_bytes=mask_bytes,
            )
            artifact_path = output_dir / f"output-{index}.{image_format}"
            artifact_publish_ms += self._write_bytes(artifact_path, payload)
            images.append(payload)
            artifacts.append(
                self._artifact_metadata(
                    job_id=job_id,
                    artifact_id=f"{job_id}::artifact-{index}",
                    role=common_pb2.IMAGE_ARTIFACT_GENERATED,
                    mime_type=mime_type,
                    image_format=image_format,
                    width=width,
                    height=height,
                    payload=payload,
                    storage_path=artifact_path,
                    variant_index=index,
                    parent_artifact_id=request.source_artifact_id,
                    ext=lineage_ext,
                )
            )

        total_output_bytes = sum(len(item) for item in images)
        peak_memory_bytes = max(total_output_bytes + len(source_bytes), width * height)
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

    @classmethod
    def _artifact_metadata(
        cls,
        *,
        job_id: str,
        artifact_id: str,
        role: int,
        mime_type: str,
        image_format: str,
        width: int,
        height: int,
        payload: bytes,
        storage_path: Path,
        variant_index: int,
        parent_artifact_id: str = "",
        ext: dict[str, str] | None = None,
    ) -> common_pb2.ImageArtifactMetadata:
        digest = hashlib.sha256(payload).hexdigest()
        return common_pb2.ImageArtifactMetadata(
            artifact_id=artifact_id,
            job_id=job_id,
            role=role,
            mime_type=mime_type,
            format=image_format,
            width=width,
            height=height,
            byte_length=len(payload),
            storage_uri=str(storage_path),
            sha256=digest,
            variant_index=variant_index,
            ext=ext or {},
            parent_artifact_id=parent_artifact_id,
        )

    @staticmethod
    def _write_bytes(path: Path, payload: bytes) -> float:
        started = time.monotonic()
        path.write_bytes(payload)
        return (time.monotonic() - started) * 1000.0

    @classmethod
    def _resolve_edit_input(
        cls,
        *,
        inline_bytes: bytes,
        uri: str,
        label: str,
    ) -> tuple[bytes, str]:
        if inline_bytes:
            return inline_bytes, "png"
        if uri:
            path = cls._path_from_uri(uri, label=label)
            return path.read_bytes(), cls._format_from_path(path)
        raise ValueError(f"No {label} provided.")

    @classmethod
    def _resolve_optional_edit_input(
        cls,
        *,
        inline_bytes: bytes,
        uri: str,
        label: str,
    ) -> tuple[bytes | None, str]:
        if inline_bytes:
            return inline_bytes, "png"
        if uri:
            path = cls._path_from_uri(uri, label=label)
            return path.read_bytes(), cls._format_from_path(path)
        return None, "png"

    @staticmethod
    def _lineage_ext(request, *, source_job_id: str) -> dict[str, str]:
        values: dict[str, str] = {}
        if request.source_artifact_id:
            values["melix.image.source_artifact_id"] = request.source_artifact_id
        if source_job_id:
            values["melix.image.source_job_id"] = source_job_id
        if request.prompt_delta:
            values["melix.image.prompt_delta"] = request.prompt_delta

        if request.edit_mode == inference_pb2.IMAGE_EDIT_MODE_VARIATION:
            values["melix.image.edit_mode"] = "variation"
        elif request.edit_mode == inference_pb2.IMAGE_EDIT_MODE_ITERATE:
            values["melix.image.edit_mode"] = "iterate"
        else:
            values["melix.image.edit_mode"] = "edit"
        return values

    @staticmethod
    def _path_from_uri(uri: str, *, label: str) -> Path:
        parsed = urlparse(uri)
        if parsed.scheme in {"", "file"}:
            candidate = Path(unquote(parsed.path)) if parsed.scheme == "file" else Path(uri)
            if not candidate.exists():
                raise ValueError(f"Missing local {label}: {uri}")
            return candidate
        raise ValueError(f"Unsupported {label} URI scheme: {parsed.scheme}")

    @classmethod
    def _format_from_path(cls, path: Path) -> str:
        suffix = path.suffix.lstrip(".").lower()
        return cls._normalized_format(suffix or "png")

    @staticmethod
    def _render_edit_payload(
        *,
        prompt: str,
        width: int,
        height: int,
        variant: int,
        model_id: str,
        strength: float,
        source_bytes: bytes,
        mask_bytes: bytes | None,
    ) -> bytes:
        source_digest = hashlib.sha256(source_bytes).hexdigest()[:12]
        mask_digest = hashlib.sha256(mask_bytes).hexdigest()[:12] if mask_bytes is not None else "none"
        payload = (
            f"MELIX_IMAGE_EDIT\n"
            f"MODEL={model_id}\n"
            f"PROMPT={prompt or '<empty>'}\n"
            f"SIZE={width}x{height}\n"
            f"VARIANT={variant}\n"
            f"STRENGTH={strength:.2f}\n"
            f"SOURCE_SHA={source_digest}\n"
            f"MASK_SHA={mask_digest}\n"
        ).encode("utf-8")
        return b"\x89PNG\r\n\x1a\n" + payload
