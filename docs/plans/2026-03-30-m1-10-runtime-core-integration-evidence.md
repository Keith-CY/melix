# M1.10 Runtime Core Integration Evidence

## Goal

Close the runtime-core milestone with live-path integration evidence, restart evidence, and measurable metrics for multi-model serving, eviction, and memory protection.

## Scope

- add live integration coverage for runtime-core behavior
- add restart and recovery evidence where runtime-core changes affect restore behavior
- record repository-owned metrics for the completed runtime-core slice

## Files

- update `tests/integration/`
- update `services/mlx-worker-python/worker/productization/`
- update `scripts/phase8_*.py`
- update `infra/release/phase8-release-gate-policy.json`
- update `docs/runbooks/`

## Implementation Notes

- evidence should cover live multi-model coexistence and memory guards
- runtime-core evidence should be machine-readable and consumable by phase-8 release gates
- eviction and adapter isolation remain backed by existing runtime-core unit coverage in this slice
- keep metrics machine-readable so later release gates can consume them
- do not rely on deterministic-only paths as the sole proof of completion

## Verification

- `make py-test`
- `make integration-test`
- touched-scope Python coverage command for the runtime-core slice

## Acceptance

- runtime-core completion is backed by live-path integration evidence
- restart and recovery behavior remains measurable after the runtime-core changes
