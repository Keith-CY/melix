# Stream assembler token-byte fast decode

## Scope

Optimize exactly one Python hot path in `RequestStreamAssembler`: complete UTF-8 token-byte fragments that arrive without pending partial bytes.

Affected files:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/stream_assembler_token_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

Register `stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json` with focused test, coverage, and command-json probe commands.

The probe feeds many ASCII `token_bytes` fragments through a plain stream assembler and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `generated_token_count_mean`

## Optimization

When there are no pending partial token bytes, decode the incoming byte fragment directly with `bytes.decode("utf-8")`. Fall back to the existing incremental decoder path for split multibyte sequences or invalid bytes so behavior remains unchanged.

## Verification

Run the registered test command, changed-scope coverage command, and registered probe locally on Linux. Compare the registered probe against the pre-optimization baseline from the same worktree after adding the probe but before changing runtime behavior.

## Success criteria

- Focused stream assembler token-byte regression tests pass.
- Changed-scope coverage remains at least 95% for touched executable files.
- Local registered probe shows lower `elapsed_ms_mean` than the pre-optimization baseline.
- PR-scoped performance CI selects and completes `stream-assembler-token-byte-fast-decode`.
