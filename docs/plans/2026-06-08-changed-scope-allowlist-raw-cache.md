# Changed-scope allowlist raw parse cache

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py`
and the focused changed-scope coverage tests. The hot path is repeated parsing of
`MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON` for probe and CI coverage workflows that
invoke the allowlist helper with the same raw environment value.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values and runs `scripts/changed_scope_coverage_measured_probe.py`.

## Plan

1. Preserve the existing allowlist semantics for empty values, simple JSON string
   values, escaped JSON strings, JSON string payloads, and JSON list payloads.
2. Cache parsing by the stripped raw environment value so repeated helper calls
   reuse the same immutable `frozenset` result without repeatedly invoking the
   JSON decoder.
3. Add a focused regression test that proves identical raw JSON list payloads are
   decoded once and then served from cache.
4. Verify with the registered focused tests, changed-scope coverage command, and
   the registered local Linux probe before using PR-scoped performance CI as the
   merge gate.

## Metrics

Success is measured by the registered probe's
`allowlist_parse_elapsed_ms_mean` while preserving `source_read_calls_mean == 0.0`
and changed-line coverage at or above 95%. This slice is Linux-verifiable and
does not claim any Swift runtime effect.
