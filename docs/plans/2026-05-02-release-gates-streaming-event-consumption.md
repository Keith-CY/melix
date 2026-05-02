# Release Gates Streaming Event Consumption

## Goal

Reduce redundant work and avoid materializing full benchmark / convert-model event streams in `release_gates.py` when the code only needs a small summary of manifest, completion, and metric fields.

## Constraints

- Worktree: Linux-only verification.
- Keep the slice Python-only and locally verifiable.
- Preserve existing output shapes, metric names, error behavior, and stage success semantics.
- Register a PR-scoped performance probe for the touched release-gate path.

## Files

- `services/mlx-worker-python/worker/productization/release_gates.py`
- `services/mlx-worker-python/tests/test_release_gates.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/release_gates_event_stream_probe.py`

## Task

1. Add small internal streaming helpers that consume benchmark and convert-model event iterables exactly once while retaining only the needed summary fields.
2. Refactor `collect_benchmark_evidence`, `collect_training_evidence`, and `collect_lora_path_evidence` to use those helpers instead of `list(...)` materialization where safe.
3. Add focused regression tests proving the hot paths no longer depend on list materialization / `events[-1]` semantics.
4. Register a PR-scoped performance probe for the release-gates event-stream path and add focused probe tests.

## Performance Probe

- Probe ID: `release-gates-event-stream-summary`
- Local probe path: `scripts/release_gates_event_stream_probe.py`
- Synthetic workload: fake release-gate benchmark / convert-model event streams with many progress/metric events and a single manifest/completed payload.
- Success metric: lower `elapsed_ms_mean` with unchanged output facts (`metric_count`, completion path presence, training artifact capture).

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_benchmark_evidence_returns_required_metrics \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_benchmark_evidence_includes_cache_recovery_report_when_repo_root_is_supplied \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_training_evidence_returns_required_metrics \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_lora_path_evidence_records_per_stage_metrics \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_lora_path_evidence_compare_stage_reflects_persisted_evidence \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_training_evidence_consumes_convert_stream_without_indexing_last_event \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_lora_path_evidence_consumes_train_stream_without_indexing_last_event \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_release_gates_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_release_gates_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same test selection>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/release_gates.py \
  services/mlx-worker-python/tests/test_release_gates.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/release_gates_event_stream_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/release_gates_event_stream_probe.py

git diff --check
```