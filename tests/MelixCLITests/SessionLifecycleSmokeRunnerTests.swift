import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

private let liveRuntimeSmokeTestsEnabled =
    ProcessInfo.processInfo.environment["MELIX_RUN_LIVE_RUNTIME_TESTS"] == "1"

@Suite("Session Lifecycle Smoke")
struct SessionLifecycleSmokeRunnerTests {
    @Test("runner records pause sleep wake and restart evidence")
    func runnerRecordsLifecycleEvidence() async throws {
        let metricsPath = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        try writeLifecycleMetrics(to: metricsPath)
        defer { try? FileManager.default.removeItem(at: metricsPath) }

        let client = LifecycleSmokeStubClient()
        let runner = SessionLifecycleSmokeRunner(
            client: client,
            metricsPath: metricsPath.path,
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        )

        let report = try await runner.run()

        #expect(report.ok)
        #expect(report.providerID == MelixProviderDefaults.defaultProviderID)
        #expect(report.modelID == "melix-dev-text")
        #expect(report.metrics["control_plane.server_pause_ms"] == 4.5)
        #expect(report.metrics["lifecycle.pause_ack_ms"] != nil)
        #expect(report.metrics["lifecycle.idle_to_light_sleep_ms"] != nil)
        #expect(report.metrics["lifecycle.wake_to_ready_ms"] != nil)
        #expect(report.metrics["lifecycle.restart_recovery_ms"] != nil)
        #expect(report.scenarios["pause"]?.lifecycle == "paused")
        #expect(report.scenarios["pause"]?.blockedStatus == "unavailable")
        #expect(report.scenarios["idle_sleep"]?.lifecycle == "sleeping")
        #expect(report.scenarios["idle_sleep"]?.powerState == "light_sleep")
        #expect(report.scenarios["wake"]?.lifecycle == "ready")
        #expect(report.scenarios["wake"]?.wakeReason == "request_activity")
        #expect(report.scenarios["wake"]?.assistantText.contains("Echo: wake") == true)
        #expect(report.scenarios["restart"]?.assistantText.contains("Echo: confirm restart recovery") == true)
        #expect(await client.loadedModelIDs == ["melix-dev-text"])
    }

    @Test("runner waits for delayed exported lifecycle metrics")
    func runnerWaitsForDelayedExportedLifecycleMetrics() async throws {
        let metricsPath = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        try writeLifecycleMetrics(to: metricsPath, includeServerStart: false)
        defer { try? FileManager.default.removeItem(at: metricsPath) }

        let exportDelay = LifecycleMetricsExportDelay(path: metricsPath, fillOnSleepCount: 2)
        let report = try await SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(),
            metricsPath: metricsPath.path,
            sleep: { seconds in try await exportDelay.sleep(seconds) }
        ).run()

