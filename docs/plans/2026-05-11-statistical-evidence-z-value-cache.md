# Statistical Evidence Z-Value Cache

## Scope

This Python-only performance slice is limited to the analytical confidence
interval z-value helper in
`services/mlx-worker-python/worker/productization/statistical_evidence.py`.
It does not change bootstrap sampling, interval payload formatting, release-gate
policy semantics, generated protocol artifacts, or Swift/macOS behavior.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`statistical-evidence-bootstrap-single-sort` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused
`test_command`, `coverage_command`, and `probe_command` values and reports
`elapsed_ms_mean`, `peak_bytes_mean`, `sorted_calls_mean`, and interval bounds.

## Optimization

Cache `_two_sided_normal_z_value(confidence_level)` with a small bounded
`lru_cache` so repeated paired-statistical-evidence builds using the same
confidence level reuse the same NormalDist inverse-CDF result. The helper keeps
the existing confidence-level clamping behavior before calculating the cached
result.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux and require
  at least 95% for changed executable scope.
- Run `scripts/statistical_evidence_bootstrap_probe.py` before and after the
  change and compare `elapsed_ms_mean`, `peak_bytes_mean`, and
  `sorted_calls_mean`.
- Use the PR-scoped performance workflow as the merge gate after push.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- The local registered probe preserves `sorted_calls_mean == 0.0` and interval
  bounds while improving or staying within noise for `elapsed_ms_mean`.