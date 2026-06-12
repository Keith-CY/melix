# Aggregated Audio Setup Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated per-audio-model setup rows in Models > Downloads with one capability-aware audio setup state machine.

**Architecture:** Keep the control plane and worker catalogs as the source of model metadata, while the macOS app owns setup-state derivation and presentation. Add audio setup metadata to catalog defaults, persist only the operator-confirmed selected setup scope in operator session state, then render one compact Downloads setup surface with inline expansion for model choice and progress.

**Tech Stack:** Swift 6, SwiftUI, Swift Testing, Python pytest, existing Melix control-plane and worker catalog metadata.

---

## Scope Notes

- Governing plan: `docs/plans/2026-04-21-macos-uiux-follow-up.md`, section `Aggregated Audio Setup Flow`.
- This plan intentionally keeps audio setup metadata audio-specific: `melix.audio.capability`, `melix.audio.setup_role`, and `melix.audio.setup_priority`.
- Chat and provider UI receive only capability-specific inline prompts in this slice if the current code path already exposes the relevant capability hooks. The main blocker remediation stays in Models > Downloads.
- Runtime performance probes are `N/A` for setup-state aggregation; verification evidence is focused Swift/Python tests and SwiftUI smoke coverage.

## File Structure

- `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
  - Add audio setup metadata to Swift catalog models.
- `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
  - Verify Swift catalog setup metadata for recommended and optional audio models.
- `services/mlx-worker-python/worker/model_registry/catalog.py`
  - Add matching setup metadata to worker catalog models.
- `services/mlx-worker-python/tests/test_audio_runtime.py`
  - Verify Python worker catalog setup metadata.
- `apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift`
  - Persist confirmed audio setup selected scope in app and shared operator session state.
- `apps/macos-menubar/Tests/MenuBarTests/OperatorSessionPersistenceSmokeTests.swift`
  - Cover selected-scope JSON persistence and shared-state bridging.
- `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
  - Define `RuntimeAudioSetupState`, capability groups, setup models, primary/secondary actions, selected scope, state derivation, and idempotent download reconciliation.
- `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
  - Cover state-machine behavior, selected scope, failure states, optional models, and queue reconciliation.
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
  - Replace `ForEach(audioSetupActions)` with one compact/expandable setup surface.
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
  - Cover compact row, expanded chooser, and no duplicate `Audio Setup Required` rendering.

## Performance Probes And Success Metrics

- Runtime hot-path probes: `N/A`.
- Required automated evidence:
  - Swift catalog tests pass.
  - Python catalog tests pass.
  - `RuntimeViewModelTests` cover setup-state derivation and queue reconciliation.
  - `OperatorSessionPersistenceSmokeTests` cover selected-scope persistence.
  - `DesktopFoundationViewTests` cover compact and expanded Downloads rendering.
- Required changed-scope coverage before commit: at least 95 percent measured for touched macOS app scope. If the current tree cannot measure that exact scope, add the closest available coverage command to the metrics report and state why exact changed-scope coverage is unavailable.

## Task 1: Add Audio Setup Metadata To Catalogs

**Files:**
- Modify: `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- Modify: `services/mlx-worker-python/worker/model_registry/catalog.py`
- Modify: `services/mlx-worker-python/tests/test_audio_runtime.py`

- [ ] **Step 1: Write failing Swift catalog assertions**

In `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`, extend the existing audio catalog metadata test with these assertions:

```swift
#expect(whisper.settings.ext["melix.audio.capability"] == "stt")
#expect(whisper.settings.ext["melix.audio.setup_role"] == "recommended")
#expect(whisper.settings.ext["melix.audio.setup_priority"] == "0")

#expect(parakeet.settings.ext["melix.audio.capability"] == "stt")
#expect(parakeet.settings.ext["melix.audio.setup_role"] == "optional")
#expect(parakeet.settings.ext["melix.audio.setup_priority"] == "20")

#expect(kokoro.settings.ext["melix.audio.capability"] == "tts")
#expect(kokoro.settings.ext["melix.audio.setup_role"] == "recommended")
#expect(kokoro.settings.ext["melix.audio.setup_priority"] == "0")

