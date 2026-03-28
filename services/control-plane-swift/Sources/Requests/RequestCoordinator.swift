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
    private let schedulerReadModel: SchedulerReadModel
    private let metricsStore: MetricsStore
    private let now: @Sendable () -> Date
    private var activeWorkerClients: [String: any WorkerClient]

    public init(
        workerRegistry: WorkerRegistry,
        abortRegistry: AbortRegistry = AbortRegistry(),
        schedulerReadModel: SchedulerReadModel = SchedulerReadModel(),
        metricsStore: MetricsStore = MetricsStore(),
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.workerRegistry = workerRegistry
        self.abortRegistry = abortRegistry
        self.schedulerReadModel = schedulerReadModel
        self.metricsStore = metricsStore
        self.now = now
        self.activeWorkerClients = [:]
    }

    public func startChatCompletion(
        _ request: TranslatedChatRequest
    ) async throws -> CoordinatedChatExecution {
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
        await schedulerReadModel.recordQueued(
            requestID: request.requestID,
            laneHint: lane,
            priority: priority,
            queuePosition: 1
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
            let upstream = try await workerClient.generate(request: request.workerRequest)
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
        await abortRegistry.finish(requestID: requestID)
        activeWorkerClients.removeValue(forKey: requestID)
        if let phase {
            await schedulerReadModel.recordTerminalState(requestID: requestID, phase: phase)
        }
    }

    private func recordPhaseObservability(
        requestID: String,
        fallbackLane: String,
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