        #expect(report.metrics["control_plane.server_start_ms"] == 8.5)
        #expect(await exportDelay.sleepCount >= 2)
    }

    @Test("runner fails when the server never reaches sleeping state")
    func runnerFailsWhenServerNeverSleeps() async throws {
        let client = LifecycleSmokeStubClient(allowSleepTransition: false)
        let runner = SessionLifecycleSmokeRunner(
            client: client,
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        )

        await #expect(throws: SessionLifecycleSmokeRunnerError.lifecycleTimeout(expected: "sleeping", observed: "ready")) {
            _ = try await runner.run()
        }
    }

    @Test("runner records reasoned server paused chat rejection as pause evidence")
    func runnerRecordsReasonedServerPausedChatRejection() async throws {
        let report = try await SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(
                pausedChatErrorReason: "chat_unavailable: server_paused: paused for smoke verification"
            ),
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        ).run()

        #expect(report.scenarios["pause"]?.blockedStatus == "unavailable")
        #expect(report.scenarios["wake"]?.assistantText.contains("Echo: wake") == true)
    }

    @Test("runner consumes wake stream while waiting for ready lifecycle")
    func runnerConsumesWakeStreamWhileWaitingForReadyLifecycle() async throws {
        let report = try await SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(deferWakeUntilStreamConsumption: true),
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        ).run()

        #expect(report.scenarios["wake"]?.lifecycle == "ready")
        #expect(report.scenarios["wake"]?.assistantText.contains("Echo: wake") == true)
    }

    @Test("command parser accepts explicit smoke arguments")
    func commandParserAcceptsExplicitArguments() throws {
        let options = try SessionLifecycleSmokeCommand.parseArguments([
            "--provider-id", "provider-9",
            "--model-id", "melix-dev-text-alt",
            "--json",
        ])

        #expect(options == .init(providerID: "provider-9", modelID: "melix-dev-text-alt"))
    }

    @Test("command renderer prints machine-readable payload")
    func commandRendererPrintsMachineReadablePayload() async throws {
        let output = try await SessionLifecycleSmokeCommand.renderReport(
            arguments: ["--json"],
            environment: [:],
            reportBuilder: { providerID, modelID, _ in
                SessionLifecycleSmokeReport(
                    ok: true,
                    providerID: providerID,
                    modelID: modelID,
                    metrics: ["lifecycle.pause_ack_ms": 4.2],
                    scenarios: [
                        "pause": SessionLifecycleSmokeScenario(
                            lifecycle: "paused",
                            powerState: "active",
                            blockedStatus: "unavailable"
                        )
                    ]
                )
            }
        )

        #expect(output.contains("\"ok\" : true"))
        #expect(output.contains("\"lifecycle.pause_ack_ms\" : 4.2"))
        #expect(output.contains("\"blockedStatus\" : \"unavailable\""))
    }

    @Test("command renderer can run through injected client path")
    func commandRendererUsesInjectedClientPath() async throws {
        let client = LifecycleSmokeStubClient(
            chatModes: [
                "wake the server": .heartbeatThenCompletedEmptyAssistant,
                "confirm restart recovery": .tokensOnly,
            ],
            stopConflictCount: 1
        )

        let output = try await SessionLifecycleSmokeCommand.renderReport(
            arguments: ["--json"],
            environment: [:],
            clientBuilder: { _ in client }
        )

        #expect(output.contains("\"wakeReason\" : \"request_activity\""))
        #expect(output.contains("\"assistantText\" : \"Echo: wake the server\""))
        #expect(output.contains("\"assistantText\" : \"Echo: confirm restart recovery\""))
    }

    @Test("command parser rejects missing values and unexpected arguments")
    func commandParserRejectsInvalidArguments() async throws {
        #expect(throws: MelixCLIError.missingValue("--provider-id")) {
            _ = try SessionLifecycleSmokeCommand.parseArguments(["--provider-id"])
        }
        #expect(throws: MelixCLIError.missingValue("--model-id")) {
            _ = try SessionLifecycleSmokeCommand.parseArguments(["--model-id"])
        }
        #expect(throws: MelixCLIError.usage("""
            Usage:
              melix-session-lifecycle-smoke [--provider-id ID] [--model-id MODEL] [--json]
            """)) {
            _ = try SessionLifecycleSmokeCommand.parseArguments(["--unexpected"])
        }
    }

    @Test("runner uses default sleep path and tolerates empty metrics path")
    func runnerUsesDefaultSleepAndEmptyMetricsPath() async throws {
        let report = try await SessionLifecycleSmokeRunner(client: LifecycleSmokeStubClient()).run()

        #expect(report.ok)
        #expect(report.metrics["lifecycle.pause_ack_ms"] != nil)
        #expect(report.metrics["control_plane.server_pause_ms"] == nil)
    }

    @Test("runner reports fallback assistant when completion omits assistant text")
    func runnerFallsBackToTokenStreamWhenCompletedAssistantIsEmpty() async throws {
        let report = try await SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(
                chatModes: ["wake the server": .heartbeatThenCompletedEmptyAssistant]
            ),
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        ).run()

        #expect(report.scenarios["wake"]?.assistantText == "Echo: wake the server")
    }

    @Test("runner throws when the assistant stream never completes")
    func runnerThrowsWhenAssistantStreamNeverCompletes() async throws {
        let runner = SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(
                chatModes: ["confirm restart recovery": .noEvents]
            ),
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        )

        await #expect(throws: SessionLifecycleSmokeRunnerError.chatDidNotComplete) {
            _ = try await runner.run()
        }
    }

    @Test("runner retries stop conflicts and supports token-only fallback completion")
    func runnerRetriesStopConflictsAndCollectsTokenOnlyCompletion() async throws {
        let report = try await SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(
                chatModes: ["confirm restart recovery": .tokensOnly],
                stopConflictCount: 1
            ),
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        ).run()

        #expect(report.scenarios["restart"]?.assistantText == "Echo: confirm restart recovery")
    }

    @Test("runner surfaces stop conflict after retry deadline")
    func runnerSurfacesStopConflictAfterRetryDeadline() async throws {
        let clock = LifecycleSmokeFakeClock()
        let runner = SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(stopConflictCount: 1000),
            now: { clock.now() },
            sleep: { seconds in
                clock.sleep(seconds)
            }
        )

        do {
            _ = try await runner.run()
            Issue.record("Expected stop conflict after retry deadline")
        } catch let error as ControlPlaneXPCClientError {
            guard case .requestFailed(let code, let message) = error else {
                Issue.record("Expected requestFailed conflict, got \(error)")
                return
            }
            #expect(code == "conflict")
            #expect(message == "Cannot stop the provider while requests are active.")
        }
    }

    @Test("runner fails when the requested runtime session is missing")
    func runnerFailsWhenRequestedRuntimeSessionIsMissing() async throws {
        let runner = SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(),
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        )

        await #expect(throws: SessionLifecycleSmokeRunnerError.missingRuntimeSession("provider-missing")) {
            _ = try await runner.run(providerID: "provider-missing")
        }
    }

    @Test("local runtime factory honors explicit repo root and makeClient")
    func localRuntimeFactoryHonorsExplicitRepoRoot() async throws {
        _ = MelixLocalRuntimeFactory.makeContext(
            environment: ["MELIX_REPO_ROOT": "/tmp/melix-explicit-root"]
        )

        let client = MelixLocalRuntimeFactory.makeClient(
            environment: ["MELIX_REPO_ROOT": "/tmp/melix-explicit-root"]
        )
        let handshake = try await client.handshake()
        #expect(!handshake.serverVersion.isEmpty)
    }

    @Test("stub client covers subscription wake and model helpers")
    func stubClientCoversSupplementalOperations() async throws {
        let client = LifecycleSmokeStubClient()

        let stream = await client.subscribe(lastSeenSeq: 9)
        for await _ in stream {
            Issue.record("subscription stream should complete immediately")
        }

        _ = try await client.wakeServerSession(serverSessionID: MelixProviderDefaults.defaultProviderID)
        _ = try await client.updateServerIdlePolicy(
            serverSessionID: MelixProviderDefaults.defaultProviderID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )
        _ = try await client.serverSnapshot()
        _ = try await client.serverSnapshot()
        let resumedSnapshot = try await client.updateServerIdlePolicy(
            serverSessionID: MelixProviderDefaults.defaultProviderID,
            autoSleepEnabled: false,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )
        #expect(resumedSnapshot.providers[0].lifecycleState == .ready)

        _ = try await client.unloadModel(modelID: "melix-dev-text")
        _ = try await client.updateModelSettings(modelID: "melix-dev-text", values: ["temperature": "0.1"])
        _ = try await client.modelInfo(modelID: "melix-dev-text")
        _ = try await client.runModelOperation(
            modelID: "melix-dev-text",
            operation: "noop",
            outputDir: "",
            quantProfileID: "",
            weightQuant: "",
            kvQuant: "",
            ext: [:]
        )
    }

    @Test(
        "local runtime factory powers the default CLI runner snapshot path",
        .enabled(if: liveRuntimeSmokeTestsEnabled)
    )
    func localRuntimeFactoryPowersDefaultCLIRunnerSnapshotPath() async throws {
        let runner = MelixCLIRunner(environment: ProcessInfo.processInfo.environment)
        let output = try await runner.run(.serverSnapshot(.init(json: true)))

        #expect(output.contains("\"server_state\""))
        #expect(output.contains("\"providers\""))
    }
}

private final class LifecycleSmokeFakeClock: @unchecked Sendable {
    private let lock = NSLock()
    private var currentTime: TimeInterval = 0

    func now() -> TimeInterval {
        lock.lock()
        defer {
            lock.unlock()
        }
        return currentTime
    }

    func sleep(_ seconds: TimeInterval) {
        lock.lock()
        currentTime += seconds
        lock.unlock()
    }
}

private enum LifecycleSmokeChatMode: Sendable {
    case standard
    case heartbeatThenCompletedEmptyAssistant
    case tokensOnly
    case noEvents
}

private actor LifecycleMetricsExportDelay {
    private let path: URL
    private let fillOnSleepCount: Int
    private var count = 0

    init(path: URL, fillOnSleepCount: Int) {
        self.path = path
        self.fillOnSleepCount = fillOnSleepCount
    }

    var sleepCount: Int {
        count
    }

    func sleep(_ seconds: TimeInterval) async throws {
        count += 1
        if count == fillOnSleepCount {
            try writeLifecycleMetrics(to: path)
        }
        try await Task.sleep(for: .milliseconds(Int(max(seconds, 0) * 1_000)))
    }
}

private actor LifecycleSmokeStubClient: ControlPlaneXPCClient {
    nonisolated let providerID: String
    private let allowSleepTransition: Bool
    private let chatModes: [String: LifecycleSmokeChatMode]
    private let pausedChatErrorReason: String?
    private let deferWakeUntilStreamConsumption: Bool
    private var snapshot: Melix_Controlplane_V1_ServerSnapshot
    private var sleepPollCount = 0
    private var awakeGraceSnapshots = 0
    private var loadedModelIDsStorage: [String] = []
    private var remainingStopConflicts: Int

    init(
        providerID: String = MelixProviderDefaults.defaultProviderID,
        allowSleepTransition: Bool = true,
        chatModes: [String: LifecycleSmokeChatMode] = [:],
        pausedChatErrorReason: String? = nil,
        deferWakeUntilStreamConsumption: Bool = false,
        stopConflictCount: Int = 0
    ) {
        self.providerID = providerID
        self.allowSleepTransition = allowSleepTransition
        self.chatModes = chatModes
        self.pausedChatErrorReason = pausedChatErrorReason
        self.deferWakeUntilStreamConsumption = deferWakeUntilStreamConsumption
        self.remainingStopConflicts = stopConflictCount
        self.snapshot = LifecycleSmokeStubClient.makeSnapshot(
            providerID: providerID,
            lifecycleState: .ready,
            powerState: .active,
            wakeReason: .initialBoot
        )
    }

    var loadedModelIDs: [String] {
        loadedModelIDsStorage
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return AsyncStream { continuation in
            continuation.finish()
        }
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        let session = snapshot.providers[0]
        if session.lifecycleState == .paused {
            if let pausedChatErrorReason {
                throw ControlPlaneChatExecutionError.unavailableReason(pausedChatErrorReason)
            }
            throw ControlPlaneChatExecutionError.unavailable
        }
        var shouldWakeDuringStream = false
        if session.lifecycleState == .sleeping {
            if deferWakeUntilStreamConsumption {
                shouldWakeDuringStream = true
            } else {
                completeDeferredWake()
            }
        }

        let prompt = request.messages.last?.content ?? "empty"
        let assistantText = "Echo: \(prompt)"
        let mode = chatModes[prompt] ?? .standard
        let events = chatEvents(mode: mode, assistantText: assistantText)
        let streamState = LifecycleSmokeChatStreamState(
            events: events,
            shouldWakeDuringStream: shouldWakeDuringStream,
            client: self
        )
        return ControlPlaneChatExecution(
            requestID: "smoke-chat",
            modelID: request.modelID,
            stream: AsyncThrowingStream {
                await streamState.next()
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        if allowSleepTransition,
           snapshot.providers[0].autoSleepEnabled,
           snapshot.providers[0].lifecycleState == .ready {
            if awakeGraceSnapshots > 0 {
                awakeGraceSnapshots -= 1
                return snapshot
            }
            sleepPollCount += 1
            if sleepPollCount >= 2 {
                mutateSession(lifecycleState: .sleeping, powerState: .lightSleep, wakeReason: .initialBoot)
            }
        }
        return snapshot
    }

    func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = providerID
        mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = providerID
        mutateSession(lifecycleState: .paused, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = providerID
        mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = providerID
        mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = providerID
        if remainingStopConflicts > 0 {
            remainingStopConflicts -= 1
            throw ControlPlaneXPCClientError.requestFailed(
                code: "conflict",
                message: "Cannot stop the provider while requests are active."
            )
        }
        mutateSession(lifecycleState: .stopped, powerState: .stopped, wakeReason: .operatorResume)
        return snapshot
    }

    func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = providerID
        snapshot.providers[0].autoSleepEnabled = autoSleepEnabled
        snapshot.providers[0].lightSleepAfterSeconds = lightSleepAfterSeconds
        snapshot.providers[0].deepSleepAfterSeconds = deepSleepAfterSeconds
        if !autoSleepEnabled, snapshot.providers[0].lifecycleState == .sleeping {
            mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        }
        sleepPollCount = 0
        return snapshot
    }

    fileprivate func completeDeferredWake() {
        mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .requestActivity)
        awakeGraceSnapshots = 2
    }

    private nonisolated func chatEvents(
        mode: LifecycleSmokeChatMode,
        assistantText: String
    ) -> [ControlPlaneChatStreamEvent] {
        switch mode {
        case .standard:
            [
                .tokenDelta(assistantText),
                .completed(finishReason: "stop", assistantText: assistantText, reasoningText: ""),
            ]
        case .heartbeatThenCompletedEmptyAssistant:
            [
                .heartbeat,
                .tokenDelta(assistantText),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        case .tokensOnly:
            [.tokenDelta(assistantText)]
        case .noEvents:
            []
        }
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        loadedModelIDsStorage.append(modelID)
        return makeSmokeModelSummary(modelID: modelID)
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        makeSmokeModelSummary(modelID: modelID)
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = values
        return makeSmokeModelSummary(modelID: modelID)
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        return Melix_Controlplane_V1_ModelInfo()
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = quantProfileID
        _ = weightQuant
        _ = kvQuant
        _ = ext
        return Melix_Controlplane_V1_ModelOperationResult()
    }

    private func mutateSession(
        lifecycleState: Melix_Controlplane_V1_ProviderLifecycleState,
        powerState: Melix_Controlplane_V1_ProviderPowerState,
        wakeReason: Melix_Controlplane_V1_ProviderWakeReason
    ) {
        snapshot.providers[0].lifecycleState = lifecycleState
        snapshot.providers[0].powerState = powerState
        snapshot.providers[0].wakeReason = wakeReason
        switch lifecycleState {
        case .paused, .sleeping:
            snapshot.serverState = .serverDegraded
        case .stopped:
            snapshot.serverState = .serverStopped
        default:
            snapshot.serverState = .serverReady
        }
    }

    private static func makeSnapshot(
        providerID: String,
        lifecycleState: Melix_Controlplane_V1_ProviderLifecycleState,
        powerState: Melix_Controlplane_V1_ProviderPowerState,
        wakeReason: Melix_Controlplane_V1_ProviderWakeReason
    ) -> Melix_Controlplane_V1_ServerSnapshot {
        var session = Melix_Controlplane_V1_ProviderRuntimeState()
        session.providerID = providerID
        session.lifecycleState = lifecycleState
        session.powerState = powerState
        session.wakeReason = wakeReason
        session.lightSleepAfterSeconds = 1
        session.deepSleepAfterSeconds = 5
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.providers = [session]
        return snapshot
    }
}

private actor LifecycleSmokeChatStreamState {
    private let events: [ControlPlaneChatStreamEvent]
    private let client: LifecycleSmokeStubClient
    private var shouldWakeDuringStream: Bool
    private var eventIndex = 0

    init(
        events: [ControlPlaneChatStreamEvent],
        shouldWakeDuringStream: Bool,
        client: LifecycleSmokeStubClient
    ) {
        self.events = events
        self.shouldWakeDuringStream = shouldWakeDuringStream
        self.client = client
    }

    func next() async -> ControlPlaneChatStreamEvent? {
        if shouldWakeDuringStream {
            await client.completeDeferredWake()
            shouldWakeDuringStream = false
        }
        guard eventIndex < events.count else {
            return nil
        }
        let event = events[eventIndex]
        eventIndex += 1
        return event
    }
}

private func makeSmokeModelSummary(modelID: String) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    return model
}

private func writeLifecycleMetrics(to path: URL, includeServerStart: Bool = true) throws {
    var values: [String: Double] = [
        "control_plane.server_pause_ms": 4.5,
        "control_plane.server_resume_ms": 5.5,
        "control_plane.server_wake_ms": 6.5,
        "control_plane.server_stop_ms": 7.5,
        "control_plane.server_idle_policy_ms": 9.5,
    ]
    if includeServerStart {
        values["control_plane.server_start_ms"] = 8.5
    }
    let data = try JSONSerialization.data(
        withJSONObject: ["values": values],
        options: [.sortedKeys]
    )
    try data.write(to: path)
}
