from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import tempfile
import threading
import time
from concurrent import futures
from pathlib import Path
from typing import Any, Mapping

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
    tool_runtime_pb2,
    tool_runtime_pb2_grpc,
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
from worker.productization.mcp_credential_environment import (
    MAX_MCP_CONFIG_SOURCES,
    MAX_MCP_CREDENTIAL_KEY_LIST_BYTES,
    MAX_MCP_CREDENTIAL_REFERENCES,
    MAX_MCP_REFERENCE_TARGET_LIST_BYTES,
)
from worker.productization.evaluation_final_result import (
    EvaluationFieldMapping,
    EvaluationMaterializationRequest,
    EvaluationProfileDefinition,
    HFEvaluationDatasetFetcher,
    HFEvaluationDatasetSource,
    materialize_hf_evaluation_dataset,
    materialize_local_evaluation_dataset,
)
from worker.model_load_trust import ModelLoadTrustRejection
from worker.registry import (
    DiskStreamingUnsupported,
    MemoryBudgetExceeded,
    WorkerInstanceMismatch,
    WorkerRegistry,
)
from worker.runtime.audio_runtime_protocols import AudioBackendUnavailableError, AudioProcessorValidationError
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime
from worker.runtime.artifact_embedding_runtime import ArtifactEmbeddingError
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime
from worker.runtime.computer_use_adapter import configured_computer_use_adapter
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime.mcp_client import (
    MCPClientError,
    MCPClientManager,
    MCPOwnerIdentity,
    MCPSourceDefinition,
    MCPStdioTransport,
    MCPStreamableHTTPTransport,
)
from worker.runtime.tool_execution_runtime import (
    ToolExecutionCall,
    ToolExecutionContext,
    ToolExecutionEvidenceStore,
    ToolExecutionRuntime,
    ToolExecutionRuntimeError,
    ToolExecutionRuntimeMetricsSnapshot,
)
from worker.productization.benchmark_export import write_export_bundle
from worker.productization.device_identity import collect_device_identity
from worker.productization.submission_builder import build_submission_payload


_BUILTIN_EVENT_EXTRACTION_TOP20_DATASET_ID = "top200.event-extraction.top20.v1"
_EXPORT_RESULTS_STREAM_CHUNK_BYTES = 1024 * 1024
_DEFAULT_MCP_SOURCE_LEASE_TTL_MS = 300_000
_MAX_MCP_SOURCE_LEASE_TTL_MS = 3_600_000


