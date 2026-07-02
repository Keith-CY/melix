# Model load requested-mode membership fast path

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/model_load_trust.py` trust-policy requested-mode resolution. It does not change model-load trust semantics, executable model-file detection, generated protocol artifacts, Swift code, or dependency metadata.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and selects this probe when `worker/model_load_trust.py` changes.

## Optimization

`_requested_mode()` currently constructs an identical two-element set literal for request-policy membership checks and another identical set for model-settings membership checks on every model-load trust-policy resolution. The hot path runs during repeated custom-loader policy checks, so this slice hoists the valid requested-mode set to a module-level `frozenset` and reuses it for both membership checks.

Expected effect: lower per-call allocation overhead with unchanged behavior for request policy, model settings, and default-safe fallback resolution.

## Verification plan

1. Run the registered focused test command for `model-load-config-json-bytes` locally on Linux.
2. Run the registered changed-scope coverage command locally and confirm changed-scope coverage remains at least 95%.
3. Run the registered probe locally against a fresh `origin/main` baseline and this branch.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.
