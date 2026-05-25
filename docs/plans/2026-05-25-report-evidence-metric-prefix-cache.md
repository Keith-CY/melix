# Report Evidence Metric Prefix Cache Slice

## Scope

This Python-only performance slice is limited to release-matrix metric-prefix rule matching in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The existing run-kind fast path already caches tuple-backed `run_kinds` normalization. This slice applies the same immutable-rule strategy to tuple-backed `metric_prefixes` rules while preserving mutation visibility for non-tuple iterables.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

This slice extends that probe to measure both:

- `run_kind_elapsed_ms_mean` for the existing tuple-backed `run_kinds` rule path;
- `metric_prefix_elapsed_ms_mean` for the tuple-backed `metric_prefixes` path added here.

The registered entry keeps focused `test_command`, `coverage_command`, and `probe_command` coverage for the source path, tests, registry entry, and probe script.

## Implementation Plan

1. Add a cached tuple normalizer for immutable tuple-backed `metric_prefixes` rules.
2. Keep non-tuple `metric_prefixes` rules uncached so caller-visible mutation behavior remains unchanged.
3. Add regression tests for tuple cache reuse and mutable list behavior.
4. Extend the registered probe script and registry metrics to report the new metric-prefix timing.

## Acceptance Criteria

- Focused report evidence gate tests pass locally on Linux.
- Changed-scope coverage for the touched Python path remains at or above 95%.
- The registered probe reports a lower `metric_prefix_elapsed_ms_mean` than the pre-change baseline.
- PR-scoped performance CI completes successfully before merge.

## Non-Goals

- No release evidence schema changes.
- No generated protocol or lockfile changes.
- No Swift runtime performance claims from local Linux validation.
