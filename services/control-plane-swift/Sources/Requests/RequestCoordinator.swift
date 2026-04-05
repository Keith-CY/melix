import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public enum RequestCoordinatorError: Error, Equatable {
    case requestAlreadyActive
    case workerUnavailable
    case requestNotResumable
}

public struct CoordinatedChatExecution: Sendable {
    public let requestID: String
    public let modelID: String
    public let stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
    public let lifecycle: AsyncStream<ConnectionLifecycleEvent>
    public let onStreamDisconnect: (@Sendable () async -> Void)?

    public init(
        requestID: String,
        modelID: String,
        stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>,
        lifecycle: AsyncStream<ConnectionLifecycleEvent> = AsyncStream { continuation in
            continuation.finish()
        },
        onStreamDisconnect: (@Sendable () async -> Void)? = nil
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.stream = stream
        self.lifecycle = lifecycle
        self.onStreamDisconnect = onStreamDisconnect
    }
}

private actor ResumableExecutionHub {
    private enum TerminalState {
        case finished
        case failed(any Error)
    }

    private let requestID: String
    private let modelID: String
    private let bufferLimit: Int
    private let onLastConsumerDetached: @Sendable () async -> Void
    private var bufferedEvents: [Melix_Worker_V1_ExecuteEvent]
    private var lifecycleEvents: [ConnectionLifecycleEvent]
    private var eventContinuations: [UUID: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation]
    private var lifecycleContinuations: [UUID: AsyncStream<ConnectionLifecycleEvent>.Continuation]
    private var terminalState: TerminalState?

    init(
        requestID: String,
        modelID: String,
        bufferLimit: Int,
        onLastConsumerDetached: @escaping @Sendable () async -> Void
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.bufferLimit = max(1, bufferLimit)
        self.onLastConsumerDetached = onLastConsumerDetached
        self.bufferedEvents = []
        self.lifecycleEvents = [.active]
        self.eventContinuations = [:]
        self.lifecycleContinuations = [:]
        self.terminalState = nil
    }

    func makeExecution() -> CoordinatedChatExecution {
        CoordinatedChatExecution(
            requestID: requestID,
            modelID: modelID,
            stream: attachStream(),
            lifecycle: attachLifecycleStream()
        )
    }

    func isTerminal() -> Bool {
        terminalState != nil
    }

    func hasConsumers() -> Bool {
        eventContinuations.isEmpty == false
    }

    func yield(_ event: Melix_Worker_V1_ExecuteEvent) {
        bufferedEvents.append(event)
        if bufferedEvents.count > bufferLimit {
            bufferedEvents.removeFirst(bufferedEvents.count - bufferLimit)
        }
        for continuation in eventContinuations.values {
            continuation.yield(event)
        }
    }

    func emitLifecycle(_ event: ConnectionLifecycleEvent) {
        lifecycleEvents.append(event)
        for continuation in lifecycleContinuations.values {
            continuation.yield(event)
        }
    }

    func finish() {
        guard terminalState == nil else {
            return
        }
        terminalState = .finished
        let eventContinuations = self.eventContinuations
        let lifecycleContinuations = self.lifecycleContinuations
        self.eventContinuations.removeAll()
        self.lifecycleContinuations.removeAll()
        for continuation in eventContinuations.values {
            continuation.finish()
        }
        for continuation in lifecycleContinuations.values {
            continuation.finish()
        }
    }

    func finish(throwing error: any Error) {
        guard terminalState == nil else {
            return
        }
        terminalState = .failed(error)
        let eventContinuations = self.eventContinuations
        let lifecycleContinuations = self.lifecycleContinuations
        self.eventContinuations.removeAll()
        self.lifecycleContinuations.removeAll()
        for continuation in eventContinuations.values {
            continuation.finish(throwing: error)
        }
        for continuation in lifecycleContinuations.values {
            continuation.finish()
        }
    }

    private func attachStream() -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            let streamID = UUID()
            continuation.onTermination = { _ in
                Task {
                    await self.detachStream(streamID)
                }
            }
            Task {
                let registration = await self.registerEventContinuation(
                    streamID,
                    continuation: continuation
                )
                for event in registration.replay {
                    continuation.yield(event)
                }
                switch registration.terminalState {
                case .finished:
                    continuation.finish()
                case .failed(let error):
                    continuation.finish(throwing: error)
                case nil:
                    break
                }
            }
        }
    }

    private func attachLifecycleStream() -> AsyncStream<ConnectionLifecycleEvent> {
        AsyncStream { continuation in
            let streamID = UUID()
            continuation.onTermination = { _ in
                Task {
                    await self.detachLifecycleStream(streamID)
                }
            }
            Task {
                let registration = await self.registerLifecycleContinuation(
                    streamID,
                    continuation: continuation
                )
                for event in registration.replay {
                    continuation.yield(event)
                }
                if registration.isTerminal {
                    continuation.finish()
                }
            }
        }
    }

    private func registerEventContinuation(
        _ streamID: UUID,
        continuation: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation
    ) -> (replay: [Melix_Worker_V1_ExecuteEvent], terminalState: TerminalState?) {
        let replay = bufferedEvents
        let terminalState = self.terminalState
        if terminalState == nil {
            eventContinuations[streamID] = continuation
        }
        return (replay, terminalState)
    }

    private func registerLifecycleContinuation(
        _ streamID: UUID,
        continuation: AsyncStream<ConnectionLifecycleEvent>.Continuation
    ) -> (replay: [ConnectionLifecycleEvent], isTerminal: Bool) {
        let replay = lifecycleEvents
        let isTerminal = terminalState != nil
        if !isTerminal {
            lifecycleContinuations[streamID] = continuation
        }
        return (replay, isTerminal)
    }

    private func detachStream(_ streamID: UUID) async {
        guard eventContinuations.removeValue(forKey: streamID) != nil else {
            return
        }
        guard eventContinuations.isEmpty, terminalState == nil else {
            return
        }
        await onLastConsumerDetached()
    }

    private func detachLifecycleStream(_ streamID: UUID) {
        lifecycleContinuations.removeValue(forKey: streamID)
    }
}

private enum CacheRouteClass: String, Sendable {
    case cold
    case warm
    case restored
}

private let boundarySafePrefillChunkTargetTokens: UInt32 = 16

private struct GatewayBatchingExecutionDefaults: Sendable {
    let concurrentProcessingEnabled: Bool
    let maxConcurrentRequests: UInt32
    let prefillBatchSize: UInt32
    let completionBatchSize: UInt32

