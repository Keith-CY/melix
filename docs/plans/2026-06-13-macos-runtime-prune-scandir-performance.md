# macOS app runtime prune scandir performance slice

## Context

The macOS app bundle slimming path prunes copied Python runtime baggage before
packaging. The runtime pruning helper previously walked the copied runtime with
`os.walk`, materializing per-directory filename lists even though the helper only
needs to stream prunable directories and archive/cache files once.

## Scope

This slice covers only `services/mlx-worker-python/worker/productization/macos_app_bundle.py`'s
Python runtime baggage pruning path. It does not change package baggage pruning,
native binary discovery, signing target discovery, or Swift packaging behavior.

## Probe registration

The slice registers `macos-app-runtime-prune-scandir` in
`infra/perf/pr_scoped_probes.json` with focused test, coverage, and command-json
probe commands. The probe builds a synthetic Python runtime with prunable
`include`, `ensurepip`, `__pycache__`, and `.a` artifacts, then records runtime
prune elapsed time and preserved pruning counts.

## Implementation plan

1. Add regression coverage proving runtime pruning no longer depends on
   `os.walk` and still tolerates scan, metadata, and delete errors.
2. Replace the `os.walk` traversal in `_prune_python_runtime_baggage` with an
   explicit `os.scandir` stack that uses `follow_symlinks=False` and skips broken
   entries instead of failing the prune pass. Keep the hot traversal loop on
   `DirEntry` strings where possible: precompute the prunable suffix tuple,
   push `entry.path` strings onto the traversal stack, and unlink prunable files
   with `os.unlink(entry.path)` to avoid transient `Path` allocations.
3. Add and register the focused runtime prune performance probe.
4. Validate with focused tests, changed-scope coverage, and the registered probe
   locally on Linux; rely on PR-scoped CI to replay the registered probe.

## Success metrics

- Behavior parity: prunable runtime directories and files are removed while
  retained runtime modules remain.
- Coverage: changed-scope coverage for the touched helper, tests, registry, and
  probe remains at or above 95%.
- Performance: registered probe `elapsed_ms_mean` is lower than the pre-change
  `os.walk` baseline, with pruning counts unchanged.
