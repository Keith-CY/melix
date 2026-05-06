# Gemma4 Weight Presence Single-Pass Optimization

## Goal

Reduce redundant work in the MLX-VLM Gemma4 text-backed fallback by scanning safetensors weight names once instead of materializing a key list and running separate vision/audio prefix scans.

## Scope

Touched files:
- `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/mlx_vlm_gemma4_weight_presence_probe.py`

## Linux Constraint

This is a Python-only helper change. It does not require macOS/Swift execution. Local verification will use focused pytest, changed-scope coverage, and a synthetic Python performance probe.

## Performance Probe

Register `mlx-vlm-gemma4-weight-presence-single-pass` in the PR-scoped performance registry. The probe measures a synthetic large Gemma4 weight-name stream with multimodal tower names late in the sequence.

Metrics:
- `elapsed_ms_mean` lower is better
- `peak_bytes_mean` lower is better
- `visited_names_mean` lower is better

Success means the head helper preserves detection semantics while reducing repeated iteration/allocation work versus the base-compatible legacy fallback.

## Verification Commands

- Focused pytest for the Gemma4 helper tests and probe registry/script tests.
- Changed-scope coverage using `scripts/changed_scope_coverage.py`, requiring >=95%.
- Direct local probe script run with concrete metrics.
- `git diff --check`.
