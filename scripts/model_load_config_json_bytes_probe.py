from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc

from worker.model_load_trust import ModelLoadTrustRejection, resolve_model_load_trust_policy
from worker.model_registry.catalog import WorkerModelCatalog


class _TrustRuntime:
    runtime_name = "mlx-lm"


def _sample_count() -> int:
    raw = os.environ.get("MELIX_MODEL_LOAD_CONFIG_BYTES_PROBE_SAMPLES", "7")
    try:
        value = int(raw)
    except ValueError:
        value = 7
    return max(3, value)


def _iterations() -> int:
    raw = os.environ.get("MELIX_MODEL_LOAD_CONFIG_BYTES_PROBE_ITERATIONS", "300")
    try:
        value = int(raw)
    except ValueError:
        value = 300
    return max(10, value)


def _config_padding_bytes() -> int:
    raw = os.environ.get("MELIX_MODEL_LOAD_CONFIG_BYTES_PROBE_PADDING_BYTES", "4096")
    try:
        value = int(raw)
    except ValueError:
        value = 4096
    return max(0, value)


def _model_spec(model_dir: Path):
    model = WorkerModelCatalog.dev_text_model()
    model.model_path = str(model_dir)
    return model


def _write_config(model_dir: Path, *, padding_bytes: int) -> None:
    payload = {
        "architectures": ["CustomForCausalLM"],
        "auto_map": {"AutoModelForCausalLM": "custom.Loader"},
        "model_type": "custom",
        "padding": "x" * padding_bytes,
    }
    (model_dir / "config.json").write_bytes(json.dumps(payload).encode("utf-8"))


def _run_sample(model, iterations: int) -> tuple[float, int, int]:
    runtime = _TrustRuntime()
    rejection_count = 0
    started = time.perf_counter()
    tracemalloc.start()
    for _ in range(iterations):
        try:
            resolve_model_load_trust_policy(
                model,
                request_policy=None,
                runtime_kind="text",
                runtime=runtime,
            )
        except ModelLoadTrustRejection as exc:
            if exc.policy.custom_loader_required:
                rejection_count += 1
            else:  # pragma: no cover - defensive guard for malformed probe setup.
                raise
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, peak_bytes, rejection_count


def main() -> int:
    samples = _sample_count()
    iterations = _iterations()
    padding_bytes = _config_padding_bytes()
    elapsed_values: list[float] = []
    peak_values: list[int] = []
    rejection_values: list[int] = []

    with tempfile.TemporaryDirectory() as tmp:
        model_dir = Path(tmp) / "custom-loader-model"
        model_dir.mkdir()
        _write_config(model_dir, padding_bytes=padding_bytes)
        model = _model_spec(model_dir)
        for _ in range(samples):
            elapsed_ms, peak_bytes, rejection_count = _run_sample(model, iterations)
            elapsed_values.append(elapsed_ms)
            peak_values.append(peak_bytes)
            rejection_values.append(rejection_count)

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_values),
        "elapsed_ms_min": min(elapsed_values),
        "peak_bytes_mean": statistics.fmean(peak_values),
        "samples": samples,
        "iterations": iterations,
        "config_padding_bytes": padding_bytes,
        "rejections_mean": statistics.fmean(rejection_values),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
