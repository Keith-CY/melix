from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from test_maintenance_service import RecordingBenchmarkBackend, build_service
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime


def test_export_results_stream_chunks_large_export_bundle(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=RecordingBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(environment={}),
    )
    service = build_service(tmp_path, registry=registry)
    dataset_root = tmp_path / "datasets" / "qa_smoke.dev.v1"
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": "qa_smoke.dev.v1",
                "suite_id": "mmlu",
                "version": "2026-03-31",
                "sample_count": 1,
                "split": "validation",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        json.dumps({"prompt": "2+2?", "expected": "4"}) + "\n",
        encoding="utf-8",
    )

    evaluation = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="mmlu",
            dataset_id="qa_smoke.dev.v1",
            dataset_root=str(dataset_root),
            sample_size=1,
        ),
        context=None,
    )
    assert evaluation.ok is True

    evidence_path = Path(evaluation.results[0].evidence_path)
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.large_export_test_evidence.v1",
                "payload": "x" * (5 * 1024 * 1024),
            }
        ),
        encoding="utf-8",
    )

    events = list(
        service.ExportResultsStream(
            maintenance_pb2.ExportResultsRequest(),
            context=None,
        )
    )

    assert events[0].HasField("started")
    assert events[-1].HasField("completed")
    chunks = [event.chunk for event in events if event.HasField("chunk")]
    assert len(chunks) > 1
    assert max(len(chunk.data) for chunk in chunks) < 4 * 1024 * 1024
    assert [chunk.sequence for chunk in chunks] == list(range(len(chunks)))

    payload_bytes = b"".join(chunk.data for chunk in chunks)
    assert len(payload_bytes) == events[0].started.total_bytes
    assert len(payload_bytes) == events[-1].completed.total_bytes
    assert events[-1].completed.chunk_count == len(chunks)
    assert hashlib.sha256(payload_bytes).hexdigest() == events[-1].completed.sha256

    payload = json.loads(payload_bytes.decode("utf-8"))
    assert payload["evaluation_jobs"][0]["job_id"] == evaluation.job.job_id


def test_export_results_stream_yields_failed_event_on_export_error(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    def fail_export_bundle(request):
        raise RuntimeError("export bundle unavailable")

    service._write_export_results_bundle = fail_export_bundle

    events = list(
        service.ExportResultsStream(
            maintenance_pb2.ExportResultsRequest(),
            context=None,
        )
    )

    assert len(events) == 1
    assert events[0].HasField("failed")
    assert events[0].failed.code == "export_failed"
    assert events[0].failed.message == "export bundle unavailable"


def test_export_results_stream_writes_json_named_temporary_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from worker import grpc_server as grpc_server_module

    service = build_service(tmp_path)
    jobs_root = tmp_path / "json-temporary-bundle"
    jobs_root.mkdir()
    observed_path: Path | None = None

    def fake_write_export_bundle(jobs_root_arg: Path, export_path_arg: Path) -> Path:
        nonlocal observed_path
        observed_path = Path(export_path_arg)
        observed_path.write_text("{}", encoding="utf-8")
        return observed_path

    monkeypatch.setattr(grpc_server_module, "write_export_bundle", fake_write_export_bundle)

    events = list(
        service.ExportResultsStream(
            maintenance_pb2.ExportResultsRequest(output_dir=str(jobs_root)),
            context=None,
        )
    )

    assert events[-1].HasField("completed")
    assert observed_path is not None
    assert observed_path.name.startswith("export-bundle-")
    assert observed_path.name.endswith(".json.tmp")


def test_export_results_stream_keeps_active_reader_stable_during_concurrent_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from worker import grpc_server as grpc_server_module

    service = build_service(tmp_path)
    jobs_root = tmp_path / "concurrent-export"
    jobs_root.mkdir()
    first_payload = b"a" * ((2 * 1024 * 1024) + 17)
    second_payload = b"b" * ((2 * 1024 * 1024) + 17)
    call_count = 0

    def fake_write_export_bundle(jobs_root_arg: Path, export_path_arg: Path) -> Path:
        nonlocal call_count
        call_count += 1
        payload = first_payload if call_count == 1 else second_payload
        Path(export_path_arg).write_bytes(payload)
        return Path(export_path_arg)

    monkeypatch.setattr(grpc_server_module, "write_export_bundle", fake_write_export_bundle)

    first_stream = service.ExportResultsStream(
        maintenance_pb2.ExportResultsRequest(output_dir=str(jobs_root)),
        context=None,
    )
    first_started = next(first_stream)
    assert first_started.HasField("started")

    second_events = list(
        service.ExportResultsStream(
            maintenance_pb2.ExportResultsRequest(output_dir=str(jobs_root)),
            context=None,
        )
    )

    first_chunks = [bytes(event.chunk.data) for event in first_stream if event.HasField("chunk")]
    assert b"".join(first_chunks) == first_payload

    second_chunks = [bytes(event.chunk.data) for event in second_events if event.HasField("chunk")]
    assert b"".join(second_chunks) == second_payload
