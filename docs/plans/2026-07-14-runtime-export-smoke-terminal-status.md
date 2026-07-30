# Runtime export smoke terminal-status performance slice

This Python-only performance slice is limited to the runtime export smoke policy terminal status reducer in `services/mlx-worker-python/worker/productization/export_target_smoke.py`.

## Scope

- Replace the small status-set materialization in `_terminal_status(...)` with a single-pass reducer.
- Preserve terminal-state precedence: `failed` > `blocked` > `waived` > `passed`.
- Keep the existing registered `runtime-export-smoke-policy` PR-scoped performance probe as the validation source.

## Verification

- Focused behavior tests in `services/mlx-worker-python/tests/test_export_target_smoke_policy.py` cover precedence and failure short-circuiting.
- Changed-scope coverage uses the registered probe entry's `coverage_command`.
- Performance is measured with `scripts/runtime_export_smoke_policy_probe.py` locally on Linux and by the PR-scoped performance workflow in CI.
