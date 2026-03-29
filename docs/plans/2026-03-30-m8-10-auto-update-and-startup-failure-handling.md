# M8.10 Auto-Update And Startup Failure Handling

## Goal

Add update checks, crash and hang awareness, and startup failure handling so packaged Melix installs can recover and explain failures clearly.

## Scope

- add update-check flow
- add crash and hang detection
- add startup failure reporting and host-port diagnostics

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `services/mlx-worker-python/worker/productization/install_assets.py`
- update `docs/runbooks/`
- update `tests/integration/`

## Implementation Notes

- failure reporting should point operators to actionable next steps and logs
- update logic should stay separate from runtime control logic
- startup failure handling should remain compatible with launch agents and packaged installs

## Verification

- `make swift-test`
- startup-failure smoke command for the touched scope

## Acceptance

- Melix can detect update availability and startup failures explicitly
- failure handling and operator messaging are test-covered
