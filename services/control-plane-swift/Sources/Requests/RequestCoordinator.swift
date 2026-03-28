import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public enum RequestCoordinatorError: Error, Equatable {
    case requestAlreadyActive
    case workerUnavailable
}

public struct CoordinatedChatExecution: Sendable {
    public let requestID: String
    public let modelID: String
    public let stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>

    public init(
        requestID: String,
        modelID: String,
        stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.stream = stream
    }
}

public actor RequestCoordinator {
    private let workerRegistry: WorkerRegistry
    private let abortRegistry: AbortRegistry
    private let admissionGate: AdmissionGate
    private let schedulerReadModel: SchedulerReadModel
    private let metricsStore: MetricsStore
    private let sessionGraphStore: SessionGraphStore?
    private let now: @Sendable () -> Date
    private var activeWorkerClients: [String: any WorkerClient]

    public init(
        workerRegistry: WorkerRegistry,
        abortRegistry: AbortRegistry = AbortRegistry(),
        admissionGate: AdmissionGate = AdmissionGate(),
        schedulerReadModel: SchedulerReadModel = SchedulerReadModel(),
        metricsStore: MetricsStore = MetricsStore(),
        sessionGraphStore: SessionGraphStore? = nil,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.workerRegistry = workerRegistry
        self.abortRegistry = abortRegistry
        self.admissionGate = admissionGate
        self.schedulerReadModel = schedulerReadModel
        self.metricsStore = metricsStore
        self.sessionGraphStore = sessionGraphStore
        self.now = now
        self.activeWorkerClients = [:]
    }

    public func startChatCompletion(
        _ translatedRequest: TranslatedChatRequest
    ) async throws -> CoordinatedChatExecution {
        let request = await resolvedRecoveryRequest(translatedRequest)
        await hydrateSessionGraph(for: request.workerRequest.execution.id)
        let lane = request.workerRequest.execution.scheduling.lane
        let priority = request.workerRequest.execution.scheduling.priority
        guard await abortRegistry.begin(requestID: request.requestID) else {
            _ = await schedulerReadModel.recordRejected(
                requestID: request.requestID,
                laneHint: lane,
                priority: priority
            )
            throw RequestCoordinatorError.requestAlreadyActive
        }
        let initialQueuePosition = await admissionGate.nextQueuePosition()
        await schedulerReadModel.recordQueued(
            requestID: request.requestID,
            laneHint: lane,
            priority: priority,
            queuePosition: initialQueuePosition
        )
        let routeStartedAt = now()
        guard let workerClient = await workerRegistry.client(forModelID: request.modelID) else {
            await abortRegistry.finish(requestID: request.requestID)
            _ = await schedulerReadModel.recordRejected(
                requestID: request.requestID,
                laneHint: lane,
                priority: priority
            )
            throw RequestCoordinatorError.workerUnavailable
        }
        await metricsStore.set(
            now().timeIntervalSince(routeStartedAt) * 1000,
            forKey: "control_plane.worker_route_ms"
        )
        if !(await abortRegistry.contains(request.requestID)) {
            return await makeCancelledExecution(requestID: request.requestID, modelID: request.modelID)
        }

        let connectStartedAt = now()
        guard await workerClient.canDispatchRequests() else {
            await abortRegistry.finish(requestID: request.requestID)
            _ = await schedulerReadModel.recordRejected(
                requestID: request.requestID,
                laneHint: lane,
                priority: priority
            )
            throw RequestCoordinatorError.workerUnavailable
        }
        await metricsStore.set(
            now().timeIntervalSince(connectStartedAt) * 1000,
            forKey: "control_plane.worker_connect_ms"
        )
        if !(await abortRegistry.contains(request.requestID)) {
            return await makeCancelledExecution(requestID: request.requestID, modelID: request.modelID)
        }

        switch await admissionGate.acquire(requestID: request.requestID) {
        case .cancelled:
            await finishRequestTracking(requestID: request.requestID, phase: .requestAborted)
            return await makeCancelledExecution(requestID: request.requestID, modelID: request.modelID)
        case .admitted:
            break
        }

        let dispatchStartedAt = now()
        _ = await schedulerReadModel.recordAdmitted(
            requestID: request.requestID,
            laneHint: lane,
            priority: priority,
            admissionLatencyMs: now().timeIntervalSince(routeStartedAt) * 1000
        )
        if !(await abortRegistry.contains(request.requestID)) {
            await finishRequestTracking(requestID: request.requestID, phase: .requestAborted)
            return await makeCancelledExecution(requestID: request.requestID, modelID: request.modelID)
        }

        do {
            let upstream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
            if let phaseAwareClient = workerClient as? any PhaseAwareWorkerClientProtocol,
               shouldUsePhaseAwareExecution(for: request.workerRequest) {
                upstream = makePhaseAwareUpstream(
                    client: phaseAwareClient,
                    request: request.workerRequest
                )
            } else {
                upstream = try await workerClient.generate(request: request.workerRequest)
            }
            if !(await abortRegistry.contains(request.requestID)) {
                _ = try? await workerClient.abort(requestID: request.requestID)
                await finishRequestTracking(requestID: request.requestID, phase: .requestAborted)
                return await makeCancelledExecution(requestID: request.requestID, modelID: request.modelID)
            }
            await metricsStore.increment("requests.inflight")
            activeWorkerClients[request.requestID] = workerClient
            let metricsStore = self.metricsStore
            let now = self.now
            let requestID = request.requestID
            let modelID = request.modelID

            let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
                let task = Task {
                    var firstDeltaRecorded = false
                    var eventCount = 0.0

                    do {
                        for try await event in upstream {
                            await self.recordPhaseObservability(
                                requestID: requestID,
                                fallbackLane: lane,
                                requestIdentity: request.workerRequest.execution.id,
                                event: event
                            )
                            if !firstDeltaRecorded, case .tokenDelta = event.payload {
                                firstDeltaRecorded = true
                                await metricsStore.set(
                                    now().timeIntervalSince(dispatchStartedAt) * 1000,
                                    forKey: "http.ttfd_ms"
                                )
                            }
                            eventCount += 1
                            await metricsStore.set(eventCount, forKey: "http.stream_event_count")
                            continuation.yield(event)
                        }
                        await metricsStore.decrement("requests.inflight")
                        let terminalPhase = await self.terminalPhase(
                            requestID: requestID,
                            fallback: .requestCompleted
                        )
                        await self.finishRequestTracking(requestID: requestID, phase: terminalPhase)
                        continuation.finish()
                    } catch {
                        await metricsStore.decrement("requests.inflight")
                        await self.finishRequestTracking(requestID: requestID, phase: .requestFailed)
                        continuation.finish(throwing: error)
                    }
                }

                continuation.onTermination = { _ in
                    task.cancel()
                    Task {
                        await metricsStore.decrement("requests.inflight")
                        await self.finishRequestTracking(requestID: requestID)
                    }
                }
            }

            return CoordinatedChatExecution(requestID: requestID, modelID: modelID, stream: stream)
        } catch let error as WorkerClientError where error == .unavailable {
            await metricsStore.decrement("requests.inflight")
            await finishRequestTracking(requestID: request.requestID, phase: .requestFailed)
            throw RequestCoordinatorError.workerUnavailable
        } catch {
            await metricsStore.decrement("requests.inflight")
            await finishRequestTracking(requestID: request.requestID, phase: .requestFailed)
            throw error
        }
    }

    public func cancel(requestID: String) async throws -> Bool {
        guard await abortRegistry.contains(requestID) else {
            return false
        }
        let phase = await schedulerReadModel.progressSnapshot(for: requestID)?.phase ?? .requestQueued
        let startedAt = now()
        guard await abortRegistry.abort(requestID) else {
            return false
        }
        if let workerClient = activeWorkerClients[requestID] {
            let aborted = try await workerClient.abort(requestID: requestID)
            if aborted {
                await recordAbortMetrics(phase: phase, startedAt: startedAt)
                await finishRequestTracking(requestID: requestID, phase: .requestAborted)
            }
            return aborted
        }

        await recordAbortMetrics(phase: phase, startedAt: startedAt)
        await finishRequestTracking(requestID: requestID, phase: .requestAborted)
        return true
    }

    private func finishRequestTracking(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase? = nil
    ) async {
        await admissionGate.release(requestID: requestID)
        await abortRegistry.finish(requestID: requestID)
        activeWorkerClients.removeValue(forKey: requestID)
        if let phase {
            await schedulerReadModel.recordTerminalState(requestID: requestID, phase: phase)
        }
    }

    private func recordPhaseObservability(
        requestID: String,
        fallbackLane: String,
        requestIdentity: Melix_Worker_V1_RequestIdentity,
        event: Melix_Worker_V1_ExecuteEvent
    ) async {
        switch event.payload {
        case .prefillStarted, .prefillProgress:
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestPrefilling,
                laneHint: event.lane.isEmpty ? "text.prefill.hot" : event.lane,
                workerID: "swift-text-worker",
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: "swift-text-worker"
            )
        case .decodeStarted(let decodeStarted):
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestDecoding,
                laneHint: event.lane.isEmpty ? fallbackLane : event.lane,
                workerID: "swift-text-worker",
                decodeHandle: decodeStarted.decodeHandle,
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: "swift-text-worker"
            )
        case .tokenDelta, .reasoningDelta, .toolCallDelta, .usageDelta:
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestDecoding,
                laneHint: event.lane.isEmpty ? fallbackLane : event.lane,
                workerID: "swift-text-worker",
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: "swift-text-worker"
            )
                if case .toolCallDelta(let toolCallDelta) = event.payload {
                    await hydrateToolResult(
                        requestIdentity: requestIdentity,
                        toolCallID: toolCallDelta.callID
                    )
                }
        case .cacheDecision(let cacheDecision):
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestDecoding,
                laneHint: event.lane.isEmpty ? fallbackLane : event.lane,
                workerID: "swift-text-worker",
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: "swift-text-worker"
            )
            if !cacheDecision.restoredSnapshotID.isEmpty {
                await metricsStore.increment("session_graph.restore_snapshot_count")
            }
        case .snapshotCreated(let snapshotCreated):
            await hydrateSnapshotCreated(
                requestIdentity: requestIdentity,
                requestID: requestID,
                snapshotID: snapshotCreated.snapshotID,
                tokenBoundary: snapshotCreated.tokenBoundary
            )
        case .completed:
            if event.phase == .executionAborted {
                await schedulerReadModel.recordPhaseTransition(
                    requestID: requestID,
                    phase: .requestAborted,
                    laneHint: event.lane.isEmpty ? fallbackLane : event.lane,
                    workerID: "swift-text-worker",
                    source: "swift-text-worker"
                )
            }
        default:
            return
        }
    }

    private func hydrateSessionGraph(for identity: Melix_Worker_V1_RequestIdentity) async {
        guard
            let sessionGraphStore,
            !identity.sessionID.isEmpty
        else {
            return
        }

        let startedAt = now()
        _ = await sessionGraphStore.recordRequestStart(
            sessionID: identity.sessionID,
            branchID: identity.branchID,
            requestID: identity.requestID
        )
        await metricsStore.set(
            now().timeIntervalSince(startedAt) * 1000,
            forKey: "session_graph.request_hydration_ms"
        )
    }

    private func hydrateToolResult(
        requestIdentity: Melix_Worker_V1_RequestIdentity,
        toolCallID: String
    ) async {
        guard
            let sessionGraphStore,
            !requestIdentity.sessionID.isEmpty,
            !toolCallID.isEmpty
        else {
            return
        }

        _ = try? await sessionGraphStore.registerToolResult(
            sessionID: requestIdentity.sessionID,
            branchID: requestIdentity.branchID,
            toolCallID: toolCallID
        )
    }

    private func hydrateSnapshotCreated(
        requestIdentity: Melix_Worker_V1_RequestIdentity,
        requestID: String,
        snapshotID: String,
        tokenBoundary: UInt32
    ) async {
        guard
            let sessionGraphStore,
            !requestIdentity.sessionID.isEmpty,
            !snapshotID.isEmpty
        else {
            return
        }

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = snapshotID
        snapshot.tokenBoundary = tokenBoundary
        snapshot.requestID = requestID
        snapshot.sessionID = requestIdentity.sessionID
        snapshot.branchID = requestIdentity.branchID

        _ = await sessionGraphStore.recordSnapshotHydration(
            sessionID: requestIdentity.sessionID,
            branchID: requestIdentity.branchID,
            snapshot: snapshot
        )
    }

    private func shouldUsePhaseAwareExecution(
        for request: Melix_Worker_V1_GenerateRequest
    ) -> Bool {
        !request.execution.cacheHints.restoreSnapshotID.isEmpty || request.execution.cacheHints.saveBoundarySnapshot
    }

    private func resolvedRecoveryRequest(
        _ translatedRequest: TranslatedChatRequest
    ) async -> TranslatedChatRequest {
        guard
            let sessionGraphStore,
            !translatedRequest.workerRequest.execution.id.sessionID.isEmpty
        else {
            return translatedRequest
        }

        var workerRequest = translatedRequest.workerRequest
        if workerRequest.execution.id.branchID.isEmpty {
            workerRequest.execution.id.branchID = "branch-main"
        }

        if workerRequest.execution.cacheHints.restoreSnapshotID.isEmpty,
           !workerRequest.execution.id.parentRequestID.isEmpty,
           let session = await sessionGraphStore.state(for: workerRequest.execution.id.sessionID) {
            let requestedBranchID = workerRequest.execution.id.branchID.isEmpty
                ? session.activeBranchID
                : workerRequest.execution.id.branchID
            let branch = session.branches.first(where: { $0.branchID == requestedBranchID })
                ?? session.branches.first(where: { $0.branchID == session.activeBranchID })
            if let branch, !branch.resumeSnapshotID.isEmpty {
                workerRequest.execution.cacheHints.restoreSnapshotID = branch.resumeSnapshotID
            }
        }

        return TranslatedChatRequest(
            requestID: translatedRequest.requestID,
            modelID: translatedRequest.modelID,
            workerRequest: workerRequest,
            stream: translatedRequest.stream
        )
    }

    private func makePhaseAwareUpstream(
        client: any PhaseAwareWorkerClientProtocol,
        request: Melix_Worker_V1_GenerateRequest
    ) -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var nextSeq: UInt64 = 1
                    let prefillRequest = makePrefillRequest(from: request)
                    let prefillResponse = try await client.prefill(request: prefillRequest)
                    guard prefillResponse.ok, !prefillResponse.decodeHandle.isEmpty else {
                        var failureEvent = makePrefillFailureEvent(
                            requestID: request.execution.id.requestID,
                            error: prefillResponse.error
                        )
                        failureEvent.seq = nextSeq
                        continuation.yield(failureEvent)
                        continuation.finish()
                        return
                    }

                    var prefillEvent = makePrefillStartedEvent(request: request, response: prefillResponse)
                    prefillEvent.seq = nextSeq
                    nextSeq += 1
                    continuation.yield(prefillEvent)
                    if !prefillResponse.restoredSnapshotID.isEmpty {
                        var cacheDecisionEvent = makeCacheDecisionEvent(
                            requestID: request.execution.id.requestID,
                            lane: request.execution.scheduling.lane,
                            blockTableID: prefillResponse.blockTableID,
                            restoredSnapshotID: prefillResponse.restoredSnapshotID,
                            accelerationMode: prefillResponse.appliedAcceleration.mode
                        )
                        cacheDecisionEvent.seq = nextSeq
                        nextSeq += 1
                        continuation.yield(cacheDecisionEvent)
                    }

                    let decodeRequest = makeDecodeRequest(
                        from: request,
                        prefillResponse: prefillResponse
                    )
                    let upstream = try await client.decode(request: decodeRequest)
                    for try await upstreamEvent in upstream {
                        var event = upstreamEvent
                        event.seq = nextSeq
                        nextSeq += 1
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private func makePrefillRequest(
        from request: Melix_Worker_V1_GenerateRequest
    ) -> Melix_Worker_V1_PrefillRequest {
        var prefill = Melix_Worker_V1_PrefillRequest()
        prefill.execution = request.execution
        prefill.messages = request.messages
        prefill.returnDecodeHandle = true
        prefill.prefillStepSize = 0
        prefill.resumeHint = request.execution.id.parentRequestID
        return prefill
    }

    private func makeDecodeRequest(
        from request: Melix_Worker_V1_GenerateRequest,
        prefillResponse: Melix_Worker_V1_PrefillResponse
    ) -> Melix_Worker_V1_DecodeRequest {
        var decode = Melix_Worker_V1_DecodeRequest()
        decode.execution = request.execution
        decode.decodeHandle = prefillResponse.decodeHandle
        decode.sampling = request.sampling
        decode.maxOutputTokens = request.sampling.maxOutputTokens
        decode.returnUsage = request.returnUsage
        return decode
    }

    private func makePrefillStartedEvent(
        request: Melix_Worker_V1_GenerateRequest,
        response: Melix_Worker_V1_PrefillResponse
    ) -> Melix_Worker_V1_ExecuteEvent {
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = request.execution.id.requestID
        event.executionKind = "prefill"
        event.seq = 1
        event.phase = response.lifecyclePhase
        event.admissionState = response.admissionState
        event.lane = "text.prefill.hot"
        event.accelerationMode = response.appliedAcceleration.mode

        var payload = Melix_Worker_V1_PrefillStarted()
        payload.inputTokens = response.promptTokens
        event.prefillStarted = payload
        return event
    }

    private func makeCacheDecisionEvent(
        requestID: String,
        lane: String,
        blockTableID: String,
        restoredSnapshotID: String,
        accelerationMode: Melix_Worker_V1_AccelerationMode
    ) -> Melix_Worker_V1_ExecuteEvent {
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "prefill"
        event.seq = 2
        event.phase = .executionPrefilling
        event.admissionState = .admissionAdmitted
        event.lane = lane.isEmpty ? "text.prefill.hot" : lane
        event.accelerationMode = accelerationMode

        var payload = Melix_Worker_V1_CacheDecision()
        payload.blockTableID = blockTableID
        payload.restoredSnapshotID = restoredSnapshotID
        payload.persistedToL2 = true
        event.cacheDecision = payload
        return event
    }

    private func makePrefillFailureEvent(
        requestID: String,
        error: Melix_Worker_V1_ErrorStatus
    ) -> Melix_Worker_V1_ExecuteEvent {
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "prefill"
        event.seq = 1
        event.phase = .executionFailed

        var payload = Melix_Worker_V1_ErrorEvent()
        payload.error = error
        event.error = payload
        return event
    }

    private func terminalPhase(
        requestID: String,
        fallback: Melix_Controlplane_V1_RequestPhase
    ) async -> Melix_Controlplane_V1_RequestPhase {
        let phase = await schedulerReadModel.progressSnapshot(for: requestID)?.phase ?? fallback
        switch phase {
        case .requestAborted, .requestFailed, .requestRejected:
            return phase
        default:
            return fallback
        }
    }

    private func makeCancelledExecution(
        requestID: String,
        modelID: String
    ) async -> CoordinatedChatExecution {
        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            var completed = Melix_Worker_V1_Completed()
            completed.finishReason = "cancelled"

            var event = Melix_Worker_V1_ExecuteEvent()
            event.requestID = requestID
            event.executionKind = "generate"
            event.phase = .executionAborted
            event.completed = completed

            continuation.yield(event)
            continuation.finish()
        }
        return CoordinatedChatExecution(requestID: requestID, modelID: modelID, stream: stream)
    }

    private func recordAbortMetrics(
        phase: Melix_Controlplane_V1_RequestPhase,
        startedAt: Date
    ) async {
        let elapsed = now().timeIntervalSince(startedAt) * 1000
        await metricsStore.set(elapsed, forKey: "http.abort_ms")
        switch phase {
        case .requestQueued:
            await metricsStore.set(elapsed, forKey: "swift_text.abort_queued_ms")
        case .requestPrefilling:
            await metricsStore.set(elapsed, forKey: "swift_text.abort_prefill_ms")
        case .requestDecoding:
            await metricsStore.set(elapsed, forKey: "swift_text.abort_decode_ms")
        default:
            break
        }
    }
}

private func controlPlaneAccelerationMode(
    from workerMode: Melix_Worker_V1_AccelerationMode
) -> Melix_Controlplane_V1_AccelerationMode? {
    switch workerMode {
    case .unspecified:
        return nil
    case .baseline:
        return .baseline
    case .speculativeDecode:
        return .speculativeDecode
    case .acceleratedPrefill:
        return .acceleratedPrefill
    case .activeKvQuantized:
        return .activeKvQuantized
    case .UNRECOGNIZED:
        return nil
    }
}
