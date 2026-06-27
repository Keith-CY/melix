# Dataset JSONL Row Reader Binding Performance

## Status

Accepted for one focused performance slice on 2026-06-27.

## Scope

Optimize the Python dataset registry JSONL row reader in
`services/mlx-worker-python/worker/dataset_registry/catalog.py` without changing
row filtering, limit handling, or supported dataset formats.

## Probe Coverage

The affected path is covered by the registered PR-scoped performance probe
`dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the dataset preview and row-reader path.

## Slice

Bind the hot JSONL row append method and JSON decoder lookup once per file-read
call so repeated JSONL row parsing avoids repeated attribute lookups while
preserving the same blank-line skipping, non-dict filtering, and limit semantics.

## Verification

Use the registered probe commands for local Linux verification:

- focused dataset registry tests from the registered probe
- changed-scope coverage from the registered probe
- `scripts/dataset_registry_preview_limit_probe.py`

CI must also run the PR-scoped performance workflow and report the registered
probe result before merge.
