# Serving diagnostics empty event attributes fast path

## Scope

This Python performance slice is limited to `ServingDiagnosticsEvent.to_dict()` in the serving diagnostics bundle writer. The queue probe workload serializes retained debug events that commonly use the default empty attributes mapping, so this slice keeps behavior unchanged while avoiding the generic mapping normalization path for that canonical empty value.

## Registered probe

The affected path is already covered by the PR-scoped probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`.

The registered entry includes:

- `test_command` for `services/mlx-worker-python/tests/test_serving_diagnostics.py` and PR-scoped probe dispatch tests.
- `coverage_command` for changed-scope coverage over the serving diagnostics source, tests, probe dispatch tests, and probe script.
- `probe_command` invoking `scripts/serving_diagnostics_queue_probe.py` with command-json metrics.

## Verification plan

1. Add a regression test proving default empty event attributes and explicit empty mappings serialize equivalently.
2. Implement only the canonical empty-attributes fast path in `ServingDiagnosticsEvent.to_dict()`.
3. Run the registered focused tests, changed-scope coverage, and local Linux probe before opening the PR.
4. Use GitHub Actions PR-scoped performance as the merge gate for base-vs-head probe validation.

## Expected metrics

Primary metric: `serialization_elapsed_ms_mean` from `serving-diagnostics-debug-queue-bounds`, direction lower-is-better.

Secondary metrics: `elapsed_ms_mean`, `serialized_bytes`, `dropped_count`, `retained_count`, and `serialization_checksum` must remain stable or explainably equivalent.
