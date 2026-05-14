# Startup Failure Pattern Check Performance Slice

## Goal

Reduce avoidable Python allocation and repeated scanning in startup failure
classification while preserving the existing direct-error, control-plane-log, and
worker-log classification behavior.

## Scope

This slice is limited to `worker.productization.startup_signals` startup failure
pattern checks and the already registered `startup-signals-lazy-worker-log-excerpts`
PR-scoped performance probe. It does not change update-channel version parsing,
startup log excerpt semantics, diagnostic report schemas, or runtime startup
behavior.

## Change

- Store startup classification pattern sets as immutable tuples.
- Replace generator-based `any(pattern in value ...)` checks with a small direct
  helper that short-circuits without allocating a generator for each
  classification pass.
- Avoid rebuilding and rescanning `error_text` after the direct-error fast path has
  already ruled out direct port-conflict and crash patterns; subsequent checks now
  scan only the lowercased control-plane log excerpt.

## Metrics

Primary registered probe: `startup-signals-lazy-worker-log-excerpts`.

- `conflict_elapsed_ms_mean`: lower is better for direct error-text conflicts.
- `control_crash_elapsed_ms_mean`: lower is better for control-plane log
  classification.
- `worker_crash_elapsed_ms_mean`: lower is better for worker log classification.
- `tail_scan_elapsed_ms_mean`: informational for this slice; tail scanning itself
  is unchanged.
- Log read and path-exists counters must remain unchanged.

## Verification

Run the registered focused test command, changed-scope coverage command, and probe
command from `infra/perf/pr_scoped_probes.json` before opening the PR. The
PR-scoped performance workflow must complete successfully before merge.
