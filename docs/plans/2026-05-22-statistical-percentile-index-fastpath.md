# Statistical Evidence Percentile Index Fast Path

## Goal

Reduce avoidable helper calls in the paired statistical evidence bootstrap
percentile path without changing percentile interpolation semantics.

## Scope

This slice only touches `worker.productization.statistical_evidence` and the
focused statistical evidence tests. It does not change release verdict logic,
bootstrap sampling, category breakdown aggregation, or report schemas.

## Registered Probe

The affected path is covered by the PR-scoped performance probe
`statistical-evidence-bootstrap-single-sort` in
`infra/perf/pr_scoped_probes.json`. The probe includes a focused test command,
coverage command, and `scripts/statistical_evidence_bootstrap_probe.py` command.

## Optimization

`_paired_bootstrap_interval` now builds bootstrap replicate values with a list
comprehension before sorting them in place, avoiding the per-replicate bound
`append` call and keeping the sum helper local while preserving the existing
deterministic `Random.choices` sampling sequence. `_ordered_percentile` also
derives the lower index with `int(position)` and only computes the upper value
when interpolation is needed. This removes the paired `math.floor`/`math.ceil`
helper calls from each percentile lookup while preserving bounded-percentile
behavior for empty inputs, singleton inputs, integer positions, interpolated
positions, and the upper endpoint.

## Verification

Run the registered probe's focused test, coverage command, and probe command on
Linux before opening the PR. Compare the probe output against the pre-change
baseline and rely on PR-scoped CI for the repository registered probe report.
