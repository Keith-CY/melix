# Training target-module cached-copy local binding

## Scope

This Python-only performance slice targets `services/mlx-worker-python/worker/model_ops/training_config.py`, specifically the cached `_resolve_target_modules(...)` path used when LoRA target-module presets have already been normalized.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `training-config-target-module-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries for the target-module resolution tests, PR-scoped performance selection tests, and `scripts/training_config_target_modules_probe.py`.

## Change

The cached target-module path now binds the module-level list-copy helper into a local variable before checking cached entries. This keeps the fresh-list-per-call safety contract while reducing repeated global lookup overhead in the hot cached resolver loop.

## Validation plan

1. Run the focused tests from the registered probe command.
2. Run the registered changed-scope coverage command and keep changed-scope coverage at or above 95%.
3. Run the registered local Linux probe for `training-config-target-module-cache` against an `origin/main` baseline and accept only if metrics show non-regression or improvement with unchanged checksum.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.

## 2026-08-25 exact-list cache-hit slice

This follow-up Python slice keeps the same registered probe and narrows only the
cached `_resolve_target_modules(...)` branch. Canonical cache entries are always
plain `list` objects, so the hot cache-hit check now uses an exact `type(...) is
list` guard before `list.copy(...)`. Non-plain historical/custom cache entries
still fall through to `list(...)`, preserving defensive compatibility while
removing subclass-aware `isinstance(...)` work from the registered cached-loop
probe.

Validation remains the focused target-module tests, changed-scope coverage, and
the local plus CI `training-config-target-module-cache` probe; `elapsed_ms_mean`
and unchanged checksum are the primary signals for this slice.
