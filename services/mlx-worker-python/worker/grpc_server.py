from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from concurrent import futures
from pathlib import Path
from typing import Any

import grpc

from packages.protocol.python.worker.v1 import (
    cache_pb2,
    cache_pb2_grpc,
    common_pb2,
    inference_pb2,
    inference_pb2_grpc,
    maintenance_pb2,
    maintenance_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)

from worker.engine.embedding_core import EmbeddingCore
from worker.engine.image_edit_core import ImageEditCore
from worker.engine.engine_core import EngineCore
from worker.engine.evaluation_core import EvaluationCore
from worker.engine.image_generation_core import ImageGenerationCore
from worker.engine.maintenance_core import MaintenanceCore
from worker.engine.rerank_core import RerankCore
from worker.engine.speech_core import SpeechCore
from worker.engine.transcription_core import TranscriptionCore
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.hub_catalog import HubCatalog
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog
from worker.productization.evaluation_final_result import (
    EvaluationFieldMapping,
    EvaluationMaterializationRequest,
    EvaluationProfileDefinition,
    HFEvaluationDatasetFetcher,
    HFEvaluationDatasetSource,
    materialize_hf_evaluation_dataset,
    materialize_local_evaluation_dataset,
)
from worker.registry import DiskStreamingUnsupported, MemoryBudgetExceeded, WorkerRegistry
from worker.runtime.audio_runtime_protocols import AudioBackendUnavailableError, AudioProcessorValidationError
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.productization.benchmark_export import write_export_bundle
from worker.productization.device_identity import collect_device_identity
from worker.productization.submission_builder import build_submission_payload


class BootstrapMetricsExporter:
    def __init__(self, export_path: str | None) -> None:
        self._export_path = Path(export_path).resolve() if export_path else None
        self._values: dict[str, int] = {
            "python_worker.spawn_to_bootstrap_ms": 0,
            "python_worker.arg_parse_ms": 0,
            "python_worker.registry_init_ms": 0,
            "python_worker.server_build_ms": 0,
            "python_worker.server_start_ms": 0,
            "python_worker.bootstrap_ms": 0,
        }
        self._write()

    def set_milliseconds(self, key: str, value: float) -> None:
        self._values[key] = max(0, int(round(value)))
        self._write()

    def _write(self) -> None:
        if self._export_path is None:
            return

        self._export_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "updated_at_unix_ms": int(time.time() * 1000),
            "values": self._values,
        }
        _write_json_atomically(self._export_path, payload)


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            json.dump(payload, temp_file, sort_keys=True)
        os.replace(os.fspath(temp_path), os.fspath(path))
    finally:
        temp_path.unlink(missing_ok=True)


