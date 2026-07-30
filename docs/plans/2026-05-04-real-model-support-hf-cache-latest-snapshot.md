# Real model support HF cache latest snapshot optimization

## Goal

Reduce redundant work in the Linux-verifiable real-model support helper that falls back to the Hugging Face cache when `refs/main` is unavailable.

## Scope

- `scripts/real_model_support.py`
- `tests/test_real_model_support.py`
- `scripts/real_model_support_hf_cache_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only constraint

This slice touches Python helper and CI probe code only. It does not require macOS or Swift validation.

## Optimization hypothesis

`_huggingface_cache_model_path(...)` currently materializes every snapshot directory name and sorts the full list to pick the lexicographically latest fallback. The fallback only needs the maximum name, so the helper can track the latest directory during the existing `os.scandir(...)` pass and avoid the `O(n log n)` sort and list allocation.

## Performance probe

Register `real-model-support-hf-cache-latest-snapshot` in the PR-scoped performance registry. The probe creates a synthetic Hugging Face cache with thousands of snapshot directories and repeatedly resolves the fallback path, reporting:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `snapshot_count` (guardrail)
- `selected_latest_snapshot` (guardrail)

2026-06-14 follow-up slice: after the single-pass scan has selected the latest
snapshot name, the fallback now returns the already-absolute `snapshots_root /
latest_snapshot_name` path directly instead of resolving that snapshot path a
second time. The registered script now reports the HF-cache fallback metrics as
`hf_cache_elapsed_ms_mean` and `hf_cache_peak_bytes_mean` alongside the existing
weight-file scan metric, so the PR-scoped report gates this fallback path
directly.

2026-07-29 follow-up slice: the runtime preflight weight-file helper keeps the
same common exact filename short-circuit but derives the filesystem string once
and probes common exact filenames before falling back to the directory-wide
suffix scan. This removes the separate directory stat from the common
`model.safetensors` hot path while preserving the existing non-directory false
case and suffix fallback scan for non-common or uppercase weight filenames. The
registered `real-model-support-hf-cache-latest-snapshot` probe already reports
`weight_scan_elapsed_ms_mean`, so this slice remains Linux-verifiable under the
same focused command, coverage command, and PR-scoped performance workflow.

## Success metrics

- Focused pytest for the real-model support fallback and PR-scoped probe registration passes.
- Changed-scope coverage for touched executable Python lines is at least 95%.
- Local head probe reports concrete elapsed and memory metrics.
- Detached `origin/main` vs head PR-scoped probe comparison shows lower elapsed time and/or peak memory for the same synthetic cache workload.
