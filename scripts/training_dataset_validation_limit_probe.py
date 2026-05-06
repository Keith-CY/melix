from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops.training_dataset import load_training_dataset_package  # noqa: E402


def _write_package(package_path: Path, validation_rows: int) -> None:
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "validation-limit-probe",
                "format": "text_completion",
                "sample_count": 1,
                "version": "1",
                "validation_sample_count": validation_rows,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        json.dumps({"text": "train-row"}) + "\n",
        encoding="utf-8",
    )
    with (package_path / "valid.jsonl").open("w", encoding="utf-8") as handle:
        for index in range(validation_rows):
            handle.write(json.dumps({"text": f"validation-{index}"}) + "\n")


def main() -> None:
    validation_rows = 50_000
    samples: list[dict[str, float]] = []
    with tempfile.TemporaryDirectory(prefix="melix-validation-limit-probe-") as temp_dir:
        package_path = Path(temp_dir) / "package"
        _write_package(package_path, validation_rows)
        for _ in range(5):
            tracemalloc.start()
            started = time.perf_counter()
            package = load_training_dataset_package(str(package_path), sample_limit=1)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            samples.append(
                {
                    "elapsed_ms": elapsed_ms,
                    "peak_bytes": float(peak_bytes),
                    "validation_sample_count": float(package.validation_sample_count),
                }
            )

    result = {
        "elapsed_ms_mean": statistics.fmean(sample["elapsed_ms"] for sample in samples),
        "peak_bytes_mean": statistics.fmean(sample["peak_bytes"] for sample in samples),
        "validation_sample_count_mean": statistics.fmean(
            sample["validation_sample_count"] for sample in samples
        ),
        "synthetic_validation_rows": float(validation_rows),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
