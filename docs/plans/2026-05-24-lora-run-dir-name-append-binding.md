# LoRA Run Directory Name Append Binding Slice

## Scope

This Python-only performance slice is limited to `_iter_lora_run_dirs()` in
`services/mlx-worker-python/worker/productization/lora_experiment_store.py`.
It keeps LoRA experiment run-directory discovery behavior unchanged while
binding the `run_dir_names.append` method once before the `os.scandir()` loop.
The hot path already avoids `DirEntry.path`; this slice removes one repeated
list method lookup per accepted run directory.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`lora-experiment-run-dir-name-scan` in `infra/perf/pr_scoped_probes.json`.
The registry already has focused `test_command`, `coverage_command`, and
`probe_command` entries. The existing probe command also emits `elapsed_ms_mean`
for local and CI inspection, while the registered counters continue to gate
path-read and peak-memory behavior without broadening the probe selection scope.

## Acceptance Criteria

- Focused LoRA experiment store tests pass locally on Linux.
- Changed-scope coverage for the touched Python and probe-registry paths remains
  at or above 95%.
- The registered probe reports no behavior drift (`path_attr_reads_mean == 0`,
  stable `run_dir_count`) and lower or neutral `elapsed_ms_mean` for the head
  branch compared with the baseline worktree.
- PR-scoped performance CI completes successfully before merge.

## Non-Goals

- No LoRA experiment index schema changes.
- No generated protocol, Swift, or lockfile changes.
