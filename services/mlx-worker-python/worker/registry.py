from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2, runtime_pb2

from worker.engine.request_state import RequestState
from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime


@dataclass
class LoadedModel:
    handle: str
    spec: common_pb2.ModelSpec
    runtime_model: object
    estimated_resident_bytes: int
    runtime_kind: str


class WorkerRegistry:
    def __init__(
        self,
        runtime: MLXTextRuntime | None = None,
        embedding_runtime: DeterministicEmbeddingRuntime | None = None,
        model_catalog: WorkerModelCatalog | None = None,
        worker_id: str = "worker-text-001",
    ) -> None:
        self.runtime = runtime or MLXTextRuntime()
        self.embedding_runtime = embedding_runtime or DeterministicEmbeddingRuntime()
        self.model_catalog = model_catalog or WorkerModelCatalog()
        self.worker_id = worker_id
        self._lock = Lock()
        self._next_model_handle = 1
        self._loaded_models: dict[str, LoadedModel] = {}
        self._requests: dict[str, RequestState] = {}
        self._draining = False

    def capabilities(self) -> common_pb2.RuntimeCapabilities:
        return common_pb2.RuntimeCapabilities(
            cache=common_pb2.CacheCapabilities(
                supports_prefix_cache=True,
                supports_paged_cache=False,
                supports_disk_cache=False,
                kv_quant_profiles=["q4"],
                supports_boundary_snapshots=False,
            ),
            execution=common_pb2.ExecutionCapabilities(
                supports_continuous_batching=False,
                supports_speculative_decoding=False,
            ),
            parsing=common_pb2.ParserCapabilities(
                supports_tool_call_auto_parsing=False,
                supports_reasoning_separation=False,
            ),
            multimodal=common_pb2.MultimodalCapabilities(),
        )

    def load_model(self, model_spec: common_pb2.ModelSpec) -> LoadedModel:
        resolved = self.model_catalog.get(model_spec.model_id) or model_spec
        runtime_kind, runtime = self._runtime_for_model(resolved)
        runtime_model = runtime.load_model(resolved)
        estimated = runtime.estimate_resident_bytes(resolved)

        with self._lock:
            handle = f"{resolved.model_id}::{self._next_model_handle}"
            self._next_model_handle += 1
            loaded = LoadedModel(
                handle=handle,
                spec=resolved,
                runtime_model=runtime_model,
                estimated_resident_bytes=estimated,
                runtime_kind=runtime_kind,
            )
            self._loaded_models[handle] = loaded
            return loaded

    def unload_model(self, handle: str) -> bool:
        with self._lock:
            return self._loaded_models.pop(handle, None) is not None

    def get_loaded_model(self, handle: str) -> LoadedModel | None:
        with self._lock:
            return self._loaded_models.get(handle)

    def list_loaded_models(self) -> list[str]:
        with self._lock:
            return sorted(self._loaded_models)

    def start_request(self, request_id: str) -> RequestState:
        state = RequestState(request_id=request_id)
        with self._lock:
            self._requests[request_id] = state
        return state

    def get_request(self, request_id: str) -> RequestState | None:
        with self._lock:
            return self._requests.get(request_id)

    def finish_request(self, request_id: str) -> None:
        with self._lock:
            self._requests.pop(request_id, None)

    def abort_request(self, request_id: str) -> bool:
        with self._lock:
            state = self._requests.get(request_id)
        if state is None:
            return False
        state.cancel_event.set()
        return True

    def runtime_stats(self) -> runtime_pb2.RuntimeStats:
        with self._lock:
            active_requests = len(self._requests)
            resident_bytes = sum(item.estimated_resident_bytes for item in self._loaded_models.values())
        return runtime_pb2.RuntimeStats(
            worker_state="draining" if self._draining else "idle",
            resident_bytes=resident_bytes,
            active_requests=active_requests,
            active_prefills=0,
            active_decodes=0,
            l1_cache_bytes=0,
            l2_cache_bytes=0,
            l1_hit_rate=0.0,
            l2_hit_rate=0.0,
        )

    def set_draining(self, draining: bool) -> None:
        with self._lock:
            self._draining = draining

    def _runtime_for_model(self, model_spec: common_pb2.ModelSpec) -> tuple[str, Any]:
        if model_spec.model_kind == "embedding":
            return "embedding", self.embedding_runtime
        return "text", self.runtime
