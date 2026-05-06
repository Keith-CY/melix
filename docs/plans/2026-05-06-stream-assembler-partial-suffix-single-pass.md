# Stream Assembler Partial Suffix Single-Pass Probe

## Goal

Reduce redundant partial structural-tag suffix checks in the Python stream assembler by making `_partial_structural_tag_suffix()` find and return the held suffix without first running the tuple-wide boolean precheck.

## Linux-only constraint

This is a Python worker/runtime slice and can be verified on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `scripts/stream_assembler_structural_prefix_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-06-stream-assembler-partial-suffix-single-pass.md`

## Performance probe

Registered scoped CI probe:

- `stream-assembler-structural-prefix-cache`

The probe now measures `_partial_structural_tag_suffix()` directly so `origin/main` and the PR branch compare the production suffix-return path rather than only the standalone boolean helper.

## Success metrics

- Focused stream assembler and scoped-probe tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- The probe preserves `held_suffix_hits` and `prefix_identity_hits`.
- A detached `origin/main` vs head probe comparison reports lower or equal `elapsed_ms_mean` without increasing peak traced allocation materially.
