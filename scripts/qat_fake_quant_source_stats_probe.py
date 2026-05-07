from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops.quantization_pipeline import _qat_fake_quant_error_table, _qat_fake_quant_source_stats


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw else default


def _write_source(path: Path, byte_count: int) -> bytes:
    pattern = bytes((index * 37 + 17) % 256 for index in range(4096))
    repeats, remainder = divmod(byte_count, len(pattern))
    payload = pattern * repeats + pattern[:remainder]
    path.write_bytes(payload)
    return payload


def main() -> int:
    byte_count = _int_env("MELIX_QAT_STATS_PROBE_BYTES", 5_000_000)
    sample_count = _int_env("MELIX_QAT_STATS_PROBE_SAMPLES", 5)
    q_bits = _int_env("MELIX_QAT_STATS_PROBE_Q_BITS", 4)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    source_sha256 = ""
    quant_error_proxy_mean = 0.0
    quant_error_proxy_max = 0.0
    table_builds = 0
    with tempfile.TemporaryDirectory(prefix="melix-qat-stats-probe-") as directory:
        source_path = Path(directory) / "source.safetensors"
        _write_source(source_path, byte_count)
        _qat_fake_quant_error_table.cache_clear()
        previous_misses = _qat_fake_quant_error_table.cache_info().misses
        for _ in range(sample_count):
            tracemalloc.start()
            started = time.perf_counter()
            stats = _qat_fake_quant_source_stats([source_path], q_bits=q_bits)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            info = _qat_fake_quant_error_table.cache_info()
            table_builds += info.misses - previous_misses
            previous_misses = info.misses
            if stats["source_byte_count"] != byte_count:
                raise SystemExit(f"unexpected byte count: {stats['source_byte_count']} != {byte_count}")
            source_sha256 = str(stats["source_sha256"])
            quant_error_proxy_mean = float(stats["quant_error_proxy_mean"])
            quant_error_proxy_max = float(stats["quant_error_proxy_max"])
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 1),
                "source_byte_count": float(byte_count),
                "sample_count": float(sample_count),
                "q_bits": float(q_bits),
                "error_table_builds": float(table_builds),
                "quant_error_proxy_mean": quant_error_proxy_mean,
                "quant_error_proxy_max": quant_error_proxy_max,
                "source_sha256_prefix_length": float(len(source_sha256[:12])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
