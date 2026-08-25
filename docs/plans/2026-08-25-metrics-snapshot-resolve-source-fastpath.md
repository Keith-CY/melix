# Melix metrics snapshot source resolution fast path

## Scope

This Python-only performance slice targets `scripts/melix_metrics_snapshot.py`, specifically `resolve_source_paths` before runtime metrics discovery. The slice keeps runtime discovery semantics unchanged while reducing per-call overhead in the configured-source path and preserving the registered runtime-discovery probe gate.

## Registered Probe

The affected path is covered by the existing PR-scoped probe `melix-metrics-snapshot-runtime-scandir` in `infra/perf/pr_scoped_probes.json`. The probe watches:

- `scripts/melix_metrics_snapshot.py`
- `scripts/melix_metrics_snapshot_discovery_probe.py`
- `tests/test_melix_metrics_snapshot.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` values and reports configured-source latency plus runtime scandir discovery latency.

## Implementation Plan

- Store `SourcePath` as a frozen slotted dataclass to reduce object overhead while preserving immutable attribute access.
- Avoid building a temporary explicit-path dictionary for every `resolve_source_paths` call.
- Bind `environment.get` and `normalize_path` locally for the tight resolution loop.
- Do not change source names, configured-by labels, runtime discovery, freshness logic, or metrics payload parsing.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux. GitHub Actions PR-scoped performance remains the merge gate after push.

## Linux Boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime performance claim is made.
