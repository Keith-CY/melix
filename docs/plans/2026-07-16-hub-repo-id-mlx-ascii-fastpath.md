# Hub repo-id MLX lowercase fast path

This Python-only performance slice is limited to the Hub catalog compatibility helper `worker.model_ops.hub_catalog._repo_id_contains_mlx()`.

## Scope

The registered Hub catalog size-hint probe also measures `_payload_is_mlx_compatible()` on representative Hub payloads. Common MLX-compatible repository identifiers already contain lowercase `mlx` in the repo id, such as `owner/model-mlx-suffix`. Before this slice, every repo-id compatibility check lowercased the whole string before checking membership.

This slice preserves case-insensitive behavior while adding a lowercase-ASCII fast path before falling back to `repo_id.lower()` for mixed- or uppercase identifiers.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Verification plan

1. Run the registered focused tests for the Hub catalog probe locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and require at least 95% for touched scope.
3. Run the registered probe command locally on Linux and compare baseline-vs-head metrics.
4. Use GitHub Actions PR-scoped performance as the final registered probe merge gate.

## Expected metrics

Primary metric: lower `payload_compatibility_elapsed_ms_mean` with unchanged `payload_compatibility_matched_count` and size-hint metrics.

## Boundaries

This slice does not change Hub API requests, summary/card record shaping, size-hint parsing, tag normalization, generated protobuf artifacts, or Swift/runtime behavior.
