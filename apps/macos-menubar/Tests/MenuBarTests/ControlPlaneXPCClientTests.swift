import Testing

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Control Plane XPC Client")
struct ControlPlaneXPCClientTests {
    @Test("local client hydrates from handshake and receives model-state events")
    func localClientHydratesAndSubscribes() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        let handshake = try await client.handshake()
        #expect(handshake.snapshot.serverState == .serverReady)
        #expect(handshake.snapshot.models.first?.modelID == "melix-dev-text")
        #expect(handshake.snapshot.models.first?.state == .modelDiscovered)

        let stream = await client.subscribe(lastSeenSeq: 0)
        let nextEvent = Task {
            var iterator = stream.makeAsyncIterator()
            return try #require(await iterator.next())
        }

        let loaded = try await client.loadModel(modelID: "melix-dev-text")
        let event = try await nextEvent.value

        #expect(loaded.modelID == "melix-dev-text")
        #expect(loaded.state == .modelWarm)
        #expect(event.eventType == "model.state_changed")
        #expect(event.modelState.modelID == "melix-dev-text")
        #expect(event.modelState.state == .modelWarm)
    }

    @Test("local client unloads the model through control-plane execute")
    func localClientUnloadsModel() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)
        _ = try await client.loadModel(modelID: "melix-dev-text")

        let unloaded = try await client.unloadModel(modelID: "melix-dev-text")

        #expect(unloaded.modelID == "melix-dev-text")
        #expect(unloaded.state == .modelUnloaded)
    }

    @Test("local client can request a fresh server snapshot through control-plane execute")
    func localClientFetchesServerSnapshot() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        let snapshot = try await client.serverSnapshot()

        #expect(snapshot.serverState == .serverReady)
        #expect(snapshot.models.first?.modelID == "melix-dev-text")
        #expect(snapshot.queues.lanes.contains(where: { $0.laneID == "text.decode.interactive" }))
    }

    @Test("load and unload surface request failures for unknown models")
    func loadAndUnloadSurfaceRequestFailures() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        do {
            _ = try await client.loadModel(modelID: "missing-model")
            Issue.record("Expected loadModel to throw for an unknown model")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "not_found",
                    message: "Unknown model ID."
                )
            )
        }

        do {
            _ = try await client.unloadModel(modelID: "missing-model")
            Issue.record("Expected unloadModel to throw for an unknown model")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "not_found",
                    message: "Unknown model ID."
                )
            )
        }
    }

    @Test("local client surfaces snapshot request failures")
    func localClientSurfacesSnapshotRequestFailures() async throws {
        let service = FailingExecuteControlPlaneService(
            code: "unavailable",
            message: "Snapshot path unavailable."
        )
        let client = LocalControlPlaneXPCClient(service: service)

        do {
            _ = try await client.serverSnapshot()
            Issue.record("Expected serverSnapshot to throw for a failed execute response")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unavailable",
                    message: "Snapshot path unavailable."
                )
            )
        }
    }

    @Test("local client updates model settings through control-plane execute")
    func localClientUpdatesModelSettings() async throws {
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let model = try await client.updateModelSettings(
            modelID: "melix-dev-text",
            values: [
                "alias": "Melix Text Turbo",
                "pin_on_load": "true",
                "memory_policy": "pinned",
                "default_acceleration_mode": "speculative_decode",
                "acceleration_profile_id": "draft-q4",
            ]
        )

        #expect(model.settings.alias == "Melix Text Turbo")
        #expect(model.settings.pinOnLoad)
        #expect(model.settings.memoryPolicy == .memoryResidencyPinned)
        #expect(model.settings.defaultAccelerationMode == .speculativeDecode)
        #expect(model.settings.accelerationProfileID == "draft-q4")
    }

    @Test("local client fetches model info through the model-operations worker")
    func localClientFetchesModelInfo() async throws {
        let modelOpsClient = XPCScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = true
            response.modelKind = "text"
            response.maxContext = 16384
            response.supportedParsers = ["text", "json"]
            response.supportedModalities = ["text"]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let info = try await client.modelInfo(modelID: "melix-dev-text")

        #expect(info.ok)
        #expect(info.modelKind == "text")
        #expect(info.maxContext == 16384)
        #expect(info.supportedParsers == ["text", "json"])
    }

    @Test("local client runs model operations through the model-operations worker")
    func localClientRunsModelOperation() async throws {
        let modelOpsClient = XPCScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-456"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.progress = Melix_Worker_V1_ConvertProgress()
                event.progress.stage = "write_artifact"
                event.progress.pct = 0.8
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = #"{"operation":"upload"}"#
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-upload/upload.receipt.json"
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let result = try await client.runModelOperation(
            modelID: "melix-dev-text",
            operation: "upload",
            outputDir: "/tmp/melix-upload",
            weightQuant: "",
            kvQuant: "",
            ext: ["target_repo": "melix/upload-target"]
        )

        #expect(result.ok)
        #expect(result.operation == "upload")
        #expect(result.jobID == "job-456")
        #expect(result.stage == "write_artifact")
        #expect(result.outputPath == "/tmp/melix-upload/upload.receipt.json")
        #expect(result.manifestJson == #"{"operation":"upload"}"#)
    }
}

private actor FailingExecuteControlPlaneService: ControlPlaneExecuting {
    private let code: String
    private let message: String

    init(code: String, message: String) {
        self.code = code
        self.message = message
    }

    func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        _ = request
        return Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription {
        _ = request
        return ControlPlaneSubscription(
            subscriptionID: "test",
            stream: AsyncStream { continuation in
                continuation.finish()
            }
        )
    }

    func unsubscribe(_ subscriptionID: String) async {
        _ = subscriptionID
    }

    func execute(_ request: Melix_Controlplane_V1_ControlPlaneRequest) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        _ = request
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = false
        response.error.code = code
        response.error.message = message
        return response
    }
}

private actor XPCScriptedModelOperationsWorkerClient: WorkerRoutingClient, ModelOperationsWorkerClientProtocol {
    private var infoResponse = Melix_Worker_V1_GetModelInfoResponse()
    private var convertEvents: [Melix_Worker_V1_ConvertModelEvent] = []

    func setInfoResponse(_ response: Melix_Worker_V1_GetModelInfoResponse) {
        infoResponse = response
    }

    func setConvertEvents(_ events: [Melix_Worker_V1_ConvertModelEvent]) {
        convertEvents = events
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        _ = request
        return infoResponse
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        _ = request
        let events = convertEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }
}
