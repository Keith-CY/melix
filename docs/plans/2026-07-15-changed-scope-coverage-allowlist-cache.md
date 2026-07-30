# Changed-Scope Coverage Allowlist Cache

## Scope

This Python-only performance slice is limited to repeated changed-scope coverage
probe allowlist lookup in `scripts/changed_scope_coverage.py`.

Behavior stays unchanged: allowlist payload parsing still accepts the same empty,
JSON list, JSON string, and simple quoted string inputs. The slice adds a tiny
last-raw-payload cache around `_coverage_path_allowlist()` so repeated callers
with the same raw `MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON` value can reuse the
already parsed allowlist without re-entering the LRU wrapper.

## Registered probe

The affected path is already covered by registered PR-scoped probe
`changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Verification plan

1. Run the focused registered test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `python3 scripts/changed_scope_coverage_measured_probe.py` locally and
   compare against the pre-change implementation loaded from `HEAD`.
4. Use GitHub Actions PR-scoped performance as the merge gate for the registered
   probe report.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above the repository 95% threshold.
- The registered probe reports stable or improved tracked metrics for repeated
  allowlist lookup.
