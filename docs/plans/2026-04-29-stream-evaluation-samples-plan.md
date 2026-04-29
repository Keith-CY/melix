# Stream Evaluation Sample Loading Plan

## Scope

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`

## Goal

Reduce peak memory when `EvaluationCore.run_local_suite()` loads packaged evaluation datasets from `samples.jsonl` without changing parsed sample content, ordering, or blank-line handling.

## Linux-Only Constraint

This change is intentionally limited to the Python worker path under `services/mlx-worker-python` so it can be verified on Linux with focused pytest, coverage, and a synthetic performance probe.

## Proposed Change

Replace the current `read_text(...).splitlines()` materialization of `samples.jsonl` with a streaming helper that iterates the file line by line, skips blank lines, and decodes JSON rows in order.

## Performance Probe

Run a self-contained Python probe that creates a synthetic `samples.jsonl`, parses it using the current `origin/main` helper logic and the new branch logic, and records:

- parsed row counts for equivalence
- elapsed seconds
- peak traced allocation via `tracemalloc`

## Success Metrics

- Parsed row counts remain identical.
- Targeted tests for `test_evaluation_core.py` pass.
- Coverage for the touched executable file remains at least 95%.
- The probe shows materially lower peak traced allocation for the streamed path.

## Verification Commands

```text
PYTHONPATH=<repo>:<repo>/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_core.py -k 'run_local_suite and not executes_code and not candidate_code'
PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_evaluation_core.py -k 'run_local_suite and not executes_code and not candidate_code'
PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/tests/test_evaluation_core.py
python /tmp/<probe>.py
git diff --check
```