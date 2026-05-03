# Model Registry, Server Target, And Diagnostics Refactor

## Status

Implemented in the macOS menu bar app.

## Goal

Unify model availability around two user-facing groups:

- `Ready to Run`: complete local model entries discovered from configured registry roots, Melix-managed downloads, Hugging Face cache snapshots, or manually placed model directories.
- `Discover & Download`: Hub discovery results and active download queue entries that are not currently present as complete local runnable model entries.

Diagnostics no longer runs against model catalog rows or raw Hugging Face repo IDs from the app UI. Benchmark, Matrix, and Evaluation choose a `Running Server` target instead. The Server page uses the same unified local/remote target model, while local server creation only exposes real `Ready to Run` models and never exposes the internal Melix placeholder catalog rows.

## Scope

- Add explicit registry availability grouping to macOS app view model state without changing the worker registry payload contract.
- Filter Hub discovery rows out of `Discover & Download` when the same repo ID already appears in `Ready to Run`.
- Replace Diagnostics target mode UI with one `Running Server` picker.
- Populate Diagnostics targets from running local server sessions, configured remote servers, and a `Start New Server...` configuration sentinel.
- Add unified server target view-model state for local server sessions and configured remote servers while keeping local and remote persistence separate.
- Replace the split local/remote Server sidebar with one scrollable `Servers` list that uses Local/Remote badges.
- Keep Server sidebar rows to three visible lines: session name with Local/Remote badge, model name with endpoint, and status with LoRA, acceleration mode, and context summary.
- Require a non-empty Server session name before submitting local or remote Server creation/editing forms; drafts are configuration state and do not appear in the unified Server list.
- Route `Start New Server...` to the Server creation flow without implicitly creating or starting a local session.
- Hide `melix-dev-text` and `melix-dev-vlm` from Server model choices, Server targets, and Diagnostics targets; they remain internal fixtures only.
- Add a local Server `LoRA Adapter` section that can serve already activated derived models and navigates to activation for pending adapters without implicit activation.
- Apply the Melix accent tint at the desktop root and opt title bar controls out of the default macOS blue focus ring.
- Keep CLI `hfRepoID` request fields compatible, but stop using repo IDs as app-level Diagnostics target selection.
- Disable Benchmark and Matrix for remote servers with the message: `Remote Server benchmark is not supported yet; select a local running server.`
- Keep remote Evaluation routed through remote target options when the selected suite/scoring path supports it.

## Non-Goals

- Remote server Benchmark/Matrix execution.
- Removing CLI `--repo-id` compatibility.
- Changing Python worker registry snapshot payload fields.
- Adding a raw adapter-path serving field to the Server protocol.

## Verification Plan

- Swift view model tests for registry grouping, duplicate Hub filtering, unified Server target construction, placeholder model hiding, non-empty Server session name submission guards, LoRA derived-model serving options, Diagnostics target construction, local/remote Evaluation request routing, and Benchmark/Matrix local-server guards.
- Swift UI/source tests proving Diagnostics no longer renders `Catalog Model` / `Hugging Face Repo` target controls, Model Registry renders `Ready to Run` / `Discover & Download`, Server renders a unified three-line `Servers` list and `LoRA Adapter` section, and desktop chrome uses Melix accent/focus styling.
- Existing Python worker tests continue to cover registry completeness rules for Hugging Face cache snapshots, including interrupted indexed shard downloads.

## Metrics

N/A for runtime performance in this UI-only target-selection slice. Behavioral probes are the recorded request payloads in view model tests and rendered control assertions in UI tests.
