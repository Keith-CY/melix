# Deterministic Image Loop Bindings

## Goal

Tighten the deterministic image generation and edit loops by binding loop-invariant helpers once before iterating over image variants. The slice preserves generated payloads, artifact metadata, and probe accounting while avoiding repeated `loaded_model.get("model_id", ...)`, method lookups, and SHA helper lookups in the per-image loop.

## Scope

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- `services/mlx-worker-python/tests/test_image_runtime.py`
- `docs/plans/2026-05-31-deterministic-image-loop-bindings.md`

## Probe coverage

The affected runtime path is already covered by the registered PR-scoped probe `deterministic-image-output-byte-accounting` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the runtime file, image runtime tests, probe smoke tests, and `scripts/deterministic_image_output_bytes_probe.py`.

## Success metrics

- Focused image runtime tests pass on Linux.
- Changed-scope coverage for the touched Python paths remains at or above 95%.
- The registered `deterministic_image_output_bytes_probe.py` reports neutral-to-improved `elapsed_ms_mean` with `output_byte_scan_calls_mean=0.0`.
- GitHub Actions PR-scoped performance completes successfully before merge.

## Validation boundary

This is a Python-only deterministic runtime slice. Local Linux tests and the registered Python probe validate the behavior and performance direction; no Swift runtime effect is claimed.
