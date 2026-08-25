# Code evaluation runner config read local binding performance slice

## Scope

This Python-only performance slice is limited to the code-evaluation sandbox runner script in `worker.engine.code_eval_runner`.

The original slice preserved runner config JSON semantics by binding `Path.read_bytes` as a default argument in the generated runner helper. The follow-up slice keeps the same semantics and switches the generated runner helper to a single `os.open`/`os.fstat`/`os.read` descriptor read so repeated config reads avoid Path-layer method dispatch in the hot probe loop.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-runner-script-cache` in `infra/perf/pr_scoped_probes.json`.

That probe already declares focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_runner_script_probe.py`

## Implementation plan

1. Keep the static runner script cache intact.
2. Add a regression assertion that the generated runner script performs one descriptor-backed config read and closes the file descriptor.
3. Run the registered focused tests, changed-scope coverage, and PR-scoped probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the merge validation source.

## Linux verification boundary

This slice changes Python code and is locally verifiable on Linux. No Swift runtime behavior is changed.
