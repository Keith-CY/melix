# Dataset JSON Preview Chunk Size

## Scope

This Python-only performance slice is limited to the limited JSON preview reader
in `services/mlx-worker-python/worker/dataset_registry/catalog.py`. It keeps the
existing `read_hf_dataset_snapshot_rows(..., limit=N)` behavior unchanged for
Hugging Face snapshot previews and does not change dataset discovery, split
selection, supported formats, protobufs, or runtime APIs.

## Optimization Hypothesis

The limited JSON preview reader currently reads 64 KiB chunks before trying the
incremental parser. The registered probe uses a large canonical `{"rows": [...]}`
JSON file and requests a single preview row. For that common preview shape, the
first row is near the beginning of the file, so a smaller default chunk should
reduce transient string allocation and traced peak memory without increasing the
number of reads needed by normal small-row previews.

This slice lowers `_JSON_LIMITED_PREVIEW_CHUNK_CHARS` to 16 KiB. The existing
loop still appends chunks until the requested rows are decoded, so large leading
metadata or large first rows remain supported by falling through to additional
bounded reads and, when needed, the existing full-payload fallback.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The registry entry already has focused
`test_command`, `coverage_command`, and `probe_command` entries for
`catalog.py`, the dataset registry tests, the probe registry tests, and
`scripts/dataset_registry_preview_limit_probe.py`.

Primary metric: `peak_bytes_mean` (lower is better). Secondary metric:
`elapsed_ms_mean` should remain neutral-to-improved.

## Validation Plan

1. Run the registered focused dataset preview tests locally on Linux.
2. Run the registered changed-scope coverage command locally and require at
   least 95% coverage for touched scope.
3. Run the registered probe locally against `origin/main` and head via
   `scripts/pr_scoped_performance_run.py` and compare `peak_bytes_mean` plus
   `elapsed_ms_mean`.
4. Use the GitHub PR-scoped performance workflow as the CI merge gate after the
   PR is opened.
