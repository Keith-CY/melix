# Integration Remove Tree Root Stat Elision

## Scope

This performance slice keeps the integration cleanup helper behavior unchanged while removing the initial `Path.exists()` check from `LiveMelixStack._remove_tree()`.

Affected path:

- `tests/integration/helpers.py`
- `tests/integration/test_helper_remove_tree.py`
- `scripts/integration_remove_tree_probe.py`
- `infra/perf/pr_scoped_probes.json` entry `integration-swift-binary-resolution-scandir`

## Registered Probe

The affected path is covered by the registered PR-scoped probe `integration-swift-binary-resolution-scandir`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, and the probe command imports `scripts/integration_remove_tree_probe.py` to report the remove-tree cleanup metrics.

## Implementation Plan

1. Preserve the existing explicit-stack `os.scandir()` cleanup path and symlink handling.
2. Remove the up-front `Path.exists()` stat so missing roots fall through the existing `FileNotFoundError` scan handling.
3. Add regression coverage proving `_remove_tree()` does not call `Path.exists()` before cleanup.
4. Run the focused registered tests, changed-scope coverage, and registered probe locally on Linux.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage for touched Python lines is at least 95%.
- The registered probe keeps remove-tree elapsed and/or peak memory better than the legacy `Path.rglob()` baseline and records the new-vs-current delta for this slice.

## Verification Boundary

This is a Python integration-helper cleanup slice and is locally verifiable on Linux. The same registered PR-scoped performance workflow remains the CI merge gate.
