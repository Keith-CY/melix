# Code evaluation runner config read local binding performance slice

## Scope

This Python-only performance slice is limited to the code-evaluation sandbox runner script in `worker.engine.code_eval_runner`.

The change preserves runner config JSON semantics while binding `Path.read_bytes` as a default argument in the generated runner helper so repeated config reads avoid the per-call bound-method lookup inside the hot probe loop.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-runner-script-cache` in `infra/perf/pr_scoped_probes.json`.

That probe already declares focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_runner_script_probe.py`

## Implementation plan

1. Keep the static runner script cache intact.
2. Add a regression assertion that the generated runner script binds `Path.read_bytes` locally and loads config bytes through that binding.
3. Run the registered focused tests, changed-scope coverage, and PR-scoped probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the merge validation source.

## Linux verification boundary

This slice changes Python code and is locally verifiable on Linux. No Swift runtime behavior is changed.
