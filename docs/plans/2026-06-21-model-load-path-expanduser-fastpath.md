# Model Load Path Expanduser Fast Path

## Scope

This Python-only performance slice is limited to model-load trust policy custom-loader detection in `services/mlx-worker-python/worker/model_load_trust.py`.

Repeated local model-load trust checks already cache parsed `config.json` payloads by file stat. This slice narrows the per-resolution path setup before that cache lookup: plain absolute or relative model paths no longer call `Path.expanduser()`. Tilde-prefixed paths keep the existing expansion behavior.

## Registered probe

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and selects this probe when `worker/model_load_trust.py` changes.

## Implementation plan

1. Add a regression test proving plain model paths do not call `Path.expanduser()` while preserving custom-loader detection receipts.
2. Update `_read_model_config()` to call `expanduser()` only when the stripped model path starts with `~`.
3. Run the registered focused tests, changed-scope coverage, and local PR-scoped probe on Linux.
4. Use GitHub Actions PR-scoped performance as the final registered probe validation before merge.

## Expected outcome

The repeated-resolution probe should show a small latency reduction for the common plain local path case without changing missing-file, invalid-config, or tilde-path behavior.

## 2026-06-29 follow-up: config path text cache

This follow-up keeps the same Python-only boundary and registered `model-load-config-json-bytes` probe. The previous slices left repeated model-load trust resolutions rebuilding the same `config.json` path string before the file-stat and JSON detection caches. This slice caches the derived `(config_path_text, stat_path)` pair by stripped model path while preserving the existing empty-path, plain-path, and tilde-path behavior.

Implementation and validation:

1. Add a focused regression test proving repeated `_model_config_path()` calls reuse the cached path derivation.
2. Factor the string-to-config-path derivation into a bounded `lru_cache` helper.
3. Run the registered focused tests, changed-scope coverage, and local PR-scoped `model-load-config-json-bytes` probe on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## 2026-06-29 follow-up: shared config path for direct reads

This follow-up keeps the same Python-only boundary and registered `model-load-config-json-bytes` probe. The direct `_read_model_config(...)` helper still rebuilt the same stripped model-path-to-`config.json` string path even though trust-policy detection now caches that derivation through `_model_config_path(...)`. This slice routes `_read_model_config(...)` through the shared cached path helper, preserving empty-path, plain-path, and tilde-path behavior while avoiding duplicate path string construction on repeated direct config reads.

Validation uses the existing focused model-load trust tests, changed-scope coverage, and registered local probe; GitHub Actions PR-scoped performance remains the merge gate.
