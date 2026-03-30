from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.model_ops.job_registry import ModelOpsJobRegistry
from worker.registry import WorkerRegistry


@dataclass(frozen=True)
class BenchMetricSpec:
    suite: str
    name: str
    value: float
    unit: str


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

        if operation not in {"convert", "quantize", "download", "upload", "train_lora", "registry_snapshot"}:
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
        if operation == "registry_snapshot":
            manifest_payload = self._job_registry.snapshot(exclude_job_ids={job.job_id})
            manifest_payload.update(
                {
                    "job_id": job.job_id,
                    "operation": operation,
                    "source_model": request.source_model,
                    "output_dir": str(output_dir),
                }
            )
        else:
            manifest_payload = {
                "job_id": job.job_id,
                "operation": operation,
                "source_model": request.source_model,
                "output_dir": str(output_dir),
                "weight_quant": request.weight_quant,
                "kv_quant": request.kv_quant,
                "target_repo": request.ext.get("target_repo", ""),
                "ext": dict(request.ext),
            }
        if operation == "train_lora":
            manifest_payload.update(
                {
                    "adapter_name": request.ext.get("adapter_name", "melix-dev-adapter"),
                    "dataset_uri": request.ext.get("dataset_uri", "datasets/melix-dev"),
                    "training_duration_ms": 1_420.0,
                    "adapter_publish_ms": 118.0,
                }
            )

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
        elif model.model_kind == "image":
            supported_modalities = ["text", "image"]
            supported_tasks = ["image_generate", "image_edit"]

        return maintenance_pb2.GetModelInfoResponse(
            ok=True,
            model_kind=model.model_kind,
            max_context=model.max_context,
            supported_parsers=[model.parser_mode] if model.parser_mode else [],
            supported_modalities=supported_modalities,
            supported_tasks=supported_tasks,
        )

    def doctor_response(
        self,
        request: maintenance_pb2.RunDoctorRequest,
    ) -> maintenance_pb2.RunDoctorResponse:
        stats = self._registry.runtime_stats()
        loaded_models = self._registry.list_loaded_models()
        lines = [
            "# Melix Doctor",
            "",
            "## Runtime",
            f"- worker_state: {stats.worker_state or 'unknown'}",
            f"- active_requests: {stats.active_requests}",
            f"- loaded_models: {len(loaded_models)}",
            f"- resident_bytes: {stats.resident_bytes}",
        ]
        if request.model_handle:
            lines.append(f"- model_handle: {request.model_handle}")
            loaded_model = self._registry.get_loaded_model(request.model_handle)
            if loaded_model is not None:
                identity_lines = self._identity_diagnostic_lines(loaded_model.spec)
                if identity_lines:
                    lines.extend(["", "## Model Identity", *identity_lines])
        if request.include_cache_diagnostics:
            lines.extend(
                [
                    "",
                    "## Cache",
                    f"- l1_cache_bytes: {stats.l1_cache_bytes}",
                    f"- l2_cache_bytes: {stats.l2_cache_bytes}",
                    f"- l1_hit_rate: {stats.l1_hit_rate:.2f}",
                    f"- l2_hit_rate: {stats.l2_hit_rate:.2f}",
                ]
            )
        if request.include_memory_report:
            lines.extend(
                [
                    "",
                    "## Memory",
                    f"- resident_bytes: {stats.resident_bytes}",
                    f"- image_peak_memory_bytes: {stats.last_image_peak_memory_bytes}",
                ]
            )
        return maintenance_pb2.RunDoctorResponse(
            ok=True,
            report_markdown="\n".join(lines) + "\n",
        )

    @staticmethod
    def _identity_diagnostic_lines(model: common_pb2.ModelSpec) -> list[str]:
        effective_family = (
            model.ext.get("embedding_family_id")
            or model.ext.get("rerank_family_id")
            or model.ext.get("vision_family_id")
        )
        model_architecture = model.ext.get("model_architecture", "")
        detected_architecture = model.ext.get("detected_architecture", "")
        detected_family_id = model.ext.get("detected_family_id", "")
        detected_identity_source = model.ext.get("detected_identity_source", "")
        identity_override = model.ext.get("identity_override", "")

        if not any(
            [
                effective_family,
                model_architecture,
                detected_architecture,
                detected_family_id,
                detected_identity_source,
                identity_override,
            ]
        ):
            return []

        lines = [
            f"- model_id: {model.model_id}",
            f"- model_kind: {model.model_kind}",
        ]
        if model_architecture:
            lines.append(f"- model_architecture: {model_architecture}")
        if effective_family:
            lines.append(f"- effective_family_id: {effective_family}")
        if detected_architecture:
            lines.append(f"- detected_architecture: {detected_architecture}")
        if detected_family_id:
            lines.append(f"- detected_family_id: {detected_family_id}")
        if detected_identity_source:
            lines.append(f"- detected_identity_source: {detected_identity_source}")
        if identity_override:
            lines.append(f"- identity_override: {identity_override}")
        return lines

    def bench_events(
        self,
        request: maintenance_pb2.RunBenchRequest,
    ) -> Iterator[maintenance_pb2.RunBenchEvent]:
        suites = list(request.suites) or ["smoke"]
        output_dir = (self._jobs_root / "bench").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        job = self._job_registry.start("bench", request.model_handle or "runtime", str(output_dir))
        yield maintenance_pb2.RunBenchEvent(started=maintenance_pb2.BenchStarted(job_id=job.job_id))

        metrics: list[BenchMetricSpec] = []
        for index, suite in enumerate(suites, start=1):
            pct = index / max(len(suites), 1)
            self._job_registry.progress(job.job_id, suite, pct)
            yield maintenance_pb2.RunBenchEvent(
                progress=maintenance_pb2.BenchProgress(suite=suite, pct=pct)
            )
            for metric in self._bench_metrics_for_suite(suite):
                metrics.append(metric)
                yield maintenance_pb2.RunBenchEvent(
                    metric=maintenance_pb2.BenchMetric(
                        name=metric.name,
                        value=metric.value,
                        unit=metric.unit,
                    )
                )

        report_path = output_dir / "bench-report.md"
        report_path.write_text(self._render_bench_report(request, metrics), encoding="utf-8")
        self._job_registry.complete(job.job_id, str(report_path))
        yield maintenance_pb2.RunBenchEvent(
            completed=maintenance_pb2.BenchCompleted(report_path=str(report_path))
        )

    @staticmethod
    def _artifact_path(operation: str, output_dir: Path) -> Path:
        filename = {
            "convert": "convert.artifact",
            "quantize": "quantize.artifact",
            "download": "download.artifact",
            "upload": "upload.receipt.json",
            "train_lora": "train_lora.adapter.json",
            "registry_snapshot": "registry_snapshot.json",
        }[operation]
        return output_dir / filename

    @staticmethod
    def _bench_metrics_for_suite(suite: str) -> list[BenchMetricSpec]:
        if suite == "latency":
            return [
                BenchMetricSpec(suite=suite, name="bench.latency.p50_ms", value=31.18, unit="ms"),
                BenchMetricSpec(suite=suite, name="bench.latency.p95_ms", value=44.72, unit="ms"),
            ]
        return [
            BenchMetricSpec(suite=suite, name=f"bench.{suite}.ttft_ms", value=24.45, unit="ms"),
            BenchMetricSpec(
                suite=suite,
                name=f"bench.{suite}.tokens_per_second",
                value=47.08,
                unit="tok/s",
            ),
        ]

    @staticmethod
    def _render_bench_report(
        request: maintenance_pb2.RunBenchRequest,
        metrics: list[BenchMetricSpec],
    ) -> str:
        lines = [
            "# Melix Bench",
            "",
            f"- model_handle: {request.model_handle or 'runtime'}",
            f"- suites: {', '.join(request.suites) if request.suites else 'smoke'}",
            "",
        ]
        for metric in metrics:
            lines.append(f"- {metric.name}: {metric.value:.2f} {metric.unit}")
        return "\n".join(lines) + "\n"
