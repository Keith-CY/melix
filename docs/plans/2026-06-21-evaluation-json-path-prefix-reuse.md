# Evaluation JSON Path Prefix Reuse Slice

## Goal

Reduce per-field overhead in schema-free final-result JSON scoring by reusing the current path prefix while `_json_typed_score(...)` walks wide dictionaries.

## Scope

- Change exactly one Python optimization point in `services/mlx-worker-python/worker/productization/evaluation_final_result.py`.
- Preserve recursive scoring semantics for dictionaries, lists, scalar mismatches, exact-root matches, and ignored JSON paths.
- Keep extraction behavior, JSON parsing/cache behavior, and materialization code unchanged.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `evaluation-final-result-json-typed-score-aggregate` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused:

- `test_command` for final result scoring behavior, PR-scoped probe selection, and probe script emission.
- `coverage_command` for the same focused tests plus changed-scope coverage on the touched implementation, test, probe registry, and probe script paths.
- `probe_command` through `scripts/evaluation_json_typed_score_probe.py`, which measures `elapsed_ms_mean`, `peak_bytes_mean`, and checksum correctness over a wide JSON scoring workload.

## Root Cause / Hypothesis

The wide JSON scoring hot path builds a child path for each dictionary key using a per-iteration conditional f-string. In a wide payload this repeats the same parent-prefix decision thousands of times. Reusing a precomputed `child_prefix` per dictionary frame should reduce string formatting overhead without changing which ignored paths are checked.

## Verification

Focused local Linux verification for this slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_evaluation_final_result.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_evaluation_json_typed_score_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/evaluation_final_result.py \
  services/mlx-worker-python/tests/test_evaluation_final_result.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/evaluation_json_typed_score_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id evaluation-final-result-json-typed-score-aggregate \
  --base-repo <baseline-worktree> \
  --head-repo "$PWD" \
  --output /tmp/evaluation_json_path_prefix_probe.json
```

## Metrics

Baseline direct probe on `origin/main` before implementation:

```json
{"elapsed_ms_mean": 19.635496331223596, "iteration_count": 40.0, "key_count": 2000.0, "peak_bytes_mean": 1189429.6666666667, "score_checksum": 35.0}
```

Accept only if the registered local probe shows non-regression or improvement for `elapsed_ms_mean`; GitHub Actions PR-scoped performance remains the merge gate.
