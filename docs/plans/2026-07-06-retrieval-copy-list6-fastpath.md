# Retrieval lookup payload six-item list copy fast path

## Goal

This Python performance slice is limited to `worker.runtime.retrieval_context._copy_payload_value(...)`, used when `project_retrieval_lookup_result(...)` copies retrieval lookup payloads into prompt-user content.

## Scope

- Add explicit six-item `list` and `tuple` copy branches in `_copy_payload_value(...)`.
- Extend the existing lookup-copy regression test with six-item list and tuple payload shapes.
- Extend the registered `retrieval-context-projection-fastpath` probe fixture so lookup payload copies exercise six-item containers.

## Registered probe

The affected path is already covered by `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

## Verification plan

1. Run the registered focused pytest command for `retrieval-context-projection-fastpath`.
2. Run the registered changed-scope coverage command.
3. Run `scripts/retrieval_context_projection_probe.py` locally on Linux.
4. Run the registered PR-scoped probe comparison against `origin/main` before pushing.

## Success metric

The local registered probe should preserve projection guard-rail counts and improve `lookup_copy_optimized_elapsed_ms_mean` / `lookup_copy_delta_ms` for the six-item lookup payload fixture versus the `origin/main` baseline.
