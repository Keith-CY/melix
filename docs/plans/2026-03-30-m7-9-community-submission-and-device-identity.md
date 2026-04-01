# M7.9 Community Submission And Device Identity

## Goal

Add a submission path for benchmark and evaluation results with stable device identity so shared result sets can be attributed and compared safely.

## Scope

- define submission payload shape
- define device-identity representation
- keep result submission optional and operator-controlled

## Files

- update `services/mlx-worker-python/worker/productization/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- device identity should be stable enough for comparison while remaining explicit and auditable
- submission should remain a productized action rather than a side effect of local benchmarking
- operator visibility for this closure may remain a control-plane or XPC mediated payload plus
  runbook flow rather than a dedicated desktop submission screen
- keep the payload shape compatible with later community-facing surfaces

## Verification

- `make py-test`
- submission-payload smoke command for the touched scope

## Acceptance

- benchmark and evaluation results can be prepared for community submission
- device identity is represented explicitly in the submission flow
