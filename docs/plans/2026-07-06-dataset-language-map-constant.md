# Dataset source language suffix map constant

## Scope

This Python-only performance slice targets
`worker.productization.dataset_preparation._language_for_suffix(...)`, which runs
while dataset ingest creates source records for code files. Behavior remains
unchanged: known code suffixes map to Melix language labels, unknown suffixes
fall back to the suffix text, and an empty suffix falls back to `text`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry has focused `test_command`, `coverage_command`, and
`probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

## Optimization

Hoist the code-source suffix-to-language lookup table from a per-call dictionary
literal inside `_language_for_suffix(...)` to a module-level constant, then use a
direct lookup on known suffixes so the fallback string normalization only runs
for unknown suffixes. This avoids allocating the same mapping for every code
source record while preserving the same lookup and fallback semantics.

## Verification plan

1. Keep behavior parity explicit with a focused unit test for known and unknown
   code suffixes.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered `dataset-source-records-scandir` probe locally before and
   after the change.
5. Use the PR-scoped GitHub Actions performance workflow as the merge gate for
   the registered probe report.

## Verification boundary

This is a Python-only slice and is locally verifiable on Linux. The PR-scoped CI
probe report remains the required merge gate for repository performance evidence.
