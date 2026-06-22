from __future__ import annotations

import json
import os
from pathlib import Path
import hashlib

import pytest


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