    init(executionExt: [String: String]) {
        self.concurrentProcessingEnabled = Self.parseBool(
            executionExt["melix.gateway.concurrent_processing"],
            fallback: true
        )
        self.maxConcurrentRequests = Self.parseUInt32(
            executionExt["melix.gateway.max_concurrent_sequences"] ?? executionExt["melix.gateway.max_concurrent_requests"],
            fallback: 4
        )
        self.prefillBatchSize = Self.parseUInt32(
            executionExt["melix.gateway.prefill_batch_size"],
            fallback: 2
        )
        self.completionBatchSize = Self.parseUInt32(
            executionExt["melix.gateway.completion_batch_size"],
            fallback: 2
        )
    }

    var effectiveAdmissionBatchSize: UInt32 {
        guard concurrentProcessingEnabled else {
            return 1
        }
        return min(maxConcurrentRequests, prefillBatchSize, completionBatchSize)
    }

    private static func parseBool(_ rawValue: String?, fallback: Bool) -> Bool {
        guard let rawValue = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), !rawValue.isEmpty else {
            return fallback
        }
        switch rawValue {
        case "1", "true", "yes", "on":
            return true
        case "0", "false", "no", "off":
            return false
        default:
            return fallback
        }
    }

    private static func parseUInt32(_ rawValue: String?, fallback: UInt32) -> UInt32 {
        guard let rawValue = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines), let parsed = UInt32(rawValue), parsed > 0 else {
            return fallback
        }
        return parsed
    }
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
    let continuousBatchEligible: Bool
    let batchCohortID: String
    let batchMaxSize: UInt32
}

private struct StructuredOutputValidationEvent: Sendable {
    let event: Melix_Worker_V1_ExecuteEvent
    let didValidate: Bool
    let didFail: Bool
}

private struct ReasoningBudgetState: Sendable {
    let limitTokens: UInt32
    private(set) var emittedTokens: UInt32 = 0
    private(set) var accumulatedText = ""
    private(set) var overflowed = false

    init?(execution: Melix_Worker_V1_ExecutionMetadata) {
        guard execution.reasoning.enabled else {
            return nil
        }
        guard
            let rawBudget = execution.ext["melix.reasoning.budget_tokens"] ?? execution.ext["melix.messages.thinking.budget_tokens"],
            let budget = UInt32(rawBudget),
            budget > 0
        else {
            return nil
        }
        self.limitTokens = budget
    }

    mutating func apply(
        to event: Melix_Worker_V1_ExecuteEvent
    ) -> (events: [Melix_Worker_V1_ExecuteEvent], didOverflow: Bool, shouldStop: Bool) {
        if overflowed {
            return ([], false, true)
        }

        switch event.payload {
        case .reasoningDelta(let delta):
            return applyReasoningDelta(event: event, text: delta.text)
        case .completed(let completed):
            return applyCompleted(event: event, completed: completed)
        default:
            return ([event], false, false)
        }
    }

    private mutating func applyReasoningDelta(
        event: Melix_Worker_V1_ExecuteEvent,
        text: String
    ) -> (events: [Melix_Worker_V1_ExecuteEvent], didOverflow: Bool, shouldStop: Bool) {
        let tokenCount = Self.tokenCount(in: text)
        guard tokenCount > 0 else {
            return ([event], false, false)
        }

        let remainingTokens = limitTokens > emittedTokens ? limitTokens - emittedTokens : 0
        guard tokenCount > remainingTokens else {
            accumulate(text)
            return ([event], false, false)
        }

        var events: [Melix_Worker_V1_ExecuteEvent] = []
        let permittedText = Self.prefix(text, limitedTo: remainingTokens)
        if !permittedText.isEmpty {
            var truncatedEvent = event
            truncatedEvent.reasoningDelta.text = permittedText
            events.append(truncatedEvent)
            accumulate(permittedText)
        }
        overflowed = true
        events.append(makeOverflowCompleted(from: event))
        return (events, true, true)
    }

    private mutating func applyCompleted(
        event: Melix_Worker_V1_ExecuteEvent,
        completed: Melix_Worker_V1_Completed
    ) -> (events: [Melix_Worker_V1_ExecuteEvent], didOverflow: Bool, shouldStop: Bool) {
        if accumulatedText.isEmpty, !completed.reasoningText.isEmpty {
            let tokenCount = Self.tokenCount(in: completed.reasoningText)
            let remainingTokens = limitTokens > emittedTokens ? limitTokens - emittedTokens : 0
            if tokenCount > remainingTokens {
                let permittedText = Self.prefix(completed.reasoningText, limitedTo: remainingTokens)
                if !permittedText.isEmpty {
                    accumulate(permittedText)
                }
                overflowed = true
                return ([makeOverflowCompleted(from: event, assistantText: completed.assistantText)], true, true)
            }
            accumulate(completed.reasoningText)
        }

        var adjustedEvent = event
        adjustedEvent.completed.reasoningText = accumulatedText.isEmpty ? completed.reasoningText : accumulatedText
        return ([adjustedEvent], false, false)
    }

    private mutating func accumulate(_ text: String) {
        guard !text.isEmpty else {
            return
        }
        emittedTokens = min(limitTokens, emittedTokens + Self.tokenCount(in: text))
        accumulatedText += text
    }

    private func makeOverflowCompleted(
        from event: Melix_Worker_V1_ExecuteEvent,
        assistantText: String? = nil
    ) -> Melix_Worker_V1_ExecuteEvent {
        var completedEvent = event
        completedEvent.completed.finishReason = "reasoning_budget_exceeded"
        completedEvent.completed.assistantText = assistantText ?? event.completed.assistantText
        completedEvent.completed.reasoningText = accumulatedText
        return completedEvent
    }

    private static func tokenCount(in text: String) -> UInt32 {
        UInt32(text.split(whereSeparator: \.isWhitespace).count)
    }

    private static func prefix(_ text: String, limitedTo tokenLimit: UInt32) -> String {
        guard tokenLimit > 0 else {
            return ""
        }

        var tokensSeen: UInt32 = 0
        var inToken = false
        var endIndex = text.startIndex

        for index in text.indices {
            let character = text[index]
            if character.isWhitespace {
                inToken = false
            } else if !inToken {
                tokensSeen += 1
                inToken = true
                if tokensSeen > tokenLimit {
                    break
                }
            }
            if tokensSeen <= tokenLimit {
                endIndex = text.index(after: index)
            }
        }

        var prefix = String(text[..<endIndex])
        while let lastCharacter = prefix.last, lastCharacter.isWhitespace {
            prefix.removeLast()
        }
        return prefix
    }
}

