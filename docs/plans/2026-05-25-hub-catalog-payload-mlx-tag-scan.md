# Hub Catalog Payload MLX Tag Scan

## Goal

Reduce `mlx_only` Hub catalog prefilter overhead by avoiding temporary tag-list materialization when checking raw payload tags for the `mlx` compatibility signal.

## Slice

This Python-only slice is limited to `worker.model_ops.hub_catalog._payload_is_mlx_compatible(...)` and the existing registered PR-scoped probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.

The registered probe already covers:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

The registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries. This slice extends the registered probe metrics with `payload_compatibility_elapsed_ms_mean` and `payload_compatibility_calls_mean` so the raw payload `mlx_only` prefilter path is measured directly.

## Implementation

- Reuse the existing `_tag_payload_contains_mlx(...)` scanner for raw payload `tags` in `_payload_is_mlx_compatible(...)`.
- Preserve existing behavior for string tags, mixed non-string list entries, library-name checks, repo-id suffix checks, and card-data tag fallback.
- Add a regression test that monkeypatches `_string_list(...)` to prove the prefilter path does not allocate a normalized tag list.

## Verification

Run the registered focused test command, changed-scope coverage command, and the `hub-catalog-size-hint-regex-precompile` probe locally on Linux. CI PR-scoped performance remains the merge gate for the registered probe report.