class WorkerRuntimeService(runtime_pb2_grpc.RuntimeServiceServicer):
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def Handshake(self, request, context):
        return runtime_pb2.HandshakeResponse(
            protocol_version=request.protocol_version,
            runtime_version=self._registry.runtime.runtime_name,
            capabilities=self._registry.capabilities(),
        )

    def LoadModel(self, request, context):
        try:
            loaded = self._registry.load_model(
                request.model,
                pin_on_load=request.pin_on_load,
                memory_budget_bytes=request.memory_budget_bytes,
                disk_streaming_mode=request.disk_streaming_mode,
            )
        except MemoryBudgetExceeded as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="memory_budget_exceeded",
                    message=str(exc),
                    details=exc.details,
                ),
            )
        except DiskStreamingUnsupported as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="disk_streaming_unsupported",
                    message=str(exc),
                    details=exc.details,
                ),
            )
        except AudioBackendUnavailableError as exc:
            self._registry.increment_audio_backend_unavailable()
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="unavailable", message=str(exc)),
            )
        except AudioProcessorValidationError as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="audio_processor_validation_failed",
                    message=str(exc),
                    details=exc.details,
                ),
            )
        except Exception as exc:
            is_real_audio_backend = (
                request.model.model_kind in {"transcription", "speech"}
                and request.model.ext.get("melix.audio.backend_id", "").startswith("mlx_audio.")
            )
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="runtime_error" if is_real_audio_backend else "load_failed",
                    message=str(exc),
                ),
            )
        if request.warmup_after_load:
            warmup_error = None
            try:
                warmup_ms = self._registry.warmup_model(loaded.handle)
                if warmup_ms is None:
                    raise RuntimeError(
                        f"warmup_model returned None for freshly loaded handle {loaded.handle}"
                    )
            except NotImplementedError as exc:
                warmup_error = common_pb2.ErrorStatus(code="unimplemented", message=str(exc))
            except Exception as exc:
                warmup_error = common_pb2.ErrorStatus(code="warmup_failed", message=str(exc))
            if warmup_error is not None:
                self._registry.unload_model(loaded.handle)
                return runtime_pb2.LoadModelResponse(ok=False, error=warmup_error)
        response = runtime_pb2.LoadModelResponse(
            ok=True,
            model_handle=loaded.handle,
            estimated_resident_bytes=loaded.estimated_resident_bytes,
            resolved_capabilities=self._registry.capabilities(),
        )
        response.residency.CopyFrom(loaded.residency)
        return response

    def UnloadModel(self, request, context):
        found = self._registry.unload_model(request.model_handle)
        return runtime_pb2.UnloadModelResponse(
            ok=found,
            error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle.") if not found else None,
        )

    def WarmupModel(self, request, context):
        try:
            warmup_ms = self._registry.warmup_model(request.model_handle, request.synthetic_messages)
        except NotImplementedError as exc:
            return runtime_pb2.WarmupModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="unimplemented", message=str(exc)),
            )
        except Exception as exc:
            return runtime_pb2.WarmupModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="warmup_failed", message=str(exc)),
            )
        if warmup_ms is None:
            return runtime_pb2.WarmupModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle."),
            )
        return runtime_pb2.WarmupModelResponse(ok=True, warmup_ms=warmup_ms)

    def GetRuntimeStats(self, request, context):
        return runtime_pb2.GetRuntimeStatsResponse(stats=self._registry.runtime_stats())

    def ListLoadedModels(self, request, context):
        return runtime_pb2.ListLoadedModelsResponse(
            model_handles=self._registry.list_loaded_models(),
            loaded_models=self._registry.list_loaded_model_summaries(),
        )

    def Drain(self, request, context):
        self._registry.set_draining(request.stop_accepting_new)
        return runtime_pb2.DrainResponse(ok=True)

    def Shutdown(self, request, context):
        return runtime_pb2.ShutdownResponse(ok=True)


