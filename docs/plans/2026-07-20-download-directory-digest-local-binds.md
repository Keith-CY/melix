# Download Directory Snapshot Digest Local Binds

## Scope

This Python-only performance slice is limited to `DownloadPipeline._sha256_directory_snapshot(...)` in `services/mlx-worker-python/worker/model_ops/download_pipeline.py`.

The implementation keeps directory snapshot digest semantics unchanged while reducing repeated attribute/global lookups in the per-file digest loop by binding hot helpers (`digest.update`, `_directory_snapshot_files`, `open`, and the chunk size) once per digest call, emitting file sizes directly as ASCII bytes, and reusing each file object's bound `read` method inside the chunk loop.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `download-pipeline-directory-size-single-stat` in `infra/perf/pr_scoped_probes.json`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- download pipeline behavior tests,
- changed-scope coverage for the download pipeline and probe-selection tests,
- digest and companion directory scan metrics, including `digest_elapsed_ms_mean` and `digest_delta_ms`.

## Validation Plan

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe result.

## Boundaries

No Swift runtime path is changed. No generated protobuf outputs or dependency lockfiles are touched.
