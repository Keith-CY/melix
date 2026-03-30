# M14.3 Redo Actions And Long-Running Timeout Policy

## Goal

Add operator-visible redo actions and a longer-running timeout policy for creative image workflows.

## Scope

- expose always-visible redo and reiteration actions
- extend timeout handling for long-running generation and edit jobs
- keep timeout, retry, and cancel state explicit

## Files

- update `services/control-plane-swift/Sources/`
- update `services/mlx-worker-python/worker/`
- update `apps/macos-menubar/Sources/AppMain/Image/`
- update `tests/integration/`

## Implementation Notes

- Redo actions should remain backed by stable image-job state rather than UI-local copies.
- Timeout policy must remain visible to operators and not collapse into generic failure state.
- Retry affordances should stay aligned with artifact lineage and role-aware model selection.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- Redo flows and longer-running timeout policy are explicit, operator-visible, and test-covered.
- Timeout-triggered failures remain distinguishable from other image-job failures.
