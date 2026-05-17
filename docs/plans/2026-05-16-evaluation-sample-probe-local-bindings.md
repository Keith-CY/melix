# Evaluation Sample Probe Local Bindings

## Scope

This Python-only performance slice is limited to `EvaluationCore._sample_probe_means` in
`services/mlx-worker-python/worker/engine/evaluation_core.py`.

## Current Behavior

Evaluation sample timing summaries aggregate a fixed tuple of numeric probe fields across
many `EvaluationSample` records. The existing helper already performs a single pass over
samples and fields, preserving missing fields as zero and returning rounded per-field means.

## Change

Keep the single-pass behavior and bind the hot-path helpers (`getattr`, `float`, and the
field index range) outside the nested sample loop. This removes repeated global lookups and
enumeration tuple creation while preserving the same output shape, zero-sample behavior, and
rounding semantics.

## Performance Probe

The affected path is covered by the registered PR-scoped probe
`evaluation-sample-probe-aggregation` in `infra/perf/pr_scoped_probes.json`. The probe has
focused test, coverage, and probe commands, and reports:

- `elapsed_ms_mean` (lower is better)
- `per_call_ms_mean` (lower is better)

Local Linux validation runs the focused tests, changed-scope coverage, and the registered
probe command. CI remains the base-vs-head validation source for the PR-scoped performance
report.