class WorkerInferenceService(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(self, registry: WorkerRegistry, images_root: Path | str | None = None) -> None:
        self._registry = registry
        self._engine = EngineCore(registry)
        self._embedding = EmbeddingCore(registry)
        self._rerank = RerankCore(registry)
        self._transcription = TranscriptionCore(registry)
        self._speech = SpeechCore(registry)
        self._image_generation = ImageGenerationCore(registry, images_root=Path(images_root or ".runtime/images"))
        self._image_edit = ImageEditCore(registry, images_root=Path(images_root or ".runtime/images"))

    def Generate(self, request, context):
        yield from self._engine.generate(request)

    def Prefill(self, request, context):
        return self._engine.prefill(request)

    def Decode(self, request, context):
        yield from self._engine.decode(request)

    def Abort(self, request, context):
        found = self._engine.abort(request.request_id)
        return inference_pb2.AbortResponse(ok=found, found=found)

    def Embed(self, request, context):
        return self._embedding.embed(request)

    def Rerank(self, request, context):
        return self._rerank.rerank(request)

    def Transcribe(self, request, context):
        return self._transcription.transcribe(request)

    def Speak(self, request, context):
        return self._speech.speak(request)

    def ImageGenerate(self, request, context):
        return self._image_generation.generate(request)

    def ImageEdit(self, request, context):
        return self._image_edit.edit(request)


class WorkerMaintenanceService(maintenance_pb2_grpc.MaintenanceServiceServicer):
    def __init__(
        self,
        registry: WorkerRegistry,
        jobs_root: Path | str | None = None,
        evaluation_jobs_root: Path | str | None = None,
        evaluation_core: EvaluationCore | None = None,
        hub_catalog: HubCatalog | None = None,
        lora_training_pipeline: LoRATrainingPipeline | None = None,
        adapter_activation_pipeline: AdapterActivationPipeline | None = None,
        benchmark_suite_catalog: BenchmarkSuiteCatalog | None = None,
        evaluation_hf_dataset_fetcher: HFEvaluationDatasetFetcher | None = None,
    ) -> None:
        root = Path(jobs_root or ".runtime/model-ops")
        self._core = MaintenanceCore(
            registry,
            jobs_root=root,
            hub_catalog=hub_catalog,
            lora_training_pipeline=lora_training_pipeline,
            adapter_activation_pipeline=adapter_activation_pipeline,
            benchmark_suite_catalog=benchmark_suite_catalog,
        )
        self._evaluation_jobs_root = Path(evaluation_jobs_root or root / "evaluation").resolve()
        # Stage the evaluation runner at service construction time so the later RPC path
        # can reuse the same file-backed jobs root without additional wiring changes.
        self._evaluation_core = evaluation_core or EvaluationCore(
            jobs_root=self._evaluation_jobs_root,
            registry=registry,
        )
        self._evaluation_hf_dataset_fetcher = evaluation_hf_dataset_fetcher

    def ConvertModel(self, request, context):
        yield from self._core.convert_model(request)

    def GetModelInfo(self, request, context):
        return self._core.get_model_info(request)

    def RunDoctor(self, request, context):
        return self._core.doctor_response(request)

    def SearchHubModels(self, request, context):
        return self._core.search_hub_models(request)

    def GetHubModelCard(self, request, context):
        return self._core.get_hub_model_card(request)

    def RunBench(self, request, context):
        yield from self._core.bench_events(request)

    def RunBenchMatrix(self, request, context):
        _ = context
        return self._core.bench_matrix_response(request)

    def RunEvaluation(self, request, context):
        try:
            parameters = dict(request.parameters)
            parameters.setdefault("dataset_id", request.dataset_id)
            if request.task_kind:
                parameters.setdefault("task_kind", request.task_kind)
            if request.source_repo:
                parameters.setdefault("source_repo", request.source_repo)
            scoring_mode = request.scoring_mode or request.profile.scoring_mode
            if scoring_mode == "event_extraction_weighted_f1":
                source_kind = request.source.WhichOneof("kind")
                if source_kind != "local_jsonl":
                    raise ValueError("event_extraction_weighted_f1 requires --source-jsonl.")
                parameters.setdefault("event_source_jsonl", request.source.local_jsonl.path)
                parameters.setdefault("evaluation_source_kind", "jsonl")
                parameters.setdefault("evaluation_source_locator", request.source.local_jsonl.path)
                dataset_root = self._evaluation_materialization_root()
            else:
                dataset_root = self._resolve_evaluation_dataset_root(request, parameters)
            run = self._evaluation_core.run_local_suite(
                model_id=request.model_handle.split("::", 1)[0] if request.model_handle else "melix-dev-text",
                model_handle=request.model_handle or None,
                suite_id=request.suite_id,
                dataset_root=dataset_root,
                sample_size=request.sample_size,
                few_shot=int(request.few_shot) if request.few_shot else None,
                seed=int(request.seed) if request.seed else None,
                scoring_mode=request.scoring_mode or None,
                code_exec_policy=request.code_exec_policy or None,
                parameters=parameters,
                remote_target=request.remote_target if request.remote_target.remote_server_id else None,
            )
        except ValueError as exc:
            return maintenance_pb2.RunEvaluationResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="invalid_argument", message=str(exc)),
            )
        except Exception as exc:
            return maintenance_pb2.RunEvaluationResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="evaluation_failed", message=str(exc)),
            )

        response = maintenance_pb2.RunEvaluationResponse(ok=True)
        response.job.schema_version = run.job.schema_version
        response.job.job_id = run.job.job_id
        response.job.model_id = getattr(run.job, "model_id", getattr(run.job, "base_model_id", ""))
        response.job.task_kind = run.job.task_kind
        response.job.source_repo = run.job.source_repo
        response.job.suite_id = run.job.suite_id
        response.job.dataset_id = run.job.dataset_id
        response.job.sample_size = run.job.sample_size
        response.job.scoring_mode = run.job.scoring_mode
        response.job.parameters.update(run.job.parameters)
        response.job.status = run.job.status
        response.job.output_dir = run.job.output_dir
        response.job.created_at_unix_ms = run.job.created_at_unix_ms
        response.job.updated_at_unix_ms = run.job.updated_at_unix_ms

        for run_result in run.results:
            result = response.results.add()
            result.schema_version = run_result.schema_version
            result.job_id = run_result.job_id
            target_model_id = getattr(run_result, "target_model_id", "")
            result.suite_id = (
                f"{run_result.suite_id}:{target_model_id}"
                if target_model_id
                else run_result.suite_id
            )
            result.dataset_id = run_result.dataset_id
            result.sample_size = run_result.sample_size
            result.report_path = run_result.report_path
            for metric in run_result.metrics:
                metric_message = result.metrics.add()
                metric_message.name = metric.name
                metric_message.value = metric.value
                metric_message.unit = metric.unit
        return response

    def ExportResults(self, request, context):
        try:
            jobs_root = Path(request.output_dir) if request.output_dir else self._evaluation_jobs_root.parent
            export_path = jobs_root / "export-bundle.json"
            bundle_path = write_export_bundle(jobs_root, export_path)
            export_json = bundle_path.read_text(encoding="utf-8")
            return maintenance_pb2.ExportResultsResponse(
                ok=True,
                export_json=export_json,
                export_path=str(bundle_path),
            )
        except Exception as exc:
            return maintenance_pb2.ExportResultsResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="export_failed", message=str(exc)),
            )

    def SubmitResults(self, request, context):
        try:
            jobs_root = Path(request.output_dir) if request.output_dir else self._evaluation_jobs_root.parent
            submission = build_submission_payload(
                jobs_root,
                _device_identity_from_metadata(request.device_metadata),
            )
            submission_json = json.dumps(submission.to_dict(), indent=2)
            return maintenance_pb2.SubmitResultsResponse(
                ok=True,
                submission_json=submission_json,
            )
        except Exception as exc:
            return maintenance_pb2.SubmitResultsResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="submit_failed", message=str(exc)),
            )

    @staticmethod
    def _default_dataset_root(dataset_id: str) -> Path:
        return (
            Path.cwd()
            / "services"
            / "mlx-worker-python"
            / "fixtures"
            / "evaluation"
            / dataset_id
        ).resolve()

    def _resolve_evaluation_dataset_root(
        self,
        request,
        parameters: dict[str, str],
    ) -> Path:
        source_kind = request.source.WhichOneof("kind")
        if source_kind == "local_csv":
            source_path = request.source.local_csv.path
            materialized = materialize_local_evaluation_dataset(
                request=EvaluationMaterializationRequest(
                    source_kind="csv",
                    source_path=Path(source_path),
                    profile=self._evaluation_profile_from_request(request),
                    field_mapping=self._evaluation_field_mapping_from_request(request),
                    dataset_id=request.dataset_id,
                    suite_id=request.suite_id,
                ),
                cache_root=self._evaluation_materialization_root(),
            )
            parameters.setdefault("evaluation_source_kind", "csv")
            parameters.setdefault("evaluation_source_locator", source_path)
            parameters.setdefault("evaluation_materialized_dataset_root", str(materialized.package_path))
            return materialized.package_path

        if source_kind == "local_jsonl":
            source_path = request.source.local_jsonl.path
            materialized = materialize_local_evaluation_dataset(
                request=EvaluationMaterializationRequest(
                    source_kind="jsonl",
                    source_path=Path(source_path),
                    profile=self._evaluation_profile_from_request(request),
                    field_mapping=self._evaluation_field_mapping_from_request(request),
                    dataset_id=request.dataset_id,
                    suite_id=request.suite_id,
                ),
                cache_root=self._evaluation_materialization_root(),
            )
            parameters.setdefault("evaluation_source_kind", "jsonl")
            parameters.setdefault("evaluation_source_locator", source_path)
            parameters.setdefault("evaluation_materialized_dataset_root", str(materialized.package_path))
            return materialized.package_path

        if source_kind == "hf_dataset":
            source = request.source.hf_dataset
            materialized = materialize_hf_evaluation_dataset(
                source=HFEvaluationDatasetSource(
                    dataset_path=source.dataset_path,
                    dataset_name=source.dataset_name,
                    dataset_revision=source.dataset_revision or "main",
                    split=source.split or "train",
                ),
                profile=self._evaluation_profile_from_request(request),
                field_mapping=self._evaluation_field_mapping_from_request(request),
                dataset_id=request.dataset_id,
                suite_id=request.suite_id,
                cache_root=self._evaluation_materialization_root(),
                fetch_json=self._evaluation_hf_dataset_fetcher,
            )
            parameters.setdefault("evaluation_source_kind", "hf_dataset")
            parameters.setdefault("evaluation_source_locator", source.dataset_path)
            parameters.setdefault("evaluation_materialized_dataset_root", str(materialized.package_path))
            return materialized.package_path

        dataset_root = request.dataset_root or parameters.get("dataset_root", "")
        return Path(dataset_root) if dataset_root else self._default_dataset_root(request.dataset_id)

    def _evaluation_materialization_root(self) -> Path:
        return (self._evaluation_jobs_root / "datasets").resolve()

    @staticmethod
    def _evaluation_field_mapping_from_request(request) -> EvaluationFieldMapping:
        return EvaluationFieldMapping(
            system_path=request.field_mapping.system_path,
            input_text_path=request.field_mapping.input_text_path,
            target_path=request.field_mapping.target_path,
            sample_id_path=request.field_mapping.sample_id_path,
        )

    @staticmethod
    def _evaluation_profile_from_request(request) -> EvaluationProfileDefinition:
        output_schema_json = request.profile.output_schema_json.strip()
        output_schema: dict[str, Any] | None = None
        if output_schema_json:
            parsed = json.loads(output_schema_json)
            if not isinstance(parsed, dict):
                raise ValueError("evaluation profile output_schema_json must decode to a JSON object.")
            output_schema = parsed
        threshold = float(request.profile.threshold or 1.0)

        return EvaluationProfileDefinition(
            profile_type=request.profile.profile_type.strip() or "final_result",
            result_kind=request.profile.result_kind.strip() or "text",
            extraction_mode=request.profile.extraction_mode.strip() or "heuristic_final",
            scoring_mode=request.profile.scoring_mode.strip() or request.scoring_mode.strip() or "normalized_exact_match",
            threshold=threshold,
            output_schema=output_schema,
            ignored_paths=tuple(
                value.strip()
                for value in request.profile.ignored_paths
                if isinstance(value, str) and value.strip()
            ),
        )


