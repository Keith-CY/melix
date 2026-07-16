# Changed-scope allowlist exact-cache slice

## Scope

This Python performance slice is limited to `scripts/changed_scope_coverage.py`, specifically repeated `_coverage_path_allowlist(...)` calls from registered changed-scope coverage probes.

## Registered probe

The affected path is covered by the existing registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`.

That registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

The probe reports `allowlist_parse_elapsed_ms_mean` over repeated allowlist lookups, which is the direct metric for this slice.

## Optimization hypothesis

Registered coverage commands repeatedly call `_coverage_path_allowlist(...)` with the exact same JSON environment value. The function already caches the normalized raw value, but it strips the environment value before checking the last-value fast path. Checking the exact raw value first keeps whitespace-normalized behavior unchanged while avoiding a repeated `str.strip()` call for the common no-whitespace JSON payload.

## Verification plan

1. Keep the existing allowlist cache regression tests green.
2. Add/retain behavior coverage for whitespace-normalized payloads so the exact-cache branch does not change semantics.
3. Run the registered focused test command and changed-scope coverage command locally on Linux.
4. Run the registered `changed-scope-coverage-measured-set-filter` probe locally against `origin/main` and this branch, using `allowlist_parse_elapsed_ms_mean` as the primary metric.
