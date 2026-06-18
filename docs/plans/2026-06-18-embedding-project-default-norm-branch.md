# Embedding project default-dimension norm branch slice

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/runtime/embedding_backends.py` and the
registered deterministic embedding projection path. It preserves deterministic
embedding values while replacing the default-dimension zero-norm guard's
exception path with an explicit norm check.

No protocol, Swift, macOS, model registry, runtime admission, or generated
protobuf behavior changes are included.

## Registered performance probe

The affected path is already covered by the registered PR-scoped performance
probe `deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` fields, and watches:

- `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_embedding_project_digest_probe.py`

## Optimization slice

1. Keep the digest projection base-value construction unchanged.
2. For the `dimensions == 8` hot path, compute `l2_norm` once, branch on
   `0.0`, and then divide by the norm for ordinary non-zero vectors.
3. Keep the zero-vector fallback identical (`[0.0] * 8`).
4. Verify with the registered focused tests, changed-scope coverage, and the
   registered local probe on Linux.
5. Use GitHub Actions PR-scoped performance as the final merge gate.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_embedding_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_embedding_project_digest_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_embedding_project_digest_probe_script_smoke
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_embedding_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_embedding_project_digest_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_embedding_project_digest_probe_script_smoke && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/embedding_backends.py services/mlx-worker-python/tests/test_embedding_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/deterministic_embedding_project_digest_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id deterministic-embedding-project-digest-allocation --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/embedding_project_digest_probe.json
```

## Expected metrics

The primary target is lower `elapsed_ms_mean` for expanded projection and no
behavior/checksum drift. `default_dimension_elapsed_ms_mean` should remain flat
or improve. Peak byte metrics are accepted only when they stay within the
registered probe threshold and the primary elapsed metric improves.
