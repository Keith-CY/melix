# Deterministic Embedding Single-Cycle Extend Performance Slice

## Scope

This Python-only slice is limited to `DeterministicEmbeddingRuntime.embed_inputs()` for large requests where every input repeats the same text (`cycle_length == 1`).

## Registered Probe

The affected path is covered by the existing PR-scoped probe `deterministic-embedding-duplicate-input-cache` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the deterministic embedding runtime, its tests, and `scripts/deterministic_embedding_duplicate_probe.py`.

## Optimization

The single-input cycle replay now seeds the result list with the first embedded vector and uses one `list.extend(...)` call for the remaining defensive copies. This preserves the existing behavior that repeated outputs do not share mutable vector lists, while avoiding a Python-level append method call for every replayed input.

## Verification Plan

Run locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_embedding_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_embedding_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_embedding_duplicate_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_embedding_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_embedding_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_embedding_duplicate_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py services/mlx-worker-python/tests/test_embedding_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/deterministic_embedding_duplicate_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/deterministic_embedding_duplicate_probe.py
python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id deterministic-embedding-duplicate-input-cache --base-repo /root/.hermes/profiles/coder/workspace/melix --head-repo "$PWD" --output /tmp/deterministic-embedding-duplicate-input-cache.json
```

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
