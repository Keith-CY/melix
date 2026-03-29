# M2.11 Cache Recovery Benchmarks

## Goal

Close the cache-and-scheduler milestone with repository-owned evidence for restart reuse, partial restore, and hot-cold tier recovery performance.

## Scope

- add reproducible recovery benchmarks
- differentiate hot-tier, cold-tier, and partial-restore evidence
- feed the results into product metrics and later release gates

## Files

- update `tests/integration/`
- update `services/mlx-worker-python/worker/productization/`
- update `docs/runbooks/`

## Implementation Notes

- the benchmark slice should be deterministic enough for CI while still exercising live recovery behavior
- report recovery by tier and by restore path rather than a single aggregate number
- keep outputs machine-readable for gate consumption

## Verification

- `make integration-test`
- touched-scope metrics or benchmark command for cache recovery

## Acceptance

- cache recovery evidence exists for restart, partial restore, and hot-cold tier reuse
- the evidence is repository-owned and machine-readable
