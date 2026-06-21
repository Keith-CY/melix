# Download companion receipt scandir slice

This Python-only performance slice is limited to directory companion artifact receipt enumeration in `DownloadPipeline._companion_artifact_receipt()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `download-pipeline-directory-size-single-stat` in `infra/perf/pr_scoped_probes.json`.

This slice extends the existing download-pipeline probe so its focused `probe_command` also measures companion directory receipt enumeration. The registered entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
- `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization

Replace the `Path.rglob("*")` materialization used for companion directory receipt file lists with an explicit `os.scandir()` stack. The helper preserves sorted absolute path output, byte counts, nested-directory traversal, and symlinked-file behavior while avoiding `Path` allocation for every candidate.

## Verification plan

1. Add focused regression coverage proving directory companion receipts do not call `Path.rglob()`.
2. Preserve symlinked-file behavior for companion directory receipts.
3. Run the registered focused test command locally on Linux.
4. Run the registered changed-scope coverage command locally on Linux.
5. Run the registered probe locally against `origin/main` and this branch.
6. Use GitHub Actions PR-scoped performance as the final merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- The local and CI registered probe reports show non-regression or improvement for the download pipeline metrics and the new companion receipt timing metric.
