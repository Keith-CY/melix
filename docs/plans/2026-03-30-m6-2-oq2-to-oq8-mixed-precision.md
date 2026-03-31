# M6.2 OQ2 To OQ8 Mixed-Precision

## Goal

Add profile definitions and calibration-driven bit allocation for a family of mixed-precision quantization modes from low-bit to higher-bit outputs.

## Scope

- define profile schema for multiple quantization levels
- add calibration-driven allocation logic
- preserve compatibility with the shared artifact manifest model

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `packages/protocol/schema/worker/v1/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `tests/integration/`

## Implementation Notes

- profile definitions should remain explicit and versioned
- calibration metadata must be inspectable for reproducibility
- later family-specific quantization extensions should build on the same schema
- the first execution slice may keep calibration metadata in the quantization manifest while the profile contract remains typed and stable

## Verification

- `make proto`
- `make py-test`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/quantization_benchmarks.py --json`

## Acceptance

- multiple quantization profiles are representable and executable
- calibration-driven allocation is reflected in manifests and tests
