# Stream Assembler Last-Marker Partial Suffix Probe

## Goal

Reduce partial structural-tag suffix overhead in the Python stream assembler by making `_partial_structural_tag_suffix()` inspect only the final `<` marker candidate in the buffered tail, instead of walking every cached structural prefix candidate with repeated `endswith()` checks.

## Linux-only constraint

This is a Python worker/runtime slice and can be verified on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-06-stream-assembler-partial-suffix-single-pass.md`

## Performance probe

Registered scoped CI probe:

- `stream-assembler-structural-prefix-cache`

The probe measures `_partial_structural_tag_suffix()` directly so `origin/main` and the PR branch compare the production suffix-return path. This follow-up keeps the same registered probe and updates its focused test/coverage commands to the new regression tests, switches the probe command to the tracked `python3` probe script, and registers `partial_suffix_elapsed_ms_mean` as a lower-is-better metric.

## Success metrics

- Focused stream assembler and scoped-probe tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- The probe preserves `held_suffix_hits`, `partial_suffix_hits`, and `prefix_identity_hits`.
- A detached `origin/main` vs head probe comparison reports lower or equal `elapsed_ms_mean` and `partial_suffix_elapsed_ms_mean` without increasing peak traced allocation materially.
