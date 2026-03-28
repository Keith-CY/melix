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

private enum CacheRouteClass: String, Sendable {
    case cold
    case warm
    case restored
}

private struct SchedulingPlan: Sendable {
    let translatedRequest: TranslatedChatRequest
    let routeKind: WorkerRouteKind
    let admissionLane: String
    let prefillLane: String
    let decodeLane: String
    let cacheRouteClass: CacheRouteClass
    let cacheRouteEligible: Bool
    let prefixAffinityEligible: Bool
    let prefixAffinityHit: Bool
}

public actor RequestCoordinator {
    private let workerRegistry: WorkerRegistry
    private let abortRegistry: AbortRegistry
    private let admissionGate: AdmissionGate
    private let schedulerReadModel: SchedulerReadModel
    private let metricsStore: MetricsStore
    private let sessionGraphStore: SessionGraphStore?
    private let cacheMetadataStore: CacheMetadataStore?
    private let now: @Sendable () -> Date
    private var activeWorkerClients: [String: any WorkerClient]
    private var requestPlans: [String: SchedulingPlan]
    private var coldTTFTBaselinesByBranch: [String: Double]
    private var schedulingDecisionCount: Double
    private var cacheRouteEligibleCount: Double
    private var warmRoutePreferenceCount: Double
    private var restoredRouteCount: Double
    private var prefixAffinityCheckCount: Double
    private var prefixAffinityHitCount: Double

    public init(
        workerRegistry: WorkerRegistry,
        abortRegistry: AbortRegistry = AbortRegistry(),
        admissionGate: AdmissionGate = AdmissionGate(),
        schedulerReadModel: SchedulerReadModel = SchedulerReadModel(),
        metricsStore: MetricsStore = MetricsStore(),
        sessionGraphStore: SessionGraphStore? = nil,
        cacheMetadataStore: CacheMetadataStore? = nil,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.workerRegistry = workerRegistry
        self.abortRegistry = abortRegistry
        self.admissionGate = admissionGate
        self.schedulerReadModel = schedulerReadModel
        self.metricsStore = metricsStore
        self.sessionGraphStore = sessionGraphStore
        self.cacheMetadataStore = cacheMetadataStore
        self.now = now
        self.activeWorkerClients = [:]
        self.requestPlans = [:]
        self.coldTTFTBaselinesByBranch = [:]
        self.schedulingDecisionCount = 0
        self.cacheRouteEligibleCount = 0
        self.warmRoutePreferenceCount = 0
        self.restoredRouteCount = 0
        self.prefixAffinityCheckCount = 0
        self.prefixAffinityHitCount = 0
    }

    public func startChatCompletion(
        _ translatedRequest: TranslatedChatRequest
    ) async throws -> CoordinatedChatExecution {
        guard !translatedRequest.modelID.isEmpty else {
            throw RequestCoordinatorError.workerUnavailable
        }
        let plan = await resolvedSchedulingPlan(translatedRequest)
        let request = plan.translatedRequest
        requestPlans[request.requestID] = plan
        await recordSchedulingMetrics(for: plan)
        await hydrateSessionGraph(for: request.workerRequest.execution.id)
        let lane = plan.admissionLane
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
        let routedWorkerClient = await workerRegistry.client(for: plan.routeKind)
        let fallbackWorkerClient = routedWorkerClient == nil
            ? await workerRegistry.client(forModelID: request.modelID)
            : nil
        guard let workerClient = routedWorkerClient ?? fallbackWorkerClient else {
            await abortRegistry.finish(requestID: request.requestID)
            requestPlans.removeValue(forKey: request.requestID)
            _ = await schedulerReadModel.recordRejected(
                requestID: request.requestID,
                laneHint: lane,
                priority: priority
            )
            throw RequestCoordinatorError.workerUnavailable
        }
        await refreshWorkerCacheObservability(using: workerClient)
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
            requestPlans.removeValue(forKey: request.requestID)
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
            if plan.routeKind.isPhaseAwareTextRoute,
               let phaseAwareClient = workerClient as? any PhaseAwareWorkerClientProtocol,
               shouldUsePhaseAwareExecution(for: request.workerRequest) {
                upstream = makePhaseAwareUpstream(
                    client: phaseAwareClient,
                    request: request.workerRequest,
                    modelID: request.modelID,
                    prefillLane: plan.prefillLane
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
                    var firstSemanticEventRecorded = false
                    var eventCount = 0.0

                    do {
                        for try await event in upstream {
                            await self.recordPhaseObservability(
                                requestID: requestID,
                                fallbackLane: plan.decodeLane,
                                requestIdentity: request.workerRequest.execution.id,
                                routeKind: plan.routeKind,
                                event: event
                            )
                            if !firstSemanticEventRecorded,
                               self.isSemanticStreamEvent(event) {
                                firstSemanticEventRecorded = true
                                let firstEventMs = now().timeIntervalSince(dispatchStartedAt) * 1000
                                await metricsStore.set(
                                    firstEventMs,
                                    forKey: "http.stream_first_event_ms"
                                )
                            }
                            if !firstDeltaRecorded, case .tokenDelta = event.payload {
                                firstDeltaRecorded = true
                                let ttftMs = now().timeIntervalSince(dispatchStartedAt) * 1000
                                await metricsStore.set(
                                    ttftMs,
                                    forKey: "http.ttfd_ms"
                                )
                                await self.recordTTFTMetrics(requestID: requestID, ttftMs: ttftMs)
                            }
                            switch event.payload {
                            case .reasoningDelta:
                                await metricsStore.increment("http.reasoning_delta_count")
                            case .toolCallDelta:
                                await metricsStore.increment("http.tool_delta_count")
                            default:
                                break
                            }
                            eventCount += 1
                            await metricsStore.set(eventCount, forKey: "http.stream_event_count")
                            continuation.yield(event)
                        }
                        await metricsStore.decrement("requests.inflight")
                        await self.refreshWorkerCacheObservability(using: workerClient)
                        await self.refreshWorkerRuntimeObservability(
                            using: workerClient,
                            routeKind: plan.routeKind
                        )
                        let terminalPhase = await self.terminalPhase(
                            requestID: requestID,
                            fallback: .requestCompleted
                        )
                        await self.finishRequestTracking(requestID: requestID, phase: terminalPhase)
                        continuation.finish()
                    } catch {
                        await metricsStore.decrement("requests.inflight")
                        await self.refreshWorkerCacheObservability(using: workerClient)
                        await self.refreshWorkerRuntimeObservability(
                            using: workerClient,
                            routeKind: plan.routeKind
                        )
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

    private func isSemanticStreamEvent(_ event: Melix_Worker_V1_ExecuteEvent) -> Bool {
        switch event.payload {
        case .tokenDelta, .reasoningDelta, .toolCallDelta:
            return true
        default:
            return false
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
        requestPlans.removeValue(forKey: requestID)
        if let phase {
            await schedulerReadModel.recordTerminalState(requestID: requestID, phase: phase)
        }
    }

    private func recordPhaseObservability(
        requestID: String,
        fallbackLane: String,
        requestIdentity: Melix_Worker_V1_RequestIdentity,
        routeKind: WorkerRouteKind,
        event: Melix_Worker_V1_ExecuteEvent
    ) async {
        let workerSource = routeKind.workerSourceID
        let observedLane = observabilityLane(
            routeKind: routeKind,
            eventLane: event.lane,
            fallbackLane: fallbackLane
        )
        switch event.payload {
        case .prefillStarted, .prefillProgress:
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestPrefilling,
                laneHint: routeKind.isMultimodalBackgroundRoute
                    ? observedLane
                    : (event.lane.isEmpty ? "text.prefill.hot" : event.lane),
                workerID: workerSource,
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: workerSource
            )
        case .decodeStarted(let decodeStarted):
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestDecoding,
                laneHint: observedLane,
                workerID: workerSource,
                decodeHandle: decodeStarted.decodeHandle,
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: workerSource
            )
        case .tokenDelta, .reasoningDelta, .toolCallDelta, .usageDelta:
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestDecoding,
                laneHint: observedLane,
                workerID: workerSource,
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: workerSource
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
                laneHint: observedLane,
                workerID: workerSource,
                accelerationMode: controlPlaneAccelerationMode(from: event.accelerationMode),
                source: workerSource
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
                    laneHint: observedLane,
                    workerID: workerSource,
                    source: workerSource
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

    private func resolvedSchedulingPlan(
        _ translatedRequest: TranslatedChatRequest
    ) async -> SchedulingPlan {
        let request = await resolvedRecoveryRequest(translatedRequest)
        let routeKind = await workerRegistry.route(forModelID: request.modelID) ?? .swiftText
        if routeKind.isMultimodalBackgroundRoute {
            let lane = routeKind.defaultSchedulingLane
            return SchedulingPlan(
                translatedRequest: request,
                routeKind: routeKind,
                admissionLane: lane,
                prefillLane: lane,
                decodeLane: lane,
                cacheRouteClass: .cold,
                cacheRouteEligible: false,
                prefixAffinityEligible: false,
                prefixAffinityHit: false
            )
        }
        guard
            let sessionGraphStore,
            !request.workerRequest.execution.id.sessionID.isEmpty
        else {
            let decodeLane = request.workerRequest.execution.scheduling.lane.isEmpty
                ? "text.decode.interactive"
                : request.workerRequest.execution.scheduling.lane
            let prefillLane = shouldUsePhaseAwareExecution(for: request.workerRequest)
                ? "text.prefill.background"
                : decodeLane
            return SchedulingPlan(
                translatedRequest: request,
                routeKind: routeKind,
                admissionLane: prefillLane,
                prefillLane: prefillLane,
                decodeLane: decodeLane,
                cacheRouteClass: .cold,
                cacheRouteEligible: shouldUsePhaseAwareExecution(for: request.workerRequest),
                prefixAffinityEligible: false,
                prefixAffinityHit: false
            )
        }

        let branchID = request.workerRequest.execution.id.branchID.isEmpty
            ? "branch-main"
            : request.workerRequest.execution.id.branchID
        let session = await sessionGraphStore.state(for: request.workerRequest.execution.id.sessionID)
        let activeBranchID = session?.activeBranchID ?? branchID
        let branch = session?.branches.first(where: { $0.branchID == branchID })
            ?? session?.branches.first(where: { $0.branchID == activeBranchID })
        let prefixAffinityEligible = isPrefixAffinityEligible(
            request: request,
            branch: branch
        )
        let prefixAffinityHit = shouldRecordPrefixAffinity(
            request: request,
            headCacheKey: branch?.headCacheKey,
            branch: branch
        )

        let cacheRouteClass: CacheRouteClass
        if !request.workerRequest.execution.cacheHints.restoreSnapshotID.isEmpty {
            cacheRouteClass = .restored
        } else if prefixAffinityHit {
            cacheRouteClass = .warm
        } else {
            cacheRouteClass = .cold
        }

        let decodeLane = request.workerRequest.execution.scheduling.lane.isEmpty
            ? "text.decode.interactive"
            : request.workerRequest.execution.scheduling.lane
        let cacheRouteEligible = shouldUsePhaseAwareExecution(for: request.workerRequest)
            || prefixAffinityEligible
        let prefillLane: String
        if shouldUsePhaseAwareExecution(for: request.workerRequest) {
            prefillLane = cacheRouteClass == .cold ? "text.prefill.background" : "text.prefill.hot"
        } else {
            prefillLane = decodeLane
        }

        return SchedulingPlan(
            translatedRequest: request,
            routeKind: routeKind,
            admissionLane: prefillLane,
            prefillLane: prefillLane,
            decodeLane: decodeLane,
            cacheRouteClass: cacheRouteClass,
            cacheRouteEligible: cacheRouteEligible,
            prefixAffinityEligible: prefixAffinityEligible,
            prefixAffinityHit: prefixAffinityHit
        )
    }

    private func makePhaseAwareUpstream(
        client: any PhaseAwareWorkerClientProtocol,
        request: Melix_Worker_V1_GenerateRequest,
        modelID: String,
        prefillLane: String
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

                    await self.hydrateHeadCacheKey(
                        requestIdentity: request.execution.id,
                        modelID: modelID,
                        blockTable: prefillResponse.blockTable
                    )

                    var prefillEvent = makePrefillStartedEvent(
                        request: request,
                        response: prefillResponse,
                        lane: prefillLane
                    )
                    prefillEvent.seq = nextSeq
                    nextSeq += 1
                    continuation.yield(prefillEvent)
                    if !prefillResponse.restoredSnapshotID.isEmpty {
                        var cacheDecisionEvent = makeCacheDecisionEvent(
                            requestID: request.execution.id.requestID,
                            lane: prefillLane,
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
        prefill.resumeHint = request.execution.cacheHints.restoreSnapshotID.isEmpty
            ? request.execution.id.parentRequestID
            : "snapshot-restore:\(request.execution.cacheHints.restoreSnapshotID)"
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
        response: Melix_Worker_V1_PrefillResponse,
        lane: String
    ) -> Melix_Worker_V1_ExecuteEvent {
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = request.execution.id.requestID
        event.executionKind = "prefill"
        event.seq = 1
        event.phase = response.lifecyclePhase
        event.admissionState = response.admissionState
        event.lane = lane
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

    private func recordSchedulingMetrics(for plan: SchedulingPlan) async {
        schedulingDecisionCount += 1
        if plan.cacheRouteEligible {
            cacheRouteEligibleCount += 1
        }
        if plan.cacheRouteEligible, plan.cacheRouteClass != .cold {
            warmRoutePreferenceCount += 1
        }
        if plan.cacheRouteEligible, plan.cacheRouteClass == .restored {
            restoredRouteCount += 1
        }
        if plan.prefixAffinityEligible {
            prefixAffinityCheckCount += 1
            if plan.prefixAffinityHit {
                prefixAffinityHitCount += 1
            }
        }

        await metricsStore.set(
            warmRoutePreferenceCount / max(cacheRouteEligibleCount, 1) * 100,
            forKey: "scheduler.warm_route_preference_rate"
        )
        await metricsStore.set(
            restoredRouteCount / max(cacheRouteEligibleCount, 1) * 100,
            forKey: "scheduler.restored_route_rate"
        )
        await metricsStore.set(
            prefixAffinityHitCount / max(prefixAffinityCheckCount, 1) * 100,
            forKey: "scheduler.prefix_affinity_hit_rate"
        )
        await metricsStore.set(
            plan.cacheRouteClass == .cold ? 0 : 1,
            forKey: "scheduler.warm_route_preferred"
        )
    }

    private func recordTTFTMetrics(requestID: String, ttftMs: Double) async {
        guard let plan = requestPlans[requestID] else {
            return
        }
        if plan.routeKind.isPhaseAwareTextRoute,
           await schedulerReadModel.hasActiveMultimodalRequests(excluding: requestID) {
            await metricsStore.set(ttftMs, forKey: "scheduler.text_ttft_under_multimodal_ms")
        }
        guard let branchKey = branchMetricKey(for: plan.translatedRequest.workerRequest.execution.id) else {
            return
        }

        switch plan.cacheRouteClass {
        case .cold:
            coldTTFTBaselinesByBranch[branchKey] = ttftMs
            await metricsStore.set(ttftMs, forKey: "session.last_cold_ttft_ms")
        case .warm, .restored:
            await metricsStore.set(ttftMs, forKey: "session.last_followup_ttft_ms")
            if let baseline = coldTTFTBaselinesByBranch[branchKey] {
                await metricsStore.set(baseline - ttftMs, forKey: "session.followup_ttft_delta_ms")
            }
        }
    }

    private func branchMetricKey(
        for identity: Melix_Worker_V1_RequestIdentity
    ) -> String? {
        guard !identity.sessionID.isEmpty else {
            return nil
        }
        let branchID = identity.branchID.isEmpty ? "branch-main" : identity.branchID
        return "\(identity.sessionID)::\(branchID)"
    }

    private func shouldRecordPrefixAffinity(
        request: TranslatedChatRequest,
        headCacheKey: Melix_Controlplane_V1_CacheKey?,
        branch: Melix_Controlplane_V1_BranchState?
    ) -> Bool {
        guard request.workerRequest.execution.cacheHints.preferHotPrefix else {
            return false
        }
        if let branch, !branch.resumeSnapshotID.isEmpty {
            return true
        }
        guard let headCacheKey else {
            return false
        }
        return !headCacheKey.scope.modelID.isEmpty && headCacheKey.scope.modelID == request.modelID
    }

    private func isPrefixAffinityEligible(
        request: TranslatedChatRequest,
        branch: Melix_Controlplane_V1_BranchState?
    ) -> Bool {
        guard request.workerRequest.execution.cacheHints.preferHotPrefix else {
            return false
        }
        guard let branch else {
            return false
        }
        if !branch.resumeSnapshotID.isEmpty {
            return true
        }
        return !branch.headCacheKey.scope.modelID.isEmpty
    }

    private func hydrateHeadCacheKey(
        requestIdentity: Melix_Worker_V1_RequestIdentity,
        modelID: String,
        blockTable: Melix_Worker_V1_BlockTable
    ) async {
        guard
            let sessionGraphStore,
            !requestIdentity.sessionID.isEmpty
        else {
            return
        }

        var key = Melix_Controlplane_V1_CacheKey()
        key.prefixHash = blockTable.cacheKey.prefixHash
        key.scope.modelID = modelID

        _ = await sessionGraphStore.recordSnapshotHydration(
            sessionID: requestIdentity.sessionID,
            branchID: requestIdentity.branchID,
            snapshot: Melix_Controlplane_V1_SnapshotRef(),
            headCacheKey: key
        )
    }

    private func refreshWorkerCacheObservability(
        using workerClient: any WorkerClient
    ) async {
        guard let introspectingClient = workerClient as? any CacheIntrospectingWorkerClientProtocol else {
            return
        }
        guard
            let runtimeStats = try? await introspectingClient.runtimeStats(),
            let cacheStats = try? await introspectingClient.cacheStats()
        else {
            return
        }

        await metricsStore.set(Double(cacheStats.stats.l1Bytes), forKey: "cache.memory_bytes")
        await metricsStore.set(Double(cacheStats.stats.l2Bytes), forKey: "cache.disk_bytes")
        await metricsStore.set(cacheStats.stats.l1HitRate * 100, forKey: "cache.hit_rate")
        await metricsStore.set(cacheStats.stats.l2RestoreHitRate * 100, forKey: "cache.l2_restore_hit_rate")
        await metricsStore.set(cacheStats.stats.compressionRatio * 100, forKey: "cache.compression_ratio")
        let residentBytes = max(Double(runtimeStats.stats.residentBytes), 1)
        let cachePressure = min(1, Double(cacheStats.stats.l1Bytes) / residentBytes)
        await metricsStore.set(cachePressure, forKey: "scheduler.cache_pressure")

        if let cacheMetadataStore {
            await cacheMetadataStore.replace(
                snapshot: controlPlaneCacheSnapshot(
                    from: cacheStats.snapshot,
                    overridingSummary: cacheStats.stats
                )
            )
        }
    }

    private func refreshWorkerRuntimeObservability(
        using workerClient: any WorkerClient,
        routeKind: WorkerRouteKind
    ) async {
        guard
            routeKind.isMultimodalBackgroundRoute,
            let introspectingClient = workerClient as? any RuntimeIntrospectingWorkerClientProtocol,
            let runtimeStats = try? await introspectingClient.runtimeStats()
        else {
            return
        }

        let stats = runtimeStats.stats
        switch routeKind {
        case .pythonOCR:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "vision.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "vision.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastFirstTokenLatencyMs, forKey: "vision.ocr_latency_ms")
        case .pythonVLM:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "vision.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "vision.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastFirstTokenLatencyMs, forKey: "vision.vlm_first_token_ms")
        case .pythonTranscription:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "audio.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastTranscriptionLatencyMs, forKey: "audio.transcription_latency_ms")
        case .pythonSpeech:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "audio.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastSpeechLatencyMs, forKey: "audio.speech_latency_ms")
        default:
            break
        }
    }
}

private func observabilityLane(
    routeKind: WorkerRouteKind,
    eventLane: String,
    fallbackLane: String
) -> String {
    if routeKind.isMultimodalBackgroundRoute {
        return fallbackLane
    }
    return eventLane.isEmpty ? fallbackLane : eventLane
}

private func controlPlaneCacheSnapshot(
    from workerSnapshot: Melix_Worker_V1_CacheSnapshot,
    overridingSummary workerStats: Melix_Worker_V1_CacheStats? = nil
) -> Melix_Controlplane_V1_CacheSnapshot {
    var snapshot = Melix_Controlplane_V1_CacheSnapshot()
    snapshot.summary = controlPlaneCacheSummary(from: workerStats ?? workerSnapshot.stats)
    snapshot.pinnedPrefixes = workerSnapshot.pinnedPrefixes.map(controlPlanePrefixRef(from:))
    snapshot.hotPrefixes = workerSnapshot.hotPrefixes.map(controlPlanePrefixRef(from:))
    snapshot.snapshots = workerSnapshot.snapshots.map(controlPlaneSnapshotRef(from:))
    snapshot.scopes = workerSnapshot.scopes.map(controlPlaneCacheScopeSummary(from:))
    return snapshot
}

private func controlPlaneCacheSummary(
    from workerStats: Melix_Worker_V1_CacheStats
) -> Melix_Controlplane_V1_CacheSummary {
    var summary = Melix_Controlplane_V1_CacheSummary()
    summary.l1Bytes = workerStats.l1Bytes
    summary.l2Bytes = workerStats.l2Bytes
    summary.l1HitRate = workerStats.l1HitRate
    summary.l2HitRate = workerStats.l2HitRate
    summary.dedupRatio = workerStats.dedupRatio
    summary.checkpointCount = workerStats.snapshotCount
    summary.blockCount = workerStats.blockCount
    summary.quantizedBytes = workerStats.quantizedBytes
    summary.compressionRatio = workerStats.compressionRatio
    summary.l2RestoreHitRate = workerStats.l2RestoreHitRate
    return summary
}

private func controlPlaneCacheScopeSummary(
    from workerScope: Melix_Worker_V1_CacheScopeSummary
) -> Melix_Controlplane_V1_CacheScopeSummary {
    var scope = Melix_Controlplane_V1_CacheScopeSummary()
    scope.scopeID = workerScope.scopeID
    scope.scope = controlPlaneCacheScopeKey(from: workerScope.scope)
    scope.l1Bytes = workerScope.l1Bytes
    scope.l2Bytes = workerScope.l2Bytes
    scope.blockCount = workerScope.blockCount
    scope.prefixCount = workerScope.prefixCount
    scope.snapshotCount = workerScope.snapshotCount
    scope.hotBlocks = workerScope.hotBlocks.map(controlPlaneCacheBlockRef(from:))
    return scope
}

private func controlPlaneCacheBlockRef(
    from workerBlock: Melix_Worker_V1_BlockRef
) -> Melix_Controlplane_V1_CacheBlockRef {
    var block = Melix_Controlplane_V1_CacheBlockRef()
    block.blockID = workerBlock.blockID
    block.tokenLength = UInt32(max(workerBlock.tokenEnd - workerBlock.tokenStart, 0))
    block.bytes = workerBlock.bytes
    return block
}

private func controlPlanePrefixRef(
    from workerPrefix: Melix_Worker_V1_PrefixRef
) -> Melix_Controlplane_V1_PrefixRef {
    var prefix = Melix_Controlplane_V1_PrefixRef()
    prefix.prefixID = workerPrefix.prefixID
    prefix.cacheKey = controlPlaneCacheKey(from: workerPrefix.cacheKey, scope: workerPrefix.scope)
    prefix.tokenLength = workerPrefix.tokenLength
    prefix.tier = workerPrefix.tier
    prefix.pinned = workerPrefix.pinned
    return prefix
}

private func controlPlaneSnapshotRef(
    from workerSnapshot: Melix_Worker_V1_SnapshotRef
) -> Melix_Controlplane_V1_SnapshotRef {
    var snapshot = Melix_Controlplane_V1_SnapshotRef()
    snapshot.snapshotID = workerSnapshot.snapshotID
    snapshot.tokenBoundary = workerSnapshot.tokenBoundary
    snapshot.requestID = workerSnapshot.requestID
    snapshot.sessionID = workerSnapshot.sessionID
    snapshot.branchID = workerSnapshot.branchID
    snapshot.checkpointID = workerSnapshot.checkpointID
    return snapshot
}

private func controlPlaneCacheKey(
    from workerKey: Melix_Worker_V1_CacheKey,
    scope: Melix_Worker_V1_CacheScope
) -> Melix_Controlplane_V1_CacheKey {
    var key = Melix_Controlplane_V1_CacheKey()
    key.prefixHash = workerKey.prefixHash
    key.scope = controlPlaneCacheScopeKey(from: scope)
    return key
}

private func controlPlaneCacheScopeKey(
    from workerScope: Melix_Worker_V1_CacheScope
) -> Melix_Controlplane_V1_CacheScopeKey {
    var scope = Melix_Controlplane_V1_CacheScopeKey()
    scope.modelID = workerScope.modelID
    scope.revision = workerScope.revision
    scope.tokenizerHash = workerScope.tokenizerHash
    scope.quantProfileID = workerScope.quantProfileID
    scope.promptTemplateHash = workerScope.promptTemplateHash
    scope.parserMode = workerScope.parserMode
    scope.reasoningMode = workerScope.reasoningMode
    return scope
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
