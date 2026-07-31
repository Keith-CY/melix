from __future__ import annotations

import json
from pathlib import Path
import time
import urllib.request

import grpc
import pytest

from packages.protocol.python.worker.v1 import runtime_pb2, runtime_pb2_grpc
from tests.integration.helpers import LiveMelixStack, read_metrics_export


def _post_embedding(stack: LiveMelixStack, request_id: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{stack.http_port}/v1/embeddings",
        data=json.dumps({
            "id": request_id,
            "model": "melix-dev-embed",
            "input": ["backend identity recovery"],
        }).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def _loaded_embedding_generation(socket_path: Path) -> tuple[int, int]:
    channel = grpc.insecure_channel(f"unix://{socket_path}")
    try:
        stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        loaded = stub.ListLoadedModels(
            runtime_pb2.ListLoadedModelsRequest(),
            timeout=5,
        ).loaded_models
        embeddings = [item for item in loaded if item.model.model_id == "melix-dev-embed"]
        generation = (
            embeddings[0].backend_identity.route_generation if embeddings else 0
        )
        return len(embeddings), generation
    finally:
        channel.close()


def _worker_mismatch_count(socket_path: Path) -> int:
    channel = grpc.insecure_channel(f"unix://{socket_path}")
    try:
        stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        return stub.GetRuntimeStats(
            runtime_pb2.GetRuntimeStatsRequest(),
            timeout=5,
        ).stats.model_identity_mismatch_count
    finally:
        channel.close()


def _wait_for_recovery_metrics(path: Path) -> dict[str, float]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            values = read_metrics_export(path).get("values", {})
            if values.get("control_plane.backend_identity_fresh_binding_count") == 1:
                return values
        time.sleep(0.1)
    raise AssertionError(f"backend identity recovery metrics were not exported to {path}")


def test_python_worker_restart_recovers_stale_binding_once_on_same_uds() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_PYTHONPATH_PREFIX": str(repo_root)},
    )
    try:
        stack.start()
        with pytest.raises(RuntimeError, match="python worker is already running"):
            stack.start_python_worker()
        stack.wait_for_models(["melix-dev-embed"])
        initial_payload = _post_embedding(stack, "identity-before-restart")
        initial_count, initial_generation = _loaded_embedding_generation(
            stack.python_socket_path
        )
        assert initial_payload["model"] == "melix-dev-embed"
        assert len(initial_payload["data"]) == 1
        assert initial_count == 1
        assert initial_generation > 0

        old_worker = stack.python_worker
        assert old_worker is not None
        old_pid = old_worker.pid
        control_plane_pid = stack.control_plane.pid if stack.control_plane is not None else 0
        socket_path = stack.python_socket_path
        stack.stop_python_worker()
        assert old_worker.poll() is not None
        assert old_worker.pid == old_pid
        assert stack.control_plane is not None
        assert stack.control_plane.pid == control_plane_pid
        assert stack.control_plane.poll() is None

        stack.start_python_worker()
        assert stack.python_socket_path == socket_path
        assert stack.python_worker is not None
        assert stack.python_worker.pid != old_pid
        assert _loaded_embedding_generation(stack.python_socket_path) == (0, 0)

        recovered_payload = _post_embedding(stack, "identity-after-restart")
        recovered_count, recovered_generation = _loaded_embedding_generation(
            stack.python_socket_path
        )
        metrics = _wait_for_recovery_metrics(stack.control_plane_metrics_path)

        assert recovered_payload["model"] == "melix-dev-embed"
        assert len(recovered_payload["data"]) == 1
        assert recovered_count == 1
        assert recovered_generation > initial_generation
        assert _worker_mismatch_count(stack.python_socket_path) == 1
        assert metrics["control_plane.backend_identity_retry_allowed_count"] == 1
        assert metrics.get("control_plane.backend_identity_retry_exhausted_count", 0) == 0
        assert metrics["control_plane.backend_identity_fresh_binding_count"] == 1
    finally:
        stack.stop()
