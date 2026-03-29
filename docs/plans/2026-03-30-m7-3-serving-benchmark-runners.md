# M7.3 Serving Benchmark Runners

## Goal

Add built-in serving benchmark runners for prefill and generation throughput so Melix can measure runtime performance without external scripts.

## Scope

- implement serving benchmark execution paths
- preserve operator-facing benchmark workflows
- keep output compatible with the benchmark job schema

## Files

- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- benchmark runners should remain repository-owned and reproducible
- separate prefill and generation measurements clearly in output
- do not collapse benchmark logic into UI-only workflows

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- Melix can execute built-in serving benchmarks through productized entrypoints
- serving benchmark outputs are aligned with the benchmark schema
