# Statistical Evidence Interval Payload Local Bindings

## Scope

This Python-only performance slice targets the interval payload assembly helper
in `services/mlx-worker-python/worker/productization/statistical_evidence.py`.
The affected path is covered by the registered PR-scoped probe
`statistical-evidence-bootstrap-single-sort` in
`infra/perf/pr_scoped_probes.json`, including focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Change

`_interval_payload(...)` now stores the rounded lower and upper interval bounds
in local variables before constructing the payload. This preserves the public
payload shape while avoiding repeated global helper lookup and repeated payload
dictionary reads when computing `crosses_zero`.

## Verification

- Run the registered focused statistical evidence test command.
- Run the registered changed-scope coverage command for the statistical evidence
  scope.
- Run the registered `scripts/statistical_evidence_bootstrap_probe.py` probe
  locally on Linux and compare `elapsed_ms_mean` and `peak_bytes_mean` against
  `origin/main`.
- Rely on the registered PR-scoped performance workflow in CI for PR validation.