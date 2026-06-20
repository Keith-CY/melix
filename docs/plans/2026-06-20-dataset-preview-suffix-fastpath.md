# Dataset preview suffix membership fast path

## Scope

This Python performance slice is limited to the dataset registry preview file scan path in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

Registered PR-scoped probe: `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for this path.

## Root Cause

The first-preview and limited-preview scans evaluate many `os.scandir()` entries before selecting the sorted supported dataset files. Each regular file candidate previously sliced the extension and called `.lower()` before checking `_SUPPORTED_DATASET_SUFFIXES`. In large snapshots with many already-lowercase `.jsonl` shards or ignored lowercase sidecars, that allocates a new suffix string for every file even when direct suffix membership is sufficient.

## Plan

1. Add a small `_is_supported_dataset_file_name()` helper that rejects missing/trailing-dot names and checks the original suffix before falling back to lowercase normalization for uppercase compatibility.
2. Reuse the helper in both first-entry and limited-entry scan loops.
3. Cover lowercase, uppercase, unsupported, extensionless, and dotfile suffix behavior in the focused dataset registry tests.
4. Keep the registered probe as the validation source and add the focused suffix-helper test to the probe registry commands.

## Validation

- Run the registered focused tests for `dataset-registry-preview-limit-short-circuit`.
- Run changed-scope coverage for `catalog.py`, dataset registry tests, PR-scoped performance tests, and the dataset preview probe scripts.
- Run `scripts/dataset_registry_preview_limit_probe.py` locally on Linux and compare against the pre-change baseline.

## Local Baseline

Before this slice on Linux with `MELIX_DATASET_PREVIEW_PROBE_SAMPLES=5`:

- `elapsed_ms_mean=112.396192`
- `multi_limit_elapsed_ms_mean=196.378293`
- `peak_bytes_mean=14685.6`
- `multi_limit_peak_bytes_mean=20737.2`

The accepted change must improve the elapsed scan metrics without changing row counts or file-yield counts.
