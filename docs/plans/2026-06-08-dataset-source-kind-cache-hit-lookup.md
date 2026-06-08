# Dataset source kind cache-hit lookup

## Scope

This Python-only performance slice is limited to source-kind classification in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.
Dataset ingest scans can classify many source paths whose basenames repeat across
input directories. The source-kind cache already preserves those repeated
basename classifications; this slice keeps the same cache semantics while making
cache hits use direct dictionary lookup instead of a sentinel `dict.get` path.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry watches `dataset_preparation.py`, includes focused
`test_command`, `coverage_command`, and `probe_command` entries, and records both
source-file scanning metrics and `source_kind_elapsed_ms_*` metrics for repeated
source-kind classification.

## Verification plan

1. Add focused regression coverage that cached `None` values still return from
   the cache without reclassifying unsupported basenames.
2. Replace the sentinel `dict.get` cache-hit path with a direct dictionary
   lookup guarded by `KeyError`.
3. Run the registered focused test command for `dataset-source-records-scandir`.
4. Run the registered changed-scope coverage command.
5. Run the registered probe locally on Linux and compare against `origin/main`
   using `scripts/pr_scoped_performance_run.py`.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior changes are included.
