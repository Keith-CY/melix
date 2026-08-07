# Dataset Quality Message Dict Binding

## Goal

Reduce per-message global lookups in the dataset quality output-length scan while preserving the existing completion-row and message-row semantics.

## Scope

This Python-only slice is limited to `services/mlx-worker-python/worker/productization/dataset_preparation.py` in `_append_rows_output_lengths(...)`:

- bind the `dict` type to a local before the inner message loop;
- keep the existing completion-key presence fast path and message fallback behavior unchanged;
- do not change dataset version payloads, quality metrics, partitioning, or file layout.

## Performance Probe

The affected path is already covered by the registered PR-scoped probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries covering `dataset_preparation.py`, the dataset preparation tests, and `scripts/dataset_quality_lengths_probe.py`.

The probe reports quality-summary scan metrics including:

- `elapsed_ms_mean`, `elapsed_ms_min`, and `elapsed_ms_p95` for `_quality_summary(...)` over prompt/completion and chat-message rows;
- failed-partition timing metrics as context for the shared registered probe.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and the registered local probe on Linux before opening the PR. CI remains the source of truth for the PR-scoped base-vs-head performance report.
