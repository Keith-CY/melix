# Issue 350 Serving Memory Telemetry Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a deterministic control-plane device-memory telemetry producer into serving memory admission so production requests can emit `memory_telemetry_source=detected` without relying on ad hoc model metadata.

**Architecture:** `RequestCoordinator` keeps the memory-admission receipt as the orchestration source of truth. The existing model metadata keys remain highest precedence, and a new injectable host-memory supplier fills the telemetry gap only when model settings do not already supply memory bytes. Diagnostics writers remain passive and continue to derive top-level receipts only from complete metadata.

**Tech Stack:** Swift control plane, Swift Testing, Melix worker request metadata, serving diagnostics runbook.

---

## Scope

In scope:

- Add an injectable `RequestCoordinator` host-memory supplier for serving memory admission.
- Use the supplier after existing model settings metadata keys:
  - `melix.serving.memory.available_bytes`
  - `melix.serving.memory.detected_memory_bytes`
  - `melix.device.memory_total_bytes`
- Pass `ProcessInfo.processInfo.physicalMemory` from production `ControlPlaneService` and bootstrap construction paths.
- Keep direct unit-test `RequestCoordinator` construction deterministic by defaulting the supplier to `nil`.
- Document that production admission now has a device-memory fallback while diagnostics remain passive.

Out of scope:

- Worker memory probes, worker health checks, or model loading.
- Runtime allocation changes, sampler changes, or KV-buffer enforcement.
- Measured OOM-reduction claims.
- Python diagnostics schema changes.

## Performance And Metrics

Observability mode: request admission metadata. The added work is one optional closure call and existing integer receipt computation before worker dispatch.

Success metrics:

- Focused RequestCoordinator tests pass.
- Focused ControlPlaneService construction test passes.
- `git diff --check` passes.
- Before PR, full local pre-commit must report scoped performance `ok` with regressions `0` and verification failures `0`.

## Tasks

### Task 1: Add RED coverage for injected memory telemetry

**Files:**

- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

- [x] **Step 1: Write the failing RequestCoordinator test**

Add a test near the existing serving memory admission tests:

```swift
@Test("serving memory admission uses injected device memory when model metadata is absent")
func servingMemoryAdmissionUsesInjectedDeviceMemoryWhenModelMetadataIsAbsent() async throws {
    let workerClient = PhaseAwareWorkerClient()
    var textModel = ModelCatalog.devTextModel()
    textModel.maxContext = 131_072
    textModel.settings.memoryBudgetBytes = 1_073_741_824
    textModel.settings.ext["melix.serving.memory.bytes_per_token"] = "262144"
    let catalog = ModelCatalog(seedModels: [textModel])
    let coordinator = RequestCoordinator(
        workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog),
        abortRegistry: AbortRegistry(),
        modelCatalog: catalog,
        servingMemoryBytesProvider: { 4_294_967_296 }
    )

    let execution = try await coordinator.startChatCompletion(
        makeTranslatedChatRequest(
            requestID: "req-memory-admission-injected-device-memory",
            saveBoundarySnapshot: true,
            executionExt: [
                "melix.gateway.concurrent_processing": "true",
                "melix.gateway.max_concurrent_sequences": "4",
            ]
        )
    )
    let consumer = Task {
        do {
            for try await _ in execution.stream {}
        } catch {}
    }
    defer { consumer.cancel() }

    let prefillRequest = try #require(await waitForPrefillRequest(workerClient: workerClient))
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.memory_telemetry_source"] == "detected")
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.memory_headroom_bytes"] == "2147483648")
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.admission_reason"] == "memory_step_down")
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.effective_context"] == "4096")
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.effective_batch"] == "1")

    let decodeRequest = try #require(await waitForDecodeRequest(workerClient: workerClient))
    await workerClient.emitDecodeStarted(
        requestID: "req-memory-admission-injected-device-memory",
        decodeHandle: decodeRequest.decodeHandle
    )
    await workerClient.emitToken(requestID: "req-memory-admission-injected-device-memory", text: "memory")
    await workerClient.finishDecode(requestID: "req-memory-admission-injected-device-memory")
    _ = await consumer.result
}
```

- [x] **Step 2: Verify RED**

Run:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/servingMemoryAdmissionUsesInjectedDeviceMemoryWhenModelMetadataIsAbsent
```

Expected: compile failure because `RequestCoordinator` has no `servingMemoryBytesProvider` initializer argument.

### Task 2: Add GREEN implementation for the injectable supplier

**Files:**

- Modify: `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`

- [x] **Step 1: Add the stored supplier**

Add this property near `now`:

```swift
private let servingMemoryBytesProvider: @Sendable () -> UInt64?
```

- [x] **Step 2: Add the initializer argument**

Extend `RequestCoordinator.init` after `lifecyclePolicy`:

```swift
servingMemoryBytesProvider: (@escaping @Sendable () -> UInt64?) = { nil },
```

Assign it in the initializer:

```swift
self.servingMemoryBytesProvider = servingMemoryBytesProvider
```

- [x] **Step 3: Use the supplier after model metadata**

Change `detectedServingMemoryBytes(for:)` so it keeps the existing metadata loop and returns the injected value only when no metadata key parsed:

```swift
for key in [
    "melix.serving.memory.available_bytes",
    "melix.serving.memory.detected_memory_bytes",
    "melix.device.memory_total_bytes",
] {
    if let value = parseUInt64Value(model.settings.ext[key], allowZero: true) {
        return value
    }
}
return servingMemoryBytesProvider()
```

- [x] **Step 4: Verify GREEN**

Run:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/servingMemoryAdmissionUsesInjectedDeviceMemoryWhenModelMetadataIsAbsent
```

