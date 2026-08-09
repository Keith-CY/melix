# Report Evidence Dict-List Exact Fast Path

## Slice

Optimize exactly one Python hot path in `worker.productization.report_evidence_gate._dict_list(...)`, used by report-evidence gate aggregation and the registered report-evidence probe.

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries for `report_evidence_gate.py`, its focused tests, and `scripts/report_evidence_gate_run_kind_probe.py`.

## Hypothesis

Most internal callers pass JSON-decoded lists that already contain only dictionaries. Returning that exact list after a single validation pass avoids allocating a duplicate list for all-dict rows while preserving filtering for mixed lists and non-list fallback behavior.

## Scope

- Preserve non-list inputs returning an empty list.
- Preserve mixed list filtering semantics.
- Preserve `dict` subclasses as valid dictionary rows.
- Do not change release-matrix matching, slowest-phase ranking, report loading, rendering, probe registry, generated artifacts, or Swift code.

## Verification

Run the registered focused tests, changed-scope coverage command, and command-json probe locally on Linux. CI PR-scoped performance remains the merge gate before squash merge.
