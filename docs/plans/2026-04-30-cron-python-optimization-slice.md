# 2026-04-30 Cron Python Optimization Slice

## Context

This cron run is limited to Linux-verifiable changes in `services/mlx-worker-python`.
The goal is one small optimization slice with focused tests, measurable coverage,
and an explicit performance probe before commit.

## Scout Result Summary

The scouting pass proposed these safe candidates:
1. Stream Hugging Face cache ref traversal in `worker/model_registry/catalog.py`.
2. Collapse repeated benchmark export directory scans in `worker/productization/benchmark_export.py`.
3. Reduce repeated manifest glob passes in `worker/model_ops/job_registry.py`.

## Chosen Slice

Optimize `services/mlx-worker-python/worker/model_registry/catalog.py` by
replacing eager `Path.rglob()` ref enumeration in `_hf_cache_revision_map()`
with a sorted `os.scandir()` tree walk that avoids materializing the full refs
path list while preserving revision mapping and ref-name ordering.

## Why This Slice

- Pure Python and Linux-verifiable.
- Reduces redundant allocation and directory traversal overhead on a path that
  scales with Hugging Face cache ref count.
- Already has strong local tests in `tests/test_model_registry_catalog.py`.
- Easy to benchmark with a synthetic large temporary refs tree.

## Task

1. Add or update tests first to lock behavior, ordering, and single-pass scan behavior.
2. Refactor `_hf_cache_revision_map()` to use deterministic `os.scandir()` recursion
   instead of `Path.rglob()` list materialization.
3. Run focused pytest for the touched scope.
4. Measure touched-file coverage and require at least 95% coverage for the
   changed executable file before commit.
5. Run an explicit synthetic performance probe and record concrete numbers.
6. Run `git diff --check`, then commit, push, and open a PR.

## Success Metrics

- Behavior and ordering unchanged in focused tests.
- `worker/model_registry/catalog.py` changed-scope coverage >= 95%.
- Performance probe shows improved wall-clock time for the synthetic refs scan.
- No whitespace or conflict issues from `git diff --check`.
