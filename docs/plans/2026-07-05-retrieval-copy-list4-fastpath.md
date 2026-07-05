# Retrieval Lookup Payload List4 Copy Fast Path

## Scope

This Python performance slice is limited to retrieval lookup payload copy behavior in
`services/mlx-worker-python/worker/runtime/retrieval_context.py`.

The hot path is `_copy_payload_value`, which deep-copies lookup payloads before they
are surfaced as prompt user payload. Existing specialized paths cover scalar values,
single-key dictionaries, lists of length 0/1/2/3/5, and tuples of length 0 through 5.
This slice adds the missing four-item list specialization for common metadata arrays.

## Probe

The affected path is already covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused test, coverage, and command-json probe commands.

This slice extends `scripts/retrieval_context_projection_probe.py` with a four-item
`quad_scores` metadata list so the registered lookup-copy metric exercises the new
specialization. The registry command now prefers the head probe script when running
against the baseline checkout, then falls back to the local script, so base/head probe
inputs remain comparable when the probe workload changes in the same PR.

## Verification

Run the registered probe commands locally on Linux:

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
