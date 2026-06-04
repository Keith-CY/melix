# Hub Catalog Tag Payload Single-Pass Probe Slice

## Scope

Optimize one small Python hot path in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`: `_tag_payload_contains_mlx(...)` currently performs list membership checks before a fallback loop for MLX tag detection. This slice keeps behavior unchanged while collapsing list payload detection into a single pass.

## Registered Probe

The affected path is covered by the registered PR-scoped `hub-catalog-size-hint-regex-precompile` command-json probe in `infra/perf/pr_scoped_probes.json`. That probe watches `hub_catalog.py`, has focused `test_command`, `coverage_command`, and `probe_command` entries, and reports both size-hint and payload-compatibility timing metrics.

## Verification Plan

- Run the focused Hub catalog test command from the registered probe.
- Run the registered changed-scope coverage command from the probe.
- Run `scripts/hub_catalog_size_hint_probe.py` locally on Linux before and after the change and compare `payload_compatibility_elapsed_ms_mean` plus the overall `elapsed_ms_mean` metrics.

## Success Criteria

- Behavior remains identical for list, string, and non-string tag payloads.
- Changed-scope coverage remains at or above 95 percent.
- The registered probe shows an improvement in payload compatibility timing without a meaningful regression in the size-hint path.
