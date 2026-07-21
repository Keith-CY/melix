# Integration Swift binary resolution local binds

## Scope

This Python-only performance slice is limited to `tests/integration/helpers.py` and the Swift product binary resolution helper used by integration tests.

The implementation keeps the existing `os.scandir()` candidate scan and executable selection semantics, but hoists repeated lookup work in `_newest_executable_swift_product_binary()` into local bindings:

- `os.path.join` is bound once per resolution call.
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

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report before merge.

## Success Criteria

Accept the slice only if focused tests pass, changed-scope coverage is at least 95 percent, the local registered probe shows non-regressing binary-resolution elapsed time, and CI's registered PR-scoped performance workflow completes successfully.