#expect(qwen3TTS.settings.ext["melix.audio.capability"] == "tts")
#expect(qwen3TTS.settings.ext["melix.audio.setup_role"] == "optional")
#expect(qwen3TTS.settings.ext["melix.audio.setup_priority"] == "20")
```

- [ ] **Step 2: Write failing Python catalog assertions**

In `services/mlx-worker-python/tests/test_audio_runtime.py`, extend the existing audio model catalog assertions:

```python
    assert whisper.ext["melix.audio.capability"] == "stt"
    assert whisper.ext["melix.audio.setup_role"] == "recommended"
    assert whisper.ext["melix.audio.setup_priority"] == "0"

    assert parakeet.ext["melix.audio.capability"] == "stt"
    assert parakeet.ext["melix.audio.setup_role"] == "optional"
    assert parakeet.ext["melix.audio.setup_priority"] == "20"

    assert kokoro.ext["melix.audio.capability"] == "tts"
    assert kokoro.ext["melix.audio.setup_role"] == "recommended"
    assert kokoro.ext["melix.audio.setup_priority"] == "0"

    assert qwen3_tts.ext["melix.audio.capability"] == "tts"
    assert qwen3_tts.ext["melix.audio.setup_role"] == "optional"
    assert qwen3_tts.ext["melix.audio.setup_priority"] == "20"
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
swift test --package-path services/control-plane-swift --filter ModelCatalogTests
PYTHONPATH="$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_audio_runtime.py -q
```

Expected: Swift and Python catalog assertions fail because setup metadata is not present.

- [ ] **Step 4: Add Swift catalog metadata**

In `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`, add optional setup fields to the `audioMetadata(...)` helper if it already centralizes audio ext output. If the helper signature is near the audio catalog definitions, use:

```swift
setupCapability: String = "",
setupRole: String = "",
setupPriority: Int? = nil
```

and include:

```swift
if setupCapability.isEmpty == false {
    metadata["melix.audio.capability"] = setupCapability
}
if setupRole.isEmpty == false {
    metadata["melix.audio.setup_role"] = setupRole
}
if let setupPriority {
    metadata["melix.audio.setup_priority"] = "\(setupPriority)"
}
```

Then pass these values from the four MLX audio catalog models:

```swift
// Whisper
setupCapability: "stt",
setupRole: "recommended",
setupPriority: 0

// Parakeet
setupCapability: "stt",
setupRole: "optional",
setupPriority: 20

// Kokoro
setupCapability: "tts",
setupRole: "recommended",
setupPriority: 0

// Qwen3 TTS
setupCapability: "tts",
setupRole: "optional",
setupPriority: 20
```

- [ ] **Step 5: Add Python catalog metadata**

In `services/mlx-worker-python/worker/model_registry/catalog.py`, add parameters to `_audio_metadata(...)` or a small `_audio_setup_metadata(...)` helper. Use this helper output in each MLX audio model:

```python
def _audio_setup_metadata(*, capability: str, role: str, priority: int) -> dict[str, str]:
    return {
        "melix.audio.capability": capability,
        "melix.audio.setup_role": role,
        "melix.audio.setup_priority": str(priority),
    }
```

Merge it into `ext`:

```python
**_audio_setup_metadata(capability="stt", role="recommended", priority=0)
**_audio_setup_metadata(capability="stt", role="optional", priority=20)
**_audio_setup_metadata(capability="tts", role="recommended", priority=0)
**_audio_setup_metadata(capability="tts", role="optional", priority=20)
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
swift test --package-path services/control-plane-swift --filter ModelCatalogTests
PYTHONPATH="$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_audio_runtime.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift \
  services/mlx-worker-python/worker/model_registry/catalog.py \
  services/mlx-worker-python/tests/test_audio_runtime.py
git commit -m "feat: add audio setup catalog metadata"
```

## Task 2: Persist Confirmed Audio Setup Scope

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/OperatorSessionPersistenceSmokeTests.swift`

- [ ] **Step 1: Write failing persistence test**

In `OperatorSessionPersistenceSmokeTests.swift`, add:

```swift
    @Test("operator session persists confirmed audio setup scope")
    @MainActor
    func operatorSessionPersistsConfirmedAudioSetupScope() throws {
        let state = OperatorSessionState(
            selectedSurface: .tools,
            selectedToolSection: .downloads,
            selectedServerSessionID: "server-session-1",
            serverSessions: [],
            confirmedAudioSetupModelIDs: ["melix-kokoro-mlx", "melix-whisper-mlx"]
        )

        let encoded = try JSONEncoder().encode(state)
        let payload = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let encodedScope = try #require(payload["confirmed_audio_setup_model_ids"] as? [String])
        #expect(encodedScope == ["melix-kokoro-mlx", "melix-whisper-mlx"])

        let decoded = try JSONDecoder().decode(OperatorSessionState.self, from: encoded)
        #expect(decoded.confirmedAudioSetupModelIDs == ["melix-kokoro-mlx", "melix-whisper-mlx"])
    }
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
swift test --package-path apps/macos-menubar --filter operatorSessionPersistsConfirmedAudioSetupScope
```

