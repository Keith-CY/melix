# Stream Assembler Token Count Disqualifier Fast Path

## Scope

This Python-only performance slice is limited to `worker.runtime.stream_assembler._whitespace_token_count`. It preserves stream assembly, token-byte decoding, Harmony parsing, tool-call parsing, and generated-token metrics semantics.

## Registered probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `ubuntu-latest`.

Primary metrics for this slice:

- `delta_token_count_new_ms_mean`: lower is better for the optimized whitespace token counter.
- `delta_token_count_delta_ms`: lower is better versus `len(text.split())` in the synthetic token-count workload.
- `delta_token_count_speedup`: higher is better.
- `elapsed_ms_mean`: full stream token-byte assembly guardrail, lower is better.
- `peak_bytes_mean`: allocation guardrail, lower is better.

## Plan

1. Replace the generator-based ASCII disqualifier scan with explicit membership checks for the same disqualifier set.
2. Keep the existing length, ASCII, leading/trailing-space, and single-space counting guards unchanged.
3. Keep fallback behavior through `len(text.split())` unchanged for short strings, non-ASCII strings, leading/trailing spaces, repeated spaces, and non-space whitespace.
4. Run focused stream assembler tests, changed-scope coverage, and the registered local Linux probe before opening the PR.

## Acceptance

- Focused behavior tests pass locally.
- Changed-scope coverage for touched stream assembler lines is at least 95 percent; if no changed lines are measurable due branch diff filtering, the registered coverage command must still pass.
- The registered local Linux probe shows improved token-count submetrics without a gated overall regression.
- GitHub Actions and the PR-scoped performance report complete successfully before merge.
