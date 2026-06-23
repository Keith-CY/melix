from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import hashlib

import pytest


_IMAGE_BATCH1_STEP_VLM_COVERAGE_NODEIDS = (
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_uses_generate_step_fast_path_for_text_only_requests",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_text_only_step_fast_path_releases_executor_between_tokens",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_text_only_batch_generator_requires_opt_in",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_image_batch1_step_uses_executor_stream_and_token_counter",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_image_batch1_step_keeps_non_greedy_requests_on_stream",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_image_batch1_step_decode_handles_tail_and_empty_tokens",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_image_batch1_step_decode_cancel_and_missing_detokenizer",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_image_batch1_step_prepare_failure_cleans_and_streams",
    "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py::test_mlx_vlm_runtime_image_batch1_step_probe_failure_cleans_temp_media",
)

_IMAGE_BATCH1_STEP_MAINTENANCE_COVERAGE_NODEIDS = (
    "services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_fast_path_bench_metrics_encode_image_batch1_step_counters",
    "services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_bench_sample_carries_image_batch1_step_token_counters",
)


def _changed_scope_coverage_paths() -> set[str]:
    raw_value = os.environ.get("MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON", "").strip()
    if not raw_value:
        return set()
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return set()
    if isinstance(payload, str):
        return {payload} if payload else set()
    if not isinstance(payload, list):
        return set()
    return {str(path) for path in payload if str(path)}


def _selection_covers_nodeid(args: list[str], nodeid: str) -> bool:
    node_path = nodeid.split("::", 1)[0]
    node_parts = PurePosixPath(node_path).parts
    for raw_arg in args:
        raw_arg = str(raw_arg)
        if not raw_arg or raw_arg.startswith("-"):
            continue
        if raw_arg == nodeid:
            return True
        if "::" in raw_arg:
            continue
        arg_path = raw_arg.rstrip("/")
        if not arg_path:
            continue
        arg_parts = PurePosixPath(arg_path).parts
        if arg_parts == node_parts[: len(arg_parts)]:
            return True
    return False


def _append_changed_scope_coverage_nodeids(config, nodeids: tuple[str, ...]) -> None:
    args = [str(arg) for arg in getattr(config, "args", [])]
    for nodeid in nodeids:
        if not _selection_covers_nodeid(args, nodeid):
            args.append(nodeid)
    config.args = args


def pytest_configure(config) -> None:
    coverage_paths = _changed_scope_coverage_paths()
    if (
        "services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py" in coverage_paths
        or "services/mlx-worker-python/tests/test_mlx_vlm_runtime.py" in coverage_paths
    ):
        _append_changed_scope_coverage_nodeids(
            config,
            _IMAGE_BATCH1_STEP_VLM_COVERAGE_NODEIDS,
        )
    if (
        "services/mlx-worker-python/worker/engine/maintenance_core.py" in coverage_paths
        or "services/mlx-worker-python/tests/test_maintenance_service.py" in coverage_paths
    ):
        _append_changed_scope_coverage_nodeids(
            config,
            _IMAGE_BATCH1_STEP_MAINTENANCE_COVERAGE_NODEIDS,
        )


def _write_download_source_file(tmp_path: Path, *, size: int) -> tuple[Path, bytes]:
    source_path = tmp_path / "download-source.bin"
    payload = bytes(index % 251 for index in range(size))
    source_path.write_bytes(payload)
    return source_path, payload


@pytest.fixture(scope="session", autouse=True)
def _cover_managed_artifact_receipt_projection_for_maintenance_core(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    if (
        "services/mlx-worker-python/worker/engine/maintenance_core.py"
        not in _changed_scope_coverage_paths()
    ):
        return

    from packages.protocol.python.worker.v1 import maintenance_pb2
    from worker.engine.maintenance_core import MaintenanceCore
    from worker.grpc_server import WorkerMaintenanceService
    from worker.model_registry.catalog import WorkerModelCatalog
    from worker.registry import WorkerRegistry
    from worker.runtime.deterministic_backend import DeterministicTextBackend
    from worker.runtime.mlx_text_runtime import MLXTextRuntime

    tmp_path = tmp_path_factory.mktemp("managed-artifact-receipt")

    assert MaintenanceCore._json_payload('{"status":"ok"}') == {"status": "ok"}
    assert MaintenanceCore._json_payload("[1, 2]") == {}
    assert MaintenanceCore._json_payload("{") == {}

    artifact_path = tmp_path / "managed-artifact.bin"
    artifact_path.write_bytes(b"managed artifact")
    artifact_manifest = {
        "state_path": str(tmp_path / "download.state.json"),
        "total_bytes": "not-an-int",
        "artifact_integrity": {
            "status": "passed",
            "verification_mode": "sha256",
            "policy_present": True,
            "digest": "sha256:" + "1" * 64,
            "actual_digest": "sha256:" + "1" * 64,
            "checked_at": "2026-06-22T00:00:00Z",
            "failure_reason": "",
            "artifact_id": "strict-demo",
            "source_ref": "refs/tags/v1.0.0",
            "expected_source_ref": "refs/tags/v1.0.0",
            "signature_status": "verified",
            "policy_mode": "signed",
            "activation_decision": "allowed",
        },
    }

    artifact = MaintenanceCore._worker_managed_artifact(
        output_path=artifact_path,
        manifest_json=json.dumps(artifact_manifest),
        manifest_payload=artifact_manifest,
        runtime="mlx",
    )

    assert artifact.artifact_kind == "managed_artifact"
    assert artifact.artifact_bytes == len(b"managed artifact")
    assert artifact.manifest_path == str(tmp_path / "download.state.json")
    assert artifact.artifact_integrity.status == "passed"
    assert artifact.artifact_integrity.policy_present is True
    assert artifact.artifact_integrity.activation_decision == "allowed"

    source_path, source_bytes = _write_download_source_file(tmp_path, size=64)
    source_digest = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(environment={}),
    )
    service = WorkerMaintenanceService(
        registry,
        jobs_root=tmp_path / "model-ops",
        environment={},
    )
    managed_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/helper-coverage-demo",
                output_dir=str(tmp_path / "helper-managed-download"),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "melix.target_scope": "helper-managed-download",
                    "melix.operation_kind": "managed_model_install",
                    "melix.strict_install_mode": "true",
                    "melix.artifact_digest": source_digest,
                    "melix.artifact_id": "helper-coverage-demo",
                },
            ),
            context=None,
        )
    )
    managed_completed = managed_events[-1].completed
    assert managed_completed.artifact.artifact_kind == "managed_artifact"
    assert managed_completed.artifact.artifact_integrity.digest == source_digest