Expected: FAIL because `confirmedAudioSetupModelIDs` does not exist.

- [ ] **Step 3: Add state field**

In `OperatorSessionState`, add:

```swift
public var confirmedAudioSetupModelIDs: [String]
```

Update the initializer:

```swift
confirmedAudioSetupModelIDs: [String] = []
```

Store a sorted, de-duplicated value:

```swift
self.confirmedAudioSetupModelIDs = Array(Set(confirmedAudioSetupModelIDs)).sorted()
```

Add coding key:

```swift
case confirmedAudioSetupModelIDs = "confirmed_audio_setup_model_ids"
```

Decode and encode:

```swift
confirmedAudioSetupModelIDs: try container.decodeIfPresent([String].self, forKey: .confirmedAudioSetupModelIDs) ?? []
try container.encode(confirmedAudioSetupModelIDs, forKey: .confirmedAudioSetupModelIDs)
```

- [ ] **Step 4: Bridge to shared session state**

If `MelixOperatorSessionState` in `MelixCLICore` has no matching field, keep the app-local JSON field in `OperatorSessionState` and do not add it to `sharedState` yet. If it already has a matching property, map it both ways:

```swift
confirmedAudioSetupModelIDs: sharedState.confirmedAudioSetupModelIDs
```

and:

```swift
confirmedAudioSetupModelIDs: confirmedAudioSetupModelIDs
```

Use only one path after inspecting the `MelixOperatorSessionState` definition; do not invent a shared field that does not exist.

- [ ] **Step 5: Restore and persist through RuntimeViewModel**

In `RuntimeViewModel`, add:

```swift
public private(set) var confirmedAudioSetupModelIDs: [String] = [] {
    didSet { persistOperatorSessionState() }
}
```

In `restoreOperatorSessionState()`:

```swift
confirmedAudioSetupModelIDs = restoredState.confirmedAudioSetupModelIDs
```

In `currentOperatorSessionState()`:

```swift
confirmedAudioSetupModelIDs: confirmedAudioSetupModelIDs
```

Add a public method used by the setup flow:

```swift
public func confirmAudioSetupScope(modelIDs: [String]) {
    confirmedAudioSetupModelIDs = Array(Set(modelIDs.filter { $0.isEmpty == false })).sorted()
    notifyStateChanged()
}
```

- [ ] **Step 6: Run test to verify pass**

Run:

```bash
swift test --package-path apps/macos-menubar --filter operatorSessionPersistsConfirmedAudioSetupScope
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift \
  apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Tests/MenuBarTests/OperatorSessionPersistenceSmokeTests.swift
git commit -m "feat: persist audio setup selected scope"
```

## Task 3: Introduce Audio Setup State Machine

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

- [ ] **Step 1: Write failing state-machine tests**

In `RuntimeViewModelTests.swift`, add tests near the existing audio setup tests:

