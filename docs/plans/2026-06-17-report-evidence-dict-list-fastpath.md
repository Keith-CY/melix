# Report Evidence Gate Dict List Fast Path

This Python performance slice is limited to `worker.productization.report_evidence_gate._dict_list`.

## Scope

- Preserve the existing behavior for non-list inputs and mixed lists that contain non-dict rows.
- Avoid allocating a filtered copy when the parsed report bucket is already a list of dictionaries, which is the normal report-evidence path for probe summaries, release matrix rows, and gate result buckets.
- Do not change release evidence gate output shape, report validation, or PR markdown rendering semantics.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. That entry includes focused `test_command`, `coverage_command`, and `probe_command` values. This slice extends the same registered probe with a direct `dict_list_elapsed_ms_mean` metric plus identity-hit counters for all-dict report buckets, while retaining `matrix_roles_elapsed_ms_mean` and aggregate `elapsed_ms_mean` coverage through probe phase extraction.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe report.
