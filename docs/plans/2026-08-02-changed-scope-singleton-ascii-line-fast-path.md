# Changed-Scope Coverage Singleton ASCII Line Fast Path

## Slice

Optimize the changed-scope coverage helper for the registered
`changed-scope-coverage-singleton-range-fastpath` probe by reusing the existing
ASCII byte classifier when a single changed line must be classified as
measurable/non-comment.

## Probe Registration

The affected implementation path is already covered by registered PR-scoped
performance probes in `infra/perf/pr_scoped_probes.json`:

- `changed-scope-coverage-singleton-range-fastpath`
- `changed-scope-coverage-measured-set-filter`
- `changed-scope-coverage-empty-path-short-circuit`
- `changed-scope-coverage-diff-parser`

Each registered probe keeps focused `test_command`, `coverage_command`, and
`probe_command` entries. The singleton probe is the primary performance gate for
this slice, while the shared changed-scope probes guard adjacent behavior.

## Behavior

No coverage semantics change. Singleton changed-line classification still skips
blank and comment-only lines, preserves indented executable lines, and falls back
to the Unicode text path when source bytes are not ASCII.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and the
registered singleton probe locally on Linux. GitHub Actions PR-scoped performance
must also complete successfully before merge.

## Metrics

Primary metric: `singleton_measured_elapsed_ms_mean` from
`scripts/changed_scope_coverage_singleton_probe.py`, lower is better.

Secondary safety metrics: `elapsed_ms_mean`, `source_read_calls_mean`, and the
shared measured/diff changed-scope probes.