```swift
    @Test("audio setup state aggregates missing shared runtime across audio models")
    @MainActor
    func audioSetupStateAggregatesMissingSharedRuntimeAcrossAudioModels() async throws {
        let client = FakeControlPlaneXPCClient()
        var whisper = ModelCatalog.mlxWhisperModel()
        var parakeet = ModelCatalog.mlxParakeetModel()
        var kokoro = ModelCatalog.mlxKokoroModel()
        for index in [0, 1, 2] {
            var model = [whisper, parakeet, kokoro][index]
            model.settings.ext["melix.audio.runtime_pack_state"] = "missing"
            model.settings.ext["melix.audio.runtime_pack_id"] = "melix-audio-runtime-pack"
            model.settings.ext["melix.audio.model_state"] = "catalog_default"
            if index == 0 { whisper = model }
            if index == 1 { parakeet = model }
            if index == 2 { kokoro = model }
        }
        await client.configureSnapshot(makeSnapshot(serverState: .serverReady, models: [whisper, parakeet, kokoro]))

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let state = try #require(viewModel.audioSetupState)
        #expect(state.kind == .runtimeRequired)
        #expect(state.title == "Audio Setup Required")
        #expect(state.primaryActionTitle == "Install Audio Support")
        #expect(state.affectedModelIDs.sorted() == ["melix-kokoro-mlx", "melix-parakeet-mlx", "melix-whisper-mlx"])
    }

    @Test("audio setup state requires recommended models and ignores missing optional models")
    @MainActor
    func audioSetupStateRequiresRecommendedModelsAndIgnoresMissingOptionalModels() async throws {
        let client = FakeControlPlaneXPCClient()
        var whisper = ModelCatalog.mlxWhisperModel()
        whisper.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        whisper.settings.ext["melix.audio.model_state"] = "managed_local"

        var kokoro = ModelCatalog.mlxKokoroModel()
        kokoro.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        kokoro.settings.ext["melix.audio.model_state"] = "catalog_default"

        var qwen = ModelCatalog.mlxQwen3TTSModel()
        qwen.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        qwen.settings.ext["melix.audio.model_state"] = "catalog_default"

        await client.configureSnapshot(makeSnapshot(serverState: .serverReady, models: [whisper, kokoro, qwen]))
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let state = try #require(viewModel.audioSetupState)
        #expect(state.kind == .modelsRequired)
        #expect(state.recommendedModelIDs == ["melix-kokoro-mlx"])
        #expect(state.optionalModelIDs == ["melix-qwen3-tts-mlx"])
    }
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
swift test --package-path apps/macos-menubar --filter 'audioSetupStateAggregatesMissingSharedRuntimeAcrossAudioModels|audioSetupStateRequiresRecommendedModelsAndIgnoresMissingOptionalModels'
```

Expected: FAIL because `audioSetupState` and related state types do not exist.

- [ ] **Step 3: Add state types**

In `RuntimeViewModel.swift`, place these near `RuntimeAudioSetupActionState`:

```swift
public enum RuntimeAudioSetupStateKind: String, Equatable, Sendable {
    case runtimeRequired
    case runtimeInstalling
    case runtimeFailed
    case modelsRequired
    case modelsDownloading
    case partiallyReady
    case readyFeedback
    case newRecommendedAvailable
}

public struct RuntimeAudioSetupModelState: Identifiable, Equatable, Sendable {
    public let modelID: String
    public let alias: String
    public let capability: String
    public let role: String
    public let priority: Int
    public let isManagedLocal: Bool
    public let isSelected: Bool
    public let queueEntry: RuntimeDownloadQueueEntryState?

    public var id: String { modelID }
}

public struct RuntimeAudioSetupCapabilityGroupState: Identifiable, Equatable, Sendable {
    public let capability: String
    public let title: String
    public let models: [RuntimeAudioSetupModelState]

    public var id: String { capability }
}

public struct RuntimeAudioSetupState: Equatable, Sendable {
    public let kind: RuntimeAudioSetupStateKind
    public let title: String
    public let detail: String
    public let primaryActionTitle: String
    public let secondaryActionTitle: String?
    public let affectedModelIDs: [String]
    public let recommendedModelIDs: [String]
    public let optionalModelIDs: [String]
    public let readyCount: Int
    public let targetCount: Int
    public let capabilityGroups: [RuntimeAudioSetupCapabilityGroupState]
    public let isExpandedByDefault: Bool
}
```

- [ ] **Step 4: Add metadata helpers**

Add private helpers in `RuntimeViewModel`:

```swift
private func audioSetupCapability(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let explicit = model.settings.ext["melix.audio.capability"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if explicit.isEmpty == false { return explicit }
    let backendID = model.settings.ext["melix.audio.backend_id"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if backendID == "mlx_audio.stt" { return "stt" }
    if backendID == "mlx_audio.tts" { return "tts" }
    if model.kind == "transcription" { return "stt" }
    if model.kind == "speech" { return "tts" }
    return ""
}

private func audioSetupRole(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let role = model.settings.ext["melix.audio.setup_role"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    return role.isEmpty ? "recommended" : role
}

private func audioSetupPriority(for model: Melix_Controlplane_V1_ModelSummary) -> Int {
    let raw = model.settings.ext["melix.audio.setup_priority"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return Int(raw) ?? 100
}

private func audioCapabilityTitle(_ capability: String) -> String {
    switch capability {
    case "stt": return "Speech to Text"
    case "tts": return "Text to Speech"
    default: return capability.isEmpty ? "Audio" : capability
    }
}
```

- [ ] **Step 5: Implement state derivation**