class _RPCExecutionAdmission:
    """Atomically closes execution admission before an RPC may dispatch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._decision: futures.Future[bool] = futures.Future()
        self._execution: futures.Future | None = None
        self._cancelled = False

    async def wait(self) -> None:
        admitted = await asyncio.wrap_future(self._decision)
        if not admitted:
            raise asyncio.CancelledError

    def attach(self, execution: futures.Future) -> None:
        with self._lock:
            self._execution = execution
            cancelled = self._cancelled
        if cancelled:
            execution.cancel()

    def allow(self) -> None:
        with self._lock:
            if self._cancelled or self._decision.done():
                return
            self._decision.set_result(True)

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            if not self._decision.done():
                self._decision.set_result(False)
            execution = self._execution
        if execution is not None:
            execution.cancel()


class BootstrapMetricsExporter:
    def __init__(self, export_path: str | None) -> None:
        self._export_path = Path(export_path).resolve() if export_path else None
        self._lock = threading.Lock()
        self._values: dict[str, int | float] = {
            "python_worker.spawn_to_bootstrap_ms": 0,
            "python_worker.arg_parse_ms": 0,
            "python_worker.registry_init_ms": 0,
            "python_worker.server_build_ms": 0,
            "python_worker.server_start_ms": 0,
            "python_worker.bootstrap_ms": 0,
        }
        self._write()

    def set_milliseconds(self, key: str, value: float) -> None:
        self.set_metrics({key: max(0, int(round(value)))})

    def set_metrics(self, values: Mapping[str, int | float]) -> None:
        normalized: dict[str, int | float] = {}
        for key, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"metric {key!r} must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"metric {key!r} must be finite")
            normalized[key] = max(0, value)
        with self._lock:
            self._values.update(normalized)
            self._write_unlocked()

    def _write(self) -> None:
        with self._lock:
            self._write_unlocked()

    def _write_unlocked(self) -> None:
        if self._export_path is None:
            return

        self._export_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "updated_at_unix_ms": int(time.time() * 1000),
            "values": self._values,
        }
        _write_json_atomically(self._export_path, payload)


def _agent_runtime_metric_values(
    snapshot: ToolExecutionRuntimeMetricsSnapshot,
) -> dict[str, int | float]:
    values: dict[str, int | float] = {
        "agent.mcp.reconnect_count": snapshot.mcp.reconnect_count,
        "agent.mcp.schema_change_count": snapshot.mcp.schema_change_count,
    }
    for key, operation in (
        ("agent.mcp.initialize_ms", snapshot.mcp.initialize),
        ("agent.mcp.list_tools_ms", snapshot.mcp.list_tools),
        ("agent.mcp.call_tool_ms", snapshot.mcp.call_tool),
        (
            "agent.mcp.cancel_propagation_ms",
            snapshot.mcp.cancel_propagation,
        ),
        (
            "agent.cancel.worker_to_adapter_ms",
            snapshot.worker_to_adapter_cancel,
        ),
    ):
        values.update(
            {
                key: operation.last_latency_ms,
                f"{key}.sample_count": operation.invocation_count,
                f"{key}.failure_count": operation.failure_count,
                f"{key}.total_ms": operation.total_latency_ms,
                f"{key}.max_ms": operation.maximum_latency_ms,
            }
        )
    return values


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
            worker_family=common_pb2.WORKER_FAMILY_OMNI,
            worker_instance_id=self._registry.worker_instance_id,
        )

    def LoadModel(self, request, context):
        try:
            loaded = self._registry.load_model(
                request.model,
                pin_on_load=request.pin_on_load,
                memory_budget_bytes=request.memory_budget_bytes,
                disk_streaming_mode=request.disk_streaming_mode,
                load_trust=request.load_trust if request.HasField("load_trust") else None,
                backend_identity=(
                    request.backend_identity if request.HasField("backend_identity") else None
                ),
            )
        except WorkerInstanceMismatch as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="worker_instance_mismatch",
                    message=str(exc),
                    retriable=True,
                ),
            )
        except ModelLoadTrustRejection as exc:
            response = runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="unsafe_load_rejected",
                    message=str(exc),
                    details=exc.details,
                ),
            )
            response.load_trust.CopyFrom(exc.policy)
            return response
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
        except ArtifactEmbeddingError as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code=exc.code, message=str(exc)),
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
        response.load_trust.CopyFrom(loaded.load_trust)
        return response

    def UnloadModel(self, request, context):
        receipt = self._registry.request_model_unload(
            request.model_handle,
            force=bool(request.force),
            expected_backend_identity=(
                request.expected_backend_identity
                if request.HasField("expected_backend_identity")
                else None
            ),
        )
        if receipt.unloaded:
            return runtime_pb2.UnloadModelResponse(ok=True)
        if receipt.pending_unload:
            return runtime_pb2.UnloadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="unload_pending",
                    message="Model unload is pending until active request leases are released.",
                    retriable=True,
                    details=receipt.details,
                ),
            )
        if receipt.identity_mismatch:
            return runtime_pb2.UnloadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="model_identity_mismatch",
                    message="The model residency no longer matches the unload request.",
                    retriable=False,
                    details=receipt.details,
                ),
            )
        return runtime_pb2.UnloadModelResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle."),
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
        if error := self._execution_identity_error(request.execution):
            yield self._execute_error(request.execution.id.request_id, error)
            return
        yield from self._engine.generate(request)

    def Prefill(self, request, context):
        if error := self._execution_identity_error(request.execution):
            return inference_pb2.PrefillResponse(ok=False, error=error)
        return self._engine.prefill(request)

    def Decode(self, request, context):
        requested = (
            request.execution.backend_identity
            if request.execution.HasField("backend_identity")
            else None
        )
        if error := self._registry.validate_decode_backend_identity(
            request_id=request.execution.id.request_id,
            decode_handle=request.decode_handle,
            model_handle=request.execution.model_handle,
            requested=requested,
        ):
            yield self._execute_error(request.execution.id.request_id, error)
            return
        yield from self._engine.decode(request)

    def Abort(self, request, context):
        found = self._engine.abort(request.request_id)
        return inference_pb2.AbortResponse(ok=found, found=found)

    def Embed(self, request, context):
        if error := self._request_identity_error(request):
            return inference_pb2.EmbedResponse(error=error)
        return self._embedding.embed(request)

    def Rerank(self, request, context):
        if error := self._request_identity_error(request):
            return inference_pb2.RerankResponse(error=error)
        return self._rerank.rerank(request)

    def Transcribe(self, request, context):
        if error := self._request_identity_error(request):
            return inference_pb2.TranscribeResponse(error=error)
        return self._transcription.transcribe(request)

    def Speak(self, request, context):
        if error := self._request_identity_error(request):
            return inference_pb2.SpeakResponse(error=error)
        return self._speech.speak(request)

    def SpeakStream(self, request, context):
        if error := self._request_identity_error(request):
            yield inference_pb2.SpeakStreamEvent(
                kind=inference_pb2.SPEAK_STREAM_EVENT_KIND_ERROR,
                error=error,
            )
            return
        yield from self._speech.speak_stream(request)

    def ImageGenerate(self, request, context):
        if error := self._request_identity_error(request):
            return inference_pb2.ImageGenerateResponse(error=error)
        return self._image_generation.generate(request)

    def ImageEdit(self, request, context):
        if error := self._request_identity_error(request):
            return inference_pb2.ImageEditResponse(error=error)
        return self._image_edit.edit(request)

    def _execution_identity_error(self, execution):
        requested = execution.backend_identity if execution.HasField("backend_identity") else None
        return self._registry.validate_backend_identity(execution.model_handle, requested)

    def _request_identity_error(self, request):
        requested = request.backend_identity if request.HasField("backend_identity") else None
        return self._registry.validate_backend_identity(request.model_handle, requested)

    @staticmethod
    def _execute_error(request_id: str, error: common_pb2.ErrorStatus):
        return inference_pb2.ExecuteEvent(
            request_id=request_id,
            error=inference_pb2.ErrorEvent(error=error),
        )


class WorkerToolRuntimeService(
    tool_runtime_pb2_grpc.ToolRuntimeServiceServicer
):
    def __init__(
        self,
        *,
        runtime: ToolExecutionRuntime | None = None,
        environment: Mapping[str, str] | None = None,
        metrics_exporter: BootstrapMetricsExporter | None = None,
    ) -> None:
        resolved_environment = (
            os.environ if environment is None else environment
        )
        evidence_home = resolved_environment.get("MELIX_HOME", "").strip()
        self._runtime = runtime or ToolExecutionRuntime(
            mcp_manager=MCPClientManager(environment=resolved_environment),
            computer_use_adapter=configured_computer_use_adapter(
                resolved_environment
            ),
            evidence_store=(
                ToolExecutionEvidenceStore(evidence_home)
                if evidence_home
                else None
            ),
        )
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._event_loop_thread: threading.Thread | None = None
        self._event_loop_lock = threading.Lock()
        self._source_lock = threading.Lock()
        self._owner_source_ids: dict[
            tuple[str, str, str],
            set[str],
        ] = {}
        self._owner_lease_expiry_monotonic: dict[
            tuple[str, str, str],
            float,
        ] = {}
        self._source_configuration_digests: dict[str, str] = {}
        self._metrics_exporter = metrics_exporter
        self._export_runtime_metrics()

    def ListAgentTools(self, request, context):
        try:
            with self._source_lock:
                self._expire_owner_leases(context)
                has_owner_identity = bool(
                    request.id.session_id
                    or request.id.branch_id
                    or request.owner_actor_id
                )
                owner = (
                    _catalog_owner(request)
                    if request.sources
                    or request.release_sources
                    or has_owner_identity
                    else None
                )
                lease_ttl_seconds = _catalog_lease_ttl_seconds(request)
                if request.release_sources:
                    assert owner is not None
                    released_source_ids = set(
                        self._owner_source_ids.pop(owner.key, set())
                    )
                    self._owner_lease_expiry_monotonic.pop(owner.key, None)
                    self._run(
                        self._runtime.release_mcp_owner(owner),
                        timeout_seconds=_remaining_rpc_seconds(
                            request.deadline_unix_ms,
                            context,
                        ),
                        context=context,
                    )
                    self._discard_unleased_source_digests(released_source_ids)
                    source_receipts = []
                    effective_source_ids: set[str] = set()
                elif owner is not None:
                    source_receipts, effective_source_ids = (
                        self._reconcile_sources(
                            request,
                            context,
                            owner=owner,
                            lease_ttl_seconds=lease_ttl_seconds,
                        )
                    )
                else:
                    source_receipts = []
                    effective_source_ids = set()
                catalog = self._run(
                    self._runtime.list_tools(
                        owner=(owner if effective_source_ids else None),
                        refresh_mcp_catalogs=bool(request.refresh_sources),
                        mcp_source_ids=effective_source_ids,
                    ),
                    timeout_seconds=_remaining_rpc_seconds(
                        request.deadline_unix_ms,
                        context,
                    ),
                    context=context,
                )
        except futures.TimeoutError:
            _abort_rpc_deadline(
                context,
                "agent tool catalog deadline exceeded",
            )
        finally:
            self._export_runtime_metrics()
        return tool_runtime_pb2.ToolCatalogReceipt(
            schema_version=catalog.schema_version,
            tools=[
                _agent_tool_definition(tool)
                for tool in catalog.tools
            ],
            sources=source_receipts,
            catalog_digest=catalog.catalog_digest,
            source_count=catalog.source_count,
            live_source_count=catalog.live_source_count,
        )

    def ExecuteAgentTool(self, request, context):
        run_id = request.context.run_id
        call_id = request.call_id
        yield tool_runtime_pb2.AgentToolExecutionEvent(
            run_id=run_id,
            call_id=call_id,
            seq=1,
            phase=tool_runtime_pb2.AGENT_TOOL_EXECUTION_QUEUED,
            emitted_at_unix_ms=int(time.time() * 1_000),
        )
        yield tool_runtime_pb2.AgentToolExecutionEvent(
            run_id=run_id,
            call_id=call_id,
            seq=2,
            phase=tool_runtime_pb2.AGENT_TOOL_EXECUTION_STARTED,
            emitted_at_unix_ms=int(time.time() * 1_000),
        )
        try:
            execution_context = ToolExecutionContext(
                run_id=run_id,
                session_id=request.context.session_id,
                branch_id=request.context.branch_id,
                actor_id=request.context.actor_id,
                admission_state=request.context.admission_state,
                approval_grant_digest=(
                    request.context.approval_grant_digest
                ),
                policy_revision=request.context.policy_revision,
                deadline_unix_ms=request.context.deadline_unix_ms,
                control_plane_authorization_key_id=(
                    request.context.control_plane_authorization_key_id
                ),
                control_plane_authorization_algorithm=(
                    request.context.control_plane_authorization_algorithm
                ),
                control_plane_authorization_payload=(
                    request.context.control_plane_authorization_payload
                ),
                control_plane_authorization_signature=(
                    request.context.control_plane_authorization_signature
                ),
            )
            arguments = json.loads(request.arguments_json or "{}")
            if not isinstance(arguments, dict):
                raise ToolExecutionRuntimeError(
                    "tool arguments must be a JSON object"
                )
            try:
                execution = self._run_rpc_admitted(
                    lambda: self._runtime.execute(
                        ToolExecutionCall(
                            call_id=call_id,
                            tool_name=request.tool_name,
                            source_id=request.source_id,
                            arguments=arguments,
                            expected_schema_digest=(
                                request.expected_schema_digest
                            ),
                            idempotency_key=request.idempotency_key,
                        ),
                        execution_context,
                    ),
                    timeout_seconds=_remaining_rpc_seconds(
                        request.context.deadline_unix_ms,
                        context,
                    ),
                    context=context,
                    on_disconnect=lambda: self._schedule_runtime_cancel(
                        run_id,
                        call_id,
                        execution_context.owner,
                    ),
                )
            finally:
                self._export_runtime_metrics()
        except futures.TimeoutError:
            yield tool_runtime_pb2.AgentToolExecutionEvent(
                run_id=run_id,
                call_id=call_id,
                seq=3,
                phase=tool_runtime_pb2.AGENT_TOOL_EXECUTION_TIMEOUT,
                emitted_at_unix_ms=int(time.time() * 1_000),
                error=common_pb2.ErrorStatus(
                    code="tool_execution_deadline_exceeded",
                    message="Tool execution exceeded its deadline.",
                    retriable=False,
                ),
            )
            return
        except futures.CancelledError:
            return
        except (json.JSONDecodeError, ToolExecutionRuntimeError) as error:
            yield tool_runtime_pb2.AgentToolExecutionEvent(
                run_id=run_id,
                call_id=call_id,
                seq=3,
                phase=tool_runtime_pb2.AGENT_TOOL_EXECUTION_FAILED,
                emitted_at_unix_ms=int(time.time() * 1_000),
                error=common_pb2.ErrorStatus(
                    code=getattr(
                        error,
                        "code",
                        "tool_arguments_invalid",
                    ),
                    message=_public_tool_error_message(error),
                    retriable=False,
                ),
            )
            return

        terminal_phase = {
            "completed": tool_runtime_pb2.AGENT_TOOL_EXECUTION_COMPLETED,
            "cancelled": tool_runtime_pb2.AGENT_TOOL_EXECUTION_CANCELLED,
            "timeout": tool_runtime_pb2.AGENT_TOOL_EXECUTION_TIMEOUT,
            "failed": tool_runtime_pb2.AGENT_TOOL_EXECUTION_FAILED,
        }.get(
            execution.status,
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_FAILED,
        )
        yield tool_runtime_pb2.AgentToolExecutionEvent(
            run_id=run_id,
            call_id=call_id,
            seq=3,
            phase=terminal_phase,
            emitted_at_unix_ms=int(time.time() * 1_000),
            result=tool_runtime_pb2.AgentToolExecutionResult(
                run_id=execution.run_id,
                call_id=execution.call_id,
                tool_name=execution.tool_name,
                source_id=execution.source_id,
                adapter_kind=execution.adapter_kind,
                status=execution.status,
                observation_json=json.dumps(
                    execution.observation.as_agentic_trace_observation(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                duration_ms=execution.duration_ms,
                receipt_json=json.dumps(
                    execution.receipt,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                evidence_reference=execution.evidence_reference,
            ),
        )

    def CancelAgentTool(self, request, context):
        try:
            cancellation_id = _validated_cancellation_correlation_id(
                request.cancellation_id
            )
        except ValueError as error:
            _abort_rpc_invalid_argument(context, str(error))
        try:
            owner = MCPOwnerIdentity(
                session_id=request.session_id,
                branch_id=request.branch_id,
                actor_id=request.actor_id,
            )
        except MCPClientError:
            return tool_runtime_pb2.CancelAgentToolResponse(
                run_id=request.run_id,
                call_id=request.call_id,
                cancellation_id=cancellation_id,
                disposition=(
                    tool_runtime_pb2.TOOL_CANCELLATION_SCOPE_MISMATCH
                ),
                side_effect_state=(
                    tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN
                ),
            )
        try:
            receipt = self._run(
                self._runtime.cancel(
                    request.run_id,
                    request.call_id,
                    owner,
                    cancellation_id,
                ),
                timeout_seconds=_remaining_rpc_seconds(0, context),
                context=context,
            )
        finally:
            self._export_runtime_metrics()
        disposition = {
            "accepted": tool_runtime_pb2.TOOL_CANCELLATION_ACCEPTED,
            "already_terminal": (
                tool_runtime_pb2.TOOL_CANCELLATION_ALREADY_TERMINAL
            ),
            "too_late": tool_runtime_pb2.TOOL_CANCELLATION_TOO_LATE,
            "not_found": tool_runtime_pb2.TOOL_CANCELLATION_NOT_FOUND,
            "scope_mismatch": (
                tool_runtime_pb2.TOOL_CANCELLATION_SCOPE_MISMATCH
            ),
        }.get(
            receipt.disposition,
            tool_runtime_pb2.TOOL_CANCELLATION_DISPOSITION_UNSPECIFIED,
        )
        return tool_runtime_pb2.CancelAgentToolResponse(
            run_id=request.run_id,
            call_id=request.call_id,
            cancellation_id=cancellation_id,
            disposition=disposition,
            adapter_kind=receipt.adapter_kind,
            source_id=receipt.source_id,
            side_effect_committed=receipt.side_effect_committed,
            side_effect_state={
                "none": tool_runtime_pb2.TOOL_SIDE_EFFECT_NONE,
                "committed": tool_runtime_pb2.TOOL_SIDE_EFFECT_COMMITTED,
                "unknown": tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN,
            }.get(
                receipt.side_effect_state,
                tool_runtime_pb2.TOOL_SIDE_EFFECT_STATE_UNSPECIFIED,
            ),
        )

    def CancelAgentRunTools(self, request, context):
        try:
            cancellation_id = _validated_cancellation_correlation_id(
                request.cancellation_id
            )
        except ValueError as error:
            _abort_rpc_invalid_argument(context, str(error))
        try:
            owner = MCPOwnerIdentity(
                session_id=request.session_id,
                branch_id=request.branch_id,
                actor_id=request.actor_id,
            )
        except MCPClientError:
            return tool_runtime_pb2.CancelAgentRunToolsResponse(
                run_id=request.run_id,
                cancellation_id=cancellation_id,
                disposition=(
                    tool_runtime_pb2.TOOL_CANCELLATION_SCOPE_MISMATCH
                ),
                side_effect_state=(
                    tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN
                ),
                computer_use_disposition=(
                    tool_runtime_pb2.TOOL_CANCELLATION_SCOPE_MISMATCH
                ),
            )
        try:
            receipt = self._run(
                self._runtime.cancel_run(
                    request.run_id,
                    owner,
                    cancellation_id,
                ),
                timeout_seconds=_remaining_rpc_seconds(0, context),
                context=context,
            )
        finally:
            self._export_runtime_metrics()
        return tool_runtime_pb2.CancelAgentRunToolsResponse(
            run_id=receipt.run_id,
            cancellation_id=cancellation_id,
            disposition=_tool_cancellation_disposition(
                receipt.disposition
            ),
            side_effect_state=_tool_side_effect_state(
                receipt.side_effect_state
            ),
            calls=[
                tool_runtime_pb2.CancelAgentToolResponse(
                    run_id=call.run_id,
                    call_id=call.call_id,
                    cancellation_id=call.cancellation_id,
                    disposition=_tool_cancellation_disposition(
                        call.disposition
                    ),
                    adapter_kind=call.adapter_kind,
                    source_id=call.source_id,
                    side_effect_committed=call.side_effect_committed,
                    side_effect_state=_tool_side_effect_state(
                        call.side_effect_state
                    ),
                )
                for call in receipt.calls
            ],
            computer_use_disposition=_tool_cancellation_disposition(
                receipt.computer_use_disposition
            ),
        )

    def close(self) -> None:
        with self._event_loop_lock:
            event_loop = self._event_loop
            event_loop_thread = self._event_loop_thread
        if event_loop is None or not event_loop.is_running():
            return
        self._run(self._runtime.close())
        event_loop.call_soon_threadsafe(event_loop.stop)
        if event_loop_thread is not None:
            event_loop_thread.join(timeout=5)
        event_loop.close()
        with self._event_loop_lock:
            self._event_loop = None
            self._event_loop_thread = None
        with self._source_lock:
            self._owner_source_ids.clear()
            self._owner_lease_expiry_monotonic.clear()
            self._source_configuration_digests.clear()

    def _reconcile_sources(
        self,
        request,
        context,
        *,
        owner: MCPOwnerIdentity,
        lease_ttl_seconds: float,
    ):
        owner_key = owner.key
        previous_owner_sources = self._owner_source_ids.get(owner_key, set())
        source_ids: list[str] = []
        seen_source_ids: set[str] = set()
        duplicate_ids: set[str] = set()
        for source in request.sources:
            source_ids.append(source.source_id)
            if source.source_id in seen_source_ids:
                duplicate_ids.add(source.source_id)
            else:
                seen_source_ids.add(source.source_id)
        if _mcp_catalog_request_limit_error(request.sources) is not None:
            return (
                [
                    tool_runtime_pb2.AgentToolSourceReceipt(
                        source_id=source.source_id,
                        transport_kind=source.WhichOneof("transport") or "",
                        connection_state="failed",
                        error_code="mcp_source_catalog_limit_exceeded",
                    )
                    for source in request.sources
                ],
                set(previous_owner_sources),
            )
        requested_live_ids = {
            source.source_id
            for source in request.sources
            if (
                source.enabled
                and source.source_id
                and source.source_id not in duplicate_ids
            )
        }
        effective_live_ids: set[str] = set()

        other_owner_sources = set().union(
            *(
                source_ids
                for owner, source_ids in self._owner_source_ids.items()
                if owner != owner_key
            ),
            set(),
        )
        for source_id in sorted(previous_owner_sources - requested_live_ids):
            self._run(
                self._runtime.remove_mcp_source(source_id, owner),
                timeout_seconds=_remaining_rpc_seconds(
                    request.deadline_unix_ms,
                    context,
                ),
                context=context,
            )
            if source_id not in other_owner_sources:
                self._source_configuration_digests.pop(source_id, None)

        source_receipts = []
        for source in request.sources:
            transport_kind = source.WhichOneof("transport") or ""
            if source.source_id in duplicate_ids:
                source_receipts.append(
                    tool_runtime_pb2.AgentToolSourceReceipt(
                        source_id=source.source_id,
                        transport_kind=transport_kind,
                        connection_state="failed",
                        error_code="mcp_source_id_duplicate",
                    )
                )
                continue
            if not source.enabled:
                source_receipts.append(
                    tool_runtime_pb2.AgentToolSourceReceipt(
                        source_id=source.source_id,
                        transport_kind=transport_kind,
                        connection_state="disabled",
                    )
                )
                continue
            try:
                definition = _mcp_source_definition(source)
                existing_digest = self._source_configuration_digests.get(
                    source.source_id
                )
                if (
                    existing_digest is not None
                    and existing_digest != definition.configuration_digest
                    and source.source_id in other_owner_sources
                ):
                    raise MCPClientError(
                        "MCP source configuration conflicts with another owner"
                    )
                capabilities = self._run(
                    self._runtime.initialize_mcp_source(
                        definition,
                        owner,
                        lease_ttl_seconds=lease_ttl_seconds,
                    ),
                    timeout_seconds=_remaining_rpc_seconds(
                        request.deadline_unix_ms,
                        context,
                    ),
                    context=context,
                )
                self._source_configuration_digests[source.source_id] = (
                    definition.configuration_digest
                )
                effective_live_ids.add(source.source_id)
                source_receipts.append(
                    tool_runtime_pb2.AgentToolSourceReceipt(
                        source_id=capabilities.source_id,
                        transport_kind=capabilities.transport_kind,
                        connection_state="live",
                        protocol_version=capabilities.protocol_version,
                        server_name=capabilities.server_name,
                        server_version=capabilities.server_version,
                        capabilities=capabilities.capability_names,
                        tool_count=capabilities.tool_count,
                        catalog_digest=capabilities.catalog_digest,
                        connected_at_unix_ms=capabilities.connected_at_unix_ms,
                    )
                )
            except futures.TimeoutError:
                raise
            except (MCPClientError, ValueError) as error:
                source_receipts.append(
                    tool_runtime_pb2.AgentToolSourceReceipt(
                        source_id=source.source_id,
                        transport_kind=transport_kind,
                        connection_state="failed",
                        error_code=getattr(
                            error,
                            "code",
                            "mcp_source_configuration_invalid",
                        ),
                    )
                )

        self._owner_source_ids[owner_key] = effective_live_ids
        self._owner_lease_expiry_monotonic[owner_key] = (
            time.monotonic() + lease_ttl_seconds
        )
        return source_receipts, effective_live_ids

    def _expire_owner_leases(self, context) -> None:
        now = time.monotonic()
        expired_owner_keys = [
            owner_key
            for owner_key, expiry in self._owner_lease_expiry_monotonic.items()
            if expiry <= now
        ]
        for owner_key in expired_owner_keys:
            owner = MCPOwnerIdentity(*owner_key)
            released_source_ids = set(
                self._owner_source_ids.pop(owner_key, set())
            )
            self._owner_lease_expiry_monotonic.pop(owner_key, None)
            self._run(
                self._runtime.release_mcp_owner(owner),
                timeout_seconds=_remaining_rpc_seconds(0, context),
                context=context,
            )
            self._discard_unleased_source_digests(released_source_ids)

    def _discard_unleased_source_digests(
        self,
        source_ids: set[str],
    ) -> None:
        retained = set().union(*self._owner_source_ids.values(), set())
        for source_id in source_ids - retained:
            self._source_configuration_digests.pop(source_id, None)

    def _schedule_runtime_cancel(
        self,
        run_id: str,
        call_id: str,
        owner: MCPOwnerIdentity,
    ) -> None:
        event_loop = self._ensure_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._runtime.cancel(run_id, call_id, owner),
            event_loop,
        )

        def consume_result(completed) -> None:
            try:
                completed.result()
            except BaseException:
                pass
            finally:
                self._export_runtime_metrics()

        future.add_done_callback(consume_result)

    def _export_runtime_metrics(self) -> None:
        if self._metrics_exporter is None:
            return
        snapshot_factory = getattr(self._runtime, "metrics_snapshot", None)
        if not callable(snapshot_factory):
            return
        self._metrics_exporter.set_metrics(
            _agent_runtime_metric_values(snapshot_factory())
        )

    @staticmethod
    def _run_event_loop(
        event_loop: asyncio.AbstractEventLoop,
        ready: threading.Event,
    ) -> None:
        asyncio.set_event_loop(event_loop)
        ready.set()
        event_loop.run_forever()

    def _run(
        self,
        coroutine,
        *,
        timeout_seconds: float | None = None,
        context=None,
    ):
        if timeout_seconds is not None and timeout_seconds <= 0:
            close_coroutine = getattr(coroutine, "close", None)
            if callable(close_coroutine):
                close_coroutine()
            raise futures.TimeoutError()
        event_loop = self._ensure_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            coroutine,
            event_loop,
        )
        if context is not None and hasattr(context, "add_callback"):
            callback_registered = context.add_callback(future.cancel)
            if callback_registered is False:
                future.cancel()
        try:
            return future.result(timeout=timeout_seconds)
        except (futures.TimeoutError, futures.CancelledError):
            future.cancel()
            raise

    def _run_rpc_admitted(
        self,
        coroutine_factory,
        *,
        timeout_seconds: float | None,
        context,
        on_disconnect,
    ):
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise futures.TimeoutError()
        event_loop = self._ensure_event_loop()
        admission = _RPCExecutionAdmission()

        async def execute_after_admission():
            await admission.wait()
            return await coroutine_factory()

        future = asyncio.run_coroutine_threadsafe(
            execute_after_admission(),
            event_loop,
        )
        admission.attach(future)

        def disconnect() -> None:
            admission.cancel()
            on_disconnect()

        if context is not None and hasattr(context, "add_callback"):
            callback_registered = context.add_callback(disconnect)
            if callback_registered is False:
                disconnect()
            else:
                admission.allow()
        else:
            admission.allow()
        try:
            return future.result(timeout=timeout_seconds)
        except (futures.TimeoutError, futures.CancelledError):
            admission.cancel()
            raise

    def _ensure_event_loop(self) -> asyncio.AbstractEventLoop:
        with self._event_loop_lock:
            if (
                self._event_loop is not None
                and self._event_loop.is_running()
            ):
                return self._event_loop
            event_loop = asyncio.new_event_loop()
            ready = threading.Event()
            event_loop_thread = threading.Thread(
                target=self._run_event_loop,
                args=(event_loop, ready),
                name="melix-tool-runtime",
                daemon=True,
            )
            self._event_loop = event_loop
            self._event_loop_thread = event_loop_thread
            event_loop_thread.start()
        ready.wait(timeout=5)
        if not event_loop.is_running():
            raise RuntimeError("tool runtime event loop failed to start")
        return event_loop


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
        environment: Mapping[str, str] | None = None,
    ) -> None:
        root = Path(jobs_root or _default_melix_home(environment) / "jobs" / "model-ops").resolve()
        self._core = MaintenanceCore(
            registry,
            jobs_root=root,
            hub_catalog=hub_catalog,
            lora_training_pipeline=lora_training_pipeline,
            adapter_activation_pipeline=adapter_activation_pipeline,
            benchmark_suite_catalog=benchmark_suite_catalog,
        )
        self._evaluation_jobs_root = (
            Path(evaluation_jobs_root).expanduser().resolve()
            if evaluation_jobs_root is not None
            else root.parent / "evaluation"
        )
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
            self._attach_evaluation_reproducibility_parameters(parameters)
            parameters.setdefault("dataset_id", request.dataset_id)
            if request.task_kind:
                parameters.setdefault("task_kind", request.task_kind)
            if request.source_repo:
                parameters.setdefault("source_repo", request.source_repo)
            scoring_mode = request.scoring_mode or request.profile.scoring_mode
            if scoring_mode in {"topic_membership_strict_micro_f1", "topic_membership_semantic_micro_f1"} or request.suite_id == "topic_membership":
                source_kind = request.source.WhichOneof("kind")
                if source_kind != "local_jsonl":
                    raise ValueError("topic_membership scoring requires --source-jsonl.")
                source_path = request.source.local_jsonl.path
                parameters.setdefault("topic_membership_source_jsonl", source_path)
                parameters.setdefault("evaluation_source_kind", "jsonl")
                parameters.setdefault("evaluation_source_locator", source_path)
                parameters.setdefault("dataset_id", request.dataset_id or "topic-membership")
                dataset_root = self._evaluation_materialization_root()
            elif scoring_mode == "event_extraction_weighted_f1":
                source_kind = request.source.WhichOneof("kind")
                if source_kind == "local_jsonl":
                    source_path = request.source.local_jsonl.path
                    parameters.setdefault("event_source_jsonl", source_path)
                    parameters.setdefault("evaluation_source_kind", "jsonl")
                    parameters.setdefault("evaluation_source_locator", source_path)
                    dataset_root = self._evaluation_materialization_root()
                elif source_kind is None:
                    resolved_dataset_id = request.dataset_id or _BUILTIN_EVENT_EXTRACTION_TOP20_DATASET_ID
                    dataset_root = self._default_dataset_root(resolved_dataset_id)
                    source_path = str((dataset_root / "samples.jsonl").resolve())
                    parameters["dataset_id"] = resolved_dataset_id
                    parameters.setdefault("event_source_jsonl", source_path)
                    parameters.setdefault("evaluation_source_kind", "builtin_package")
                    parameters.setdefault("evaluation_source_locator", source_path)
                    parameters.setdefault("event_dataset_root", str(dataset_root))
                else:
                    raise ValueError(
                        "event_extraction_weighted_f1 requires a built-in event extraction dataset "
                        "or --source-jsonl."
                    )
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
            result.evidence_path = str(run.persisted_paths.get("evidence", ""))
            for metric in run_result.metrics:
                metric_message = result.metrics.add()
                metric_message.name = metric.name
                metric_message.value = metric.value
                metric_message.unit = metric.unit
        return response

    def ExportResults(self, request, context):
        try:
            bundle_path = self._write_export_results_bundle(request)
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

    def ExportResultsStream(self, request, context):
        try:
            bundle_path = self._write_export_results_bundle(request)
            chunk_size = _EXPORT_RESULTS_STREAM_CHUNK_BYTES

            checksum = hashlib.sha256()
            chunk_count = 0
            with bundle_path.open("rb") as bundle_file:
                total_bytes = os.fstat(bundle_file.fileno()).st_size
                yield maintenance_pb2.ExportResultsEvent(
                    started=maintenance_pb2.ExportResultsStarted(
                        export_path=str(bundle_path),
                        total_bytes=total_bytes,
                        chunk_size=chunk_size,
                    )
                )

                while True:
                    data = bundle_file.read(chunk_size)
                    if not data:
                        break
                    checksum.update(data)
                    yield maintenance_pb2.ExportResultsEvent(
                        chunk=maintenance_pb2.ExportResultsChunk(
                            sequence=chunk_count,
                            data=data,
                        )
                    )
                    chunk_count += 1

            yield maintenance_pb2.ExportResultsEvent(
                completed=maintenance_pb2.ExportResultsCompleted(
                    export_path=str(bundle_path),
                    total_bytes=total_bytes,
                    chunk_count=chunk_count,
                    sha256=checksum.hexdigest(),
                )
            )
        except Exception as exc:
            yield maintenance_pb2.ExportResultsEvent(
                failed=common_pb2.ErrorStatus(code="export_failed", message=str(exc))
            )

    def _write_export_results_bundle(self, request) -> Path:
        jobs_root = Path(request.output_dir) if request.output_dir else self._evaluation_jobs_root.parent
        export_path = jobs_root / "export-bundle.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=export_path.parent,
            prefix="export-bundle-",
            suffix=".json.tmp",
        )
        os.close(temp_fd)
        temp_bundle_path = Path(temp_path)
        try:
            write_export_bundle(jobs_root, temp_bundle_path)
            os.replace(temp_bundle_path, export_path)
        except Exception:
            temp_bundle_path.unlink(missing_ok=True)
            raise
        return export_path

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
        repo_root = Path(os.environ.get("MELIX_REPO_ROOT", "").strip() or Path.cwd())
        return (
            repo_root
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
    def _attach_evaluation_reproducibility_parameters(parameters: dict[str, str]) -> None:
        hints_path = str(parameters.get("hints_path") or "").strip()
        if hints_path and not str(parameters.get("hints_format") or "").strip():
            parameters["hints_format"] = WorkerMaintenanceService._hints_format(Path(hints_path))

    @staticmethod
    def _hints_format(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix == ".md":
            return "markdown"
        if suffix == ".txt":
            return "text"
        return suffix.lstrip(".") or "text"

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
    environment: Mapping[str, str] | None = None,
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
        environment=environment,
    )


def _catalog_owner(request) -> MCPOwnerIdentity:
    return MCPOwnerIdentity(
        session_id=request.id.session_id,
        branch_id=request.id.branch_id,
        actor_id=request.owner_actor_id,
    )


def _catalog_lease_ttl_seconds(request) -> float:
    ttl_ms = int(request.lease_ttl_ms or _DEFAULT_MCP_SOURCE_LEASE_TTL_MS)
    if ttl_ms < 1 or ttl_ms > _MAX_MCP_SOURCE_LEASE_TTL_MS:
        raise ValueError(
            "MCP source lease_ttl_ms must be between 1 and "
            f"{_MAX_MCP_SOURCE_LEASE_TTL_MS}"
        )
    return ttl_ms / 1_000


def _validated_cancellation_correlation_id(value: str) -> str:
    if not value.strip():
        raise ValueError("cancellation_id must not be blank")
    if "\x00" in value or len(value.encode("utf-8")) > 256:
        raise ValueError("cancellation_id is invalid")
    return value


def _tool_cancellation_disposition(value: str) -> int:
    return {
        "accepted": tool_runtime_pb2.TOOL_CANCELLATION_ACCEPTED,
        "already_terminal": (
            tool_runtime_pb2.TOOL_CANCELLATION_ALREADY_TERMINAL
        ),
        "too_late": tool_runtime_pb2.TOOL_CANCELLATION_TOO_LATE,
        "not_found": tool_runtime_pb2.TOOL_CANCELLATION_NOT_FOUND,
        "scope_mismatch": (
            tool_runtime_pb2.TOOL_CANCELLATION_SCOPE_MISMATCH
        ),
    }.get(
        value,
        tool_runtime_pb2.TOOL_CANCELLATION_DISPOSITION_UNSPECIFIED,
    )


def _tool_side_effect_state(value: str) -> int:
    return {
        "none": tool_runtime_pb2.TOOL_SIDE_EFFECT_NONE,
        "committed": tool_runtime_pb2.TOOL_SIDE_EFFECT_COMMITTED,
        "unknown": tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN,
    }.get(
        value,
        tool_runtime_pb2.TOOL_SIDE_EFFECT_STATE_UNSPECIFIED,
    )


def _mcp_source_definition(source) -> MCPSourceDefinition:
    transport_kind = source.WhichOneof("transport")
    if transport_kind == "stdio":
        transport = MCPStdioTransport(
            command=source.stdio.command,
            arguments=tuple(source.stdio.arguments),
            working_directory=source.stdio.working_directory or None,
            environment_references=dict(
                source.stdio.environment_references
            ),
        )
    elif transport_kind == "streamable_http":
        transport = MCPStreamableHTTPTransport(
            url=source.streamable_http.url,
            headers=dict(source.streamable_http.headers),
            header_environment_references=dict(
                source.streamable_http.header_environment_references
            ),
        )
    else:
        raise ValueError("MCP source transport is required")
    return MCPSourceDefinition(
        source_id=source.source_id,
        transport=transport,
        request_timeout_seconds=(
            source.request_timeout_ms / 1_000
            if source.request_timeout_ms
            else 30.0
        ),
        connect_timeout_seconds=(
            source.connect_timeout_ms / 1_000
            if source.connect_timeout_ms
            else 15.0
        ),
        max_result_bytes=(
            int(source.max_result_bytes)
            if source.max_result_bytes
            else 262_144
        ),
        redaction_terms=tuple(source.redaction_terms),
    )


def _mcp_catalog_request_limit_error(sources) -> str | None:
    if len(sources) > MAX_MCP_CONFIG_SOURCES:
        return "source_count"

    reference_count = 0
    http_header_count = 0
    source_keys: set[str] = set()
    reference_target_names: list[str] = []
    http_header_names: list[str] = []
    for source in sources:
        transport_kind = source.WhichOneof("transport")
        if transport_kind == "stdio":
            references = source.stdio.environment_references
            reference_count += len(references)
            source_keys.update(references.values())
            reference_target_names.extend(references.keys())
        elif transport_kind == "streamable_http":
            references = source.streamable_http.header_environment_references
            headers = source.streamable_http.headers
            reference_count += len(references)
            http_header_count += len(references) + len(headers)
            source_keys.update(references.values())
            reference_target_names.extend(references.keys())
            http_header_names.extend(references.keys())
            http_header_names.extend(headers.keys())

    if (
        reference_count > MAX_MCP_CREDENTIAL_REFERENCES
        or http_header_count > MAX_MCP_CREDENTIAL_REFERENCES
    ):
        return "reference_count"
    encoded_source_key_bytes = sum(
        len(key.encode("utf-8")) for key in source_keys
    ) + max(0, len(source_keys) - 1)
    if encoded_source_key_bytes > MAX_MCP_CREDENTIAL_KEY_LIST_BYTES:
        return "source_key_bytes"
    encoded_reference_target_name_bytes = sum(
        len(name.encode("utf-8")) for name in reference_target_names
    ) + max(0, len(reference_target_names) - 1)
    if encoded_reference_target_name_bytes > MAX_MCP_REFERENCE_TARGET_LIST_BYTES:
        return "target_name_bytes"
    encoded_http_header_name_bytes = sum(
        len(name.encode("utf-8")) for name in http_header_names
    ) + max(0, len(http_header_names) - 1)
    if encoded_http_header_name_bytes > MAX_MCP_REFERENCE_TARGET_LIST_BYTES:
        return "http_header_name_bytes"
    return None


def _agent_tool_definition(tool) -> tool_runtime_pb2.AgentToolDefinition:
    return tool_runtime_pb2.AgentToolDefinition(
        source_id=tool.source_id,
        adapter_kind=tool.adapter_kind,
        name=tool.name,
        source_tool_name=tool.source_tool_name,
        title=tool.title,
        description=tool.description,
        input_schema_json=json.dumps(
            tool.input_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        output_schema_json=(
            json.dumps(
                tool.output_schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if tool.output_schema is not None
            else ""
        ),
        schema_digest=tool.schema_digest,
        risk_class=tool.risk_class,
        replayability=tool.replayability,
        annotations_untrusted=tool.annotations_untrusted,
    )


def _public_tool_error_message(error: BaseException) -> str:
    code = getattr(error, "code", "")
    if code == "tool_admission_required":
        return "Tool execution requires operator approval."
    if code == "tool_not_found":
        return "The requested tool is unavailable."
    if isinstance(error, json.JSONDecodeError):
        return "Tool arguments must be a valid JSON object."
    return "Tool execution failed."


def _remaining_rpc_seconds(
    deadline_unix_ms: int,
    context,
) -> float | None:
    candidates: list[float] = []
    if deadline_unix_ms:
        candidates.append(
            max(
                0.0,
                (deadline_unix_ms - int(time.time() * 1_000)) / 1_000,
            )
        )
    if context is not None and hasattr(context, "time_remaining"):
        context_remaining = context.time_remaining()
        if context_remaining is not None:
            try:
                context_seconds = float(context_remaining)
            except (TypeError, ValueError, OverflowError):
                context_seconds = float("inf")
            if (
                math.isfinite(context_seconds)
                and context_seconds <= threading.TIMEOUT_MAX
            ):
                candidates.append(max(0.0, context_seconds))
    return min(candidates) if candidates else None


def _abort_rpc_deadline(context, message: str) -> None:
    if context is not None and hasattr(context, "abort"):
        context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, message)
    raise futures.TimeoutError(message)


def _abort_rpc_invalid_argument(context, message: str) -> None:
    if context is not None and hasattr(context, "abort"):
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, message)
    raise ValueError(message)


def build_server(
    socket_path: str,
    registry: WorkerRegistry | None = None,
    backend_mode: str = "auto",
    metrics_exporter: BootstrapMetricsExporter | None = None,
    environment: Mapping[str, str] | None = None,
):
    environment = os.environ if environment is None else environment
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
        jobs_root=_resolved_env_path("MELIX_MODEL_OPS_JOBS_ROOT", environment),
        evaluation_jobs_root=_resolved_env_path("MELIX_EVALUATION_JOBS_ROOT", environment),
        backend_mode=backend_mode,
        environment=environment,
    )
    cache_service = WorkerCacheService(registry)
    tool_runtime_service = WorkerToolRuntimeService(
        environment=environment,
        metrics_exporter=metrics_exporter,
    )
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(runtime_service, server)
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(inference_service, server)
    maintenance_pb2_grpc.add_MaintenanceServiceServicer_to_server(maintenance_service, server)
    cache_pb2_grpc.add_CacheServiceServicer_to_server(cache_service, server)
    tool_runtime_pb2_grpc.add_ToolRuntimeServiceServicer_to_server(
        tool_runtime_service,
        server,
    )
    server.add_insecure_port(f"unix://{socket_path}")
    if metrics_exporter is not None:
        metrics_exporter.set_milliseconds(
            "python_worker.server_build_ms",
            _elapsed_milliseconds_since(server_build_started_at),
        )
    return server, runtime_service, inference_service


def _resolved_env_path(key: str, environment: Mapping[str, str] | None = None) -> Path | None:
    environment = os.environ if environment is None else environment
    raw_value = environment.get(key, "").strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser().resolve()


def _default_melix_home(environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    raw_home = environment.get("MELIX_HOME", "").strip()
    return Path(raw_home or Path.home() / ".melix").expanduser().resolve()


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
