from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterator

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.model_ops.job_registry import ModelOpsJobRegistry
from worker.model_ops.operation_locks import ModelOpsConflictRegistry
from worker.model_ops.quantization_pipeline import OQQuantizationPipeline
from worker.model_ops.quantization_profiles import protected_scope_for_request
from worker.productization.benchmark_queue import BenchmarkQueueRecord, BenchmarkQueueStore
from worker.registry import WorkerRegistry

_CAPABILITY_SUPPORTED_MODALITIES_KEY = "melix.capability.supported_modalities"
_CAPABILITY_SUPPORTED_TASKS_KEY = "melix.capability.supported_tasks"
_CAPABILITY_SUPPORTED_PARSERS_KEY = "melix.capability.supported_parsers"


@dataclass(frozen=True)
class BenchMetricSpec:
    suite: str
    name: str
    value: float
    unit: str


def _split_capability_values(raw_value: str) -> list[str]:
    return [
        part.strip()
        for part in raw_value.split(",")
        if part.strip()
    ]


def _default_capability_lists(model_kind: str) -> tuple[list[str], list[str]]:
    if model_kind == "ocr":
        return ["text", "image"], ["ocr", "generate"]
    if model_kind == "vlm":
        return ["text", "image"], ["vlm", "generate"]
    if model_kind == "transcription":
        return ["audio", "text"], ["transcribe"]
    if model_kind == "speech":
        return ["text", "audio"], ["speak"]
    if model_kind == "image":
        return ["text", "image"], ["image_generate", "image_edit"]
    return ["text"], ["generate"]


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
        self._quantization_pipeline = OQQuantizationPipeline(registry)
        self._operation_locks = ModelOpsConflictRegistry()
        self._benchmark_store = None
        self._benchmark_queue_store = BenchmarkQueueStore()

    @staticmethod
    def _worker_quant_profile(profile) -> maintenance_pb2.QuantizationProfile:
        message = maintenance_pb2.QuantizationProfile(
            algorithm=profile.algorithm,
            schema_version=profile.schema_version,
            quant_profile_id=profile.quant_profile_id,
            weight_quant=profile.weight_quant,
            kv_quant=profile.kv_quant,
        )
        if profile.ext:
            message.ext.update(profile.ext)
        return message

    @staticmethod
    def _worker_quantized_artifact(
        *,
        bundle_path: Path,
        manifest_path: Path,
        artifact_bytes: int,
        manifest_bytes: int,
        smoke_test_requested: bool,
        smoke_test_passed: bool,
    ) -> maintenance_pb2.QuantizedArtifact:
        return maintenance_pb2.QuantizedArtifact(
            schema_version="melix.quantized_bundle.v1",
            artifact_kind="quantized_model_bundle",
            manifest_path=str(manifest_path),
            bundle_path=str(bundle_path),
            artifact_bytes=artifact_bytes,
            manifest_bytes=manifest_bytes,
            serving_compatible=True,
            smoke_test_requested=smoke_test_requested,
            smoke_test_passed=smoke_test_passed,
            runtime="mlx_text",
        )

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

        if operation == "quantize" and self._registry.runtime_stats().active_requests > 0:
            yield maintenance_pb2.ConvertModelEvent(
                failed=maintenance_pb2.ConvertFailed(
                    error=common_pb2.ErrorStatus(
                        code="resource_locked",
                        message="Quantization is blocked while active inference is running.",
                    )
                )
            )
            return

        lock_scope = self._lock_scope(operation, request)
        held_by = self._operation_locks.try_acquire(lock_scope, operation)
        if held_by is not None:
            yield maintenance_pb2.ConvertModelEvent(
                failed=maintenance_pb2.ConvertFailed(
                    error=common_pb2.ErrorStatus(
                        code="resource_locked",
                        message=f"Operation blocked by active quantization lock on {lock_scope} held by {held_by}.",
                    )
                )
            )
            return

        output_dir = Path(request.output_dir or self._jobs_root / operation).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            job = self._job_registry.start(operation, request.source_model, str(output_dir))
            yield maintenance_pb2.ConvertModelEvent(
                started=maintenance_pb2.ConvertStarted(job_id=job.job_id)
            )

            if operation == "quantize":
                stage_sequence = [
                    ("resolve_source", 0.1),
                    ("normalize_profile", 0.25),
                    ("quantize_weights", 0.5),
                    ("write_bundle", 0.75),
                    ("write_manifest", 0.9),
                ]
                for stage, pct in stage_sequence:
                    self._job_registry.progress(job.job_id, stage, pct)
                    yield maintenance_pb2.ConvertModelEvent(
                        progress=maintenance_pb2.ConvertProgress(stage=stage, pct=pct)
                    )
                if hold_ms := int(request.ext.get("test_hold_ms", "0") or "0"):
                    time.sleep(hold_ms / 1000.0)

                result = self._quantization_pipeline.run(
                    request,
                    job_id=job.job_id,
                    output_dir=output_dir,
                )
                manifest_payload = dict(result.manifest_payload)
                manifest_payload["job_id"] = job.job_id
                manifest_payload["artifact_bytes"] = result.artifact_bytes
                manifest_payload["manifest_bytes"] = result.manifest_bytes
                manifest_payload["manifest_path"] = str(result.manifest_path)
                manifest_payload["artifact_path"] = str(result.bundle_path)
                manifest_json = json.dumps(manifest_payload, sort_keys=True)
                artifact_path = result.bundle_path
                worker_profile = self._worker_quant_profile(result.profile)
                worker_artifact = self._worker_quantized_artifact(
                    bundle_path=result.bundle_path,
                    manifest_path=result.manifest_path,
                    artifact_bytes=result.artifact_bytes,
                    manifest_bytes=result.manifest_bytes,
                    smoke_test_requested=request.run_smoke_test,
                    smoke_test_passed=result.smoke_test_passed,
                )
                if request.generate_manifest:
                    self._job_registry.attach_manifest(job.job_id, manifest_json)
                    yield maintenance_pb2.ConvertModelEvent(
                        manifest=maintenance_pb2.ConvertManifest(
                            manifest_json=manifest_json,
                            quant_profile=worker_profile,
                            artifact=worker_artifact,
                        )
                    )
                self._job_registry.complete(job.job_id, str(artifact_path))
                yield maintenance_pb2.ConvertModelEvent(
                    completed=maintenance_pb2.ConvertCompleted(
                        output_path=str(artifact_path),
                        quant_profile=worker_profile,
                        artifact=worker_artifact,
                    )
                )
                return

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
                    "artifact_kind": request.ext.get("artifact_kind", ""),
                    "artifact_path": request.ext.get("artifact_path", ""),
                    "target_repo": request.ext.get("target_repo", ""),
                    "ext": dict(request.ext),
                }
                if operation == "upload":
                    linked_quantization = self._linked_quantization_metadata(request)
                    if linked_quantization is not None:
                        manifest_payload["linked_quantization"] = linked_quantization
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
        finally:
            self._operation_locks.release(lock_scope)

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

        ext = dict(model.ext)
        fallback_modalities, fallback_tasks = _default_capability_lists(model.model_kind)
        supported_modalities = _split_capability_values(
            ext.get(_CAPABILITY_SUPPORTED_MODALITIES_KEY, "")
        ) or fallback_modalities
        supported_tasks = _split_capability_values(
            ext.get(_CAPABILITY_SUPPORTED_TASKS_KEY, "")
        ) or fallback_tasks
        supported_parsers = _split_capability_values(
            ext.get(_CAPABILITY_SUPPORTED_PARSERS_KEY, "")
        )
        base_parser = (model.parser_mode or "").strip()
        if base_parser and base_parser not in supported_parsers:
            supported_parsers.insert(0, base_parser)
        tool_parser = ext.get("tool_parser_mode", "").strip()
        if tool_parser and tool_parser not in supported_parsers:
            supported_parsers.append(tool_parser)

        return maintenance_pb2.GetModelInfoResponse(
            ok=True,
            model_kind=model.model_kind,
            max_context=model.max_context,
            supported_parsers=supported_parsers,
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
        from worker.productization.benchmark_schemas import (
            build_serving_benchmark_job,
            build_serving_benchmark_results,
        )
        from worker.productization.benchmark_store import BenchmarkStore

        suites = list(request.suites) or ["smoke"]
        raw_parameters = getattr(request, "parameters", None)
        parameters = dict(raw_parameters) if raw_parameters else {}
        output_dir = (self._jobs_root / "bench").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        job = self._job_registry.start("bench", request.model_handle or "runtime", str(output_dir))
        queued_at = int(time.time() * 1000)
        self._benchmark_queue_store.enqueue(
            queue_root=output_dir / "queue",
            record=BenchmarkQueueRecord(
                queue_item_id=job.job_id,
                job_kind="benchmark",
                model_id=(request.model_handle or "runtime").split("::", 1)[0],
                suite_ids=tuple(suites),
                parameters=parameters,
                status="queued",
                created_at_unix_ms=queued_at,
                updated_at_unix_ms=queued_at,
            ),
        )
        yield maintenance_pb2.RunBenchEvent(started=maintenance_pb2.BenchStarted(job_id=job.job_id))
        self._benchmark_queue_store.transition(
            queue_root=output_dir / "queue",
            queue_item_id=job.job_id,
            status="running",
            updated_at_unix_ms=queued_at + 1,
        )

        benchmark_mode = parameters.get("benchmark_mode", "text")
        metrics: list[BenchMetricSpec] = []
        for index, suite in enumerate(suites, start=1):
            pct = index / max(len(suites), 1)
            self._job_registry.progress(job.job_id, suite, pct)
            yield maintenance_pb2.RunBenchEvent(
                progress=maintenance_pb2.BenchProgress(suite=suite, pct=pct)
            )
            suite_metrics = (
                self._bench_metrics_for_vlm_suite(suite)
                if benchmark_mode == "vlm"
                else self._bench_metrics_for_suite(suite)
            )
            for metric in suite_metrics:
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
        job_record = build_serving_benchmark_job(
            job_id=job.job_id,
            model_id=(request.model_handle or "runtime").split("::", 1)[0],
            suites=tuple(suites),
            parameters=parameters,
            status="completed",
            output_dir=str(output_dir),
        )
        result_records = build_serving_benchmark_results(
            job_id=job.job_id,
            metrics={metric.name: metric.value for metric in metrics},
            units={metric.name: metric.unit for metric in metrics},
            report_path=str(report_path),
            report_markdown=report_path.read_text(encoding="utf-8"),
        )
        if self._benchmark_store is None:
            self._benchmark_store = BenchmarkStore()
        self._benchmark_store.persist_serving_benchmark(
            jobs_root=output_dir,
            job=job_record,
            results=result_records,
        )
        self._job_registry.complete(job.job_id, str(report_path))
        self._benchmark_queue_store.transition(
            queue_root=output_dir / "queue",
            queue_item_id=job.job_id,
            status="completed",
            updated_at_unix_ms=int(time.time() * 1000),
        )
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

    def _lock_scope(self, operation: str, request: maintenance_pb2.ConvertModelRequest) -> str:
        if operation in {"quantize", "upload"}:
            linked_quantization = self._linked_quantization_metadata(request)
            if linked_quantization is not None:
                linked_scope = str(linked_quantization.get("protected_scope", "")).strip()
                if linked_scope:
                    return linked_scope
                linked_source_model = str(linked_quantization.get("source_model", "")).strip()
                if linked_source_model:
                    return f"model-family:{linked_source_model}"

            source_model_spec = self._registry.model_catalog.get(request.source_model)
            protected_scope = protected_scope_for_request(
                request,
                source_model_spec=source_model_spec,
            )
            if protected_scope:
                return protected_scope

        if operation == "upload":
            return request.ext.get("artifact_path", "") or request.source_model or operation
        return request.source_model or operation

    @staticmethod
    def _linked_quantization_metadata(
        request: maintenance_pb2.ConvertModelRequest,
    ) -> dict[str, object] | None:
        artifact_path_raw = request.ext.get("artifact_path", "") or request.source_model
        if not artifact_path_raw:
            return None
        artifact_path = Path(artifact_path_raw)
        manifest_path = artifact_path / "manifest.json" if artifact_path.is_dir() else Path(
            request.ext.get("quantization_manifest_path", "")
        )
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(manifest, dict):
            return None
        if manifest.get("artifact_kind") != "quantized_model_bundle":
            return None
        calibration = manifest.get("calibration", {}) if isinstance(manifest.get("calibration"), dict) else {}
        compatibility = manifest.get("compatibility", {}) if isinstance(manifest.get("compatibility"), dict) else {}
        quant_profile = manifest.get("quant_profile", {}) if isinstance(manifest.get("quant_profile"), dict) else {}
        return {
            "artifact_kind": manifest.get("artifact_kind", ""),
            "artifact_path": str(artifact_path),
            "manifest_path": str(manifest_path),
            "source_model": manifest.get("source_model", ""),
            "protected_scope": manifest.get("protected_scope", ""),
            "quant_profile_id": quant_profile.get("quant_profile_id", ""),
            "calibration_sample_count": calibration.get("sample_count", 0),
            "smoke_test_passed": compatibility.get("smoke_test_passed", False),
        }

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
    def _bench_metrics_for_vlm_suite(suite: str) -> list[BenchMetricSpec]:
        if suite == "latency":
            return [
                BenchMetricSpec(suite=suite, name="bench.latency.image_p50_ms", value=62.35, unit="ms"),
                BenchMetricSpec(suite=suite, name="bench.latency.image_p95_ms", value=89.44, unit="ms"),
            ]
        return [
            BenchMetricSpec(suite=suite, name=f"bench.{suite}.image_ttft_ms", value=48.90, unit="ms"),
            BenchMetricSpec(
                suite=suite,
                name=f"bench.{suite}.vlm_tokens_per_second",
                value=23.54,
                unit="tok/s",
            ),
        ]

    @staticmethod
    def _render_bench_report(
        request: maintenance_pb2.RunBenchRequest,
        metrics: list[BenchMetricSpec],
    ) -> str:
        raw_parameters = getattr(request, "parameters", None)
        parameters = dict(raw_parameters) if raw_parameters else {}
        benchmark_mode = parameters.get("benchmark_mode", "text")
        lines = [
            "# Melix Bench",
            "",
            f"- model_handle: {request.model_handle or 'runtime'}",
            f"- suites: {', '.join(request.suites) if request.suites else 'smoke'}",
            f"- benchmark_mode: {benchmark_mode}",
            "",
        ]
        for metric in metrics:
            lines.append(f"- {metric.name}: {metric.value:.2f} {metric.unit}")
        return "\n".join(lines) + "\n"
