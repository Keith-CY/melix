import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Session Lifecycle Smoke")
struct SessionLifecycleSmokeRunnerTests {
    @Test("runner records pause sleep wake and restart evidence")
    func runnerRecordsLifecycleEvidence() async throws {
        let metricsPath = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        try Data(
            """
            {
              "values": {
                "control_plane.server_pause_ms": 4.5,
                "control_plane.server_resume_ms": 5.5,
                "control_plane.server_wake_ms": 6.5,
                "control_plane.server_stop_ms": 7.5,
                "control_plane.server_start_ms": 8.5,
                "control_plane.server_idle_policy_ms": 9.5
              }
            }
            """.utf8
        ).write(to: metricsPath)
        defer { try? FileManager.default.removeItem(at: metricsPath) }

        let client = LifecycleSmokeStubClient()
        let runner = SessionLifecycleSmokeRunner(
            client: client,
            metricsPath: metricsPath.path,
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        )

        let report = try await runner.run()

        #expect(report.ok)
        #expect(report.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
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

    @Test("command parser accepts explicit smoke arguments")
    func commandParserAcceptsExplicitArguments() throws {
        let options = try SessionLifecycleSmokeCommand.parseArguments([
            "--server-session-id", "server-session-9",
            "--model-id", "melix-dev-text-alt",
            "--json",
        ])

        #expect(options == .init(serverSessionID: "server-session-9", modelID: "melix-dev-text-alt"))
    }

    @Test("command renderer prints machine-readable payload")
    func commandRendererPrintsMachineReadablePayload() async throws {
        let output = try await SessionLifecycleSmokeCommand.renderReport(
            arguments: ["--json"],
            environment: [:],
            reportBuilder: { serverSessionID, modelID, _ in
                SessionLifecycleSmokeReport(
                    ok: true,
                    serverSessionID: serverSessionID,
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
        #expect(throws: MelixCLIError.missingValue("--server-session-id")) {
            _ = try SessionLifecycleSmokeCommand.parseArguments(["--server-session-id"])
        }
        #expect(throws: MelixCLIError.missingValue("--model-id")) {
            _ = try SessionLifecycleSmokeCommand.parseArguments(["--model-id"])
        }
        #expect(throws: MelixCLIError.usage("""
            Usage:
              melix-session-lifecycle-smoke [--server-session-id ID] [--model-id MODEL] [--json]
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

    @Test("runner fails when the requested runtime session is missing")
    func runnerFailsWhenRequestedRuntimeSessionIsMissing() async throws {
        let runner = SessionLifecycleSmokeRunner(
            client: LifecycleSmokeStubClient(),
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        )

        await #expect(throws: SessionLifecycleSmokeRunnerError.missingRuntimeSession("server-session-missing")) {
            _ = try await runner.run(serverSessionID: "server-session-missing")
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

        _ = try await client.wakeServerSession(serverSessionID: ServerSessionRuntimeStore.defaultServerSessionID)
        _ = try await client.updateServerIdlePolicy(
            serverSessionID: ServerSessionRuntimeStore.defaultServerSessionID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )
        _ = try await client.serverSnapshot()
        _ = try await client.serverSnapshot()
        let resumedSnapshot = try await client.updateServerIdlePolicy(
            serverSessionID: ServerSessionRuntimeStore.defaultServerSessionID,
            autoSleepEnabled: false,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 5
        )
        #expect(resumedSnapshot.runtimeSessions[0].lifecycleState == .ready)

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

    @Test("local runtime factory powers the default CLI runner snapshot path")
    func localRuntimeFactoryPowersDefaultCLIRunnerSnapshotPath() async throws {
        let runner = MelixCLIRunner(environment: [:])
        let output = try await runner.run(.serverSnapshot(.init(json: true)))

        #expect(output.contains("\"server_state\""))
        #expect(output.contains("\"runtime_sessions\""))
    }
}

private enum LifecycleSmokeChatMode: Sendable {
    case standard
    case heartbeatThenCompletedEmptyAssistant
    case tokensOnly
    case noEvents
}

private actor LifecycleSmokeStubClient: ControlPlaneXPCClient {
    nonisolated let serverSessionID: String
    private let allowSleepTransition: Bool
    private let chatModes: [String: LifecycleSmokeChatMode]
    private var snapshot: Melix_Controlplane_V1_ServerSnapshot
    private var sleepPollCount = 0
    private var awakeGraceSnapshots = 0
    private var loadedModelIDsStorage: [String] = []
    private var remainingStopConflicts: Int

    init(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID,
        allowSleepTransition: Bool = true,
        chatModes: [String: LifecycleSmokeChatMode] = [:],
        stopConflictCount: Int = 0
    ) {
        self.serverSessionID = serverSessionID
        self.allowSleepTransition = allowSleepTransition
        self.chatModes = chatModes
        self.remainingStopConflicts = stopConflictCount
        self.snapshot = LifecycleSmokeStubClient.makeSnapshot(
            serverSessionID: serverSessionID,
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
        let session = snapshot.runtimeSessions[0]
        if session.lifecycleState == .paused {
            throw ControlPlaneChatExecutionError.unavailable
        }
        if session.lifecycleState == .sleeping {
            mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .requestActivity)
            awakeGraceSnapshots = 2
        }

        let prompt = request.messages.last?.content ?? "empty"
        let assistantText = "Echo: \(prompt)"
        let mode = chatModes[prompt] ?? .standard
        return ControlPlaneChatExecution(
            requestID: "smoke-chat",
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                switch mode {
                case .standard:
                    continuation.yield(.tokenDelta(assistantText))
                    continuation.yield(.completed(finishReason: "stop", assistantText: assistantText, reasoningText: ""))
                case .heartbeatThenCompletedEmptyAssistant:
                    continuation.yield(.heartbeat)
                    continuation.yield(.tokenDelta(assistantText))
                    continuation.yield(.completed(finishReason: "stop", assistantText: "", reasoningText: ""))
                case .tokensOnly:
                    continuation.yield(.tokenDelta(assistantText))
                case .noEvents:
                    break
                }
                continuation.finish()
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        if allowSleepTransition,
           snapshot.runtimeSessions[0].autoSleepEnabled,
           snapshot.runtimeSessions[0].lifecycleState == .ready {
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
        _ = serverSessionID
        mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        mutateSession(lifecycleState: .paused, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        return snapshot
    }

    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        if remainingStopConflicts > 0 {
            remainingStopConflicts -= 1
            throw ControlPlaneXPCClientError.requestFailed(
                code: "conflict",
                message: "Cannot stop the server session while requests are active."
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
        _ = serverSessionID
        snapshot.runtimeSessions[0].autoSleepEnabled = autoSleepEnabled
        snapshot.runtimeSessions[0].lightSleepAfterSeconds = lightSleepAfterSeconds
        snapshot.runtimeSessions[0].deepSleepAfterSeconds = deepSleepAfterSeconds
        if !autoSleepEnabled, snapshot.runtimeSessions[0].lifecycleState == .sleeping {
            mutateSession(lifecycleState: .ready, powerState: .active, wakeReason: .operatorResume)
        }
        sleepPollCount = 0
        return snapshot
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
        lifecycleState: Melix_Controlplane_V1_ServerSessionLifecycleState,
        powerState: Melix_Controlplane_V1_ServerSessionPowerState,
        wakeReason: Melix_Controlplane_V1_ServerWakeReason
    ) {
        snapshot.runtimeSessions[0].lifecycleState = lifecycleState
        snapshot.runtimeSessions[0].powerState = powerState
        snapshot.runtimeSessions[0].wakeReason = wakeReason
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
        serverSessionID: String,
        lifecycleState: Melix_Controlplane_V1_ServerSessionLifecycleState,
        powerState: Melix_Controlplane_V1_ServerSessionPowerState,
        wakeReason: Melix_Controlplane_V1_ServerWakeReason
    ) -> Melix_Controlplane_V1_ServerSnapshot {
        var session = Melix_Controlplane_V1_ServerSessionRuntimeState()
        session.serverSessionID = serverSessionID
        session.lifecycleState = lifecycleState
        session.powerState = powerState
        session.wakeReason = wakeReason
        session.lightSleepAfterSeconds = 1
        session.deepSleepAfterSeconds = 5
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.runtimeSessions = [session]
        return snapshot
    }
}

private func makeSmokeModelSummary(modelID: String) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    return model
}
