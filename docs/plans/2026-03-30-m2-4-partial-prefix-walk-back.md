# M2.4 Partial Prefix Walk-Back

## Goal

Support partial-prefix cache matches and deterministic walk-back truncation when a request diverges from a previously cached boundary.

## Scope

- compute partial cache matches
- walk back to the last safe reusable boundary
- expose truncation decisions to scheduling and metrics

## Files

- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `tests/integration/test_recovery_flows.py`

## Implementation Notes

- walk-back should be correctness-first even when it reduces reuse
- the reused boundary must remain explainable through restore metadata
- avoid hidden heuristics that are not observable in metrics

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- partial-prefix matches can reuse a safe prefix subset
- walk-back truncation decisions are deterministic and measurable
