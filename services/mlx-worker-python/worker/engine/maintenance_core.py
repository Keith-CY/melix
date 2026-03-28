from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.model_ops.job_registry import ModelOpsJobRegistry
from worker.registry import WorkerRegistry


class MaintenanceCore:
    def __init__(
        self,
        registry: WorkerRegistry,
        jobs_root: Path,
        job_registry: ModelOpsJobRegistry | None = None,
    ) -> None:
        self._registry = registry
        self._jobs_root = Path(jobs_root)
        self._job_registry = job_registry or ModelOpsJobRegistry()

    def convert_model(
        self,
        request: maintenance_pb2.ConvertModelRequest,
    ) -> Iterator[maintenance_pb2.ConvertModelEvent]:
        operation = request.ext.get("operation")
        if not operation:
            operation = "quantize" if request.weight_quant or request.kv_quant else "convert"

        if operation not in {"convert", "quantize", "download", "upload"}:
            yield maintenance_pb2.ConvertModelEvent(
                failed=maintenance_pb2.ConvertFailed(
                    error=common_pb2.ErrorStatus(
                        code="invalid_argument",
                        message=f"Unsupported model operation: {operation}",
                    )
                )
            )
            return

        output_dir = Path(request.output_dir or self._jobs_root / operation).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        job = self._job_registry.start(operation, request.source_model, str(output_dir))
        yield maintenance_pb2.ConvertModelEvent(
            started=maintenance_pb2.ConvertStarted(job_id=job.job_id)
        )

        self._job_registry.progress(job.job_id, "prepare", 0.25)
        yield maintenance_pb2.ConvertModelEvent(
            progress=maintenance_pb2.ConvertProgress(stage="prepare", pct=0.25)
        )

        artifact_path = self._artifact_path(operation, output_dir)
        manifest_payload = {
            "job_id": job.job_id,
            "operation": operation,
            "source_model": request.source_model,
            "output_dir": str(output_dir),
            "weight_quant": request.weight_quant,
            "kv_quant": request.kv_quant,
            "target_repo": request.ext.get("target_repo", ""),
        }

        artifact_path.write_text(json.dumps(manifest_payload, indent=2) + "\n")

        self._job_registry.progress(job.job_id, "write_artifact", 0.75)
        yield maintenance_pb2.ConvertModelEvent(
            progress=maintenance_pb2.ConvertProgress(stage="write_artifact", pct=0.75)
        )

        if request.generate_manifest:
            manifest_json = json.dumps(manifest_payload, sort_keys=True)
            self._job_registry.attach_manifest(job.job_id, manifest_json)
            yield maintenance_pb2.ConvertModelEvent(
                manifest=maintenance_pb2.ConvertManifest(manifest_json=manifest_json)
            )

        self._job_registry.complete(job.job_id, str(artifact_path))
        yield maintenance_pb2.ConvertModelEvent(
            completed=maintenance_pb2.ConvertCompleted(output_path=str(artifact_path))
        )

    def get_model_info(
        self,
        request: maintenance_pb2.GetModelInfoRequest,
    ) -> maintenance_pb2.GetModelInfoResponse:
        model = self._registry.model_catalog.get(request.source_model)
        if model is None:
            return maintenance_pb2.GetModelInfoResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown source model."),
            )

        supported_modalities = ["text"]
        supported_tasks = ["generate"]
        if model.model_kind == "ocr":
            supported_modalities = ["text", "image"]
            supported_tasks = ["ocr", "generate"]
        elif model.model_kind == "vlm":
            supported_modalities = ["text", "image"]
            supported_tasks = ["vlm", "generate"]
        elif model.model_kind == "transcription":
            supported_modalities = ["audio", "text"]
            supported_tasks = ["transcribe"]
        elif model.model_kind == "speech":
            supported_modalities = ["text", "audio"]
            supported_tasks = ["speak"]

        return maintenance_pb2.GetModelInfoResponse(
            ok=True,
            model_kind=model.model_kind,
            max_context=model.max_context,
            supported_parsers=[model.parser_mode] if model.parser_mode else [],
            supported_modalities=supported_modalities,
            supported_tasks=supported_tasks,
        )

    @staticmethod
    def doctor_response() -> maintenance_pb2.RunDoctorResponse:
        return maintenance_pb2.RunDoctorResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Doctor is deferred in phase 5."),
        )

    @staticmethod
    def bench_events() -> Iterator[maintenance_pb2.RunBenchEvent]:
        yield maintenance_pb2.RunBenchEvent(
            failed=maintenance_pb2.BenchFailed(
                error=common_pb2.ErrorStatus(code="unimplemented", message="Bench is deferred in phase 5.")
            )
        )

    @staticmethod
    def _artifact_path(operation: str, output_dir: Path) -> Path:
        filename = {
            "convert": "convert.artifact",
            "quantize": "quantize.artifact",
            "download": "download.artifact",
            "upload": "upload.receipt.json",
        }[operation]
        return output_dir / filename
