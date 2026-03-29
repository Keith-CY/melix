# M7.8 VLM Benchmark Options

## Goal

Add benchmark options for VLM-capable models so serving and evaluation workflows can include image-aware models explicitly.

## Scope

- add VLM benchmark job parameters
- preserve compatibility with the shared benchmark queue
- distinguish VLM benchmark output from text-only output

## Files

- update `services/mlx-worker-python/worker/productization/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- VLM benchmark inputs should preserve image-source identity and scenario metadata
- benchmark outputs should remain comparable without pretending text and VLM jobs are identical
- keep the UI surface explicit about image-aware benchmark modes

## Verification

- `make py-test`
- VLM benchmark smoke command for the touched scope

## Acceptance

- VLM benchmark jobs can be queued and executed explicitly
- result outputs distinguish VLM scenarios from text-only scenarios
