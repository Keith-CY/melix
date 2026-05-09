# Engine Generate Finish Reason Elision

## Scope

This Python-only performance slice reduces per-token bookkeeping in
`EngineCore.generate(...)` when callers do not request usage accounting. The
engine still needs the terminal finish reason for the completed event, but it no
longer needs to retain the full last `RuntimeTokenEvent` object or increment
completion-token counters on the no-usage path.

Affected files:

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `infra/perf/pr_scoped_probes.json`

## Probe Coverage

The affected path is covered by the registered
`engine-generate-usage-token-elision` PR-scoped performance probe in
`infra/perf/pr_scoped_probes.json`. The probe has focused test, coverage, and
command-json probe commands for the Python generate no-usage hot path.

## Plan

1. Keep usage-token behavior unchanged when `return_usage=True`.
2. Track only the string finish reason when `return_usage=False`.
3. Avoid no-usage completion-token counter increments and last-token-event
   retention in the per-token loop.
4. Add a regression test proving no-usage generation still preserves token text,
   completed assistant text, and the terminal finish reason.
5. Run focused pytest, changed-scope coverage, and the registered performance
   probe locally on Linux.

## Validation Boundary

This slice is Python-only and locally verifiable on Linux. GitHub Actions remains
the merge gate for the registered PR-scoped performance workflow.
