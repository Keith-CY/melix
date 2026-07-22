# Stream Assembler Token-Byte Direct Decode Slice

## Goal

Reduce Python stream assembler overhead when a UTF-8 token byte sequence is split across fragments by replacing the incremental decoder allocation in `_token_byte_delta()` with a direct `bytes.decode("utf-8")` path that buffers only trailing incomplete UTF-8 bytes.

## Scope

This Python-only performance slice is limited to:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`

No protobuf or generated artifact changes are required.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and watches the stream assembler implementation, focused tests, PR-scoped performance tests, and `scripts/stream_assembler_token_bytes_probe.py`.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.

## Success Metrics

- Focused stream assembler and scoped-probe tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Registered probe reports no regression for the token-byte path; local Linux probe should show directionally lower `elapsed_ms_mean` or an acceptable neutral result for this targeted split-byte path.
