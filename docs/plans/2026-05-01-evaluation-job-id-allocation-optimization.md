# Evaluation Job-ID Allocation Optimization Plan

## Goal

Reduce redundant filesystem work in `EvaluationCore._next_job_id()` by avoiding repeated low-index directory probes for every new evaluation run while preserving job ID semantics and on-disk layout.

## Constraints

- Host verification is Linux-only.
- The touched runtime path is Python under `services/mlx-worker-python`.
- The change must remain small, behavior-preserving, and locally verifiable.
- Pull request evidence must include focused tests, changed-scope coverage, and a measurable performance probe.
- The change must register a PR-scoped performance probe in the existing scoped performance infrastructure.

## Touched Files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/changed_scope_coverage.py`

## Proposed Change

1. Cache the next evaluation job index inside `EvaluationCore`.
2. Prime that cache once from the highest existing `eval-####` run directory.
3. Keep the existing on-disk uniqueness guarantee by still creating the run directory under the job-ID lock.
4. Add regression tests for:
   - existing run directories with gaps
   - repeated allocations from the same process
   - single-pass priming behavior
5. Register a new PR-scoped performance probe for evaluation job-ID allocation.

## Performance Probe

### Probe name

`evaluation-job-id-high-water-mark`

### Measurement path

- Seed a synthetic evaluation `runs/` tree with many existing `eval-####` directories.
- Call `_next_job_id()` repeatedly in the same process.
- Compare base vs head mean elapsed milliseconds.

### Success metric

- Lower `elapsed_ms_mean` is better.
- Lower `per_call_ms_mean` is better.
- Job IDs must remain sequential and unique.

## Local Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id evaluation-job-id-high-water-mark --base-repo . --head-repo . --output /tmp/evaluation-job-id-probe.json
git diff --check
```

## 2026-05-01 Probe Registry Follow-up

The implementation slice is complete, but a follow-up registry-only slice tightened the PR-scoped evidence contract:

- `evaluation-job-id-high-water-mark` now declares the required `probe_command` alongside its focused test and coverage commands.
- The focused coverage command uses `python3 scripts/changed_scope_coverage.py` to match the repository automation constraint.
- The local probe helper invokes `uv run ... python3` so all evaluation job-id probe paths avoid the unqualified `python` executable.

No runtime allocation behavior changes are introduced by this follow-up; it only makes the registered CI probe runnable and auditable from the registry.