def _device_identity_from_metadata(metadata: dict[str, str]) -> Any:
    return collect_device_identity(
        chip=metadata.get("chip") or None,
        memory_gb=_parse_optional_float(metadata.get("memory_gb")),
        os_version=metadata.get("os_version") or None,
        os_build=metadata.get("os_build") or None,
        hostname_hash=metadata.get("hostname_hash") or None,
        melix_version=metadata.get("melix_version", "0.0.0-dev"),
    )


def _parse_optional_float(raw_value: str | None) -> float | None:
    if raw_value in (None, ""):
        return None
    try:
        return float(raw_value)
    except ValueError:
        return None


class WorkerCacheService(cache_pb2_grpc.CacheServiceServicer):
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def GetCacheStats(self, request, context):
        return self._registry.cache_stats_response()

    def PinPrefix(self, request, context):
        return cache_pb2.PinPrefixResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Pinning is deferred in phase 0."),
        )

    def UnpinPrefix(self, request, context):
        return cache_pb2.UnpinPrefixResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Unpinning is deferred in phase 0."),
        )

    def SaveBoundarySnapshot(self, request, context):
        return cache_pb2.SaveBoundarySnapshotResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Boundary snapshots are deferred in phase 0."),
        )

    def RestoreBoundarySnapshot(self, request, context):
        return cache_pb2.RestoreBoundarySnapshotResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Boundary restore is deferred in phase 0."),
        )

    def PurgeCache(self, request, context):
        return cache_pb2.PurgeCacheResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Cache purge is deferred in phase 0."),
        )


