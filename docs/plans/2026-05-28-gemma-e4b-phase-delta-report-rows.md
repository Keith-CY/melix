# Gemma E4B Phase And Delta Report Rows

## Goal

Close #1649 by making the Gemma E4B comparison artifacts carry structured
per-request phase rows, scenario-level Melix versus best-peer deltas, and
threshold status rows that can be read by scripts or rendered in Markdown.

## Scope

- Extend the two-way and three-way serving comparison reports.
- Keep client-measured phases separate from runtime metrics snapshots.
- Record unavailable phase fields explicitly as `null` instead of inferring
  queue, prefill, or worker internals from TTFT.
- Render the new rows in Markdown and persist them in `summary.json` plus the
  artifact manifest.

## Non-Goals

- Do not add new runtime instrumentation.
- Do not change benchmark request scheduling or endpoint behavior.
- Do not claim the root #1642 performance acceptance is met.

## Contract

Per-request phase rows include:

- endpoint, model, scenario identifiers, repeat and request indexes
- status and HTTP status
- prompt/output token counts and token sources
- client-observed first HTTP/SSE event latency, decode latency, total latency,
  streamed chunk count, and aggregate group elapsed time
- queue, prefill, and worker-stream phase fields as `null` unless a future
  source can populate them directly

Peer-delta rows include, per scenario:

- target endpoint
- best peer for total latency and decode throughput
- signed percent deltas versus that best peer
- configured threshold values
- status flags for total latency and decode throughput

The threshold status rolls these rows into report-level `ok` or
`threshold_failed` status.

## Verification

- Focused pytest for the two-way and three-way report helpers.
- Coverage report for changed scripts and tests.
- `python3 -m compileall` for changed Python files.
- `git diff --check`.
- Scoped performance report for the PR file set.