Add:

```swift
public var audioSetupState: RuntimeAudioSetupState? {
    let audioModels = latestSnapshot.models.filter { model in
        let backendID = model.settings.ext["melix.audio.backend_id"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return backendID.hasPrefix("mlx_audio.")
    }
    guard audioModels.isEmpty == false else { return nil }

    let missingRuntime = audioModels.filter { model in
        let state = model.settings.ext["melix.audio.runtime_pack_state"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return state != "installed"
    }
    if missingRuntime.isEmpty == false {
        let ids = missingRuntime.map(\.modelID).sorted()
        return RuntimeAudioSetupState(
            kind: .runtimeRequired,
            title: "Audio Setup Required",
            detail: "Install shared audio support for \(ids.count) audio model\(ids.count == 1 ? "" : "s").",
            primaryActionTitle: "Install Audio Support",
            secondaryActionTitle: nil,
            affectedModelIDs: ids,
            recommendedModelIDs: [],
            optionalModelIDs: [],
            readyCount: 0,
            targetCount: ids.count,
            capabilityGroups: audioSetupCapabilityGroups(from: audioModels, selectedIDs: Set(confirmedAudioSetupModelIDs)),
            isExpandedByDefault: false
        )
    }

    let groups = audioSetupCapabilityGroups(from: audioModels, selectedIDs: Set(confirmedAudioSetupModelIDs))
    let recommendedIDs = recommendedAudioSetupModelIDs(from: groups)
    let selectedIDs = confirmedAudioSetupModelIDs.isEmpty ? recommendedIDs : confirmedAudioSetupModelIDs
    let selectedSet = Set(selectedIDs)
    let selectedModels = groups.flatMap(\.models).filter { selectedSet.contains($0.modelID) }
    let readyCount = selectedModels.filter(\.isManagedLocal).count
    let targetCount = selectedModels.count

    if targetCount > 0, readyCount < targetCount {
        return RuntimeAudioSetupState(
            kind: selectedModels.contains(where: { $0.queueEntry?.resumeReady == true }) ? .partiallyReady : .modelsRequired,
            title: readyCount > 0 ? "Audio Setup Partially Ready" : "Audio Models Required",
            detail: readyCount > 0 ? "\(readyCount) of \(targetCount) selected audio models ready." : "Download recommended audio models.",
            primaryActionTitle: selectedModels.contains(where: { $0.queueEntry?.resumeReady == true }) ? "Retry Failed" : "Start Downloads",
            secondaryActionTitle: nil,
            affectedModelIDs: selectedIDs.sorted(),
            recommendedModelIDs: recommendedIDs.sorted(),
            optionalModelIDs: optionalAudioSetupModelIDs(from: groups).sorted(),
            readyCount: readyCount,
            targetCount: targetCount,
            capabilityGroups: groups,
            isExpandedByDefault: confirmedAudioSetupModelIDs.isEmpty
        )
    }

    return nil
}
```

Add helper methods called above:

```swift
private func audioSetupCapabilityGroups(
    from audioModels: [Melix_Controlplane_V1_ModelSummary],
    selectedIDs: Set<String>
) -> [RuntimeAudioSetupCapabilityGroupState] {
    let models = audioModels.map { model in
        let capability = audioSetupCapability(for: model)
        let role = audioSetupRole(for: model)
        let alias = model.settings.alias.isEmpty ? model.modelID : model.settings.alias
        let queueEntry = downloadQueue.first { $0.sourceModel == model.modelID }
        return RuntimeAudioSetupModelState(
            modelID: model.modelID,
            alias: alias,
            capability: capability,
            role: role,
            priority: audioSetupPriority(for: model),
            isManagedLocal: (model.settings.ext["melix.audio.model_state"] ?? "") == "managed_local",
            isSelected: selectedIDs.contains(model.modelID),
            queueEntry: queueEntry
        )
    }
    let grouped = Dictionary(grouping: models) { $0.capability }
    return grouped.keys.sorted().map { capability in
        RuntimeAudioSetupCapabilityGroupState(
            capability: capability,
            title: audioCapabilityTitle(capability),
            models: (grouped[capability] ?? []).sorted {
                if $0.role == $1.role {
                    if $0.priority == $1.priority { return $0.modelID < $1.modelID }
                    return $0.priority < $1.priority
                }
                return $0.role == "recommended"
            }
        )
    }
}

private func recommendedAudioSetupModelIDs(from groups: [RuntimeAudioSetupCapabilityGroupState]) -> [String] {
    groups.compactMap { group in
        group.models
            .filter { $0.role == "recommended" }
            .sorted { lhs, rhs in
                if lhs.priority == rhs.priority { return lhs.modelID < rhs.modelID }
                return lhs.priority < rhs.priority
            }
            .first?
            .modelID
    }
}

private func optionalAudioSetupModelIDs(from groups: [RuntimeAudioSetupCapabilityGroupState]) -> [String] {
    groups.flatMap(\.models).filter { $0.role != "recommended" }.map(\.modelID)
}
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
swift test --package-path apps/macos-menubar --filter 'audioSetupStateAggregatesMissingSharedRuntimeAcrossAudioModels|audioSetupStateRequiresRecommendedModelsAndIgnoresMissingOptionalModels'
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift
git commit -m "feat: derive aggregated audio setup state"
```

