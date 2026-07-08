# Retrieval Lookup Payload List7 Copy Fast Path

## Scope

This Python performance slice is limited to retrieval lookup payload copy behavior in
`services/mlx-worker-python/worker/runtime/retrieval_context.py`.

The hot path is `_copy_payload_value`, which deep-copies lookup payloads before they
are surfaced as prompt user payload. Existing specialized paths cover scalar values,
single-key dictionaries, lists of length 0 through 6, and tuples of length 0 through
6. This slice adds the next fixed-size seven-item list and tuple specialization for
retrieval metadata arrays that carry an additional section/window marker.

## Probe

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries for the touched retrieval path and the command-json probe script.

This slice extends `scripts/retrieval_context_projection_probe.py` with seven-item
`seven_scores` and `seven_labels` metadata containers so the registered lookup-copy
metric exercises the new specialization. The registry command already prefers the
head probe script when running against baseline, keeping base/head workloads
comparable when probe inputs change in the same PR.

## Verification

Run the registered probe commands locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_retrieval_lookup_payload_copy_preserves_scalar_and_none_values services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_retrieval_lookup_payload_copy_preserves_scalar_and_none_values services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/retrieval_context.py services/mlx-worker-python/tests/test_retrieval_context.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/retrieval_context_projection_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_RETRIEVAL_CONTEXT_PROJECTION_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/retrieval_context_projection_probe.py
```

## Success Criteria

- Behavior remains unchanged for nested payload copying and isolation.
- Changed-scope coverage for the touched retrieval context files remains at or above
  the repository threshold.
- The registered probe reports lookup-copy speedup above baseline and no in-scope
  regression for the existing projection/store metrics.