# M11.3 Streaming Cache Compatibility And Settings Surface

## Goal

Expose the cache-policy and settings surface needed to run disk-streamed sessions without hidden
compatibility rules.

## Status

In progress on 2026-04-05. `M11.2` is closed; `M11.3` starts from a repository state where cache
statistics, cache modes, and worker cache roots already exist internally, but operators still do
not have a typed, control-plane-owned surface for streaming-compatible cache policy, effective
cache compatibility resolution, or cache-budget diagnostics.

## Scope

- define cache compatibility under disk streaming
- expose cache memory and directory controls
- expose memory-aware cache and multimodal-cache budget controls
- keep cache policy visible after settings resolution

## Current Gap

- The worker stack already exposes runtime cache statistics and internal cache-mode metadata, but
  those values are not projected as an operator-owned settings surface.
- The native desktop shell can show cache utilization, yet it cannot explain why a cache tier is
  enabled, disabled, downgraded, redirected, or bounded under disk-streaming safety policy.
- Control-plane model settings currently cover disk-streaming mode and memory budget, but not the
  streaming-compatible cache controls required by the `M11` roadmap coverage:
  cache mode, cache-memory budgeting, block sizing, cache directories, or multimodal cache limits.

## Recommended Approach

Use a contract-first, control-plane-owned projection path in two steps:

1. Add a read-only typed cache-policy summary that projects worker configuration and effective cache
   compatibility into control-plane snapshots and the desktop shell.
2. Add explicit control-plane settings and mutation plumbing for the cache controls that Melix
   intends operators to tune, then keep requested-versus-effective policy visible after resolution.

This keeps the first slice small and verifiable while preserving the roadmap requirement that the
eventual operator surface show effective policy instead of raw, hidden worker defaults.

## Execution Slices

### Slice 1: Read-Only Cache Policy Projection

- extend the worker contract with a typed cache-policy summary that includes the worker cache root,
  initial cache blocks, supported cache capabilities, and the currently effective cache mode
- project that summary into the control-plane snapshot and desktop foundation view so operators can
  inspect streaming-compatible cache state before any mutation path is added
- expose explicit compatibility labels such as `compatible`, `limited`, `disabled`, or `unknown`
  instead of expecting operators to infer them from raw stats

### Slice 2: Typed Cache Settings Contract

- add control-plane-owned fields for the cache controls Melix will support directly in `M11.3`
- keep request-time cache hints distinct from durable operator settings
- define which controls are global worker settings, which are per-model preferences, and which are
  compatibility outputs only

### Slice 3: Mutation Plumbing And Effective Policy Resolution

- thread supported cache settings through control-plane policy application and worker-facing runtime
  configuration
- compute effective cache-policy resolution under disk streaming, memory-aware policy, and
  multimodal constraints
- persist both requested policy and effective resolved policy in model or runtime summaries

### Slice 4: Operator Surface, Verification, And Bookkeeping

- extend the native desktop shell with cache-policy controls and effective-policy summaries
- add focused control-plane, worker, and menu-bar coverage for compatibility labels and policy
  resolution
- close `M11.3` only after changed-line coverage for the touched handwritten executable scope is at
  least `95%`, the roadmap execution index is updated, and `progress.md` records the verification
  evidence

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/schema/worker/v1/`
- update `packages/protocol/descriptors/`
- update `packages/protocol/python/`
- update `packages/protocol/swift/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Tests/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-text-worker-swift/Tests/CoreTests/`

## Implementation Notes

- Settings should explain when cache tiers are disabled, limited, or downgraded.
- Memory-aware policy should show tracked-byte budgets, RAM-percentage budgets, and the explicit
  disable path.
- Directory and size controls must remain deterministic and inspectable.
- UI should show effective policy, not only requested settings.
- Request-scoped benchmark cache profiles are out of scope for `M11.3`; this milestone concerns
  durable runtime and operator policy for streaming-compatible cache behavior.

## Verification

- `make proto`
- focused worker, control-plane, and menu-bar Swift test slices for the touched paths
- changed-line coverage commands for every touched handwritten executable scope
- `make py-test`
- `make swift-test`
- `make integration-test`
- `git diff --check`

## Acceptance

- Cache compatibility rules under disk streaming are operator-visible and test-covered.
- Effective cache settings can be inspected after merges and overrides.
- Multimodal cache budgets and memory-aware policy remain visible after settings resolution.
