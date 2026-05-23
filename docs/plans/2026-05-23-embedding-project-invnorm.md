# Deterministic Embedding Projection Inverse-Norm Slice

## Goal

Reduce per-projection arithmetic overhead in deterministic embedding vector
projection without changing vector values, normalization semantics, or public
embedding runtime behavior.

## Scope

This is a Python-only slice limited to
`services/mlx-worker-python/worker/runtime/embedding_backends.py`, its focused
embedding runtime tests, and this plan. It does not change real MLX embedding
model behavior or generated protocol artifacts.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. That probe has focused `test_command`,
`coverage_command`, and `probe_command` entries and measures repeated
`_project_digest()` calls at 4096 dimensions with elapsed time, peak bytes, and
checksum stability.

## Implementation Plan

1. Keep the existing regression parity test against the legacy projection values
   across small, boundary, and large dimensions.
2. Compute `1.0 / l2_norm` once per projected digest and multiply each base
   value by that inverse during normalization, instead of dividing each base
   value by the same norm repeatedly.
3. Preserve the `l2_norm == 0.0` guard and the existing rounded values.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR. GitHub Actions PR-scoped performance remains
   the merge gate.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_embedding_runtime.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_embedding_project_digest_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_embedding_project_digest_probe_script_smoke

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_embedding_runtime.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_embedding_project_digest_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_embedding_project_digest_probe_script_smoke
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/runtime/embedding_backends.py \
  services/mlx-worker-python/tests/test_embedding_runtime.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/deterministic_embedding_project_digest_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id deterministic-embedding-project-digest-allocation \
  --base-repo <baseline-worktree> \
  --head-repo "$PWD" \
  --output /tmp/embedding-project-invnorm-probe.json
```
