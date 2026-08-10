# Stream assembler unclosed marker suffix fast path

## Scope

This Python-only performance slice is limited to
`RequestStreamAssembler._longest_unclosed_reasoning_marker_prefix_suffix()` in
`services/mlx-worker-python/worker/runtime/stream_assembler.py`.

Malformed reasoning streams keep a bounded ambiguous tail so split recovery
markers that arrive across fragments are not prematurely emitted as hidden
reasoning. The marker-prefix suffix helper currently checks every recovery
marker even when the inspected tail cannot contain the newline or carriage-return
prefix that all registered unclosed-reasoning recovery markers require.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`stream-assembler-structural-prefix-cache` in `infra/perf/pr_scoped_probes.json`.
This slice keeps the existing focused `test_command`, `coverage_command`, and
`probe_command` entries and extends the probe metrics with
`unclosed_reasoning_marker_suffix_elapsed_ms_mean` so CI compares this specific
helper on base and head.

## Optimization

Add a small tail precheck before iterating over the marker list: if the maximum
possible marker-prefix suffix window contains neither `\n` nor `\r`, no
registered recovery marker can be in progress, so the helper returns an empty
suffix immediately. Newline-bearing partial labels and blank-line markers keep
the existing marker-prefix behavior.

## Verification

- Focused stream assembler tests prove marker-free tails avoid marker suffix
  checks while newline-bearing partial labels are still held.
- The registered structural-prefix probe reports the new suffix metric together
  with existing structural-prefix metrics.
- Changed-scope coverage includes `stream_assembler.py`, the stream assembler
  tests, PR-scoped performance tests, the probe script, registry entry, and this
  plan.
