# Serving Diagnostics Queue Retained Count Slice

## Scope

This plan now tracks the next small serving diagnostics queue slice: avoid per-event empty
attribute dictionary allocation when debug queue events are created without attributes. The
change keeps bounded-queue append/drop semantics unchanged and preserves `to_dict()` output for
empty attributes.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and is locally verifiable on Linux
with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `docs/plans/2026-05-13-serving-diagnostics-queue-retained-count.md`

## Registered probe

The affected path is already covered by `serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`,
`coverage_command`, and `probe_command` values. The probe repeatedly appends debug events to a
bounded queue and reports:

- `elapsed_ms_mean` — lower is better
- `dropped_count` — guard rail for bounded drop semantics
- `retained_count` — guard rail for fixed retained capacity

## Acceptance

- Focused serving diagnostics tests pass.
- Changed-scope coverage for `serving_diagnostics.py` is at least 95%.
- The registered local probe reports lower `elapsed_ms_mean` than the origin/main baseline while
  preserving `dropped_count` and `retained_count`.
- `git diff --check` passes.
