# Stream unclosed reasoning candidate loop slice

## Scope

This Python-only performance slice is limited to `RequestStreamAssembler._unclosed_reasoning_candidate_index()` in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

The helper runs while streaming malformed or unclosed reasoning bodies and checking for the earliest visible-tail recovery marker, such as a blank-line boundary or a final-answer label.

## Registered probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-structural-prefix-cache` in `infra/perf/pr_scoped_probes.json`. This slice extends the existing focused probe script and registry metrics with `unclosed_reasoning_candidate_elapsed_ms_mean`, while preserving the existing `test_command`, `coverage_command`, and `probe_command` entries.

## Plan

1. Preserve earliest-marker behavior for blank-line and visible-tail recovery markers.
2. Replace the nested generator/min expression with an explicit loop that tracks the best non-negative index and returns immediately for a marker at index zero.
3. Add focused regression coverage for earliest-marker selection and the index-zero fast return.
4. Extend the registered structural-prefix probe to measure repeated candidate-marker detection locally and in CI.
5. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before pushing.

## Success criteria

- Focused stream assembler tests pass.
- Changed-scope coverage remains at least 95 percent for the touched scope.
- The registered structural-prefix probe reports no regression and a lower or neutral `unclosed_reasoning_candidate_elapsed_ms_mean` for the candidate-marker workload.
