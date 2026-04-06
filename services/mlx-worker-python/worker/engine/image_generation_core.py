from __future__ import annotations

import time
from pathlib import Path

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry
from worker.runtime.deterministic_image_generation_runtime import ImageGenerationCancelled


class ImageGenerationCore:
    def __init__(self, registry: WorkerRegistry, images_root: Path | str) -> None:
        self._registry = registry
        self._images_root = Path(images_root)

    def generate(self, request: inference_pb2.ImageGenerateRequest) -> inference_pb2.ImageGenerateResponse:
        request_id = request.id.request_id
        job_id = f"{request_id}::image-generate"
        created_at_unix_ms = int(time.time() * 1000)

        loaded_model = self._registry.get_loaded_model(request.model_handle)
        if loaded_model is None:
            return self._failed_response(
                request=request,
                job_id=job_id,
                created_at_unix_ms=created_at_unix_ms,
                code="not_found",
                message="Unknown model handle.",
            )

        if loaded_model.runtime_kind != "image":
            return self._failed_response(
                request=request,
                job_id=job_id,
                created_at_unix_ms=created_at_unix_ms,
                code="invalid_argument",
                message="Loaded model does not support image generation.",
            )
        if _supports_image_generation(loaded_model.spec) is False:
            return self._failed_response(
                request=request,
                job_id=job_id,
                created_at_unix_ms=created_at_unix_ms,
                code="invalid_argument",
                message=f"Image model {loaded_model.spec.model_id} does not support generation workflows.",
            )

        state = self._registry.start_request(request_id, runtime_kind="image")
        try:
            result = self._registry.image_generation_runtime.generate_images(
                loaded_model.runtime_model,
                request,
                job_id=job_id,
                images_root=self._images_root,
                cancel_event=state.cancel_event,
            )
        except ImageGenerationCancelled as exc:
            return self._terminal_response(
                request=request,
                job_id=job_id,
                created_at_unix_ms=created_at_unix_ms,
                state=common_pb2.IMAGE_JOB_CANCELED,
                progress=common_pb2.ImageJobProgress(stage="canceled", pct=0.0),
                images=[],
                artifacts=[],
                error=common_pb2.ErrorStatus(code="cancelled", message=str(exc)),
            )
        except ValueError as exc:
            return self._failed_response(
                request=request,
                job_id=job_id,
                created_at_unix_ms=created_at_unix_ms,
                code="invalid_argument",
                message=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            return self._failed_response(
                request=request,
                job_id=job_id,
                created_at_unix_ms=created_at_unix_ms,
                code="runtime_error",
                message=str(exc),
            )
        finally:
            self._registry.finish_request(request_id)

        self._registry.record_image_probe(
            self._registry.image_generation_runtime.last_probe_snapshot()
        )
        return self._terminal_response(
            request=request,
            job_id=job_id,
            created_at_unix_ms=created_at_unix_ms,
            state=common_pb2.IMAGE_JOB_COMPLETED,
            progress=result.progress,
            images=result.images,
            artifacts=result.artifacts,
            error=common_pb2.ErrorStatus(),
        )

    def _failed_response(
        self,
        *,
        request: inference_pb2.ImageGenerateRequest,
        job_id: str,
        created_at_unix_ms: int,
        code: str,
        message: str,
    ) -> inference_pb2.ImageGenerateResponse:
        return self._terminal_response(
            request=request,
            job_id=job_id,
            created_at_unix_ms=created_at_unix_ms,
            state=common_pb2.IMAGE_JOB_FAILED,
            progress=common_pb2.ImageJobProgress(stage="failed", pct=0.0),
            images=[],
            artifacts=[],
            error=common_pb2.ErrorStatus(code=code, message=message),
        )

    @staticmethod
    def _terminal_response(
        *,
        request: inference_pb2.ImageGenerateRequest,
        job_id: str,
        created_at_unix_ms: int,
        state: int,
        progress: common_pb2.ImageJobProgress,
        images: list[bytes],
        artifacts,
        error: common_pb2.ErrorStatus,
    ) -> inference_pb2.ImageGenerateResponse:
        updated_at_unix_ms = int(time.time() * 1000)
        return inference_pb2.ImageGenerateResponse(
            images=images,
            error=error,
            job=inference_pb2.ImageJobDescriptor(
                request_id=request.id.request_id,
                job_id=job_id,
                model_handle=request.model_handle,
                operation="image_generate",
                state=state,
                progress=progress,
                artifacts=artifacts,
                error=error,
                cancelable=False,
                created_at_unix_ms=created_at_unix_ms,
                updated_at_unix_ms=updated_at_unix_ms,
            ),
        )


def _supports_image_generation(model_spec: common_pb2.ModelSpec) -> bool:
    ext = model_spec.ext
    raw = ext.get("melix.image.supports_generation", "").strip().lower()
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"false", "0", "no", "off"}:
        return False
    supported_tasks = {
        part.strip()
        for part in ext.get("melix.capability.supported_tasks", "").split(",")
        if part.strip()
    }
    if "image_generate" in supported_tasks:
        return True
    task_kind = ext.get("melix.image.task_kind", "").strip().lower()
    if task_kind == "image-text-to-image":
        return False
    return True
