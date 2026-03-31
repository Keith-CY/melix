# M7.6 Benchmark Queue And Parameters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable queue state and explicit `sample_size` or `batch_factor` parameter handling for benchmark and evaluation jobs.

**Architecture:** Keep queue truth in the Python productization layer, expose typed queue snapshots through the control plane, and surface queue state minimally in the desktop shell. Reuse the persisted benchmark and evaluation job artifacts from `M7.3-M7.5`.

**Tech Stack:** Python productization queue store, Swift control-plane XPC service, file-backed JSON manifests, protobuf schemas, pytest, Swift Testing.

---

### Task 1: Add Queue Record Schemas And Python Queue Store

**Files:**
- Create: `services/mlx-worker-python/worker/productization/benchmark_queue.py`
- Create: `services/mlx-worker-python/tests/test_benchmark_queue.py`
- Modify: `services/mlx-worker-python/worker/productization/__init__.py`

- [ ] Write failing queue-store tests for enqueue, state transition, and parameter persistence.
- [ ] Run the focused queue tests and verify they fail.
- [ ] Implement a file-backed queue store with `queued`, `running`, `completed`, and `failed` states.
- [ ] Re-run the focused queue tests and verify they pass.
- [ ] Commit.

### Task 2: Thread Queue State Through Benchmark And Evaluation Execution

**Files:**
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`

- [ ] Write failing tests proving benchmark and evaluation execution persist queue-state transitions.
- [ ] Run the focused tests and verify they fail.
- [ ] Implement enqueue, running, and terminal-state transitions.
- [ ] Re-run the focused tests and verify they pass.
- [ ] Commit.

### Task 3: Add Parameter Fields For `sample_size` And `batch_factor`

**Files:**
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/schema/worker/v1/maintenance.proto`
- Regenerate protocol outputs and descriptors.
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`

- [ ] Write the failing Swift test that expects queued requests to preserve `sample_size` and `batch_factor`.
- [ ] Run the focused proto or Swift verification and confirm failure.
- [ ] Add the minimal protocol fields and control-plane translation logic.
- [ ] Re-run `make proto` and the focused Swift test.
- [ ] Commit.

### Task 4: Surface Queue State In Desktop Read Models

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

- [ ] Write failing view-model tests for queued benchmark or evaluation state visibility.
- [ ] Run the focused desktop tests and verify they fail.
- [ ] Implement the minimal queue-state read model and operator-visible strings.
- [ ] Re-run the focused desktop tests and verify they pass.
- [ ] Commit.

### Task 5: Add Runbook And Final Verification For M7.6

**Files:**
- Create: `docs/runbooks/m7-benchmark-queue-and-parameters.md`
- Modify: `docs/runbooks/README.md`
- Modify: `docs/README.md`

- [ ] Write the runbook with exact queue verification commands.
- [ ] Run `make proto`, focused Python tests, and focused Swift tests for touched scope.
- [ ] Record changed-line coverage for touched Python files.
- [ ] Commit.