## Task 4: Add Audio Setup Actions And Idempotent Download Reconcile

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

- [ ] **Step 1: Write failing action tests**

Add:

```swift
    @Test("audio setup start downloads confirms scope and skips managed local models")
    @MainActor
    func audioSetupStartDownloadsConfirmsScopeAndSkipsManagedLocalModels() async throws {
        let client = FakeControlPlaneXPCClient()
        var whisper = ModelCatalog.mlxWhisperModel()
        whisper.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        whisper.settings.ext["melix.audio.model_state"] = "managed_local"

        var kokoro = ModelCatalog.mlxKokoroModel()
        kokoro.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        kokoro.settings.ext["melix.audio.model_state"] = "catalog_default"

        await client.configureSnapshot(makeSnapshot(serverState: .serverReady, models: [whisper, kokoro]))
        await client.configureModelOperation(makeNamedModelOperationResult(operation: "download"), forNamedOperation: "download")

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.startAudioModelDownloads(modelIDs: ["melix-whisper-mlx", "melix-kokoro-mlx"])

        #expect(viewModel.confirmedAudioSetupModelIDs == ["melix-kokoro-mlx", "melix-whisper-mlx"])
        let requests = await client.recordedModelOperationRequests
        #expect(requests.contains { $0.operation == "download" && $0.modelID == "melix-kokoro-mlx" })
        #expect(requests.contains { $0.operation == "download" && $0.modelID == "melix-whisper-mlx" } == false)
    }
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
swift test --package-path apps/macos-menubar --filter audioSetupStartDownloadsConfirmsScopeAndSkipsManagedLocalModels
```

Expected: FAIL because `startAudioModelDownloads` does not exist.

- [ ] **Step 3: Add primary action methods**

In `RuntimeViewModel.swift`, add:

```swift
public func performPrimaryAudioSetupAction() async {
    guard let state = audioSetupState else { return }
    switch state.kind {
    case .runtimeRequired, .runtimeFailed:
        if let modelID = state.affectedModelIDs.first {
            await installAudioRuntime(modelID: modelID)
        }
    case .modelsRequired, .modelsDownloading, .partiallyReady:
        await startAudioModelDownloads(modelIDs: state.affectedModelIDs)
    case .runtimeInstalling, .readyFeedback, .newRecommendedAvailable:
        return
    }
}

public func startAudioModelDownloads(modelIDs: [String]) async {
    let normalizedIDs = Array(Set(modelIDs.filter { $0.isEmpty == false })).sorted()
    guard normalizedIDs.isEmpty == false else { return }
    confirmAudioSetupScope(modelIDs: normalizedIDs)
    for modelID in normalizedIDs {
        guard let model = latestSnapshot.models.first(where: { $0.modelID == modelID }) else { continue }
        if (model.settings.ext["melix.audio.model_state"] ?? "") == "managed_local" { continue }
        if downloadQueue.contains(where: { $0.sourceModel == modelID && ($0.isActive || $0.resumeReady) }) { continue }
        await downloadAudioModel(modelID: modelID)
    }
    await refreshDownloadQueueState(notify: true, surfaceErrors: false)
}
```

- [ ] **Step 4: Preserve existing prompt compatibility**

Keep existing `RuntimeAudioSetupActionState`, `RuntimeAudioSetupPromptState`, and `performAudioSetupAction(_:)` through this task so older tests still compile. Mark them as compatibility only in comments if needed:

```swift
// Compatibility path for existing prompt tests while Downloads migrates to audioSetupState.
```

- [ ] **Step 5: Run test to verify pass**

