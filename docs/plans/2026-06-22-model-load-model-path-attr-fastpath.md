# Model Load Model Path Attribute Fast Path

## Scope

This Python-only performance slice is limited to model-load trust policy custom-loader detection in `services/mlx-worker-python/worker/model_load_trust.py`.

Repeated local model-load trust checks read `ModelSpec.model_path` before probing `config.json`. Earlier slices removed unnecessary `Path.expanduser()` and `Path` join work for plain paths. This slice removes the remaining generic `getattr(..., "model_path", "")` lookup in the hot path and uses the typed protobuf field directly.

## Registered probe

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and selects this probe when `worker/model_load_trust.py` changes.

## Implementation plan

1. Preserve the existing model-load trust behavior tests for custom-loader detection, config byte loading, stat-keyed caching, tilde expansion, plain-path fast paths, and missing config handling.
2. Update `_read_model_config()` to read `model_spec.model_path` directly instead of using a dynamic attribute fallback.
3. Run the registered focused tests, changed-scope coverage, and local PR-scoped probe on Linux.
4. Use GitHub Actions PR-scoped performance as the final registered probe validation before merge.

## Expected outcome

The repeated-resolution probe should show a small latency reduction for the typed `ModelSpec` hot path without changing custom-loader detection receipts, tilde-path behavior, or missing-config behavior.
