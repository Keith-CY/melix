# Maintenance Prompt Split Cache

## Scope

This Python-only performance slice is limited to shaped benchmark prompts in
`services/mlx-worker-python/worker/engine/maintenance_core.py`.

`ShapedBenchmarkPrompt.split()` already returns an immutable list-like view for
plain `split()` calls so benchmark token-count consumers can reuse the shaped
prompt token tuple without reparsing whitespace. This slice caches that immutable
split list on the shaped prompt instance, so repeated plain `split()` calls on the
same shaped prompt avoid reallocating a fresh `ImmutableBenchmarkTokens` wrapper.
Explicit separator or `maxsplit` calls still delegate to `str.split()` and keep
normal string split semantics.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`maintenance-prompt-shape-vector-repeat` in `infra/perf/pr_scoped_probes.json`.
The entry includes focused `test_command`, `coverage_command`, and
`probe_command` values and now lists this plan as a watched file.

The probe measures shaped prompt expansion, single-context truncation, plain
prompt token counting, and repeated shaped prompt `split()` identity reuse via
`split_identity_reuse_count_mean`.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff
--check`, and the registered `maintenance-prompt-shape-vector-repeat` probe
locally on Linux before opening the PR. GitHub Actions PR-scoped performance is
the merge gate for the registered probe report.
