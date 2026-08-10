# Stream assembler unclosed reasoning newline fast path

## Scope

This Python-only performance slice is limited to
`RequestStreamAssembler._recover_unclosed_reasoning_body()` in
`services/mlx-worker-python/worker/runtime/stream_assembler.py`.

Malformed reasoning recovery only has safe visible-tail boundaries when the body
contains newline-delimited separators or English newline-prefixed section labels.
Bodies without `\n` or `\r` cannot match any registered recovery marker.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`stream-assembler-structural-prefix-cache` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports
`unclosed_reasoning_recovery_elapsed_ms_mean` for this helper.

## Implementation

Add a no-newline fast path that returns no recovery split before scanning the
separator and visible-tail marker list. Preserve blank-body behavior and all
newline-bearing recovery semantics.

## Verification

Run the focused stream assembler tests, changed-scope coverage, and the
registered probe locally on Linux. GitHub Actions PR-scoped performance remains
the merge gate for base-vs-head validation.

## Success criteria

- Focused tests pass, including a regression guard proving the marker-free body
  path avoids `str.find()` scanning.
- Changed-scope coverage for the touched Python/test/probe/registry/doc files is
  at least 95%.
- The registered probe reports lower
  `unclosed_reasoning_recovery_elapsed_ms_mean` without regressing the existing
  structural-prefix metrics.
