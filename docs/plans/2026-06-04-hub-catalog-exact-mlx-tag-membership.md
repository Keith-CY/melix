# Hub Catalog Exact MLX Tag Membership Slice

## Scope

This Python-only performance slice targets `services/mlx-worker-python/worker/model_ops/hub_catalog.py`, specifically the hot tag-payload compatibility helper used while classifying Hugging Face Hub catalog payloads.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. That entry has focused `test_command`, `coverage_command`, and `probe_command` fields and reports `payload_compatibility_elapsed_ms_mean` for this exact helper path alongside the size-hint metrics.

## Implementation Plan

1. Preserve the existing mixed-case `_is_mlx_atom` fallback for broad compatibility.
2. Add a narrow exact-list membership fast path for common `"MLX"` / `"mlx"` Hub tag payloads before falling back to per-item atom checks.
3. Add a focused regression test proving exact `"MLX"` list membership short-circuits the atom helper.
4. Run focused pytest, changed-scope coverage, and the registered PR-scoped performance probe locally on Linux.

## Validation Boundary

This slice is Python-only and locally verifiable on Linux. CI remains the source of truth for the registered PR-scoped performance workflow before merge.
