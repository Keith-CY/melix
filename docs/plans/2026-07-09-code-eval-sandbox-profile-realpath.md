# Code eval sandbox profile realpath slice

## Scope

This Python-only performance slice is limited to the code-evaluation sandbox
profile builder in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.
The hot path rebuilds the temp-root read filters for every candidate execution;
those temp roots are normal `pathlib.Path` instances, so resolving them through
`Path.resolve()` adds avoidable object overhead while preserving no additional
behavior over `os.path.realpath(str(path))` for this path.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`code-eval-stdio-tail-single-stat` in `infra/perf/pr_scoped_probes.json`. The
probe has focused `test_command`, `coverage_command`, and `probe_command` entries
covering:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_stdio_probe.py`

The probe reports `sandbox_profile_elapsed_ms_mean`,
`sandbox_profile_static_builds_mean`, `sandbox_profile_length_mean`, and the
existing stdio tail metrics. CI PR-scoped performance remains the registered
merge gate.

## Implementation

Use `os.path.realpath(str(temp_root))` for normal `Path` instances inside
`_sandbox_temp_root_read_filters(...)`, while keeping the existing
`temp_root.resolve()` fallback for non-`Path` test doubles that can raise
`OSError`. `_sandbox_profile(...)` also reuses a single quoted temp-root string
and builds the final profile directly instead of allocating a tuple for
`" ".join(...)`.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux before opening the PR. Compare the probe against the
same-worktree origin/main implementation with at least three samples. The main
acceptance metric is lower `sandbox_profile_elapsed_ms_mean` with unchanged
`sandbox_profile_static_builds_mean` and `sandbox_profile_length_mean`.
