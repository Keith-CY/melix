# PR-Scoped Performance Sparse Selection

## Context

The PR-scoped performance scope builder loads the registered probe registry and
matches changed paths to probe indexes before returning the selected probe
payload. Most pull requests touch a small set of paths, so the matched probe set
is usually much smaller than the full registry.

The affected path is already covered by the registered
`pr-scoped-performance-registry-cache` probe in `infra/perf/pr_scoped_probes.json`.
That probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
and `services/mlx-worker-python/tests/test_pr_scoped_performance.py`.

## Slice

Use the already-computed matched probe indexes directly when materializing
`selected_probes` and `matched_probe_ids` for non-force-all scope reports. This
keeps registry order by sorting the index set once and avoids scanning the full
probe tuple again for sparse matches.

## Verification

- Focused unit coverage verifies sparse selections still preserve registry order
  for both `matched_probe_ids` and `selected_probes`.
- The registered `pr-scoped-performance-registry-cache` probe measures local
  `build_scope_report` performance on Linux and is the required PR-scoped CI
  probe for this path.

## Boundaries

This is a Python-only optimization slice. No Swift runtime validation is claimed.
