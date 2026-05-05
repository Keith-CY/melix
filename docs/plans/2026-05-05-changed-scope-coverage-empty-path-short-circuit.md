# Changed Scope Coverage Empty Path Short-Circuit

## Goal

Reduce redundant work in `scripts/changed_scope_coverage.py` when a requested path has no changed executable lines. The helper currently still reads source files and builds coverage sets before discovering that there is nothing to measure.

## Scope

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`
- `scripts/changed_scope_coverage_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only verification path

This is a Python/CI-helper slice and is locally verifiable on Linux.

## Performance probe

Register `changed-scope-coverage-empty-path-short-circuit` in the PR-scoped performance registry. The probe measures a synthetic workload with many requested paths whose `changed` set is empty and reports:

- `elapsed_ms_mean` (lower is better)
- `source_read_calls_mean` (lower is better; target is zero on the optimized branch)
- `path_count`

## Success metrics

- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Local probe shows fewer source reads and lower elapsed time than `origin/main` on the same synthetic workload.
- `git diff --check` passes.
