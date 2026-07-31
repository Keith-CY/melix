from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2

from worker.grpc_server import (
    WorkerInferenceService as ProductionWorkerInferenceService,
    WorkerRuntimeService as ProductionWorkerRuntimeService,
)

WorkerInferenceService = ProductionWorkerInferenceService


class WorkerRuntimeService(ProductionWorkerRuntimeService):
    """Test control-plane boundary that assigns a positive route generation."""

    def __init__(self, registry) -> None:
        super().__init__(registry)
        self._next_test_route_generation = 1

    def LoadModel(self, request, context):
        if request.HasField("backend_identity"):
            return super().LoadModel(request, context)

        bound_request = request.__class__()
        bound_request.CopyFrom(request)
        bound_request.backend_identity.CopyFrom(
            common_pb2.BackendModelIdentity(
                requested_model_id=request.model.model_id,
                requested_adapter_id=request.model.ext.get(
                    "melix.adapter_set_hash", ""
                ),
                route_generation=self._next_test_route_generation,
                worker_instance_id=self._registry.worker_id,
            )
        )
        self._next_test_route_generation += 1
        return super().LoadModel(bound_request, context)


def bind_backend_identity(
    service: ProductionWorkerInferenceService,
    request,
    *,
    source_handle: str | None = None,
):
    """Explicitly bind a test request to the service's current loaded residency."""

    identity_owner = (
        request.execution
        if "execution" in request.DESCRIPTOR.fields_by_name
        else request
    )
    if identity_owner.HasField("backend_identity"):
        return request
    loaded = service._registry.get_loaded_model(
        source_handle or identity_owner.model_handle
    )
    if loaded is not None:
        identity_owner.backend_identity.CopyFrom(loaded.backend_identity)
    return request
