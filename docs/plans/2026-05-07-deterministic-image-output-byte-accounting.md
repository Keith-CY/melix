# Deterministic Image Output Byte Accounting Optimization

## Goal

Avoid rescanning generated image payload lists after deterministic image generation and image edit requests finish. The runtime already has each payload in hand inside the generation loop, so output byte accounting can be accumulated during that loop.

## Scope

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- `services/mlx-worker-python/tests/test_image_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_image_output_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python worker slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit command-json performance probe.

## Performance probe

Register `deterministic-image-output-byte-accounting` in PR-scoped performance CI. The probe runs deterministic image generation and image edit workloads while instrumenting the runtime module's global `sum` lookup. The old implementation performs one post-loop image-list scan for generation and one for edit; the optimized implementation should report:

- `output_byte_scan_calls_mean == 0.0`
- unchanged generated/edit image counts and non-zero output byte snapshots
- lower or comparable `elapsed_ms_mean`

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python files.
- Local probe reports `output_byte_scan_calls_mean=0.0` on the branch.
- Local base-vs-head scoped probe shows `output_byte_scan_calls_mean` reduced from `2.0` on `origin/main` to `0.0` on the branch.
