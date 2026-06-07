# Code-eval test count line scan

## Goal

Reduce allocation pressure in the code-evaluation fallback test counter by avoiding `str.splitlines()` list materialization when `_count_tests()` cannot derive an assert count from the AST.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_count_tests_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python worker slice and is locally verifiable on Linux with focused pytest, changed-scope coverage, and a command-json performance probe.

## Performance probe definition

Register `code-eval-count-tests-line-scan` in the PR-scoped performance registry. The probe exercises the syntax-error and no-assert fallback paths with large blank-heavy test strings and reports:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- structural row-count metrics to prove the same synthetic workload ran

## Success metrics

- Functional behavior matches the old nonblank-line counting semantics for LF, CRLF, CR, blank, and whitespace-only lines.
- Changed-scope coverage is at least 95%.
- Local base-vs-head probe shows lower peak allocation and no severe latency regression on the fallback line-count path.

## 2026-05-30 regex fallback slice

The follow-up slice keeps the same registered probe and replaces the manual
character-by-character fallback line counter with a compiled regex that matches
each line containing at least one non-whitespace character while preserving LF,
CRLF, CR, and Unicode whitespace behavior.

## 2026-06-07 all-assert AST fast path

This follow-up keeps the same registered `code-eval-count-tests-line-scan` probe
and narrows the implementation to `_count_assert_nodes()` when parsed test code
is made entirely of top-level `assert` statements. That common generated-test
shape can return `len(module.body)` after exact-type checks, avoiding stack setup
and nested-container traversal work while preserving the existing traversal for
mixed or nested modules.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <focused test nodes>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <focused test nodes>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json <changed files>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/code_eval_count_tests_probe.py
python scripts/pr_scoped_performance_run.py --probe-id code-eval-count-tests-line-scan --base-ref origin/main --head-ref HEAD --output /tmp/code-eval-count-tests-probe.json
```
