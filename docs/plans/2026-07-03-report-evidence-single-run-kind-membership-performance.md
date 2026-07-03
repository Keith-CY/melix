# Report Evidence Gate Single Run-Kind Membership Performance

## Slice

Optimize the report evidence gate matrix-role hot path for matrix rules that
contain exactly one `run_kinds` entry. The release evidence matrix commonly
contains single-kind role rules, so `_report_matrix_roles()` repeatedly calls
`_run_kind_rule_matches()` with one-item tuples while evaluating reports.

## Registered Probe

This path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused tests for `report_evidence_gate.py` rule matching and probe behavior;
- a changed-scope coverage command for the touched module, tests, and probe;
- `scripts/report_evidence_gate_run_kind_probe.py`, which emits JSON metrics for
  run-kind matching, matrix role selection, release matrix rows, and related
  helper hot paths.

## Implementation Plan

1. Keep behavior identical for tuple and non-tuple `run_kinds` rules.
2. Add a one-item tuple fast path in `_run_kind_rule_matches()` that performs a
   direct membership check before falling back to string coercion for non-string
   rule values.
3. Do not change release matrix semantics, report schema, or generated artifacts.

## Local Evidence

Baseline from `origin/main` on Linux:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/report_evidence_gate_run_kind_probe.py`
- `elapsed_ms_mean=1007.9713843530044`
- `matrix_roles_elapsed_ms_mean=3.7600655807182193`
- `run_kind_elapsed_ms_mean=208.04008902050555`

Candidate after this slice:

- same direct command
- `elapsed_ms_mean=947.7171488106251`
- `matrix_roles_elapsed_ms_mean=3.5894158063456416`
- `run_kind_elapsed_ms_mean=201.75135780591518`
- registered probe command replay: `elapsed_ms_mean=976.4612587168813`,
  `matrix_roles_elapsed_ms_mean=3.5127400187775493`

Initial probe direction is positive: the direct replay overall mean improved by
about 60.254 ms (~5.98%), matrix-role selection improved by about 0.171 ms
(~4.54%), and the run-kind subprobe improved by about 6.289 ms (~3.02%). The
registered probe replay kept the targeted matrix-role metric positive at about
0.247 ms faster than baseline (~6.58%) while unrelated submetrics showed normal
noise. A focused single-rule microprobe over 1,000,000 iterations and seven
samples measured old_mean=193.395 ms, new_mean=189.821 ms, speedup=1.019x.
