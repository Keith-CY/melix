import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Control Plane Service")
struct ControlPlaneServiceTests {
    @Test("handshake returns a typed snapshot")
    func handshakeReturnsTypedSnapshot() async throws {
        let service = ControlPlaneService()

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-1"

        let response = try await service.handshake(request)

        #expect(response.protocolVersion == "melix.controlplane.v1")
        #expect(!response.serverVersion.isEmpty)
        #expect(!response.daemonInstanceID.isEmpty)
        #expect(response.snapshot.serverState == .serverReady)
        #expect(response.features.contains("cache-metadata"))
        #expect(response.features.contains("session-graph"))
    }

    @Test("execute handles server.get_snapshot")
    func executeHandlesServerSnapshot() async throws {
        let service = ControlPlaneService()
        let request = makeServerSnapshotRequest()

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.requestID == request.requestID)
        #expect(response.commandType == request.commandType)
        #expect(response.server.snapshot.serverState == .serverReady)
    }

    @Test("execute handles model.list")
    func executeHandlesModelList() async throws {
        let service = ControlPlaneService()
        let request = makeListModelsRequest()

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.model.models.count == 1)
        #expect(response.model.models.first?.modelID == "melix-dev-text")
        #expect(response.model.models.first?.state == .modelDiscovered)
    }

    @Test("execute handles model.load and emits a state change event")
    func executeHandlesModelLoad() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return try #require(await iterator.next())
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let event = try await eventTask.value

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.state == .modelWarm)
        #expect(response.model.models.first?.state == .modelWarm)
        #expect(event.eventType == "model.state_changed")
        #expect(event.modelState.modelID == "melix-dev-text")
        #expect(event.modelState.state == .modelWarm)
    }

    @Test("execute handles model.unload and emits a state change event")
    func executeHandlesModelUnload() async throws {
        let service = ControlPlaneService()
        _ = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))

        let subscription = await service.subscribe()
        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return try #require(await iterator.next())
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let event = try await eventTask.value

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.state == .modelUnloaded)
        #expect(response.model.models.first?.state == .modelUnloaded)
        #expect(event.modelState.modelID == "melix-dev-text")
        #expect(event.modelState.state == .modelUnloaded)
    }

    @Test("execute returns not found for unknown model operations")
    func executeReturnsNotFoundForUnknownModelOperations() async throws {
        let service = ControlPlaneService()

        let loadResponse = try await service.execute(makeLoadModelRequest(modelID: "missing-model"))
        let unloadResponse = try await service.execute(makeUnloadModelRequest(modelID: "missing-model"))

        #expect(!loadResponse.ok)
        #expect(loadResponse.error.code == "not_found")
        #expect(!unloadResponse.ok)
        #expect(unloadResponse.error.code == "not_found")
    }

    @Test("execute handles ops.get_metrics")
    func executeHandlesOpsMetrics() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makeMetricsRequest())

        #expect(response.ok)
        #expect(response.ops.metrics.values["requests.inflight"] == 0)
        #expect(response.ops.metrics.values["workers.connected"] == 0)
    }

    @Test("execute handles cache.get_snapshot with typed cache metadata")
    func executeHandlesCacheSnapshot() async throws {
        let cacheStore = CacheMetadataStore(snapshot: makeCacheSnapshot())
        let service = ControlPlaneService(cacheMetadataStore: cacheStore)

        let response = try await service.execute(makeCacheSnapshotRequest())

        #expect(response.ok)
        #expect(response.cache.summary.blockCount == 4)
        #expect(response.cache.summary.compressionRatio == 2.5)
        #expect(response.cache.snapshot.scopes.count == 1)
        #expect(response.cache.snapshot.hotPrefixes.count == 1)
        #expect(response.cache.snapshot.snapshots.first?.snapshotID == "snap-1")
    }

    @Test("execute handles session.get_state with typed branch metadata")
    func executeHandlesSessionState() async throws {
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let response = try await service.execute(makeSessionStateRequest(sessionID: "session-1"))

        #expect(response.ok)
        #expect(response.session.session.sessionID == "session-1")
        #expect(response.session.session.activeBranchID == "branch-main")
        #expect(response.session.session.branches.count == 2)
        #expect(response.session.session.availableSnapshots.first?.snapshotID == "snap-1")
        #expect(response.session.session.branches.first?.headCacheKey.scope.modelID == "melix-dev-text")
    }

    @Test("execute returns not found for unknown session state")
    func executeReturnsNotFoundForUnknownSessionState() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makeSessionStateRequest(sessionID: "missing-session"))

        #expect(!response.ok)
        #expect(response.error.code == "not_found")
    }

    @Test("execute handles session lifecycle mutations and publishes typed state events")
    func executeHandlesSessionLifecycleMutations() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()

        let created = try await service.execute(makeSessionCreateRequest())
        #expect(created.ok)
        let sessionID = created.session.session.sessionID
        #expect(!sessionID.isEmpty)
        #expect(created.session.session.activeBranchID == "branch-main")

        let branched = try await service.execute(
            makeCreateBranchRequest(sessionID: sessionID, parentBranchID: "branch-main")
        )
        #expect(branched.ok)
        #expect(branched.session.session.branches.count == 2)
        let derivedBranchID = branched.session.session.activeBranchID
        #expect(!derivedBranchID.isEmpty)
        #expect(derivedBranchID != "branch-main")

        var iterator = subscription.stream.makeAsyncIterator()
        let firstEvent = await iterator.next()
        let secondEvent = await iterator.next()
        #expect(firstEvent?.eventType == "session.state_changed")
        #expect(firstEvent?.source == "session_graph")
        #expect(secondEvent?.eventType == "session.state_changed")
        #expect(secondEvent?.source == "session_graph")
        #expect(secondEvent?.sessionState.state.activeBranchID == derivedBranchID)
    }

    @Test("execute handles tool registration, resume, and close for sessions")
    func executeHandlesToolResumeAndCloseForSessions() async throws {
        let sessionStore = SessionGraphStore(
            sessions: [makeSessionState()],
            nowUnixMs: { 5_000 }
        )
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let registered = try await service.execute(
            makeRegisterToolResultRequest(
                sessionID: "session-1",
                branchID: "branch-alt",
                toolCallID: "tool-99"
            )
        )
        #expect(registered.ok)
        #expect(registered.session.session.activeBranchID == "branch-alt")
        #expect(registered.session.session.latestToolCallID == "tool-99")

        let resumed = try await service.execute(
            makeResumeAfterToolRequest(
                sessionID: "session-1",
                branchID: "branch-alt",
                snapshotID: "snap-tool"
            )
        )
        #expect(resumed.ok)
        #expect(resumed.session.session.latestSnapshotID == "snap-tool")
        #expect(resumed.session.session.branches.last?.resumeSnapshotID == "snap-tool")

        let closed = try await service.execute(makeCloseSessionRequest(sessionID: "session-1"))
        #expect(closed.ok)
        #expect(closed.session.session.sessionID == "session-1")

        let missing = try await service.execute(makeSessionStateRequest(sessionID: "session-1"))
        #expect(!missing.ok)
        #expect(missing.error.code == "not_found")
    }

    @Test("execute returns not found for invalid session mutation requests")
    func executeReturnsNotFoundForInvalidSessionMutations() async throws {
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let missingSession = try await service.execute(
            makeCreateBranchRequest(sessionID: "missing-session", parentBranchID: "branch-main")
        )
        let missingBranch = try await service.execute(
            makeRegisterToolResultRequest(
                sessionID: "session-1",
                branchID: "branch-missing",
                toolCallID: "tool-404"
            )
        )
        let missingResumeBranch = try await service.execute(
            makeResumeAfterToolRequest(
                sessionID: "session-1",
                branchID: "branch-missing",
                snapshotID: "snap-404"
            )
        )
        let missingClose = try await service.execute(makeCloseSessionRequest(sessionID: "missing-session"))

        #expect(!missingSession.ok)
        #expect(missingSession.error.code == "not_found")
        #expect(!missingBranch.ok)
        #expect(missingBranch.error.code == "not_found")
        #expect(!missingResumeBranch.ok)
        #expect(missingResumeBranch.error.code == "not_found")
        #expect(!missingClose.ok)
        #expect(missingClose.error.code == "not_found")
    }

    @Test("session mutation responses preserve correlation metadata")
    func sessionMutationResponsesPreserveCorrelationMetadata() async throws {
        let service = ControlPlaneService()
        var request = makeSessionCreateRequest()
        request.correlationID = "corr-session"
        request.causationID = "cause-session"

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.requestID == request.requestID)
        #expect(response.commandType == request.commandType)
        #expect(response.correlationID == "corr-session")
        #expect(response.causationID == "cause-session")
    }

    @Test("handshake includes live scheduler queue summary")
    func handshakeIncludesLiveSchedulerQueueSummary() async throws {
        let schedulerReadModel = SchedulerReadModel()
        _ = await schedulerReadModel.recordAdmitted(
            requestID: "req-live-queue",
            laneHint: "text.decode.interactive",
            priority: 100,
            workerID: "swift-text-worker",
            admissionLatencyMs: 3
        )
        let service = ControlPlaneService(schedulerReadModel: schedulerReadModel)

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-live-queue"

        let response = try await service.handshake(request)
        let interactiveLane = response.snapshot.queues.lanes.first { lane in
            lane.laneID == "text.decode.interactive"
        }

        #expect(response.snapshot.queues.activeRequests == 1)
        #expect(response.snapshot.queues.admittedRequests == 1)
        #expect(response.snapshot.queues.admissionLatencyMs == 3)
        #expect(response.snapshot.queues.backpressure == 1)
        #expect(interactiveLane?.activeRequests == 1)
        #expect(interactiveLane?.backpressure == 1)
    }

    @Test("handshake includes cache summary and session summaries")
    func handshakeIncludesCacheAndSessionSummaries() async throws {
        let cacheStore = CacheMetadataStore(snapshot: makeCacheSnapshot())
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(
            cacheMetadataStore: cacheStore,
            sessionGraphStore: sessionStore
        )

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-session-cache"

        let response = try await service.handshake(request)

        #expect(response.snapshot.cache.blockCount == 4)
        #expect(response.snapshot.cache.hotPrefixes.count == 1)
        #expect(response.snapshot.sessions.count == 1)
        #expect(response.snapshot.sessions.first?.sessionID == "session-1")
        #expect(response.snapshot.sessions.first?.branchCount == 2)
    }

    @Test("execute returns unimplemented for unsupported command families")
    func executeReturnsUnimplementedForUnsupportedCommandFamilies() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makePresetRequest())

        #expect(!response.ok)
        #expect(response.requestID == "req-preset-list")
        #expect(response.commandType == "preset.list")
        #expect(response.error.code == "unimplemented")
    }

    @Test("execute returns unimplemented for unsupported server, model, and ops variants")
    func executeReturnsUnimplementedForUnsupportedVariants() async throws {
        let service = ControlPlaneService()

        let serverResponse = try await service.execute(makeServerShutdownRequest())
        let modelResponse = try await service.execute(makeModelPinRequest())
        let opsResponse = try await service.execute(makeOpsTraceRequest())

        #expect(!serverResponse.ok)
        #expect(serverResponse.error.code == "unimplemented")
        #expect(!modelResponse.ok)
        #expect(modelResponse.error.code == "unimplemented")
        #expect(!opsResponse.ok)
        #expect(opsResponse.error.code == "unimplemented")
    }

    @Test("unsubscribe closes the subscription stream")
    func unsubscribeClosesSubscriptionStream() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()
        await service.unsubscribe(subscription.subscriptionID)

        var iterator = subscription.stream.makeAsyncIterator()
        let next = await iterator.next()

        #expect(next == nil)
    }

    private func makeServerSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-snapshot"
        request.commandType = "server.get_snapshot"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.getSnapshot = Melix_Controlplane_V1_GetServerSnapshot()
        return request
    }

    private func makeListModelsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-list"
        request.commandType = "model.list"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.list = Melix_Controlplane_V1_ListModels()
        return request
    }

    private func makeLoadModelRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-load-\(modelID)"
        request.commandType = "model.load"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.load = Melix_Controlplane_V1_LoadModel()
        request.model.load.modelID = modelID
        return request
    }

    private func makeUnloadModelRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-unload-\(modelID)"
        request.commandType = "model.unload"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.unload = Melix_Controlplane_V1_UnloadModel()
        request.model.unload.modelID = modelID
        return request
    }

    private func makeMetricsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-metrics"
        request.commandType = "ops.get_metrics"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.getMetrics = Melix_Controlplane_V1_GetMetricsSnapshot()
        return request
    }

    private func makeCacheSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-cache-snapshot"
        request.commandType = "cache.get_snapshot"
        request.cache = Melix_Controlplane_V1_CacheCommand()
        request.cache.getSnapshot = Melix_Controlplane_V1_GetCacheSnapshot()
        return request
    }

    private func makeSessionStateRequest(sessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-state-\(sessionID)"
        request.commandType = "session.get_state"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.getState = Melix_Controlplane_V1_GetSessionState()
        request.session.getState.sessionID = sessionID
        return request
    }

    private func makeSessionCreateRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-create"
        request.commandType = "session.create"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.createSession = Melix_Controlplane_V1_CreateSession()
        return request
    }

    private func makeCreateBranchRequest(
        sessionID: String,
        parentBranchID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-branch-\(sessionID)"
        request.commandType = "session.create_branch"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.createBranch = Melix_Controlplane_V1_CreateBranch()
        request.session.createBranch.sessionID = sessionID
        request.session.createBranch.parentBranchID = parentBranchID
        return request
    }

    private func makeRegisterToolResultRequest(
        sessionID: String,
        branchID: String,
        toolCallID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-tool-\(toolCallID)"
        request.commandType = "session.register_tool_result"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.registerToolResult = Melix_Controlplane_V1_RegisterToolResult()
        request.session.registerToolResult.sessionID = sessionID
        request.session.registerToolResult.branchID = branchID
        request.session.registerToolResult.toolCallID = toolCallID
        return request
    }

    private func makeResumeAfterToolRequest(
        sessionID: String,
        branchID: String,
        snapshotID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-resume-\(snapshotID)"
        request.commandType = "session.resume_after_tool"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.resumeAfterTool = Melix_Controlplane_V1_ResumeAfterTool()
        request.session.resumeAfterTool.sessionID = sessionID
        request.session.resumeAfterTool.branchID = branchID
        request.session.resumeAfterTool.snapshotID = snapshotID
        return request
    }

    private func makeCloseSessionRequest(sessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-close-\(sessionID)"
        request.commandType = "session.close"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.closeSession = Melix_Controlplane_V1_CloseSession()
        request.session.closeSession.sessionID = sessionID
        return request
    }

    private func makePresetRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-preset-list"
        request.commandType = "preset.list"
        request.preset = Melix_Controlplane_V1_PresetCommand()
        request.preset.list = Melix_Controlplane_V1_ListPresets()
        return request
    }

    private func makeServerShutdownRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-stop"
        request.commandType = "server.stop"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.stop = Melix_Controlplane_V1_StopServer()
        return request
    }

    private func makeModelPinRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-pin"
        request.commandType = "model.pin"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.pin = Melix_Controlplane_V1_PinModel()
        request.model.pin.modelID = "melix-dev-text"
        return request
    }

    private func makeOpsTraceRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-tail-logs"
        request.commandType = "ops.tail_logs"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.tailLogs = Melix_Controlplane_V1_TailLogs()
        return request
    }

    private func makeCacheSnapshot() -> Melix_Controlplane_V1_CacheSnapshot {
        var summary = Melix_Controlplane_V1_CacheSummary()
        summary.l1Bytes = 2048
        summary.l2Bytes = 8192
        summary.blockCount = 4
        summary.checkpointCount = 1
        summary.compressionRatio = 2.5
        summary.l2RestoreHitRate = 0.5

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA, 0xBB])
        cacheKey.scope = Melix_Controlplane_V1_CacheScopeKey()
        cacheKey.scope.modelID = "melix-dev-text"
        cacheKey.scope.revision = "main"
        cacheKey.scope.tokenizerHash = "tok-1"
        cacheKey.scope.quantProfileID = "q4"

        var prefix = Melix_Controlplane_V1_PrefixRef()
        prefix.prefixID = "prefix-1"
        prefix.cacheKey = cacheKey
        prefix.tokenLength = 64
        prefix.tier = "l1"
        prefix.pinned = true

        var block = Melix_Controlplane_V1_CacheBlockRef()
        block.blockID = "block-1"
        block.tokenLength = 64
        block.bytes = 2048

        var snapshotRef = Melix_Controlplane_V1_SnapshotRef()
        snapshotRef.snapshotID = "snap-1"
        snapshotRef.tokenBoundary = 64
        snapshotRef.requestID = "req-main"
        snapshotRef.sessionID = "session-1"
        snapshotRef.branchID = "branch-main"
        snapshotRef.checkpointID = "ckpt-main"

        var scope = Melix_Controlplane_V1_CacheScopeSummary()
        scope.scopeID = "scope-1"
        scope.scope = cacheKey.scope
        scope.l1Bytes = 2048
        scope.l2Bytes = 8192
        scope.blockCount = 4
        scope.prefixCount = 1
        scope.snapshotCount = 1
        scope.hotBlocks = [block]
        scope.recentSnapshots = [snapshotRef]

        summary.hotKeys = [cacheKey]
        summary.hotPrefixes = [prefix]
        summary.recentSnapshots = [snapshotRef]

        var snapshot = Melix_Controlplane_V1_CacheSnapshot()
        snapshot.summary = summary
        snapshot.scopes = [scope]
        snapshot.pinnedPrefixes = [prefix]
        snapshot.hotPrefixes = [prefix]
        snapshot.snapshots = [snapshotRef]
        return snapshot
    }

    private func makeSessionState() -> Melix_Controlplane_V1_SessionState {
        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA])
        cacheKey.scope = Melix_Controlplane_V1_CacheScopeKey()
        cacheKey.scope.modelID = "melix-dev-text"
        cacheKey.scope.revision = "main"

        var branchMain = Melix_Controlplane_V1_BranchState()
        branchMain.branchID = "branch-main"
        branchMain.parentBranchID = ""
        branchMain.headRequestID = "req-main"
        branchMain.headCheckpointID = "ckpt-main"
        branchMain.resumeSnapshotID = "snap-1"
        branchMain.lastToolCallID = "tool-1"
        branchMain.label = "main"
        branchMain.createdAtUnixMs = 1000
        branchMain.updatedAtUnixMs = 2000
        branchMain.headCacheKey = cacheKey

        var branchAlt = Melix_Controlplane_V1_BranchState()
        branchAlt.branchID = "branch-alt"
        branchAlt.parentBranchID = "branch-main"
        branchAlt.headRequestID = "req-alt"
        branchAlt.headCheckpointID = "ckpt-alt"
        branchAlt.resumeSnapshotID = "snap-2"
        branchAlt.lastToolCallID = "tool-2"
        branchAlt.label = "alternate"
        branchAlt.createdAtUnixMs = 3000
        branchAlt.updatedAtUnixMs = 4000
        branchAlt.headCacheKey = cacheKey

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-1"
        snapshot.tokenBoundary = 64
        snapshot.requestID = "req-main"
        snapshot.sessionID = "session-1"
        snapshot.branchID = "branch-main"
        snapshot.checkpointID = "ckpt-main"

        var session = Melix_Controlplane_V1_SessionState()
        session.sessionID = "session-1"
        session.branches = [branchMain, branchAlt]
        session.activeBranchID = "branch-main"
        session.latestRequestID = "req-main"
        session.latestCheckpointID = "ckpt-main"
        session.latestSnapshotID = "snap-1"
        session.createdAtUnixMs = 1000
        session.updatedAtUnixMs = 4000
        session.latestToolCallID = "tool-2"
        session.availableSnapshots = [snapshot]
        return session
    }
}