public actor RequestCoordinator {
    private let workerRegistry: WorkerRegistry
    private let abortRegistry: AbortRegistry
    private let admissionGate: AdmissionGate
    private let schedulerReadModel: SchedulerReadModel
    private let metricsStore: MetricsStore
    private let modelCatalog: ModelCatalog?
    private let sessionGraphStore: SessionGraphStore?
    private let cacheMetadataStore: CacheMetadataStore?
    private let now: @Sendable () -> Date
    private let lifecyclePolicy: ConnectionLifecyclePolicy
    private var activeWorkerClients: [String: any WorkerClient]
    private var executionHubs: [String: ResumableExecutionHub]
    private var disconnectGraceTasks: [String: Task<Void, Never>]
    private var disconnectStartedAt: [String: Date]
    private var terminalResumeIneligibleRequestIDs: Set<String>
    private var dispatchStartedAt: [String: Date]
    private var disconnectResumeAttemptCount: Double
    private var disconnectResumeSuccessCount: Double
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
        modelCatalog: ModelCatalog? = nil,
        sessionGraphStore: SessionGraphStore? = nil,
        cacheMetadataStore: CacheMetadataStore? = nil,
        lifecyclePolicy: ConnectionLifecyclePolicy = ConnectionLifecyclePolicy.fromEnvironment(),
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.workerRegistry = workerRegistry
        self.abortRegistry = abortRegistry
        self.admissionGate = admissionGate
        self.schedulerReadModel = schedulerReadModel
        self.metricsStore = metricsStore
        self.modelCatalog = modelCatalog
        self.sessionGraphStore = sessionGraphStore
        self.cacheMetadataStore = cacheMetadataStore
        self.lifecyclePolicy = lifecyclePolicy
        self.now = now
        self.activeWorkerClients = [:]
        self.executionHubs = [:]
        self.disconnectGraceTasks = [:]
        self.disconnectStartedAt = [:]
        self.terminalResumeIneligibleRequestIDs = []
        self.dispatchStartedAt = [:]
        self.disconnectResumeAttemptCount = 0
        self.disconnectResumeSuccessCount = 0
        self.requestPlans = [:]
        self.coldTTFTBaselinesByBranch = [:]
        self.schedulingDecisionCount = 0
        self.cacheRouteEligibleCount = 0
        self.warmRoutePreferenceCount = 0
        self.restoredRouteCount = 0
        self.prefixAffinityCheckCount = 0
        self.prefixAffinityHitCount = 0
    }

    public func resumeChatCompletion(requestID: String) async throws -> CoordinatedChatExecution {
        guard !terminalResumeIneligibleRequestIDs.contains(requestID) else {
            throw RequestCoordinatorError.requestNotResumable
        }
        guard let hub = executionHubs[requestID], !(await hub.isTerminal()) else {
            throw RequestCoordinatorError.requestNotResumable
        }

        disconnectResumeAttemptCount += 1
        if let startedAt = disconnectStartedAt.removeValue(forKey: requestID) {
            disconnectGraceTasks.removeValue(forKey: requestID)?.cancel()
            let recoveryLatencyMs = now().timeIntervalSince(startedAt) * 1000
            disconnectResumeSuccessCount += 1
            await metricsStore.set(recoveryLatencyMs, forKey: "disconnect.recovery_latency_ms")
            await metricsStore.set(
                (disconnectResumeSuccessCount / max(1, disconnectResumeAttemptCount)) * 100,
                forKey: "disconnect.resume_success_rate"
            )
            await hub.emitLifecycle(.resumed(recoveryLatencyMs: recoveryLatencyMs))
        } else {
            await metricsStore.set(
                (disconnectResumeSuccessCount / max(1, disconnectResumeAttemptCount)) * 100,
                forKey: "disconnect.resume_success_rate"
            )
        }

        let execution = await hub.makeExecution()
        return CoordinatedChatExecution(
            requestID: execution.requestID,
            modelID: execution.modelID,
            stream: execution.stream,
            lifecycle: execution.lifecycle,
            onStreamDisconnect: { [self] in
                await self.handleLastConsumerDetached(requestID: requestID)
            }
        )
    }

    public func startChatCompletion(
        _ translatedRequest: TranslatedChatRequest,
        requestStartedAt: Date? = nil
    ) async throws -> CoordinatedChatExecution {
        guard !translatedRequest.modelID.isEmpty else {
            throw RequestCoordinatorError.workerUnavailable
        }
        let requestMetricStartedAt = requestStartedAt ?? now()
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
        let initialQueuePosition = await admissionGate.nextQueuePosition(
            cohortID: plan.batchCohortID,
            maxBatchSize: plan.batchMaxSize
        )
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
        _ = await refreshWorkerCacheObservability(using: workerClient)
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

        let admission = await admissionGate.acquire(
            requestID: request.requestID,
            cohortID: plan.batchCohortID,
            maxBatchSize: plan.batchMaxSize
        )
        switch admission.outcome {
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
        await schedulerReadModel.recordContinuousBatchAdmission(
            requestID: request.requestID,
            cohortID: plan.batchCohortID,
            batchPosition: admission.batchPosition,
            batchSize: admission.batchSize,
            batchCapacity: admission.batchCapacity,
            eligible: plan.continuousBatchEligible,
            mergedIntoBatch: admission.mergedIntoBatch,
            affinityClass: plan.cacheRouteClass.rawValue
        )
        _ = await modelCatalog?.markModelUsed(id: request.modelID)
        if !(await abortRegistry.contains(request.requestID)) {
            await finishRequestTracking(requestID: request.requestID, phase: .requestAborted)
            return await makeCancelledExecution(requestID: request.requestID, modelID: request.modelID)
        }

        do {
            let upstream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
            if plan.routeKind.supportsPhaseAwareExecution,
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
            let requestID = request.requestID
            let modelID = request.modelID
            activeWorkerClients[requestID] = workerClient
            self.dispatchStartedAt[requestID] = dispatchStartedAt
            let hub = ResumableExecutionHub(
                requestID: requestID,
                modelID: modelID,
                bufferLimit: lifecyclePolicy.resumeBufferLimit,
                onLastConsumerDetached: { [self] in
                    await self.handleLastConsumerDetached(requestID: requestID)
                }
            )
            executionHubs[requestID] = hub
            let metricsStore = self.metricsStore
            let now = self.now
            let structuredOutputConfiguration = StructuredOutputConfiguration(
                executionExt: request.workerRequest.execution.ext
            )
            let structuredOutputValidator = StructuredOutputValidator()
            let initialReasoningBudget = ReasoningBudgetState(execution: request.workerRequest.execution)
            Task {
                var firstDeltaRecorded = false
                var firstSemanticEventRecorded = false
                var eventCount = 0.0
                var reasoningBudget = initialReasoningBudget

                do {
                    for try await event in upstream {
                        let validatedEvent = try self.validatedStructuredOutputEvent(
                            event,
                            requestID: requestID,
                            configuration: structuredOutputConfiguration,
                            validator: structuredOutputValidator
                        )
                        if validatedEvent.didValidate {
                            if validatedEvent.didFail {
                                await metricsStore.increment("http.structured_output_validation_failure_count")
                            } else {
                                await metricsStore.increment("http.structured_output_validation_pass_count")
                            }
                        }
                        let budgetOutcome: (events: [Melix_Worker_V1_ExecuteEvent], didOverflow: Bool, shouldStop: Bool) =
                            reasoningBudget?.apply(to: validatedEvent.event)
                            ?? (events: [validatedEvent.event], didOverflow: false, shouldStop: false)
                        if budgetOutcome.didOverflow,
                           let reasoningBudget {
                            await metricsStore.increment("http.reasoning_budget_overflow_count")
                            await metricsStore.set(
                                Double(reasoningBudget.limitTokens),
                                forKey: "http.reasoning_budget_limit_tokens"
                            )
                            await metricsStore.set(
                                Double(reasoningBudget.emittedTokens),
                                forKey: "http.reasoning_budget_emitted_tokens"
                            )
                        }
                        for outputEvent in budgetOutcome.events {
                            await self.recordPhaseObservability(
                                requestID: requestID,
                                fallbackLane: plan.decodeLane,
                                requestIdentity: request.workerRequest.execution.id,
                                routeKind: plan.routeKind,
                                event: outputEvent
                            )
                            if !firstSemanticEventRecorded,
                               self.isSemanticStreamEvent(outputEvent) {
                                firstSemanticEventRecorded = true
                                let firstEventMs = now().timeIntervalSince(dispatchStartedAt) * 1000
                                await metricsStore.set(
                                    firstEventMs,
                                    forKey: "http.stream_first_event_ms"
                                )
                            }
                            if !firstDeltaRecorded, case .tokenDelta = outputEvent.payload {
                                firstDeltaRecorded = true
                                let ttftMs = now().timeIntervalSince(dispatchStartedAt) * 1000
                                let followupTTFTMs = now().timeIntervalSince(requestMetricStartedAt) * 1000
                                await metricsStore.set(
                                    ttftMs,
                                    forKey: "http.ttfd_ms"
                                )
                                await self.recordTTFTMetrics(
                                    requestID: requestID,
                                    ttftMs: followupTTFTMs
                                )
                            }
                            switch outputEvent.payload {
                            case .reasoningDelta:
                                await metricsStore.increment("http.reasoning_delta_count")
                            case .toolCallDelta:
                                await metricsStore.increment("http.tool_delta_count")
                            default:
                                break
                            }
                            eventCount += 1
                            await metricsStore.set(eventCount, forKey: "http.stream_event_count")
                            await hub.yield(outputEvent)
                        }
                        if budgetOutcome.shouldStop {
                            _ = try? await workerClient.abort(requestID: requestID)
                            break
                        }
                    }
                    await metricsStore.decrement("requests.inflight")
                    _ = await self.refreshWorkerCacheObservability(using: workerClient)
                    await self.refreshWorkerRuntimeObservability(
                        using: workerClient,
                        routeKind: plan.routeKind
                    )
                    let terminalPhase = await self.terminalPhase(
                        requestID: requestID,
                        fallback: .requestCompleted
                    )
                    await hub.emitLifecycle(.completed)
                    await hub.finish()
                    await self.finishRequestTracking(requestID: requestID, phase: terminalPhase)
                } catch {
                    await metricsStore.decrement("requests.inflight")
                    _ = await self.refreshWorkerCacheObservability(using: workerClient)
                    await self.refreshWorkerRuntimeObservability(
                        using: workerClient,
                        routeKind: plan.routeKind
                    )
                    await hub.emitLifecycle(.terminalFailure(code: "transport_error", message: error.localizedDescription))
                    await hub.finish(throwing: error)
                    await self.finishRequestTracking(requestID: requestID, phase: .requestFailed)
                }
            }

            let execution = await hub.makeExecution()
            return CoordinatedChatExecution(
                requestID: execution.requestID,
                modelID: execution.modelID,
                stream: execution.stream,
                lifecycle: execution.lifecycle,
                onStreamDisconnect: { [self] in
                    await self.handleLastConsumerDetached(requestID: requestID)
                }
            )
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
        disconnectGraceTasks.removeValue(forKey: requestID)?.cancel()
        disconnectStartedAt.removeValue(forKey: requestID)
        terminalResumeIneligibleRequestIDs.remove(requestID)
        if let hub = executionHubs[requestID] {
            await hub.emitLifecycle(.cancelled)
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
        disconnectGraceTasks.removeValue(forKey: requestID)?.cancel()
        disconnectStartedAt.removeValue(forKey: requestID)
        terminalResumeIneligibleRequestIDs.remove(requestID)
        dispatchStartedAt.removeValue(forKey: requestID)
        await admissionGate.release(requestID: requestID)
        await abortRegistry.finish(requestID: requestID)
        activeWorkerClients.removeValue(forKey: requestID)
        executionHubs.removeValue(forKey: requestID)
        requestPlans.removeValue(forKey: requestID)
        if let phase {
            await schedulerReadModel.recordTerminalState(requestID: requestID, phase: phase)
        }
    }

    private func handleLastConsumerDetached(requestID: String) async {
        guard disconnectGraceTasks[requestID] == nil else {
            return
        }
        guard disconnectStartedAt[requestID] == nil else {
            return
        }
        let detachedAt = now()
        disconnectStartedAt[requestID] = detachedAt
        guard let hub = executionHubs[requestID], !(await hub.isTerminal()) else {
            disconnectStartedAt.removeValue(forKey: requestID)
            return
        }
        await metricsStore.increment("http.stream_disconnect_count")
        if let dispatchStartedAt = dispatchStartedAt[requestID] {
            await metricsStore.set(
                now().timeIntervalSince(dispatchStartedAt) * 1000,
                forKey: "http.stream_disconnect_ms"
            )
        }
        await hub.emitLifecycle(.disconnectGraceStarted(timeoutMs: lifecyclePolicy.disconnectGracePeriod * 1000))
        let graceNanoseconds = UInt64(lifecyclePolicy.disconnectGracePeriod * 1_000_000_000)
        disconnectGraceTasks[requestID] = Task { [self] in
            do {
                try await Task.sleep(nanoseconds: graceNanoseconds)
            } catch {
                return
            }
            guard !Task.isCancelled else {
                return
            }
            await self.handleDisconnectGraceExpiry(requestID: requestID)
        }
    }

    private func handleDisconnectGraceExpiry(requestID: String) async {
        disconnectGraceTasks.removeValue(forKey: requestID)
        guard let hub = executionHubs[requestID], !(await hub.isTerminal()) else {
            disconnectStartedAt.removeValue(forKey: requestID)
            return
        }
        guard !(await hub.hasConsumers()) else {
            disconnectStartedAt.removeValue(forKey: requestID)
            return
        }
        terminalResumeIneligibleRequestIDs.insert(requestID)
        await metricsStore.set(
            disconnectResumeAttemptCount == 0 ? 0 : (disconnectResumeSuccessCount / disconnectResumeAttemptCount) * 100,
            forKey: "disconnect.resume_success_rate"
        )
        await metricsStore.increment("disconnect.terminal_failure_count")
        if let workerClient = activeWorkerClients[requestID] {
            _ = try? await workerClient.abort(requestID: requestID)
        }
        let errorEvent = makeLifecycleFailureEvent(
            requestID: requestID,
            code: "stream_disconnect_timeout",
            message: "The client disconnected and the resume grace period expired."
        )
        await hub.yield(errorEvent)
        await hub.emitLifecycle(.terminalFailure(code: "stream_disconnect_timeout", message: "The client disconnected and the resume grace period expired."))
        await hub.finish()
        await finishRequestTracking(requestID: requestID, phase: .requestFailed)
    }

    private func makeLifecycleFailureEvent(
        requestID: String,
        code: String,
        message: String
    ) -> Melix_Worker_V1_ExecuteEvent {
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionFailed
        event.lane = "text.decode.interactive"
        var errorEvent = Melix_Worker_V1_ErrorEvent()
        errorEvent.error.code = code
        errorEvent.error.message = message
        event.error = errorEvent
        return event
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
        case .error:
            await schedulerReadModel.recordPhaseTransition(
                requestID: requestID,
                phase: .requestFailed,
                laneHint: observedLane,
                workerID: workerSource,
                source: workerSource
            )
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
        !request.execution.cacheHints.restoreSnapshotID.isEmpty
            || request.execution.cacheHints.saveBoundarySnapshot
            || resolvedPrefillChunkTarget(for: request.messages) > 0
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
        let recoveredRequest = await resolvedRecoveryRequest(translatedRequest)
        let request = await resolvedModelAccelerationRequest(recoveredRequest)
        let batchingDefaults = GatewayBatchingExecutionDefaults(executionExt: request.workerRequest.execution.ext)
        let routeKind = await workerRegistry.route(forModelID: request.modelID) ?? .swiftText
        if routeKind.isMultimodalBackgroundRoute {
            let lane = routeKind.defaultSchedulingLane
            let usesPhaseAwareExecution = routeKind.supportsPhaseAwareExecution
                && shouldUsePhaseAwareExecution(for: request.workerRequest)
            return SchedulingPlan(
                translatedRequest: request,
                routeKind: routeKind,
                admissionLane: lane,
                prefillLane: lane,
                decodeLane: lane,
                cacheRouteClass: .cold,
                cacheRouteEligible: usesPhaseAwareExecution,
                prefixAffinityEligible: false,
                prefixAffinityHit: false,
                continuousBatchEligible: false,
                batchCohortID: "",
                batchMaxSize: 1
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
                prefixAffinityHit: false,
                continuousBatchEligible: isContinuousBatchEligible(
                    request: request,
                    routeKind: routeKind,
                    prefillLane: prefillLane,
                    batchingDefaults: batchingDefaults
                ),
                batchCohortID: continuousBatchCohortID(
                    request: request,
                    routeKind: routeKind,
                    prefillLane: prefillLane,
                    cacheRouteClass: .cold
                ),
                batchMaxSize: resolvedContinuousBatchSize(
                    request: request,
                    routeKind: routeKind,
                    prefillLane: prefillLane,
                    batchingDefaults: batchingDefaults
                )
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

        let continuousBatchEligible = isContinuousBatchEligible(
            request: request,
            routeKind: routeKind,
            prefillLane: prefillLane,
            batchingDefaults: batchingDefaults
        )
        return SchedulingPlan(
            translatedRequest: request,
            routeKind: routeKind,
            admissionLane: prefillLane,
            prefillLane: prefillLane,
            decodeLane: decodeLane,
            cacheRouteClass: cacheRouteClass,
            cacheRouteEligible: cacheRouteEligible,
            prefixAffinityEligible: prefixAffinityEligible,
            prefixAffinityHit: prefixAffinityHit,
            continuousBatchEligible: continuousBatchEligible,
            batchCohortID: continuousBatchEligible
                ? continuousBatchCohortID(
                    request: request,
                    routeKind: routeKind,
                    prefillLane: prefillLane,
                    cacheRouteClass: cacheRouteClass
                )
                : "",
            batchMaxSize: continuousBatchEligible
                ? resolvedContinuousBatchSize(
                    request: request,
                    routeKind: routeKind,
                    prefillLane: prefillLane,
                    batchingDefaults: batchingDefaults
                )
                : 1
        )
    }

    private func resolvedModelAccelerationRequest(
        _ translatedRequest: TranslatedChatRequest
    ) async -> TranslatedChatRequest {
        guard
            let modelCatalog,
            let model = await modelCatalog.model(id: translatedRequest.modelID)
        else {
            return translatedRequest
        }

        var workerRequest = translatedRequest.workerRequest
        if workerRequest.execution.acceleration.mode == .unspecified {
            workerRequest.execution.acceleration.mode = workerAccelerationMode(
                from: model.settings.defaultAccelerationMode
            )
        }

        if workerRequest.execution.acceleration.profileID.isEmpty,
           !model.settings.accelerationProfileID.isEmpty {
            workerRequest.execution.acceleration.profileID = model.settings.accelerationProfileID
        }

        switch workerRequest.execution.acceleration.mode {
        case .activeKvQuantized:
            if workerRequest.execution.acceleration.activeKvQuantProfile.isEmpty {
                workerRequest.execution.acceleration.activeKvQuantProfile = model.settings.accelerationProfileID
            }
        case .acceleratedPrefill, .sparsePrefill:
            if workerRequest.execution.acceleration.prefillHint.isEmpty {
                workerRequest.execution.acceleration.prefillHint = model.settings.accelerationProfileID
            }
        default:
            break
        }

        return TranslatedChatRequest(
            requestID: translatedRequest.requestID,
            modelID: translatedRequest.modelID,
            workerRequest: workerRequest,
            stream: translatedRequest.stream
        )
    }

    private func isContinuousBatchEligible(
        request: TranslatedChatRequest,
        routeKind: WorkerRouteKind,
        prefillLane: String,
        batchingDefaults: GatewayBatchingExecutionDefaults
    ) -> Bool {
        guard routeKind == .swiftText else {
            return false
        }
        guard shouldUsePhaseAwareExecution(for: request.workerRequest) else {
            return false
        }
        guard batchingDefaults.concurrentProcessingEnabled else {
            return false
        }
        guard batchingDefaults.effectiveAdmissionBatchSize > 1 else {
            return false
        }
        return prefillLane.hasPrefix("text.prefill.")
    }

    private func resolvedContinuousBatchSize(
        request: TranslatedChatRequest,
        routeKind: WorkerRouteKind,
        prefillLane: String,
        batchingDefaults: GatewayBatchingExecutionDefaults
    ) -> UInt32 {
        isContinuousBatchEligible(
            request: request,
            routeKind: routeKind,
            prefillLane: prefillLane,
            batchingDefaults: batchingDefaults
        ) ? batchingDefaults.effectiveAdmissionBatchSize : 1
    }

    private func continuousBatchCohortID(
        request: TranslatedChatRequest,
        routeKind: WorkerRouteKind,
        prefillLane: String,
        cacheRouteClass: CacheRouteClass
    ) -> String {
        let restoreKey = request.workerRequest.execution.cacheHints.restoreSnapshotID
        let affinityKey: String
        if !restoreKey.isEmpty {
            affinityKey = "restore:\(restoreKey)"
        } else if request.workerRequest.execution.cacheHints.preferHotPrefix {
            affinityKey = "prefer-hot"
        } else {
            affinityKey = cacheRouteClass.rawValue
        }
        return [
            routeKind.rawValue,
            request.modelID,
            prefillLane,
            cacheRouteClass.rawValue,
            affinityKey,
        ].joined(separator: "|")
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

                    let effectiveRestorePlan = prefillResponse.hasRestorePlan
                        ? prefillResponse.restorePlan
                        : nil
                    let effectivePromptTokens = max(
                        prefillResponse.promptTokens,
                        estimatedPromptTokens(for: request.messages)
                    )
                    let effectiveBlockTableID = effectiveRestorePlan?.blockTableID.isEmpty == false
                        ? effectiveRestorePlan?.blockTableID ?? prefillResponse.blockTableID
                        : prefillResponse.blockTableID
                    let effectiveBlockTable = effectiveRestorePlan?.blockTable ?? prefillResponse.blockTable

                    await self.hydrateHeadCacheKey(
                        requestIdentity: request.execution.id,
                        modelID: modelID,
                        blockTable: effectiveBlockTable
                    )
                    if let effectiveRestorePlan {
                        await self.recordRestorePlanMetrics(
                            effectiveRestorePlan,
                            promptTokens: effectivePromptTokens
                        )
                        if let cacheMetadataStore = self.cacheMetadataStore {
                            await cacheMetadataStore.appendRecentRestorePlan(
                                makeControlPlaneRestorePlan(from: effectiveRestorePlan)
                            )
                        }
                    }
                    let restoreStage = self.restoreStageLabel(for: effectiveRestorePlan)
                    let cachePressure = await self.refreshWorkerCacheObservability(using: client) ?? 0
                    let decodeRequest = makeDecodeRequest(
                        from: request,
                        prefillResponse: prefillResponse
                    )
                    // Start decode before surfacing prefill progress so direct worker aborts do not
                    // observe a false-negative gap between prefill cleanup and decode registration.
                    let upstream = try await client.decode(request: decodeRequest)

                    var prefillEvent = makePrefillStartedEvent(
                        request: request,
                        response: prefillResponse,
                        lane: prefillLane
                    )
                    if case .prefillStarted(var payload) = prefillEvent.payload {
                        payload.inputTokens = effectivePromptTokens
                        prefillEvent.prefillStarted = payload
                    }
                    prefillEvent.seq = nextSeq
                    nextSeq += 1
                    continuation.yield(prefillEvent)
                    let prefillChunkBoundaries = makeBoundarySafePrefillChunkBoundaries(
                        messages: request.messages,
                        chunkTokenTarget: prefillRequest.prefillStepSize,
                        restoredTokenCount: effectiveRestorePlan?.restoredTokenCount ?? 0
                    )
                    await self.recordPrefillChunkMetrics(
                        boundaries: prefillChunkBoundaries,
                        chunkTokenTarget: prefillRequest.prefillStepSize
                    )
                    let observedPrefillBoundaries = prefillChunkBoundaries.isEmpty
                        ? [effectivePromptTokens]
                        : prefillChunkBoundaries
                    for boundary in observedPrefillBoundaries {
                        await self.schedulerReadModel.recordPrefillProgress(
                            requestID: request.execution.id.requestID,
                            processedTokens: boundary,
                            totalTokens: effectivePromptTokens,
                            restoreStage: restoreStage,
                            cachePressure: cachePressure,
                            source: "swift-text-worker"
                        )
                        var progressEvent = makePrefillProgressEvent(
                            requestID: request.execution.id.requestID,
                            lane: prefillLane,
                            accelerationMode: prefillResponse.appliedAcceleration.mode,
                            processedTokens: boundary,
                            totalTokens: effectivePromptTokens
                        )
                        progressEvent.seq = nextSeq
                        nextSeq += 1
                        continuation.yield(progressEvent)
                    }
                    if !prefillResponse.restoredSnapshotID.isEmpty {
                        var cacheDecisionEvent = makeCacheDecisionEvent(
                            requestID: request.execution.id.requestID,
                            lane: prefillLane,
                            blockTableID: effectiveBlockTableID,
                            restoredSnapshotID: prefillResponse.restoredSnapshotID,
                            accelerationMode: prefillResponse.appliedAcceleration.mode
                        )
                        cacheDecisionEvent.seq = nextSeq
                        nextSeq += 1
                        continuation.yield(cacheDecisionEvent)
                    }

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
        prefill.prefillStepSize = resolvedPrefillChunkTarget(for: request.messages)
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

    private func makePrefillProgressEvent(
        requestID: String,
        lane: String,
        accelerationMode: Melix_Worker_V1_AccelerationMode,
        processedTokens: UInt32,
        totalTokens: UInt32
    ) -> Melix_Worker_V1_ExecuteEvent {
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "prefill"
        event.phase = .executionPrefilling
        event.admissionState = .admissionAdmitted
        event.lane = lane
        event.accelerationMode = accelerationMode

        var payload = Melix_Worker_V1_PrefillProgress()
        payload.processedTokens = processedTokens
        payload.totalTokens = totalTokens
        event.prefillProgress = payload
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

    private func validatedStructuredOutputEvent(
        _ event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        configuration: StructuredOutputConfiguration?,
        validator: StructuredOutputValidator
    ) throws -> StructuredOutputValidationEvent {
        guard
            let configuration,
            configuration.isEnabled,
            case .completed(let completed) = event.payload
        else {
            return StructuredOutputValidationEvent(
                event: event,
                didValidate: false,
                didFail: false
            )
        }

        let trimmed = completed.assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return StructuredOutputValidationEvent(
                event: event,
                didValidate: false,
                didFail: false
            )
        }

        do {
            try validator.validate(outputText: completed.assistantText, against: configuration)
            return StructuredOutputValidationEvent(
                event: event,
                didValidate: true,
                didFail: false
            )
        } catch let failure as StructuredOutputValidationFailure {
            return StructuredOutputValidationEvent(
                event: makeStructuredOutputValidationFailureEvent(
                    from: event,
                    requestID: requestID,
                    failure: failure
                ),
                didValidate: true,
                didFail: true
            )
        }
    }

    private func makeStructuredOutputValidationFailureEvent(
        from event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        failure: StructuredOutputValidationFailure
    ) -> Melix_Worker_V1_ExecuteEvent {
        var failedEvent = event
        failedEvent.requestID = requestID
        failedEvent.phase = .executionFailed

        var error = Melix_Worker_V1_ErrorStatus()
        error.code = failure.code
        error.message = failure.message
        error.details = failure.details

        var payload = Melix_Worker_V1_ErrorEvent()
        payload.error = error
        failedEvent.error = payload
        return failedEvent
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

    private func recordRestorePlanMetrics(
        _ restorePlan: Melix_Worker_V1_CacheRestorePlan,
        promptTokens: UInt32
    ) async {
        await metricsStore.set(
            Double(restorePlan.restoredTokenCount),
            forKey: "scheduler.restore_plan_restored_tokens"
        )
        await metricsStore.set(
            Double(promptTokens),
            forKey: "scheduler.restore_plan_total_tokens"
        )
        let ratioPct = promptTokens > 0
            ? (Double(restorePlan.restoredTokenCount) / Double(promptTokens) * 100.0)
            : 0
        await metricsStore.set(
            ratioPct,
            forKey: "scheduler.restore_plan_ratio_pct"
        )
        if restorePlan.partial {
            await metricsStore.increment("scheduler.partial_restore_walk_back_count")
            await metricsStore.set(
                ratioPct,
                forKey: "scheduler.partial_restore_last_ratio_pct"
            )
        }
    }

    private func recordPrefillChunkMetrics(
        boundaries: [UInt32],
        chunkTokenTarget: UInt32
    ) async {
        await metricsStore.set(
            Double(boundaries.count),
            forKey: "scheduler.prefill_chunk_count"
        )
        await metricsStore.set(
            Double(chunkTokenTarget),
            forKey: "scheduler.prefill_chunk_target_tokens"
        )
        await metricsStore.set(
            Double(boundaries.last ?? 0),
            forKey: "scheduler.prefill_last_chunk_tokens"
        )
    }

    private func restoreStageLabel(
        for restorePlan: Melix_Worker_V1_CacheRestorePlan?
    ) -> String {
        guard let restorePlan else {
            return "none"
        }
        return restorePlan.partial ? "partial" : "restored"
    }

    private func recordTTFTMetrics(requestID: String, ttftMs: Double) async {
        guard let plan = requestPlans[requestID] else {
            return
        }
        if plan.routeKind.isPhaseAwareTextRoute,
           await schedulerReadModel.hasActiveMultimodalRequests(excluding: requestID) {
            await metricsStore.set(ttftMs, forKey: "scheduler.text_ttft_under_multimodal_ms")
        }
        if plan.routeKind.isPhaseAwareTextRoute,
           await metricsStore.value(forKey: "images.active_jobs") > 0 {
            await metricsStore.set(ttftMs, forKey: "scheduler.text_ttft_under_image_load_ms")
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
        key.fingerprintHash = blockTable.cacheKey.fingerprintHash
        key.scope.modelID = modelID
        key.scope.scopeID = blockTable.scopeID.isEmpty ? blockTable.cacheKey.scopeID : blockTable.scopeID

        _ = await sessionGraphStore.recordSnapshotHydration(
            sessionID: requestIdentity.sessionID,
            branchID: requestIdentity.branchID,
            snapshot: Melix_Controlplane_V1_SnapshotRef(),
            headCacheKey: key
        )
    }

    private func refreshWorkerCacheObservability(
        using workerClient: any WorkerClient
    ) async -> Double? {
        guard let introspectingClient = workerClient as? any CacheIntrospectingWorkerClientProtocol else {
            return nil
        }
        guard
            let runtimeStats = try? await introspectingClient.runtimeStats(),
            let cacheStats = try? await introspectingClient.cacheStats()
        else {
            return nil
        }

        await metricsStore.set(Double(cacheStats.stats.l1Bytes), forKey: "cache.memory_bytes")
        await metricsStore.set(Double(cacheStats.stats.l2Bytes), forKey: "cache.disk_bytes")
        await metricsStore.set(cacheStats.stats.l1HitRate * 100, forKey: "cache.hit_rate")
        await metricsStore.set(cacheStats.stats.l2RestoreHitRate * 100, forKey: "cache.l2_restore_hit_rate")
        await metricsStore.set(cacheStats.stats.compressionRatio * 100, forKey: "cache.compression_ratio")
        let activeCacheMode = makeControlPlaneCacheMode(from: cacheStats.stats.activeMode)
        await metricsStore.set(cacheModeMetricValue(activeCacheMode), forKey: "cache.active_mode")
        let residentBytes = max(Double(runtimeStats.memoryEvidence.residentBytes), 1)
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
        return cachePressure
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
            await metricsStore.set(Double(stats.l1CacheBytes), forKey: "vision.cache_memory_bytes")
            await metricsStore.set(stats.l1HitRate * 100, forKey: "vision.cache_hit_rate")
        case .pythonVLM:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "vision.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "vision.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastFirstTokenLatencyMs, forKey: "vision.vlm_first_token_ms")
            await metricsStore.set(Double(stats.l1CacheBytes), forKey: "vision.cache_memory_bytes")
            await metricsStore.set(stats.l1HitRate * 100, forKey: "vision.cache_hit_rate")
        case .pythonTranscription:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "audio.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessInputBytes),
                forKey: "audio.preprocess_input_bytes"
            )
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastTranscriptionLatencyMs, forKey: "audio.transcription_latency_ms")
            await metricsStore.set(stats.lastAudioDurationSeconds, forKey: "audio.estimated_duration_seconds")
            await metricsStore.set(stats.lastAudioDurationSeconds, forKey: "audio.audio_duration_seconds")
            await metricsStore.set(Double(stats.lastAudioChunkCount), forKey: "audio.chunk_count")
            await metricsStore.set(Double(stats.lastAudioChunkCount), forKey: "audio.audio_chunk_count")
            await metricsStore.set(stats.lastAudioModelLoadLatencyMs, forKey: "audio.model_load_latency_ms")
            await metricsStore.set(
                Double(stats.lastAudioBackendUnavailableCount),
                forKey: "audio.backend_unavailable_count"
            )
            await metricsStore.set(
                Double(stats.lastLanguageFallbackCount),
                forKey: "audio.language_fallback_count"
            )
        case .pythonSpeech:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "audio.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessInputBytes),
                forKey: "audio.preprocess_input_bytes"
            )
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastSpeechLatencyMs, forKey: "audio.speech_latency_ms")
            await metricsStore.set(stats.lastAudioModelLoadLatencyMs, forKey: "audio.model_load_latency_ms")
            await metricsStore.set(
                Double(stats.lastAudioBackendUnavailableCount),
                forKey: "audio.backend_unavailable_count"
            )
            await metricsStore.set(
                Double(stats.lastVoiceFallbackCount),
                forKey: "audio.voice_fallback_count"
            )
            if stats.lastAudioOutputBytes > 0 {
                await metricsStore.set(Double(stats.lastAudioOutputBytes), forKey: "audio.speech_output_bytes")
            }
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
    summary.activeMode = makeControlPlaneCacheMode(from: workerStats.activeMode)
    summary.cacheRoot = workerStats.cacheRoot
    summary.initialCacheBlocks = workerStats.initialCacheBlocks
    summary.supportedModes = workerStats.supportedModes.map(makeControlPlaneCacheMode(from:))
    summary.experimentalModes = workerStats.experimentalModes.map(makeControlPlaneCacheMode(from:))
    summary.supportsPrefixCache = workerStats.supportsPrefixCache
    summary.supportsPagedCache = workerStats.supportsPagedCache
    summary.supportsDiskCache = workerStats.supportsDiskCache
    summary.supportsBoundarySnapshots = workerStats.supportsBoundarySnapshots
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
    key.fingerprintHash = workerKey.fingerprintHash
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
    scope.multimodalAdapterHash = workerScope.multimodalAdapterHash
    scope.scopeID = workerScope.scopeID
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
    case .sparsePrefill:
        return .sparsePrefill
    case .activeKvQuantized:
        return .activeKvQuantized
    case .UNRECOGNIZED:
        return nil
    }
}

private func workerAccelerationMode(
    from controlPlaneMode: Melix_Controlplane_V1_AccelerationMode
) -> Melix_Worker_V1_AccelerationMode {
    switch controlPlaneMode {
    case .unspecified:
        return .unspecified
    case .baseline:
        return .baseline
    case .speculativeDecode:
        return .speculativeDecode
    case .acceleratedPrefill:
        return .acceleratedPrefill
    case .sparsePrefill:
        return .sparsePrefill
    case .activeKvQuantized:
        return .activeKvQuantized
    case .UNRECOGNIZED:
        return .unspecified
    }
}

private func resolvedPrefillChunkTarget(
    for messages: [Melix_Worker_V1_ChatMessage]
) -> UInt32 {
    let chunkBoundaries = makeBoundarySafePrefillChunkBoundaries(
        messages: messages,
        chunkTokenTarget: boundarySafePrefillChunkTargetTokens
    )
    if messagesContainVisionInput(messages) {
        return chunkBoundaries.isEmpty ? 0 : boundarySafePrefillChunkTargetTokens
    }
    return chunkBoundaries.count > 1 ? boundarySafePrefillChunkTargetTokens : 0
}

private func makeBoundarySafePrefillChunkBoundaries(
    messages: [Melix_Worker_V1_ChatMessage],
    chunkTokenTarget: UInt32,
    restoredTokenCount: UInt32 = 0
) -> [UInt32] {
    guard chunkTokenTarget > 0 else {
        return []
    }

    let fragments = promptReuseFragments(from: messages)
    guard !fragments.isEmpty else {
        return []
    }

    var boundaries: [UInt32] = []
    var processedTokens: UInt32 = 0
    var nextBoundary = max(chunkTokenTarget, restoredTokenCount &+ chunkTokenTarget)

    for fragment in fragments {
        processedTokens += fragment.tokenCount
        guard processedTokens > restoredTokenCount else {
            continue
        }

        if processedTokens >= nextBoundary {
            boundaries.append(processedTokens)
            nextBoundary = processedTokens &+ chunkTokenTarget
        }
    }

    if processedTokens > restoredTokenCount,
       boundaries.last != processedTokens {
        boundaries.append(processedTokens)
    }

    return boundaries
}

private func estimatedPromptTokens(
    for messages: [Melix_Worker_V1_ChatMessage]
) -> UInt32 {
    let total = promptReuseFragments(from: messages).reduce(0) { partial, fragment in
        partial + fragment.tokenCount
    }
    if total > 0 {
        return total
    }
    return messages.isEmpty ? 0 : 1
}

private enum PromptReuseFragment: Equatable {
    case role(String)
    case nameToken(String)
    case textToken(String)
    case imageURI(String)
    case imageBytes(Data)
    case audioURI(String)
    case audioBytes(Data)

    var tokenCount: UInt32 {
        switch self {
        case .role:
            return 0
        case .nameToken, .textToken:
            return 1
        case .imageURI, .imageBytes, .audioURI, .audioBytes:
            return 256
        }
    }
}

private func promptReuseFragments(
    from messages: [Melix_Worker_V1_ChatMessage]
) -> [PromptReuseFragment] {
    messages.flatMap { message in
        var fragments: [PromptReuseFragment] = [.role(message.role)]
        fragments += tokenFragments(from: message.name, kind: PromptReuseFragment.nameToken)
        for part in message.parts {
            switch part.part {
            case .text(let text):
                fragments += tokenFragments(from: text, kind: PromptReuseFragment.textToken)
            case .imageUri(let uri):
                fragments.append(.imageURI(uri))
            case .imageBytes(let bytes):
                fragments.append(.imageBytes(Data(bytes)))
            case .audioUri(let uri):
                fragments.append(.audioURI(uri))
            case .audioBytes(let bytes):
                fragments.append(.audioBytes(Data(bytes)))
            case nil:
                continue
            }
        }
        return fragments
    }
}

private func tokenFragments(
    from text: String,
    kind: (String) -> PromptReuseFragment
) -> [PromptReuseFragment] {
    text
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .split(whereSeparator: \.isWhitespace)
        .map(String.init)
        .map(kind)
}

private func messagesContainVisionInput(
    _ messages: [Melix_Worker_V1_ChatMessage]
) -> Bool {
    messages.contains(where: { message in
        message.parts.contains(where: { part in
            switch part.part {
            case .imageUri, .imageBytes:
                return true
            default:
                return false
            }
        })
    })
}
