# Issue 1386 Priority Scheduler and Preemption Plan

## Goal

Add the first operator-facing priority scheduling and cooperative preemption slice for the shared single-slot inference runtime.

## Current State

The control plane already records queued, admitted, phase, and terminal request progress through `SchedulerReadModel`. `RequestCoordinator` uses `AdmissionGate` to serialize active text execution and supports queued or active cancellation through `AbortRegistry` and worker `abort`. The missing issue 1386 behavior is scheduling policy: queued work is FIFO, priority classes do not influence admission order, and high-priority interactive work does not preempt lower-priority active work.

## End-State Architecture

The best Melix architecture is a scheduler-owned admission boundary that sits above worker dispatch. It should own priority ordering, cooperative preemption, cancellation receipts, and queue metrics while leaving worker-specific generation and streaming in the existing coordinator. Workers continue to receive scheduling hints, but the control plane remains the source of truth for which request owns the scarce inference slot.

This PR implements a small vertical slice in the current `RequestCoordinator` path:

- keep `AdmissionGate` as the concrete slot/batch primitive;
- add priority-aware queued ordering before admission;
- add a preemption check before a high-priority request waits behind active lower-priority work;
- cancel the lower-priority active request through the existing cooperative abort path;
- record typed cancellation/preemption receipts and metrics in the existing route-selection JSONL evidence stream.

## Scope

In scope:

- priority queue ordering for text chat completions in `RequestCoordinator`;
- cooperative preemption when an interactive or otherwise higher-priority request arrives behind lower-priority active work;
- cancellation/preemption receipt payloads with request id, preempting request id, cancellation reason, priority class, wait/run timing, upstream cancel latency, lifecycle, cancel source, and partial-output flag;
- metrics for scheduler preemption count and cancellation receipt emission;
- deterministic Swift tests covering priority ordering, preemption, and receipt content.

Out of scope:

- distributed scheduling;
- hard process kill;
- UI changes;
- new public HTTP endpoints;
- worker protobuf schema changes beyond existing scheduling hints;
- durable queue persistence across daemon restart.

## Performance Probes

- `scheduler.queue_delay_ms`: existing queue-delay metric must remain populated for admitted work.
- `scheduler.preemption_count`: increments when active work is preempted.
- `scheduler.cancellation_receipt_emitted`: increments when a cancellation/preemption receipt is written.
- `http.abort_ms` and phase-specific abort metrics: existing cancellation latency metrics must remain populated.

## Implementation Slices

### Slice 1: Priority-Aware Admission

- Extend `AdmissionGate` queue entries with `priorityScore`.
- Sort queued entries by descending priority and FIFO sequence within equal priority.
- Keep compatible cohort batching constrained to the selected front entry.
- Preserve existing FIFO behavior when priorities match.

### Slice 2: Cooperative Preemption Receipt

- Track active request priority, lane, start time, and stream output evidence in `RequestCoordinator`.
- Before a newly queued request waits, compare it with active requests.
- When the incoming request has higher priority than the lowest active request, call worker `abort`, record terminal state as `requestAborted`, release admission, and write a cancellation receipt.
- Keep disconnected detached-chat semantics unchanged: ordinary disconnect still uses the resume grace window; explicit scheduler preemption is an owned cancellation path.

### Slice 3: Verification and Evidence

- Add red-green tests in `RequestCoordinatorTests` for:
  - higher-priority queued work admitted before older lower-priority work;
  - interactive work preempting lower-priority active work and completing first;
  - interactive work preempting lower-priority work at the pre-worker-send checkpoint;
  - cancellation receipt fields and scheduler metrics.
- Run focused Swift tests, changed-line coverage for touched Swift files, `git diff --check`, and PR evidence validation.

## Acceptance

- A queued high-priority request is admitted before older lower-priority queued work once the slot frees.
- A high-priority request preempts lower-priority active work through cooperative worker abort and then completes first.
- The preempted request receives a cancelled completion rather than hanging.
- Receipts preserve the cancellation reason and partial-output flag.
- Metrics expose preemption and cancellation receipt emission.

## Review Remediation

PR review identified two liveness and cancellation gaps after the initial priority scheduler merge.

- `AdmissionGate` must not leave a queued front request idle when the request is not eligible for batch formation. `admitNextOrScheduleFormationFlush()` centralizes the choice between immediate admission and formation-window scheduling, and queued-front release reuses that same path.
- `RequestCoordinator` must send a safeguard worker abort when cancellation is observed immediately after `workerClient.generate` returns. This covers the race where the first abort arrived before the worker registered generation state.

Verification coverage:

- `admissionGateAdmitsNonFormingQueuedFrontImmediately`
- `admissionGateKeepsFormationQueueLiveAfterCancellingQueuedFront`
- `admittedRequestCancellationBeforeGenerateReturnsYieldsACancelledExecution`
- `interactiveWorkCanPreemptLowerPriorityWorkBeforeWorkerGenerateReturns`
