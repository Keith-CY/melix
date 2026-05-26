# Report Evidence Target Field Key Scan Slice

## Scope

This Python performance slice is limited to release evidence matrix target-field
matching in `worker.productization.report_evidence_gate._rule_matches_report(...)`.

The previous implementation normalized target-field rule names and then checked
every requested rule field against each target dictionary. Sparse target payloads
therefore paid `len(target_fields) * len(targets)` dictionary lookups even when
each target only carried one or two keys.

This slice keeps the release evidence behavior unchanged while scanning the keys
present on each target and testing those keys against the normalized target-field
set. Tuple target-field rules still reuse the existing cached string frozenset,
and list-backed rules still reflect mutation on the next call.

## Registered probe

Existing registered probe: `report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The probe covers:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

The registry already defines focused `test_command`, `coverage_command`, and
`probe_command` entries. The `target_field_elapsed_ms_mean` metric is the primary
signal for this slice.

## Verification plan

1. Run the registered focused test command for `report-evidence-gate-run-kind-set-membership`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered probe locally on Linux and compare against the pre-change
   baseline from the same worktree.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Local registered probe result

Before implementation on `origin/main` (`4470e30d`) with
`MELIX_REPORT_EVIDENCE_RUN_KIND_ITERATIONS=30000` and
`MELIX_REPORT_EVIDENCE_RUN_KIND_SAMPLES=7`:

- `elapsed_ms_mean=7129.528`
- `target_field_elapsed_ms_mean=6053.784`
- `run_kind_elapsed_ms_mean=159.962`
- `metric_prefix_elapsed_ms_mean=915.782`

After implementation with the same local probe settings:

- `elapsed_ms_mean=1465.681`
- `target_field_elapsed_ms_mean=345.265`
- `run_kind_elapsed_ms_mean=163.554`
- `metric_prefix_elapsed_ms_mean=956.863`

Primary target-field scan delta: `-5708.519 ms` (`17.53x` faster on the sparse
synthetic target-field workload). The unrelated run-kind and metric-prefix
sub-metrics were effectively unchanged relative to local noise.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- Local registered probe shows lower `target_field_elapsed_ms_mean` without a
  material regression in the other metrics.
- CI PR-scoped performance completes successfully before merge.
