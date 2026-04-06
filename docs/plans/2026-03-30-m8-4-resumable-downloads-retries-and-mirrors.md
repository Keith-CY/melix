# M8.4 Resumable Downloads, Retries, And Mirrors

## Status

Completed on 2026-04-04. Melix now ships resumable model-download workflows with explicit retry,
stall, mirror, and progress-manifest state, exposes that state through the existing worker bridge
and control-plane model-operations path, and records the changed-line coverage and deterministic
download-smoke evidence for the touched scope in the backend-foundations implementation plan.

## Goal

Add resilient model-download flows with resume, retry, stall detection, and mirror support for constrained network environments.

## Scope

- add download resume and retry behavior
- detect stalled downloads explicitly
- support configurable mirror endpoints

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- download state should remain machine-readable and operator-visible
- stall detection should distinguish genuine stalls from slow but progressing transfers
- mirror configuration must remain explicit and auditable

## Verification

- `make py-test`
- download-resume smoke command for the touched scope

## Acceptance

- model downloads can resume, retry, and surface stall state
- mirror support is configurable and test-covered