def build_registry_for_backend(backend_mode: str) -> WorkerRegistry:
    process_memory_budget_bytes = max(0, int(os.environ.get("MELIX_PYTHON_WORKER_PROCESS_MEMORY_BUDGET_BYTES", "0")))
    memory_headroom_bytes = max(0, int(os.environ.get("MELIX_PYTHON_WORKER_MODEL_LOAD_HEADROOM_BYTES", "0")))
    if backend_mode == "deterministic":
        return WorkerRegistry(
            runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
            embedding_runtime=DeterministicEmbeddingRuntime(),
            rerank_runtime=DeterministicRerankRuntime(),
            process_memory_budget_bytes=process_memory_budget_bytes,
            memory_headroom_bytes=memory_headroom_bytes,
        )
    return WorkerRegistry(
        process_memory_budget_bytes=process_memory_budget_bytes,
        memory_headroom_bytes=memory_headroom_bytes,
    )


def _deterministic_benchmark_fetch_json(endpoint: str, params: dict[str, str]) -> dict[str, object]:
    dataset = params.get("dataset", "")
    offset = params.get("offset", "0")
    if endpoint == "rows" and offset != "0":
        return {"rows": []}

    if dataset == "HuggingFaceH4/ultrachat_200k":
        if endpoint == "rows":
            return {
                "rows": [
                    {
                        "row": {
                            "messages": [
                                {"role": "user", "content": "Say hi."},
                                {"role": "assistant", "content": "Hi."},
                            ]
                        }
                    },
                    {
                        "row": {
                            "messages": [
                                {"role": "user", "content": "Say bye."},
                                {"role": "assistant", "content": "Bye."},
                            ]
                        }
                    },
                ]
            }
        return {"splits": [{"dataset": dataset, "config": "default", "split": "train_sft"}]}

    if dataset == "databricks/databricks-dolly-15k":
        if endpoint == "rows":
            return {
                "rows": [
                    {"row": {"instruction": "List two colors.", "response": "Red and blue."}},
                    {"row": {"instruction": "List two animals.", "response": "Cat and dog."}},
                ]
            }
        return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}

    if dataset == "huggingface/documentation-images":
        if endpoint == "rows":
            return {
                "rows": [
                    {"row": {"image": {"src": "https://example.com/doc-image-1.jpg"}}},
                    {"row": {"image": {"src": "https://example.com/doc-image-2.jpg"}}},
                ]
            }
        return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}

    raise AssertionError(f"Unexpected deterministic benchmark fetch: endpoint={endpoint} dataset={dataset}")


