# M11 Disk Streaming, Memory Budgeting, And Cache Policy

## Goal

Add a controlled disk-streaming execution mode for large-model serving, with explicit virtual-memory budgeting and cache policy so Melix can safely operate beyond pure RAM-resident model footprints.

## Scope

- add disk-streaming mode and operator controls
- define virtual-memory budgeting and unsafe-load rejection behavior
- make cache compatibility under disk streaming explicit
- expose RAM, SSD, and restore-cost metrics for streamed sessions

## Coverage

- session-level disk-streaming enablement
- adjustable virtual-memory budget
- load admission based on memory and SSD headroom
- explicit policy for prefix cache, paged KV cache, persistent disk cache, and cache quantization when disk streaming is active
- memory-aware cache accounting by tracked bytes rather than entry count alone
- cache memory limit, cache memory percentage, memory-aware-cache disable mode, block size, max cache size, block-cache directory, and cache directory controls
- multimodal cache controls, including explicit image or video cache budgets where multimodal reuse remains enabled
- operator-visible hot-tier, paged-tier, and cold-tier state for large-model sessions
- benchmark coverage for SSD-backed execution paths

## Execution Slices

- `M11.1` Disk-streaming mode and runtime flags
- `M11.2` Memory-budget admission and safety guards
- `M11.3` Streaming-cache compatibility and settings surface
- `M11.4` Large-model streaming benchmarks and runbooks

## Files

- update `services/control-plane-swift/Sources/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-worker-python/worker/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`
- update `docs/runbooks/`

## Implementation Notes

- Disk streaming should remain an explicit mode, not an implicit fallback after memory pressure has already destabilized the runtime.
- Cache policy should prefer correctness and observability over opportunistic reuse when streaming compatibility is unclear.
- Virtual-memory budgets should align with the existing memory-enforcement and residency-accounting model rather than creating a second budgeting scheme.
- Memory-aware cache policy should stay measurable in bytes and should not silently degrade to entry-count heuristics.
- Metrics must separate RAM-resident reuse from SSD-backed restore and execution cost.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- disk-streaming smoke command for the touched scope

## Acceptance

- Disk-streaming mode is configurable, observable, and safe under explicit memory budgets.
- Cache behavior under disk streaming is deterministic and operator-visible.
- Large-model sessions report meaningful SSD-backed performance and recovery metrics.
