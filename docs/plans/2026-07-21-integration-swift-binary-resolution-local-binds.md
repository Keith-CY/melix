# Integration Swift binary resolution local binds

## Scope

This Python-only performance slice is limited to `tests/integration/helpers.py` and the Swift product binary resolution helper used by integration tests.

The implementation keeps the existing `os.scandir()` candidate scan and executable selection semantics, but hoists repeated lookup work in `_newest_executable_swift_product_binary()` into local bindings:

- `os.path.join` is bound once per resolution call.
- `os.stat` and `stat.S_ISREG` are bound once per resolution call before the nested candidate check.
- the executable mode bit mask is computed once per resolution call.

No Swift runtime behavior changes are included.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `integration-swift-binary-resolution-scandir` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `tests/integration/helpers.py`
- `tests/integration/test_helper_binary_resolution.py`
- the probe script `scripts/integration_swift_binary_resolution_probe.py`

## Verification Plan

Local Linux validation must run:

1. Focused integration helper tests.
2. Changed-scope coverage through the registered coverage command.
3. The registered probe command and recorded metrics.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report before merge. The registered gate treats `elapsed_ms_mean` as the binary-resolution pass/fail metric; `delta_ms_mean` remains informational because it is the within-run gap against the legacy glob fallback and can move with base-side noise even when the direct head elapsed time improves.

## Success Criteria

Accept the slice only if focused tests pass, changed-scope coverage is at least 95 percent, the local registered probe shows non-regressing binary-resolution elapsed time, and CI's registered PR-scoped performance workflow completes successfully.

## 2026-08-02 Scoped Debug Suffix Follow-up

This Python-only follow-up keeps the same `tests/integration/helpers.py` boundary and the registered `integration-swift-binary-resolution-scandir` probe. `_newest_executable_swift_product_binary()` now precomputes the scoped `/debug/<product>` suffix once per resolution call and appends it to each `os.DirEntry.path` while scanning architecture-specific build directories. The flat candidate still uses `os.path.join`, and executable selection semantics, mtime ordering, depth tie-breaker behavior, and final `Path` return type remain unchanged.

Expected metrics are lower `elapsed_ms_mean` and unchanged candidate counts in `scripts/integration_swift_binary_resolution_probe.py`; remove-tree metrics are reported by the same registered probe but are not in this slice's affected path.
