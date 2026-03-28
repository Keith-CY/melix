# P1-M6 Workflow, Integration, and Metrics Plan

**Goal:** Make the Phase 1 Swift text route reproducible for local development, integration testing, and operator troubleshooting, while producing a repeatable metrics report for the Swift-vs-Python text path comparison.

**Scope:** This milestone closes the remaining Phase 1 evidence gap after the control plane has switched default text routing to the Swift worker.

## Non-Goals

- No new public endpoints beyond `/v1/models` and `/v1/chat/completions`.
- No fallback from the default Swift text route to the Python text path.
- No speculative decode, cache tiers, or session-graph work from later phases.
- No benchmark dashboard or desktop metrics UI.

## Current Gaps

- `scripts/dev_up.sh` and `scripts/dev_down.sh` still manage the old two-process stack.
- Integration coverage does not yet prove the Phase 1 default route end to end.
- The Swift worker has no deterministic mode for stable CI and local repeatability.
- There is no single reproducible command that emits a Phase 1 metrics report.

## Performance Probes

This milestone must preserve and surface these measurements:

- `swift_text.load_model_ms`
- `swift_text.ttft_ms`
- `swift_text.tokens_per_second`
- `swift_text.abort_ms`
- `swift_text.stream_event_count`
- `swift_text.peak_resident_bytes`
- `control_plane.worker_route_ms`
- `control_plane.worker_connect_ms`
- `control_plane.worker_preload_ms`

## Work Plan

### Task 1: Make the Swift worker reproducible in deterministic mode

- Add a deterministic backend for the Swift text worker so Phase 1 integration can run without a live MLX model source.
- Keep `swift` as the real MLX backend mode and add `deterministic` as the repeatable integration mode.
- Verify that load, generate, and abort still work through the shared worker RPC surface when the Swift worker runs in deterministic mode.

### Task 2: Refresh the local developer workflow for the three-process Phase 1 stack

- Update `scripts/dev_up.sh` to launch:
  - the Swift text worker
  - the Python compatibility worker
  - the Swift control plane
- Update `scripts/dev_down.sh` to stop and clean up all three processes and both sockets.
- Standardize runtime environment output so operators can inspect the active socket and port layout quickly.

### Task 3: Expand integration coverage for Phase 1 evidence

- Keep separate integration evidence for:
  - `/v1/models`
  - streamed `/v1/chat/completions`
  - abort on the default Swift route
  - explicit failure when the Swift text worker becomes unavailable
- Update the test harness to boot the Phase 1 stack predictably and to force the failure-path test without reintroducing fallback behavior.

### Task 4: Add a reproducible metrics report path

- Add a script or command that compares:
  - Swift worker direct text path
  - Python worker compatibility text path
  - control-plane HTTP text path
- Record at least:
  - load-model latency
  - TTFT
  - end-to-end generation time
  - tokens per second
  - abort latency when measurable
- Write a short runbook that explains the deterministic path, the optional MLX path, and the exact metrics-report command.

## Verification

```bash
swift test --package-path services/mlx-text-worker-swift
make swift-test
make py-test
make integration-test
make coverage
bash scripts/dev_up.sh
bash scripts/dev_down.sh
```

Optional MLX smoke:

```bash
MELIX_DEV_TEXT_MODEL_PATH="<model path or repo>" \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift \
bash scripts/dev_up.sh
```

## Acceptance

- The default integration path boots the Swift text worker in deterministic mode and still exercises the shared worker RPC boundary.
- `scripts/dev_up.sh` and `scripts/dev_down.sh` manage the full Phase 1 stack reliably.
- Integration tests cover models, streamed chat, abort, and explicit Swift-worker failure as separate cases.
- A reproducible Phase 1 metrics-report command exists and is documented.
- The touched repository scope remains at or above `95%` measured automated coverage where measurable.
