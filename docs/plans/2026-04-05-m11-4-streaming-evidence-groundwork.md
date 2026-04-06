# M11.4 Streaming Evidence Groundwork

## Goal

Add truthful large-model streaming evidence, smoke coverage, and operator runbook material for the
current Melix disk-streaming surface.

## Current Constraint

The repository runtime still reports `supports_disk_streaming = false` and both worker paths reject
`prefer_disk` and `require_disk` with typed `disk_streaming_unsupported` failures. This execution
plan therefore targets the evidence Melix can measure truthfully today:

- RAM-resident baseline benchmark metrics
- typed unsupported-path smoke evidence for disk-streaming requests
- operator runbook guidance for setup, diagnosis, and interpretation

True SSD-backed restore latency, SSD footprint, and throughput delta remain blocked on a future
runtime slice that implements disk-backed execution.

## Scope

- add a repository-owned `melix-disk-streaming-smoke` command
- capture RAM baseline benchmark metrics through the existing control-plane benchmark path
- capture typed unsupported-path evidence for `prefer_disk` and `require_disk`
- emit a machine-readable report suitable for future release gates
- add live integration coverage and an operator runbook

## Execution Slices

### Slice 1: Smoke Command Contract

- add a CLI command and report model for `melix-disk-streaming-smoke`
- reuse the control-plane client directly instead of shelling out to `melix bench run`
- guarantee settings restoration so the smoke path is safe to run repeatedly

### Slice 2: Evidence Runner

- measure the RAM baseline with `disk_streaming_mode=disabled`
- run `prefer_disk` and `require_disk` attempts and record typed unsupported evidence
- record requested-versus-effective modes, transition reasons, runtime support flags, and cache
  compatibility summaries

### Slice 3: Integration Coverage

- add a live integration test that runs the smoke command against a real local stack
- assert baseline metrics, unsupported-path diagnostics, and JSON report structure

### Slice 4: Runbook And Bookkeeping

- add a dedicated disk-streaming evidence runbook
- update the docs map as needed
- record verification and changed-line coverage in `progress.md`
- keep `M11.4` open unless the transaction also lands true SSD-backed execution evidence

## Verification

- focused CLI runner tests for the smoke command
- focused control-plane tests for typed evidence capture and settings restoration
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_disk_streaming_smoke.py -q`
- `make swift-test`
- `make py-test`
- `make integration-test`
- changed-line coverage at or above `95%` for the touched handwritten executable scope
- `git diff --check`

## Acceptance

- Melix owns a reproducible smoke command for the current disk-streaming surface
- operators can compare the RAM baseline against explicit unsupported-path diagnostics
- runbook guidance explains setup, interpretation, and current capability limits without implying
  SSD-backed execution exists today