Run:

```bash
swift test --package-path apps/macos-menubar --filter audioSetupStartDownloadsConfirmsScopeAndSkipsManagedLocalModels
```

Expected: PASS.

- [ ] **Step 6: Run existing audio action tests**

Run:

```bash
swift test --package-path apps/macos-menubar --filter 'audioSetupActionsDispatchInstallAndDownloadOperationsThenRefreshSnapshot|audioSetupRemediationStaysContextualInsteadOfBecomingDesktopBanner'
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift
git commit -m "feat: reconcile audio setup downloads"
```

## Task 5: Replace Downloads Audio Rows With One Setup Surface

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

- [ ] **Step 1: Write failing SwiftUI tests**

Add:

```swift
    @Test("downloads renders one aggregated audio setup surface for shared runtime")
    @MainActor
    func downloadsRendersOneAggregatedAudioSetupSurfaceForSharedRuntime() async throws {
        let client = FakeControlPlaneXPCClient()
        var whisper = ModelCatalog.mlxWhisperModel()
        whisper.settings.ext["melix.audio.runtime_pack_state"] = "missing"
        var kokoro = ModelCatalog.mlxKokoroModel()
        kokoro.settings.ext["melix.audio.runtime_pack_state"] = "missing"
        await client.configureSnapshot(makeAudioSetupSnapshot(models: [whisper, kokoro]))

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)

        let hosted = hostView(DesktopDownloadsToolSectionView(viewModel: viewModel))
        let texts = renderedTextValues(in: hosted)
        #expect(texts.filter { $0 == "Audio Setup Required" }.count == 1)
        #expect(texts.contains("Install Audio Support"))
    }

    @Test("downloads expanded audio setup shows recommended and optional groups")
    @MainActor
    func downloadsExpandedAudioSetupShowsRecommendedAndOptionalGroups() async throws {
        let client = FakeControlPlaneXPCClient()
        var whisper = ModelCatalog.mlxWhisperModel()
        whisper.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        whisper.settings.ext["melix.audio.model_state"] = "catalog_default"
        var parakeet = ModelCatalog.mlxParakeetModel()
        parakeet.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        parakeet.settings.ext["melix.audio.model_state"] = "catalog_default"
        await client.configureSnapshot(makeAudioSetupSnapshot(models: [whisper, parakeet]))

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        let hosted = hostView(DesktopAudioSetupSurfaceView(viewModel: viewModel))
        let texts = renderedTextValues(in: hosted)
        #expect(texts.contains("Audio Models Required"))
        #expect(texts.contains("Recommended"))
        #expect(texts.contains("Optional"))
    }
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
swift test --package-path apps/macos-menubar --filter 'downloadsRendersOneAggregatedAudioSetupSurfaceForSharedRuntime|downloadsExpandedAudioSetupShowsRecommendedAndOptionalGroups'
```

Expected: FAIL because `DesktopAudioSetupSurfaceView` does not exist and Downloads still renders per-action rows.

- [ ] **Step 3: Replace per-action rows**

In `DesktopDownloadsToolSectionView`, replace:

```swift
if viewModel.audioSetupActions.isEmpty == false {
    VStack(alignment: .leading, spacing: 8) {
        ForEach(viewModel.audioSetupActions) { action in
            DesktopAudioSetupNoticeRow(
                action: action,
                performAction: { viewModel.presentAudioSetupPrompt(action) }
            )
        }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
}
```

with:

```swift
if viewModel.audioSetupState != nil {
    DesktopAudioSetupSurfaceView(viewModel: viewModel)
}
```

- [ ] **Step 4: Add compact and expanded views**

In `DesktopWorkspaceShellView.swift`, add:

