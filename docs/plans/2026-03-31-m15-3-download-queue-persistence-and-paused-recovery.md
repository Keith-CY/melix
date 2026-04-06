# M15.3 Download-Queue Persistence And Paused-Recovery

Status: completed on 2026-04-06. Desktop download queues now persist through operator-session
restore, `registry_snapshot` download rows expose resume metadata, and the Window UI plus status
menu surface shared queue-recovery signals and resume actions.

## Goal

Persist the desktop download queue and restore paused downloads after restarting the shell.

## Scope

- persist download-queue state across shell restarts
- restore paused downloads and queue metadata
- keep status-bar messaging aligned with queue truth

## Files

- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `services/mlx-worker-python/worker/model_ops/`
- update `tests/integration/`

## Implementation Notes

- Restored download state should come from persisted queue truth, not UI guesswork.
- Queue recovery should preserve mirrors, retries, and partial-progress metadata.
- Status-bar surfaces should remain readable during resume and stall states.

## Verification

- `make swift-test`
- `make py-test`
- download-recovery smoke command for the touched scope

## Acceptance

- Paused downloads can be restored after reopening the desktop shell.
- Queue state and resume behavior are test-covered and operator-visible.
