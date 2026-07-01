# Stream assembler token-byte positional delta slice

## Scope

Optimize exactly one Python hot path in `RequestStreamAssembler.accept`: the plain
`token_bytes` fast path that emits an `AssemblyDelta` immediately for complete
visible byte fragments.

Affected files:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py` (existing focused coverage)
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py` (existing probe selection coverage)
- `scripts/stream_assembler_token_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` fields for Linux CI.

## Optimization

The immediate visible `token_bytes` branch constructs the returned
`AssemblyDelta` with positional arguments instead of keyword arguments. The
field values and parsing semantics remain unchanged; the change only avoids
keyword-binding overhead in the registered hot path.

## Verification

Run the registered test command, changed-scope coverage command, and registered
probe locally on Linux. Compare the registered probe against the pre-optimization
baseline from the same worktree before pushing.

## Success criteria

- Focused stream assembler token-byte regression tests pass.
- Changed-scope coverage remains at least 95% for touched executable files.
- Local registered probe shows lower `elapsed_ms_mean` than the pre-optimization
  baseline.
- PR-scoped performance CI selects and completes
  `stream-assembler-token-byte-fast-decode`.