def build_maintenance_service(
    registry: WorkerRegistry,
    *,
    jobs_root: Path | str | None = None,
    evaluation_jobs_root: Path | str | None = None,
    backend_mode: str = "auto",
    evaluation_core: EvaluationCore | None = None,
    hub_catalog: HubCatalog | None = None,
) -> WorkerMaintenanceService:
    lora_training_pipeline = None
    adapter_activation_pipeline = None
    benchmark_suite_catalog = None
    if backend_mode == "deterministic":
        runner = DeterministicLoRARunner()
        lora_training_pipeline = LoRATrainingPipeline(runner=runner)
        adapter_activation_pipeline = AdapterActivationPipeline(runner=runner)
        benchmark_suite_catalog = BenchmarkSuiteCatalog(
            hf_dataset_fetcher=_deterministic_benchmark_fetch_json
        )
    return WorkerMaintenanceService(
        registry,
        jobs_root=jobs_root,
        evaluation_jobs_root=evaluation_jobs_root,
        evaluation_core=evaluation_core,
        hub_catalog=hub_catalog,
        lora_training_pipeline=lora_training_pipeline,
        adapter_activation_pipeline=adapter_activation_pipeline,
        benchmark_suite_catalog=benchmark_suite_catalog,
    )


def build_server(
    socket_path: str,
    registry: WorkerRegistry | None = None,
    backend_mode: str = "auto",
    metrics_exporter: BootstrapMetricsExporter | None = None,
):
    registry_started_at = time.perf_counter_ns()
    registry = registry or build_registry_for_backend(backend_mode)
    if metrics_exporter is not None:
        metrics_exporter.set_milliseconds(
            "python_worker.registry_init_ms",
            _elapsed_milliseconds_since(registry_started_at),
        )

    server_build_started_at = time.perf_counter_ns()
    socket_path = os.fspath(Path(socket_path).resolve())
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    maintenance_service = build_maintenance_service(
        registry,
        jobs_root=_resolved_env_path("MELIX_MODEL_OPS_JOBS_ROOT"),
        evaluation_jobs_root=_resolved_env_path("MELIX_EVALUATION_JOBS_ROOT"),
        backend_mode=backend_mode,
    )
    cache_service = WorkerCacheService(registry)
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(runtime_service, server)
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(inference_service, server)
    maintenance_pb2_grpc.add_MaintenanceServiceServicer_to_server(maintenance_service, server)
    cache_pb2_grpc.add_CacheServiceServicer_to_server(cache_service, server)
    server.add_insecure_port(f"unix://{socket_path}")
    if metrics_exporter is not None:
        metrics_exporter.set_milliseconds(
            "python_worker.server_build_ms",
            _elapsed_milliseconds_since(server_build_started_at),
        )
    return server, runtime_service, inference_service