Expected: pass.

### Task 3: Prove metadata precedence over the supplier

**Files:**

- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

- [x] **Step 1: Write the RED precedence test**

Add a second focused test:

```swift
@Test("serving memory admission prefers explicit model memory metadata over injected device memory")
func servingMemoryAdmissionPrefersExplicitModelMemoryMetadataOverInjectedDeviceMemory() async throws {
    let workerClient = PhaseAwareWorkerClient()
    var textModel = ModelCatalog.devTextModel()
    textModel.maxContext = 131_072
    textModel.settings.memoryBudgetBytes = 1_073_741_824
    textModel.settings.ext["melix.serving.memory.available_bytes"] = "0"
    textModel.settings.ext["melix.serving.memory.bytes_per_token"] = "262144"
    let catalog = ModelCatalog(seedModels: [textModel])
    let coordinator = RequestCoordinator(
        workerRegistry: WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog),
        abortRegistry: AbortRegistry(),
        modelCatalog: catalog,
        servingMemoryBytesProvider: { 17_179_869_184 }
    )

    let execution = try await coordinator.startChatCompletion(
        makeTranslatedChatRequest(
            requestID: "req-memory-admission-metadata-precedence",
            saveBoundarySnapshot: true,
            executionExt: [
                "melix.gateway.concurrent_processing": "true",
                "melix.gateway.max_concurrent_sequences": "4",
            ]
        )
    )
    let consumer = Task {
        do {
            for try await _ in execution.stream {}
        } catch {}
    }
    defer { consumer.cancel() }

    let prefillRequest = try #require(await waitForPrefillRequest(workerClient: workerClient))
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.memory_telemetry_source"] == "detected")
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.admission_reason"] == "insufficient_memory")
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.effective_context"] == "2048")
    #expect(prefillRequest.execution.ext["melix.serving.memory_admission.fits_memory"] == "false")

    let decodeRequest = try #require(await waitForDecodeRequest(workerClient: workerClient))
    await workerClient.emitDecodeStarted(
        requestID: "req-memory-admission-metadata-precedence",
        decodeHandle: decodeRequest.decodeHandle
    )
    await workerClient.emitToken(requestID: "req-memory-admission-metadata-precedence", text: "memory")
    await workerClient.finishDecode(requestID: "req-memory-admission-metadata-precedence")
    _ = await consumer.result
}
```

- [x] **Step 2: Verify RED**

Temporarily invert the implementation to call the supplier before model metadata, or run before Task 2 implementation if possible.

Run:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/servingMemoryAdmissionPrefersExplicitModelMemoryMetadataOverInjectedDeviceMemory
```

Expected: fail if supplier precedence is wrong; pass once metadata precedence is restored.

### Task 4: Wire production construction paths

**Files:**

- Modify: `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Sources/Bootstrap/main.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`

- [x] **Step 1: Add a reusable production supplier**

Add to `RequestCoordinator`:

```swift
public static func processInfoPhysicalMemoryBytes() -> UInt64? {
    let bytes = ProcessInfo.processInfo.physicalMemory
    return bytes > 0 ? bytes : nil
}
```

- [x] **Step 2: Pass the supplier from production construction**

In `ControlPlaneService` and bootstrap `OpenAIHandler` construction, pass:

```swift
servingMemoryBytesProvider: RequestCoordinator.processInfoPhysicalMemoryBytes
```

- [x] **Step 3: Add a default-unknown regression assertion**

Keep the existing direct `RequestCoordinator` tests that assert `memory_telemetry_source == "unknown"` unchanged. They prove unit-test construction remains deterministic unless the supplier is injected.

- [x] **Step 4: Add a production wiring regression test**

Add a `ControlPlaneService` test that constructs the service through its default
`RequestCoordinator` path and proves a request without model memory metadata
emits `memory_telemetry_source=detected`.

- [x] **Step 5: Verify focused tests**

Run:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/servingMemoryAdmission
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter ControlPlaneServiceTests/startChatDefaultCoordinatorUsesProcessMemoryTelemetry
```

Expected: all serving memory admission focused tests pass.

### Task 5: Update docs and verify hygiene

**Files:**

- Modify: `docs/runbooks/serving-diagnostics-evidence.md`

- [x] **Step 1: Update the runbook**

Replace the current telemetry wiring gap paragraph with wording that says production control-plane construction now falls back to `ProcessInfo.processInfo.physicalMemory` when model settings metadata does not provide a more specific memory value, while tests and custom coordinators can inject `nil` to keep receipts at `unknown`.

- [x] **Step 2: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output.

- [x] **Step 3: Run focused Swift verification**

Run:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/servingMemoryAdmission
```

Expected: pass.

- [x] **Step 4: Run changed-line coverage**

Run:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --enable-code-coverage --filter 'servingMemoryAdmission|startChatDefaultCoordinatorUsesProcessMemoryTelemetry'
UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift
```

Expected: changed-line coverage is at least 95%.

- [x] **Step 5: Commit the slice**

Run:

```bash
git add docs/plans/2026-07-07-issue-350-serving-memory-telemetry-producer.md docs/runbooks/serving-diagnostics-evidence.md services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift
git commit -m "Add serving memory telemetry producer"
```
