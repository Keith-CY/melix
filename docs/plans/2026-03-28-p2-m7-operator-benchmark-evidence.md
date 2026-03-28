# P2-M7 Operator and Benchmark Evidence Implementation Plan

**Goal:** Leave Phase 2 with a reproducible operator workflow that exercises real queue pressure, emits phase-aware metrics from the live stack, and records non-`N/A` evidence for admission latency, queue delay, TTFT, TPS, abort latency, and acceleration behavior.

**Scope:** This milestone covers real admission queueing in the control plane, exportable metrics snapshots for the control plane and Swift text worker, a Phase 2 metrics report script, a queue-pressure integration case, and the runbook plus command wiring needed to reproduce the evidence locally. It does not add new public HTTP endpoints or desktop UI.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code:
  - `services/control-plane-swift/Sources/Requests/*`
  - `services/control-plane-swift/Sources/Metrics/*`
  - `services/mlx-text-worker-swift/Sources/Core/*`
  - `tests/integration/*`
  - `scripts/dev_up.sh`
  - `scripts/dev_down.sh`

## Non-Goals

- Add `/metrics`, `/health`, or any other new public operator endpoint.
- Build a desktop scheduler inspector or queue dashboard.
- Introduce Phase 3 cache persistence or restart-aware recovery.
- Rework the Phase 2 scheduler into a multi-lane fairness engine beyond the admission queue needed for this milestone.

## Performance Probes

- `scheduler.admission_latency_ms`
- `scheduler.queue_delay_ms`
- `scheduler.active_lane_depth`
- `scheduler.backpressure`
- `swift_text.prefill_ms`
- `swift_text.decode_ttft_ms`
- `swift_text.decode_tokens_per_second`
- `swift_text.speculative_acceptance_rate`
- `swift_text.speculative_rollback_rate`
- `swift_text.accelerated_prefill_gain_pct`
- `swift_text.active_kv_quantization_ratio`
- `swift_text.abort_ms`

## Work Plan

### Task 1: Replace single-request tracking with real admission queueing

- Promote request tracking from single-active to multi-request state.
- Add a real admission gate so one request can be active while later requests queue and accumulate measurable `queue_delay_ms`.
- Keep abort behavior valid for queued, admitted, prefill, and decode states.

### Task 2: Export live metrics without widening the public API

- Add optional metrics-file export to the control-plane and Swift text worker metric stores.
- Wire the export paths through local bootstrap and dev scripts.
- Keep the export JSON machine-readable so runbooks and scripts can consume it directly.

### Task 3: Add Phase 2 operator workflow and benchmark script

- Add `make phase2-metrics`.
- Implement `scripts/phase2_metrics_report.py` to collect:
  - HTTP baseline TTFT and TPS
  - queue-pressure evidence
  - direct worker prefill and decode probes
  - speculative and accelerated-prefill evidence
  - active-KV-quantized evidence
  - decode abort latency
- Keep deterministic backend as the default reproducible path.

### Task 4: Add queue-pressure integration coverage and runbook

- Add a live integration case proving the follower request actually queues behind the leader.
- Add a Phase 2 runbook for boot, queue-pressure reproduction, metrics capture, and recovery.
- Update docs indexes and command references so the operator path is discoverable from `docs/README.md`.

## Verification

```bash
swift test --package-path services/control-plane-swift
swift test --package-path services/mlx-text-worker-swift
make swift-test
make py-test
make integration-test
make coverage
make phase2-metrics
git diff --check
```

## Acceptance

- The live stack exposes real queue delay under concurrent text load.
- Metrics exports exist for the running control plane and Swift text worker.
- `make phase2-metrics` reports admission latency, queue delay, TTFT, TPS, abort latency, speculative metrics, accelerated-prefill gain, and active-KV-quantization data without `N/A` for the deterministic path.
- The touched scope remains at or above `95%` measured coverage where coverage is currently measurable.
