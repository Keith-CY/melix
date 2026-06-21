# Model load route class map performance slice

## Scope

This Python-only performance slice is limited to `worker.model_load_trust._route_class()` in `services/mlx-worker-python/worker/model_load_trust.py`.

## Change

`resolve_model_load_trust_policy(...)` calls `_route_class()` for applicable text/VLM model loads before config JSON custom-loader detection. The previous fallback flow rebuilt the same runtime-kind-to-route-class dictionary on each policy resolution when neither the request nor model spec provided an explicit route class.

This slice hoists that static mapping to the module-level `ROUTE_CLASS_BY_RUNTIME_KIND` constant and reuses it for fallback lookup. That removes a repeated dictionary allocation while preserving request override behavior, model-spec override behavior, unknown-runtime fallback behavior, and all supported runtime-kind route defaults.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `Model load config JSON bytes` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` commands for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

## Local validation plan

Run on Linux:

1. Focused model-load trust tests.
2. Registered changed-scope coverage command for the `Model load config JSON bytes` probe.
3. Registered probe command with repeated samples and the same iteration count before/after the implementation.

## Expected effect

The slice removes repeated fallback route-class dictionary construction from each model-load trust policy resolution. Accept only if the registered probe shows directionally better elapsed-time metrics without behavior drift.
