# Task Plan

## Goal

Split Melix operator benchmarking into two explicit product lines on `main`:

- `bench` for performance benchmarking
- `eval` for intelligence evaluation

The transaction must expose the new evaluation workflow through protocol contracts, the shared control-plane client, the Python worker, the Window UI, and the public `melix` CLI.

## Scope

- add typed evaluation request and export schema fields to the control-plane and worker protocols
- add shared Swift export decoding and control-plane execution support for evaluation jobs, results, and samples
- expose `melix eval run`, `melix eval list`, `melix eval export-summary-csv`, `melix eval export-samples-csv`, and `melix eval export-samples-jsonl`
- persist evaluation jobs, summary results, and per-sample rows in the Python worker productization layer
- expose evaluation configuration, history, summary cards, and sample previews in the Window UI
- update execution planning and progress documents so the repository reflects the benchmark and evaluation split

## Phases

1. Plan and status reset for the benchmark and evaluation redesign
   - status: completed
2. Protocol and generated artifact updates
   - status: completed
3. Python worker evaluation persistence and export support
   - status: completed
4. Shared Swift export decoding and control-plane evaluation plumbing
   - status: completed
5. `melix eval` CLI parser and runner implementation
   - status: completed
6. Window UI evaluation workspace and history views
   - status: completed
7. Verification, coverage, metrics, and commit closure
   - status: completed

## Acceptance

- `melix eval ...` is a first-class CLI product that supports direct model IDs and direct Hugging Face repo targets.
- Evaluation runs persist typed jobs, results, and sample-level evidence under the productization layer and can be exported as CSV and JSONL.
- Window UI exposes evaluation target selection, suite selection, run controls, history, summary cards, and sample previews without overloading the performance benchmark cards.
- Control-plane export decoding understands both benchmark and evaluation history from one shared export bundle.
- The touched executable Python and Swift scope maintains changed-line coverage of at least `95%`.

## Risks

- SwiftUI host-view tests can validate stateful rendering, but direct button-click automation remains brittle in the current AppKit test harness.
- Evaluation export compatibility depends on keeping the benchmark export bundle backward-compatible for older persisted benchmark-only runs.
- Generated protobuf artifacts widen the change set, so schema and generated outputs must stay in sync in the same commit.

## Outcome

- Completed slices:
  - plan and progress reset for the benchmark and evaluation redesign
  - protocol updates for evaluation request shapes and export metadata
  - Python worker evaluation schemas, persistence, export collection, and gRPC wiring
  - shared Swift export decoding and control-plane evaluation execution plumbing
  - `melix eval` CLI parser and runner implementation
  - Window UI evaluation configuration, history, summary cards, and sample previews
  - targeted verification, changed-line coverage, and metrics evidence for the touched executable scope
- Follow-up slices:
  - review `omlx` benchmark and intelligence design and decide the next-generation Melix benchmark and evaluation input/output contract
