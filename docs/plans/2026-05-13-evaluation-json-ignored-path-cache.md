# Evaluation JSON Ignored-Path Cache Slice

## Scope

This Python-only performance slice is limited to JSON final-result scoring in
`worker.productization.evaluation_final_result`. It preserves scoring semantics
while avoiding repeated allocation of the merged default/profile ignored-path set
when the same evaluation profile is used across many scoring calls.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`evaluation-final-result-json-typed-score-aggregate` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries and measures:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `score_checksum`
- `key_count`
- `iteration_count`

## Implementation plan

1. Add a small LRU-cached helper for merging `_DEFAULT_IGNORED_PATHS` with
   profile-provided ignored paths.
2. Keep `_json_typed_score` behavior unchanged and accept the cached immutable
   set through the existing membership-only interface.
3. Add regression coverage proving repeated calls reuse the cached ignored-path
   set while retaining default and profile-specific ignored paths.
4. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux before opening the PR. GitHub Actions PR-scoped
   performance remains the merge gate.

## Success criteria

- Focused behavior tests pass.
- Changed-scope coverage for touched evaluation/probe files is at least 95%.
- The registered local probe reports lower `elapsed_ms_mean` without changing
  `score_checksum`, `key_count`, or `iteration_count`.
