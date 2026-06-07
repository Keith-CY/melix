# Code Eval Sandbox Key Fast Path

## Scope

This Python-only performance slice is limited to `worker.engine.code_eval_runner._sandbox_static_profile_key()`.
The sandbox profile builder runs for each code-evaluation attempt while the static sandbox fragments are cached. On the cached path it only needs to prove the Python environment has not changed.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-stdio-tail-single-stat` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_stdio_probe.py`

## Change

Fast-path the populated static-profile key cache by comparing the cached fingerprint fields directly against the current Python environment. This avoids rebuilding a fingerprint tuple on every cached sandbox profile request, while preserving the slower miss path that includes `sysconfig.get_paths()` in the cache key.

## Verification plan

1. Add focused regression coverage proving the cached key path does not rebuild the fingerprint tuple while still returning the exact cached key object.
2. Run the registered focused tests locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered local probe against `origin/main` and this branch to compare `sandbox_profile_ms_mean`, `sandbox_profile_length_mean`, and existing stdio metrics.
5. Use PR-scoped performance CI as the merge gate before squash merging.

## Metrics

Success is measured by a lower or non-regressing `sandbox_profile_elapsed_ms_mean` in `code-eval-stdio-tail-single-stat`, with unchanged existing stdio tail/stat counters. Sandbox profile length is tracked as a diagnostic because absolute temp-root path lengths can differ between baseline and head worktrees. This slice has no Swift runtime effect.
