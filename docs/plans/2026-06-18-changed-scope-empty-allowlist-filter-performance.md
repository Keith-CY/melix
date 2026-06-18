# Changed-scope coverage empty allowlist filter performance

## Scope

Optimize one Python hot path in `scripts/changed_scope_coverage.py`: the path filter used when `MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON` resolves to an empty allowlist.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-empty-path-short-circuit` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused tests through `test_command`
- changed-scope coverage through `coverage_command`
- local/CI performance measurement through `probe_command` (`python3 scripts/changed_scope_coverage_probe.py`)

## Implementation Plan

1. Preserve current behavior for unset allowlists by returning the original path list.
2. Add a direct empty-allowlist return before the list comprehension so empty allowlists avoid scanning every candidate path.
3. Verify with the registered focused tests, coverage command, and probe on Linux.

## Success Metric

`main_empty_allowlist_elapsed_ms_mean` should decrease or remain within noise while `main_empty_allowlist_coverage_read_calls_mean` remains `0.0`. The probe also reports the helper path metric `elapsed_ms_mean`; no behavior change is expected there.
