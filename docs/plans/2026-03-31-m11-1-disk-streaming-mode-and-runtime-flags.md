# M11.1 Disk Streaming Mode And Runtime Flags

## Goal

Define the runtime-facing disk-streaming mode and the typed flags or settings needed to enable it safely.

## Scope

- add disk-streaming mode to runtime settings
- carry session-level streaming flags through control-plane state
- keep mode visibility explicit for operators

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-worker-python/worker/`

## Implementation Notes

- Disk streaming should be an explicit operator choice or policy outcome.
- Mode flags must remain compatible with existing residency and runtime stats.
- Unsupported runtime paths should fail explicitly rather than silently ignoring the flag.

## Verification

- `make proto`
- `make swift-test`
- `make py-test`

## Acceptance

- Disk-streaming mode is represented consistently across protocol, control plane, and runtime settings.
