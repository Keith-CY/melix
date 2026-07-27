# Retrieval lookup payload list-11 copy fast path

## Scope

This slice keeps the retrieval lookup payload projection behavior unchanged while
adding a direct copy fast path for hot eleven-item list payload values in
`services/mlx-worker-python/worker/runtime/retrieval_context.py`.

## Probe Coverage

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
That registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries. This slice extends the probe fixture with an
eleven-item list payload so the registered lookup-copy metric exercises the new
branch.

## Verification Plan

1. Run the focused retrieval copy regression test.
2. Run the registered probe focused test command for
   `retrieval-context-projection-fastpath`.
3. Run the registered changed-scope coverage command.
4. Run the registered probe command locally on Linux and compare with the
   pre-change baseline.

## Expected Metrics

The primary metric is the registered probe's
`lookup_copy_optimized_elapsed_ms_mean`; lower is better. The direct eleven-item
list branch avoids the generic list-comprehension path for fixed-width retrieval
metadata vectors while preserving deep-copy behavior for nested values.
