# Release gates M9 string-key fast path

## Scope

This Python performance slice is limited to M9 release-gate metric evaluation in `worker.productization.release_gates._evaluate_section_metrics_with_counts()`.

It preserves release-gate policy semantics and failure strings. Non-string policy keys remain supported by coercing them to strings before metric lookup, while the normal string-key path avoids an unnecessary `str()` call for every metric rule.

## Registered Probe

Registered PR-scoped probe: `release-gates-m9-failure-count-single-pass` in `infra/perf/pr_scoped_probes.json`.

The registered probe watches `services/mlx-worker-python/worker/productization/release_gates.py` and includes focused `test_command`, `coverage_command`, and `probe_command` entries. It measures repeated M9 section evaluation through `elapsed_ms_mean` and verifies the optimized path does not reintroduce suffix scans through `endswith_checks_mean`.

## Change

Bind the metric lookup key as `name` directly when the rule key is already a `str`; only fall back to `str(name)` for non-string keys. This keeps the compatibility behavior but reduces per-rule work on the common JSON policy path where all metric names are strings.

## Verification

- Run the registered focused test command locally on Linux.
- Run the registered coverage command locally on Linux and require changed-scope coverage >= 95%.
- Run the registered probe locally on Linux before and after the change.
- Run `git diff --check`.

## Acceptance Criteria

- Behavior parity for string and non-string policy keys.
- Changed-scope coverage remains at least 95%.
- Local registered probe shows neutral-to-improved `elapsed_ms_mean` and keeps `endswith_checks_mean` at `0.0`.
