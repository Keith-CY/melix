# Trajectory Adapter Inline Token Aliases

## Scope

This Python-only performance slice is limited to the exact clean-dict fast path in
`adapter_manifest_trajectory_provenance()` / `_fast_adapter_manifest_trajectory_provenance()` in
`services/mlx-worker-python/worker/trajectory_provenance.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the trajectory provenance helper, tests, and probe
script.

## Plan

1. Preserve the fallback normalization path for dirty token metrics, missing keys,
   non-int counters, blank estimators, or non-exact mapping shapes.
2. For the existing exact clean adapter-manifest shape, extract the six
   `agentic_sft_token_metrics` fields once inside the fast path.
3. Build the copied token metric payload and ordered `training.agentic_sft.*`
   aliases inline, avoiding the separate token-copy and alias-helper passes.
4. Keep nested quality-metric isolation through the existing trajectory value
   copier.
5. Run focused tests, changed-scope coverage, and the registered probe locally on
   Linux before opening the PR. GitHub Actions PR-scoped performance remains the
   merge gate.

## Metrics

Local Linux validation must include `adapter_manifest_*` metrics from the
registered probe, plus changed-scope coverage for the touched Python and probe
files.
