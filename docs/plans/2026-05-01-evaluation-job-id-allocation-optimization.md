# Evaluation Job-ID Allocation Optimization Plan

## Goal

Reduce redundant filesystem work in `EvaluationCore._next_job_id()` by avoiding repeated low-index directory probes for every new evaluation run while preserving job ID semantics and on-disk layout.

## Constraints

- Host verification is Linux-only.
- The touched runtime path is Python under `services/mlx-worker-python`.
- The change must remain small, behavior-preserving, and locally verifiable.
- Pull request evidence must include focused tests, changed-scope coverage, and a measurable performance probe.
- The existing registered PR-scoped performance probe must remain the verification path; this slice does not modify the probe registry.

## Touched Files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`

## Proposed Change

1. Keep the cached next evaluation job index inside `EvaluationCore`.
2. Prime that cache once from the highest existing `eval-` run directory whose suffix is at least four decimal digits, including rollover names such as `eval-10000`.
3. Replace per-entry `re.fullmatch(...)` calls with a small helper that parses the `eval-` prefix plus decimal suffix directly.
4. Preserve Melix-emitted rollover IDs and valid decimal-digit suffixes that `int(...)` can parse, while still rejecting malformed names.
5. Keep the existing on-disk uniqueness guarantee by still creating the run directory under the job-ID lock.
6. Add regression tests for:
   - parser acceptance/rejection boundaries
   - existing run directories with gaps
   - repeated allocations from the same process
   - single-pass priming behavior
   - rollover directories beyond `9999`

## Performance Probe

### Probe name

`evaluation-job-id-high-water-mark`

### Measurement path

- Seed a synthetic evaluation `runs/` tree with many existing `eval-####` and rollover directories.
- Call `_next_job_id()` repeatedly in the same process.
- Compare base vs head mean elapsed milliseconds.

### Success metric

- Lower `elapsed_ms_mean` is better.
- Lower `per_call_ms_mean` is better.
- Job IDs must remain sequential and unique.

## Local Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_executes_packaged_dataset_and_persists_result services/mlx-worker-python/tests/test_evaluation_core.py::test_parse_run_directory_index_accepts_melix_ids_and_python_decimal_suffixes services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_primes_from_highest_existing_run_directory services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_primes_from_rollover_run_directories services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_only_scans_existing_runs_once_per_process services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_skips_conflicting_cached_index_and_non_directory_entries services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_job_id_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_executes_packaged_dataset_and_persists_result services/mlx-worker-python/tests/test_evaluation_core.py::test_parse_run_directory_index_accepts_melix_ids_and_python_decimal_suffixes services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_primes_from_highest_existing_run_directory services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_primes_from_rollover_run_directories services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_only_scans_existing_runs_once_per_process services/mlx-worker-python/tests/test_evaluation_core.py::test_next_job_id_skips_conflicting_cached_index_and_non_directory_entries services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_job_id_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id evaluation-job-id-high-water-mark --base-repo /tmp/melix-base-20260501-162400 --head-repo /tmp/melix-cron-opt-20260501-162400 --output /tmp/melix-cron-opt-20260501-162400/pr-scoped-evaluation-job-id.json
git diff --check
```

## 2026-05-01 Probe Registry Follow-up

The implementation slice is complete, but a follow-up registry-only slice tightened the PR-scoped evidence contract:

- `evaluation-job-id-high-water-mark` now declares the required `probe_command` alongside its focused test and coverage commands.
- The focused coverage command uses `python3 scripts/changed_scope_coverage.py` to match the repository automation constraint.
- The local probe helper invokes `uv run ... python3` so all evaluation job-id probe paths avoid the unqualified `python` executable.

No runtime allocation behavior changes are introduced by this follow-up; it only makes the registered CI probe runnable and auditable from the registry.
