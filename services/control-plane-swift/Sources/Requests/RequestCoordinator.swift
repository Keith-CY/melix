import Foundation
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
    private let metricsStore: MetricsStore
    private let now: @Sendable () -> Date
    private var activeWorkerClients: [String: any WorkerClient]

    public init(
        workerRegistry: WorkerRegistry,
        abortRegistry: AbortRegistry = AbortRegistry(),
        metricsStore: MetricsStore = MetricsStore(),
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.workerRegistry = workerRegistry
        self.abortRegistry = abortRegistry
        self.metricsStore = metricsStore
        self.now = now
        self.activeWorkerClients = [:]
    }

    public func startChatCompletion(
        _ request: TranslatedChatRequest
    ) async throws -> CoordinatedChatExecution {
        guard await abortRegistry.begin(requestID: request.requestID) else {
            throw RequestCoordinatorError.requestAlreadyActive
        }
        let routeStartedAt = now()
        guard let workerClient = await workerRegistry.client(forModelID: request.modelID) else {
            await abortRegistry.finish(requestID: request.requestID)
            throw RequestCoordinatorError.workerUnavailable
        }
        await metricsStore.set(
            now().timeIntervalSince(routeStartedAt) * 1000,
            forKey: "control_plane.worker_route_ms"
        )

        let connectStartedAt = now()
        guard await workerClient.canDispatchRequests() else {
            await abortRegistry.finish(requestID: request.requestID)
            throw RequestCoordinatorError.workerUnavailable
        }
        await metricsStore.set(
            now().timeIntervalSince(connectStartedAt) * 1000,
            forKey: "control_plane.worker_connect_ms"
        )

        let dispatchStartedAt = now()
        await metricsStore.increment("requests.inflight")
        activeWorkerClients[request.requestID] = workerClient

        do {
            let upstream = try await workerClient.generate(request: request.workerRequest)
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
                        await self.finishRequestTracking(requestID: requestID)
                        continuation.finish()
                    } catch {
                        await metricsStore.decrement("requests.inflight")
                        await self.finishRequestTracking(requestID: requestID)
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
            await abortRegistry.finish(requestID: request.requestID)
            activeWorkerClients.removeValue(forKey: request.requestID)
            throw RequestCoordinatorError.workerUnavailable
        } catch {
            await metricsStore.decrement("requests.inflight")
            await abortRegistry.finish(requestID: request.requestID)
            activeWorkerClients.removeValue(forKey: request.requestID)
            throw error
        }
    }

    public func cancel(requestID: String) async throws -> Bool {
        guard await abortRegistry.contains(requestID) else {
            return false
        }
        guard let workerClient = activeWorkerClients[requestID] else {
            return false
        }

        let startedAt = now()
        let aborted = try await workerClient.abort(requestID: requestID)
        if aborted {
            await metricsStore.set(
                now().timeIntervalSince(startedAt) * 1000,
                forKey: "http.abort_ms"
            )
            await finishRequestTracking(requestID: requestID)
        }
        return aborted
    }

    private func finishRequestTracking(requestID: String) async {
        await abortRegistry.finish(requestID: requestID)
        activeWorkerClients.removeValue(forKey: requestID)
    }
}
