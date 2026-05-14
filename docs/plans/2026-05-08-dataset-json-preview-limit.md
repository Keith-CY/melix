# Dataset JSON Preview Limit Short-Circuit

## Goal

Reduce memory pressure when previewing local Hugging Face dataset snapshots whose first selected file is a large `.json` payload but callers request a small `limit`.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and is verifiable on Linux with focused pytest, changed-scope coverage, and the existing `dataset-registry-preview-limit-short-circuit` PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `scripts/dataset_registry_preview_limit_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Implementation plan

1. Thread `limit` into the JSON payload row extraction helper used by `_read_rows_from_file`.
2. For top-level lists and canonical `rows` / `data` arrays, collect only dict rows up to the requested limit.
3. Preserve unlimited behavior and the generic fallback shape for arbitrary nested list payloads.
4. Add focused regression coverage that guards against the old full list materialization for canonical JSON arrays.
5. Update the existing preview-limit probe to exercise a large single-file JSON payload and make the registry command use the head probe script for base-vs-head comparisons.
6. Reuse a module-level `json.JSONDecoder` for limited JSON preview scanning so each preview call avoids reconstructing identical decoder state while preserving `raw_decode` semantics.
7. Add regression coverage proving the limited JSON preview path routes both wrapper-object and row decoding through the shared decoder.

## Performance probe definition

Probe ID: `dataset-registry-preview-limit-short-circuit`.

The probe builds a synthetic snapshot with one large `train.json` file containing `rows`, then repeatedly calls `read_hf_dataset_snapshot_rows(snapshot_dir, limit=1)` while measuring elapsed time and traced peak allocation.

## Success metrics

- Focused pytest passes.
- Changed executable line coverage for touched Python scope is at least 95%.
- `git diff --check` passes.
- Local probe reports concrete `elapsed_ms_mean` and `peak_bytes_mean`; expected primary win is lower peak bytes for JSON preview reads versus `origin/main`.
