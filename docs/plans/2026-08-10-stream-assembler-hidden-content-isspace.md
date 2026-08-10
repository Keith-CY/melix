# Stream assembler hidden content whitespace scan

This Python-only performance slice is limited to `RequestStreamAssembler._hidden_pipe_channel_deltas()` in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

## Scope

The hidden Harmony/pipe-channel path decides whether a hidden reasoning body has content before emitting a reasoning delta or recording an empty-thinking sentinel. The previous implementation used `hidden.strip()` for that check, which copies the hidden payload on non-empty reasoning bodies and copies/trims whitespace-only bodies.

This slice preserves the same truth table while using `bool(hidden) and not hidden.isspace()` so the hot-path content check avoids the `strip()` allocation.

## Probe registration

The affected file is already covered by the registered PR-scoped probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/stream_assembler_parser_mode_probe.py`

## Local verification plan

Run the focused regression test, the registered test command, changed-scope coverage command, and registered probe command locally on Linux. Compare the helper-level check before/after with repeated samples. The registered CI probe remains the merge gate.

## Expected metrics

- Behavior: hidden reasoning deltas and empty hidden channels remain unchanged.
- Local helper probe: lower mean elapsed time for both nonblank hidden payloads and blank hidden payloads.
- Registered probe: no regression in `elapsed_ms_mean` for the stream assembler parser-mode workload.
