from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import MLXLMRunner, TrainingMetrics, TrainingRequest, TrainingResult


class ProbeRunner(MLXLMRunner):
    def is_native_available(self) -> bool:
        return True

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"probe-weights")
        adapter_config_path.write_text("{}\n", encoding="utf-8")
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1.0,
                tokens_seen=12,
                examples_seen=2,
                loss_final=0.5,
                loss_best=0.4,
                learning_rate_final=1e-5,
            ),
            execution_backend="probe",
        )


def _write_dataset_package(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "probe-dataset",
                "format": "prompt_completion",
                "sample_count": 2,
                "validation_sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "samples.jsonl").write_text(
        '{"prompt":"alpha","completion":"beta"}\n'
        '{"prompt":"gamma","completion":"delta"}\n',
        encoding="utf-8",
    )
    (path / "valid.jsonl").write_text(
        '{"prompt":"holdout","completion":"answer"}\n',
        encoding="utf-8",
    )
    return path


def _run_once(index: int) -> tuple[float, int, int, int]:
    original_write_text = Path.write_text
    original_read_text = Path.read_text
    manifest_write_count = 0
    manifest_read_count = 0

    def counting_write_text(self: Path, data: str, *args: object, **kwargs: object) -> int:
        nonlocal manifest_write_count
        if self.parts[-2:] == ("normalized_dataset", "manifest.json"):
            manifest_write_count += 1
        return original_write_text(self, data, *args, **kwargs)

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal manifest_read_count
        if self.parts[-2:] == ("normalized_dataset", "manifest.json"):
            manifest_read_count += 1
        return original_read_text(self, *args, **kwargs)

    with tempfile.TemporaryDirectory(prefix="melix-lora-manifest-probe-") as temp_dir:
        temp_root = Path(temp_dir)
        dataset_path = _write_dataset_package(temp_root / "dataset")
        output_dir = temp_root / "output"
        source_model = common_pb2.ModelSpec(
            model_id="probe-model",
            model_path=str(temp_root / "base-model"),
            revision="main",
            model_kind="text",
        )
        pipeline = LoRATrainingPipeline(runner=ProbeRunner())
        Path.write_text = counting_write_text  # type: ignore[method-assign]
        Path.read_text = counting_read_text  # type: ignore[method-assign]
        try:
            start = time.perf_counter()
            result = pipeline.run(
                job_id=f"probe-{index}",
                request_ext={
                    "dataset_uri": str(dataset_path),
                    "adapter_name": "probe-adapter",
                },
                source_model=source_model,
                output_dir=output_dir,
                jobs_root=temp_root / "jobs",
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
        finally:
            Path.write_text = original_write_text  # type: ignore[method-assign]
            Path.read_text = original_read_text  # type: ignore[method-assign]

        payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        normalized_manifest = Path(payload["normalized_dataset_manifest_path"])
        normalized_payload = json.loads(normalized_manifest.read_text(encoding="utf-8"))
        checksum = int(normalized_payload["validation_sample_count"])
        checksum += int(normalized_payload["validation_strategy"] == "none")
        return elapsed_ms, manifest_write_count, manifest_read_count, checksum


def main() -> None:
    elapsed_ms: list[float] = []
    manifest_write_counts: list[int] = []
    manifest_read_counts: list[int] = []
    checksum_total = 0
    iteration_count = 12
    for index in range(iteration_count):
        elapsed, write_count, read_count, checksum = _run_once(index)
        elapsed_ms.append(elapsed)
        manifest_write_counts.append(write_count)
        manifest_read_counts.append(read_count)
        checksum_total += checksum
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.mean(elapsed_ms),
                "manifest_write_text_calls_mean": statistics.mean(manifest_write_counts),
                "manifest_read_text_calls_mean": statistics.mean(manifest_read_counts),
                "iteration_count": float(iteration_count),
                "manifest_checksum": float(checksum_total),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
