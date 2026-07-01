# Code Eval Temp Root Sandbox Filter Fast Path

## Scope

This Python-only performance slice is limited to `worker.engine.code_eval_runner._sandbox_profile()` and the temp-root read filter construction used for each sandboxed code-evaluation attempt.

The static sandbox profile fragments are cached, but each invocation still builds the per-attempt temp-root read filters. The previous implementation routed a single temp root through the generic multi-path `_sandbox_allow_path_variants()` helper, allocating a tuple, list, and set before joining the generated filters.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-stdio-tail-single-stat` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_stdio_probe.py`

## Change

Add a single-temp-root helper that formats the temp-root read filters directly while preserving the existing path-variant semantics:

- include the original temp-root path;
- include the resolved temp-root path when it differs;
- elide the duplicate filter when the original and resolved path text match;
- fall back to the original path if resolution raises `OSError`.

This keeps the generic multi-path variant helper available for static runtime paths while avoiding its allocation overhead on the per-attempt sandbox profile path.

## Verification plan

1. Add focused regression coverage for duplicate-elision and relative-path preservation in the new temp-root filter helper.
2. Run the registered focused tests locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered local probe before and after the change and compare `sandbox_profile_elapsed_ms_mean` while confirming stdio metrics remain unchanged.
5. Use PR-scoped performance CI as the merge gate before squash merging.

## Metrics

Success is measured by a lower or non-regressing `sandbox_profile_elapsed_ms_mean` in `code-eval-stdio-tail-single-stat`, with unchanged `stdio_stat_calls_mean` and `sandbox_profile_static_builds_mean`. This slice has no Swift runtime effect.
