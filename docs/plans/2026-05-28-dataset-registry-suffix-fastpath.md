# Dataset Registry Suffix Fast Path

## Goal

Reduce per-file suffix normalization overhead in `worker.dataset_registry.catalog._dataset_file_format(...)` during dataset registry snapshot scans.

## Scope

This slice is Python-only and limited to the dataset registry file-format classification path:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`

It does not change dataset discovery order, supported dataset formats, row parsing, Hugging Face cache resolution, generated protocol artifacts, or Swift/macOS runtime behavior.

## Registered Probe

Registered PR-scoped probe: `dataset-registry-snapshot-inference-single-pass` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and scans a synthetic Hugging Face dataset cache with thousands of files. Relevant metrics:

- `elapsed_ms_mean` — lower is better.
- `peak_bytes_mean` — lower is better as an allocation signal.
- `legacy_inference_helper_calls_mean` — must remain `0.0`, proving the snapshot builder still uses the combined split/config inference helper.

## Implementation Plan

1. Keep README metadata handling and the supported suffix table unchanged.
2. Replace `Path.suffix.lower()` with a direct filename `rfind(".")` suffix lookup so each dataset file avoids `Path.suffix` property work on the scan hot path.
3. Add focused regression coverage for uppercase supported suffixes, trailing-dot names, dotfiles, and README metadata.
4. Reuse the registered dataset registry tests, changed-scope coverage, and local PR-scoped probe before opening the PR.

## Success Criteria

- Focused dataset registry tests pass on Linux.
- Changed-scope coverage for the touched executable scope is at least 95%.
- The registered local probe shows a clear `elapsed_ms_mean` direction without changing `legacy_inference_helper_calls_mean`.
- `git diff --check` passes.
