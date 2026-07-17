# Evaluation text answer-prefix guard performance slice

## Scope

This Python-only performance slice is limited to heuristic text extraction in
`worker.productization.evaluation_final_result._extract_text_heuristic`.

The slice keeps extraction behavior unchanged while avoiding the full
answer-prefix extraction regex on fallback responses that do not contain an
answer-prefix marker.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`evaluation-final-result-text-fallback-tail-scan` in
`infra/perf/pr_scoped_probes.json`. The probe defines focused
`test_command`, `coverage_command`, and `probe_command` entries for local Linux
validation and CI PR-scoped performance reporting.

## Implementation plan

1. Add a regression test proving fallback text extraction does not invoke the
   answer-prefix extraction regex when no line-level answer-prefix marker is
   present.
2. Guard answer-prefix extraction with a non-capturing line-level marker search
   before running the full extraction regex.
3. Keep fenced-block and tail-line fallback behavior unchanged.
4. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused extraction and PR-scoped probe tests pass.
- Changed-scope coverage for touched files remains at least 95%.
- Registered local probe reports lower elapsed time and no peak-memory
  regression for no-marker text fallback payloads.
- PR-scoped performance CI completes successfully before merge.