def _resolved_env_path(key: str) -> Path | None:
    raw_value = os.environ.get(key, "").strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser().resolve()


def main() -> None:
    bootstrap_started_at = time.perf_counter_ns()
    metrics_exporter = BootstrapMetricsExporter(os.environ.get("MELIX_PYTHON_WORKER_METRICS_PATH"))
    metrics_exporter.set_milliseconds(
        "python_worker.spawn_to_bootstrap_ms",
        _elapsed_milliseconds_from_origin(os.environ.get("MELIX_PYTHON_WORKER_STARTUP_T0_NS"), bootstrap_started_at),
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", default="/var/run/melix/worker-text-001.sock")
    parser.add_argument("--backend-mode", choices=["auto", "deterministic"], default="auto")
    args = parser.parse_args()
    metrics_exporter.set_milliseconds(
        "python_worker.arg_parse_ms",
        _elapsed_milliseconds_since(bootstrap_started_at),
    )

    server, _, _ = build_server(
        args.socket_path,
        backend_mode=getattr(args, "backend_mode", "auto"),
        metrics_exporter=metrics_exporter,
    )
    server_start_started_at = time.perf_counter_ns()
    server.start()
    metrics_exporter.set_milliseconds(
        "python_worker.server_start_ms",
        _elapsed_milliseconds_since(server_start_started_at),
    )
    metrics_exporter.set_milliseconds(
        "python_worker.bootstrap_ms",
        _elapsed_milliseconds_since(bootstrap_started_at),
    )
    server.wait_for_termination()


def _elapsed_milliseconds_since(started_at_nanoseconds: int, now_nanoseconds: int | None = None) -> float:
    current = now_nanoseconds if now_nanoseconds is not None else time.perf_counter_ns()
    if current < started_at_nanoseconds:
        return 0.0
    return (current - started_at_nanoseconds) / 1_000_000.0


def _elapsed_milliseconds_from_origin(raw_origin_nanoseconds: str | None, now_nanoseconds: int | None = None) -> float:
    if raw_origin_nanoseconds is None:
        return 0.0
    try:
        origin_nanoseconds = int(raw_origin_nanoseconds)
    except ValueError:
        return 0.0
    if origin_nanoseconds < 0:
        return 0.0
    return _elapsed_milliseconds_since(origin_nanoseconds, now_nanoseconds)
