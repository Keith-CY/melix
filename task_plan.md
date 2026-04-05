# Task Plan

## Goal

Close the first executable `M13.3` slice by turning embedding, tool-parser, MCP, config-path,
and launch-arguments state into one typed, reconnect-stable control-plane snapshot summary that the
desktop settings surface can render without source-level discovery.

## Scope

- add a typed `tooling_settings` snapshot summary under `ServerSnapshot`
- project the active embedding-model choice and preload state from capability-aware model discovery
- expose built-in tool-parser modes and effective MCP configuration through the same summary
- expose inspectable config paths and boot additional arguments from control-plane truth
- render the tooling summary in the Window UI settings surface instead of relying on hardcoded
  operator knowledge

## Measurement Points

- `ServerSnapshot.tooling_settings` must remain populated after handshake and snapshot refresh
- embedding settings must identify the active embedding model, backend family, and whether it is
  preloaded
- tool-parser settings must come from repository-owned registry truth, not UI-local enumerations
- config-path and launch-argument state must remain inspectable after restart and reconnect
- changed-line coverage for the touched handwritten executable scope must remain at or above `95%`

## Phases

1. Planning and snapshot contract
   - status: completed
   - evidence:
     - confirmed `M13.3` can start with a read-only settings-truth slice instead of coupling
       visibility to new persistence or mutation semantics
     - identified the current gap: MCP summary exists in `ServerSnapshot`, but embedding, built-in
       parser modes, config paths, and additional arguments do not appear as one coherent operator
       surface
     - selected a bounded implementation: add `tooling_settings` to the control-plane protocol and
       hydrate the existing Tools > Settings workspace from that summary
2. Typed tooling summary and desktop hydration
   - status: completed
   - evidence:
     - `ServerSnapshot` now carries typed tooling state for embedding, built-in parsers, MCP,
       config paths, and boot arguments
     - control-plane snapshot projection uses repository-owned registry, MCP, and store-path truth
       instead of UI-local reconstruction
     - the existing Tools > Settings surface renders the typed tooling summary, including
       embedding preload detail and config-path rows
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - `make proto` passed after schema regeneration
     - focused control-plane and menu-bar coverage runs passed, with changed-line coverage at
       `100.00%` (`309/309`) across the touched handwritten executable scope
     - `git diff --check` passed, while `make swift-test` still reports the pre-existing
       `services/mlx-text-worker-swift` `WorkerScaffoldTests` signal-11 failure outside the
       touched scope

## Acceptance

- tooling, embedding, and config-file state are visible from one settings surface
- the settings surface survives restart and reconnect because it hydrates from snapshot truth
- operators can inspect embedding preload state, built-in parser modes, MCP config, config paths,
  and boot arguments without reading source files

## Risks

- the desktop settings tab could become a second source of truth if it reconstructs parser modes or
  embedding state locally instead of consuming a typed snapshot summary
- config-path visibility could drift if store-backed paths remain private to persistence actors
- launch arguments could become uninspectable in packaged flows unless they are captured at
  bootstrap and projected through the control plane

## Outcome

- m13_3_tooling_settings_slice_1_completed
