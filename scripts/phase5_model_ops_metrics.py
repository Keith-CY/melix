from __future__ import annotations

from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def build_service(root: Path) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    return WorkerMaintenanceService(registry, jobs_root=root)


def artifact_size(path: Path) -> int:
    if path.is_dir():
        return sum(
            child.stat().st_size
            for child in path.rglob("*")
            if child.is_file()
        )
    return path.stat().st_size


def main() -> None:
    with TemporaryDirectory(prefix="melix-model-ops-") as tmpdir:
        root = Path(tmpdir)
        service = build_service(root)

        for operation in ("convert", "quantize", "download", "upload"):
            samples: list[float] = []
            artifact_bytes = 0
            manifest_bytes = 0

            for _ in range(20):
                request = maintenance_pb2.ConvertModelRequest(
                    source_model="melix-dev-text" if operation != "download" else "melix/demo-repo",
                    output_dir=str(root / operation),
                    weight_quant="q4" if operation == "quantize" else "",
                    kv_quant="q8" if operation == "quantize" else "",
                    generate_manifest=operation in {"convert", "quantize"},
                    run_smoke_test=operation == "quantize",
                    ext={"operation": operation, "target_repo": "melix/upload-target"},
                )

                started = perf_counter()
                events = list(service.ConvertModel(request, context=None))
                elapsed_ms = (perf_counter() - started) * 1000.0
                samples.append(elapsed_ms)

                completed = events[-1].completed
                artifact_path = Path(completed.output_path)
                artifact_bytes = (
                    int(completed.artifact.artifact_bytes)
                    if completed.HasField("artifact") and completed.artifact.artifact_bytes > 0
                    else artifact_size(artifact_path)
                )
                manifest = next((event.manifest for event in events if event.HasField("manifest")), None)
                manifest_bytes = 0
                if manifest is not None:
                    manifest_bytes = (
                        int(manifest.artifact.manifest_bytes)
                        if manifest.HasField("artifact") and manifest.artifact.manifest_bytes > 0
                        else len(manifest.manifest_json.encode("utf-8"))
                    )

            average_ms = mean(samples)
            print(
                f"job_kind={operation} "
                f"job_ms={average_ms:.3f} "
                f"artifact_bytes={artifact_bytes} "
                f"manifest_bytes={manifest_bytes}"
            )


if __name__ == "__main__":
    main()
