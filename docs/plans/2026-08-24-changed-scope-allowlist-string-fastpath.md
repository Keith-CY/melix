# Changed-scope allowlist string-list fast path

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py` path allowlist parsing for `MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `changed-scope-coverage-empty-path-short-circuit` in `infra/perf/pr_scoped_probes.json`. This slice extends that probe with `allowlist_parse_elapsed_ms_mean` so CI and local runs measure large JSON string-list allowlist parsing directly. The probe keeps focused `test_command`, `coverage_command`, and `probe_command` entries and watches the changed script, probe script, tests, and registry.

## Optimization

JSON allowlists emitted by automation are lists of strings. `_coverage_path_allowlist_from_raw()` now builds the resulting set in one explicit pass, adding string entries directly and only coercing mixed non-string entries when needed. This avoids the previous generator's duplicate `str()` call for mixed payloads and keeps the common string payload on a direct append path while preserving legacy coercion behavior.

## Verification plan

1. Run the focused changed-scope coverage tests and PR-scoped registry tests.
2. Run changed-scope coverage for the touched tool, probe, tests, registry, and this plan.
3. Run the registered local probe on Linux before pushing.
4. Use the PR-scoped performance workflow as the merge gate for the registered CI probe report.
