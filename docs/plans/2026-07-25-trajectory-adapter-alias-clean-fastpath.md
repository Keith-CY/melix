# Trajectory Adapter Alias Clean Fast Path

## Scope

This Python-only performance slice is limited to
`adapter_manifest_trajectory_provenance()` in
`services/mlx-worker-python/worker/trajectory_provenance.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries, and its adapter-manifest metrics exercise the target helper locally on
Linux.

## Plan

1. Preserve the existing normalization and alias semantics for generic mappings.
2. Add a narrow exact-`dict` fast path for the clean adapter-manifest provenance
   shape emitted by the agentic trajectory pipeline.
3. Keep nested JSON container isolation by copying the quality metrics and token
   metrics before returning the payload.
4. Run focused tests, changed-scope coverage, and the registered probe locally
   before opening the PR. GitHub Actions PR-scoped performance remains the merge
   gate.

## Metrics

Local Linux validation must include the registered probe output with
`adapter_manifest_*` old/new timings plus changed-scope coverage for the touched
Python and probe files.
