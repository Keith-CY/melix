# Report Evidence Gate `_dict_list` Exact-List Fast Path

## Slice

Optimize the report evidence gate helper `_dict_list` for the common exact `list`
input used while rendering release matrix, probe phase, and evidence rows.

## Behavior Contract

- Non-list values still return an empty list.
- Exact `list[dict]` values continue to return the original list object.
- Lists containing non-dict entries continue to return a filtered list of dict
  entries.
- List subclasses keep the previous `isinstance(value, list)` fallback behavior.

## Registered Probe

This path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused tests, changed
scope coverage, and `scripts/report_evidence_gate_run_kind_probe.py` metrics.

## Evidence Plan

1. Run the focused report evidence gate tests from the registered probe.
2. Run changed-scope coverage using the registered coverage command.
3. Run the registered probe locally on Linux and compare against the pre-change
   baseline.
4. Use the PR-scoped performance CI report as the merge gate.
