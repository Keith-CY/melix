# Quantization Release Gates

## Purpose

Run deterministic benchmark evidence and fail-closed regression checks for the current quantized artifact profiles.

## Commands

Benchmark evidence:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/quantization_benchmarks.py --json
```

Regression gate:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/quantization_release_gate.py --json
```

## Policy

Thresholds are versioned in:

```text
infra/release/quantization-release-gate-policy.json
```

The current gate checks:

- all `q2` through `q8` profiles are benchmarked
- all profiles pass smoke validation
- artifact and manifest sizes stay within deterministic bounds
- calibration sample counts remain explicit and non-zero
