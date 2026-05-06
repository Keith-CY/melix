# Runtime Utils Bound Kwarg Parameter Scan Optimization

## Goal

Avoid materializing a temporary `list(parameters.items())` plus sliced `dict` in `worker.runtime.runtime_utils.callable_accepts_kwarg(...)` when checking bound methods through the underlying unbound function.

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a local synthetic probe. No Swift/macOS behavior is changed.

## Touched files

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `docs/plans/2026-05-06-runtime-utils-bound-kwarg-scan.md`

## Performance probe definition

Use the already-registered scoped CI probe selected by `runtime_utils.py` changes:

- `runtime-utils-kwarg-signature-cache`

For local evidence, run a file-backed synthetic bound-method cold-cache probe against a detached `origin/main` worktree and this branch. The probe repeatedly clears the kwarg cache and checks two keywords on a bound method with many parameters, recording elapsed time and peak traced allocation.

## Success metrics

- Behavior-preserving focused tests pass.
- Changed-scope coverage for touched executable Python lines is at least 95%.
- Local bound-method probe shows lower elapsed time and/or lower peak allocation while preserving expected boolean results.
- Existing scoped CI probe `runtime-utils-kwarg-signature-cache` is selected for the PR.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_runtime_utils.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_utils_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_utils_kwarg_cache_probe_script_emits_metrics`
- Coverage command matching `runtime-utils-kwarg-signature-cache`.
- Local `/tmp/runtime_utils_bound_kwarg_probe.py` run against detached `origin/main` and head.
- `git diff --check`
