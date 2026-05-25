# Stream assembler direct UTF-8 token-byte decode

## Scope

This Python-only performance slice narrows one hot path in
`RequestStreamAssembler._token_byte_delta`: complete `token_bytes` fragments that
arrive without pending partial bytes.

Affected files:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `docs/plans/2026-05-25-stream-token-bytes-direct-utf8.md`

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`.
That registry entry has focused `test_command`, `coverage_command`, and
`probe_command` entries and watches the stream assembler implementation, focused
stream assembler tests, PR-scoped-performance selection tests, and
`scripts/stream_assembler_token_bytes_probe.py`.

The primary metric is `elapsed_ms_mean` (`lower_is_better`). `peak_bytes_mean`
is a guardrail, and `generated_token_count_mean` remains informational behavior
parity evidence.

## Optimization

The previous fast path checked `token_bytes.isascii()` and decoded ASCII payloads
with `decode("ascii")`, then fell through to `decode("utf-8")` for complete
non-ASCII payloads. This slice removes the redundant ASCII pre-check and attempts
a direct default UTF-8 decode first (`bytes.decode()`), which avoids passing an
encoding argument on the hot path. Invalid or split multibyte fragments still
fall back to the existing incremental decoder path after `UnicodeDecodeError`.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux. Compare the registered probe against an `origin/main`
baseline from the same commit before pushing. CI PR-scoped performance remains
the merge gate.

## Success criteria

- Focused stream assembler token-byte tests pass.
- Changed-scope coverage remains at least 95% for touched executable scope.
- The registered probe shows an improved or clearly non-regressed
  `elapsed_ms_mean` with unchanged `generated_token_count_mean`.
- GitHub Actions PR-scoped performance selects and completes the registered probe
  before merge.
