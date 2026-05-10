# Vision Prompt Token Count Scan Optimization

## Goal

Reduce memory pressure in vision-family prompt token accounting by replacing `prompt_text.split()` list materialization with a single-pass whitespace token counter. Follow-up slices may also keep media-token accounting on the same registered path as long as they preserve the no-`split()` prompt invariant and validate the image/video token components in the same probe.

## Scope

- `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `scripts/vision_family_prompt_token_count_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only constraint

This slice is Python-only and can be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit command-json performance probe.

## Performance probe

Register `vision-family-prompt-token-count-scan` in the PR-scoped performance registry. The probe compares repeated prompt-token estimates for a whitespace-delimited prompt with representative image inputs and video frame policies, and reports:

- `elapsed_ms_mean` (lower is better)
- `split_calls_mean` (lower is better; optimized branch should be `0.0`)
- `peak_bytes_mean` (lower is better)
- `token_count` (structural parity metric)

## Success metrics

- Focused tests pass.
- Changed executable scope coverage is at least 95%.
- Local probe shows the optimized path avoids `split()` calls and materially reduces peak traced allocation while preserving token count.