```swift
struct DesktopAudioSetupSurfaceView: View {
    let viewModel: RuntimeViewModel
    @State private var isExpanded = false

    private var state: RuntimeAudioSetupState? { viewModel.audioSetupState }

    var body: some View {
        if let state {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    Label(state.title, systemImage: "waveform.badge.exclamationmark")
                        .font(.caption.weight(.semibold))
                        .lineLimit(1)
                    Text(state.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    Spacer(minLength: 8)
                    Button(state.primaryActionTitle) {
                        Task { await viewModel.performPrimaryAudioSetupAction() }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .fixedSize(horizontal: true, vertical: false)
                    if state.capabilityGroups.isEmpty == false {
                        Button(isExpanded ? "Hide" : "Review") {
                            isExpanded.toggle()
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .fixedSize(horizontal: true, vertical: false)
                    }
                }
                .padding(.horizontal, 10)
                .frame(height: DesktopDownloadsLayoutMetrics.compactAudioNoticeHeightBudget)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))

                if isExpanded || state.isExpandedByDefault {
                    DesktopAudioSetupExpandedPanel(state: state, viewModel: viewModel)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct DesktopAudioSetupExpandedPanel: View {
    let state: RuntimeAudioSetupState
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(state.capabilityGroups) { group in
                VStack(alignment: .leading, spacing: 6) {
                    Text(group.title)
                        .font(.caption.weight(.semibold))
                    ForEach(group.models) { model in
                        HStack(spacing: 8) {
                            Image(systemName: model.isSelected ? "checkmark.circle.fill" : "circle")
                            VStack(alignment: .leading, spacing: 2) {
                                Text(model.alias)
                                    .font(.caption)
                                Text(model.role == "recommended" ? "Recommended" : "Optional")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(model.isManagedLocal ? "Ready" : (model.queueEntry?.progressText ?? "Not installed"))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
    }
}
```

- [ ] **Step 5: Run tests to verify pass**

Run:

```bash
swift test --package-path apps/macos-menubar --filter 'downloadsRendersOneAggregatedAudioSetupSurfaceForSharedRuntime|downloadsExpandedAudioSetupShowsRecommendedAndOptionalGroups'
```

Expected: PASS.

- [ ] **Step 6: Run compact notice regression test**

Run:

```bash
swift test --package-path apps/macos-menubar --filter downloadsSectionRendersCompactAudioSetupNotice
```

Expected: PASS, or update the test to host `DesktopAudioSetupSurfaceView` and assert `compactAudioNoticeHeightBudget`.

- [ ] **Step 7: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift \
  apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift
git commit -m "feat: render aggregated audio setup surface"
```

## Task 6: Update Plan Evidence And Run Verification

**Files:**
- Modify: `docs/plans/2026-04-21-macos-uiux-follow-up.md`
- Modify: `docs/superpowers/plans/2026-06-12-aggregated-audio-setup-flow.md`

- [ ] **Step 1: Run focused Swift tests**

Run:

```bash
swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|OperatorSessionPersistenceSmokeTests'
```

Expected: PASS.

- [ ] **Step 2: Run catalog tests**

Run:

```bash
swift test --package-path services/control-plane-swift --filter ModelCatalogTests
PYTHONPATH="$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_audio_runtime.py -q
```

Expected: PASS.

- [ ] **Step 3: Run repository formatting check**

Run:

```bash
git diff --check
```

Expected: PASS.

- [ ] **Step 4: Update evidence in the governing plan**

In `docs/plans/2026-04-21-macos-uiux-follow-up.md`, add a short `Latest aggregated audio setup evidence` subsection under `Verification` with the commands run and pass/fail status:

```markdown
Latest aggregated audio setup evidence:

- `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|OperatorSessionPersistenceSmokeTests'`: passed.
- `swift test --package-path services/control-plane-swift --filter ModelCatalogTests`: passed.
- `PYTHONPATH="$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_audio_runtime.py -q`: passed.
- `git diff --check`: passed.
```

- [ ] **Step 5: Record metrics**

Under `Metrics`, keep runtime hot-path probes as `N/A` and add measured test evidence. If coverage tooling is available, run it for the macOS menu-bar package and record the changed-scope percentage. If coverage tooling is not available in this repo slice, record:

```markdown
- Changed-scope coverage: N/A for this worktree because no focused Swift coverage command exists for the macOS menu-bar package in the current command contract. Focused state-machine and SwiftUI tests listed above cover the changed setup paths.
```

- [ ] **Step 6: Commit**

```bash
git add docs/plans/2026-04-21-macos-uiux-follow-up.md \
  docs/superpowers/plans/2026-06-12-aggregated-audio-setup-flow.md
git commit -m "docs: plan aggregated audio setup flow"
```

## Self-Review

- Spec coverage: The tasks cover catalog metadata, app persistence, state derivation, download reconciliation, SwiftUI rendering, verification evidence, and metrics reporting from the governing plan.
- Placeholder scan: This plan uses concrete file paths, test names, commands, expected outcomes, and code snippets for each implementation step.
- Type consistency: Public types use the `RuntimeAudioSetup...` prefix and the single top-level ViewModel property is `audioSetupState`.
