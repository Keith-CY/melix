# Release Gates Rule Name Fast Path

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/productization/release_gates.py` and the M9
release-gate section metric evaluator used by `evaluate_m9_release_evidence`.

## Goal

Keep release-gate failure messages, nested metric lookup compatibility, non-string
rule-key compatibility, and failure counters unchanged while reducing per-rule
overhead in `_evaluate_section_metrics_with_counts` by using a direct bound
`values.get` lookup for the common flat string-key policy path and only falling
back to `_metric_value` when nested dotted lookup is possible or the rule key is
not a string.

## Probe

The affected path is covered by the registered PR-scoped probe
`release-gates-m9-failure-count-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries and measures `elapsed_ms_mean`,
`endswith_checks_mean`, and `failure_count_mean` for a large M9 policy workload.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux before opening the PR. CI remains the source
of truth for the PR-scoped registered probe report.

## Success Metrics

- Focused tests preserve string-key and non-string-key behavior.
- Changed-scope coverage remains at or above 95%.
- Local registered probe improves `elapsed_ms_mean` versus the pre-change
  baseline while preserving `failure_count_mean` and `endswith_checks_mean`.
