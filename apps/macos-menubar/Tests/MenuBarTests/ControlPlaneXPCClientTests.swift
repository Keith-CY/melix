import Foundation
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
                event.manifest.artifact = Melix_Worker_V1_QuantizedArtifact()
                event.manifest.artifact.schemaVersion = "melix.quantized_bundle.v1"
                event.manifest.artifact.artifactKind = "upload_receipt"
                event.manifest.artifact.manifestPath = "/tmp/melix-upload/upload.receipt.json"
                event.manifest.artifact.bundlePath = "/tmp/melix-upload/upload.receipt.json"
                event.manifest.artifact.artifactBytes = 64
                event.manifest.artifact.manifestBytes = 32
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-upload/upload.receipt.json"
                event.completed.artifact = Melix_Worker_V1_QuantizedArtifact()
                event.completed.artifact.schemaVersion = "melix.quantized_bundle.v1"
                event.completed.artifact.artifactKind = "upload_receipt"
                event.completed.artifact.manifestPath = "/tmp/melix-upload/upload.receipt.json"
                event.completed.artifact.bundlePath = "/tmp/melix-upload/upload.receipt.json"
                event.completed.artifact.artifactBytes = 64
                event.completed.artifact.manifestBytes = 32
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
            quantProfileID: "",
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
        #expect(result.artifact.artifactKind == "upload_receipt")
        #expect(result.artifact.bundlePath == "/tmp/melix-upload/upload.receipt.json")
        #expect(result.artifact.artifactBytes == 64)
        #expect(result.artifact.manifestBytes == 32)
    }

    @Test("local client runs doctor and bench through control-plane execute")
    func localClientRunsDoctorAndBench() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-xpc-bench.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = XPCScriptedModelOperationsWorkerClient()
        await modelOpsClient.setDoctorResponse({
            var response = Melix_Worker_V1_RunDoctorResponse()
            response.ok = true
            response.reportMarkdown = "# Melix Doctor\n"
            return response
        }())
        await modelOpsClient.setBenchEvents([
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = "bench-456"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.metric = Melix_Worker_V1_BenchMetric()
                event.metric.name = "bench.smoke.ttft_ms"
                event.metric.value = 24.45
                event.metric.unit = "ms"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.completed = Melix_Worker_V1_BenchCompleted()
                event.completed.reportPath = reportPath
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

        let doctor = try await client.runDoctor()
        let bench = try await client.runBench()

        #expect(doctor.contains("Melix Doctor"))
        #expect(bench.reportPath == reportPath)
        #expect(bench.reportMarkdown.contains("Melix Bench"))
        #expect(bench.metrics["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("local client submits image generation through control-plane execute")
    func localClientSubmitsImageGeneration() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = XPCScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "menubar-image-generate"
            response.job.jobID = "menubar-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let job = try await client.generateImage(
            ControlPlaneImageGenerationRequest(
                modelID: "melix-dev-image",
                prompt: "Render a sunrise",
                size: "512x512",
                n: 2
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageGenerateRequest)

        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Render a sunrise")
        #expect(forwardedRequest.size == "512x512")
        #expect(forwardedRequest.n == 2)
        #expect(job.jobID == "menubar-image-generate::image-generate")
        #expect(job.state == .imageJobCompleted)
    }

    @Test("local client submits image edits through control-plane execute")
    func localClientSubmitsImageEdit() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = XPCScriptedImageWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.job.requestID = "menubar-image-edit"
            response.job.jobID = "menubar-image-edit::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let job = try await client.editImage(
            ControlPlaneImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Change the clouds",
                imageURL: "file:///tmp/source.png",
                maskURL: "file:///tmp/mask.png",
                strength: 0.4
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageEditRequest)

        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Change the clouds")
        #expect(forwardedRequest.imageUri == "file:///tmp/source.png")
        #expect(forwardedRequest.maskUri == "file:///tmp/mask.png")
        #expect(forwardedRequest.strength == 0.4)
        #expect(job.jobID == "menubar-image-edit::image-edit")
        #expect(job.operation == "image_edit")
    }

    @Test("local client cancels requests through control-plane execute")
    func localClientCancelsRequestsThroughControlPlaneExecute() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        let cancelled = try await client.cancelRequest(requestID: "req-image-running")
        let request = try #require(await service.lastExecuteRequest)

        #expect(cancelled)
        #expect(request.requestID == "menubar-cancel-req-image-running")
        #expect(request.commandType == "ops.cancel_request")
        #expect(request.ops.cancelRequest.requestID == "req-image-running")
    }

    @Test("local client surfaces cancel request failures")
    func localClientSurfacesCancelRequestFailures() async throws {
        let service = FailingExecuteControlPlaneService(
            code: "not_found",
            message: "Unknown request ID."
        )
        let client = LocalControlPlaneXPCClient(service: service)

        do {
            _ = try await client.cancelRequest(requestID: "req-missing")
            Issue.record("Expected cancelRequest to throw for a failed execute response")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "not_found",
                    message: "Unknown request ID."
                )
            )
        }
    }

    @Test("default image ops doctor bench and cancel client methods throw unimplemented errors")
    func defaultImageOpsDoctorBenchAndCancelClientMethodsThrowUnimplementedErrors() async throws {
        let client = DefaultImagelessControlPlaneXPCClient()

        do {
            _ = try await client.generateImage(ControlPlaneImageGenerationRequest(modelID: "melix-dev-image", prompt: "fox"))
            Issue.record("Expected generateImage to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Image generation is not implemented for this control-plane client."
                )
            )
        }

        do {
            _ = try await client.editImage(
                ControlPlaneImageEditRequest(
                    modelID: "melix-dev-image",
                    prompt: "edit",
                    imageURL: "file:///tmp/source.png"
                )
            )
            Issue.record("Expected editImage to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Image editing is not implemented for this control-plane client."
                )
            )
        }

        do {
            _ = try await client.cancelRequest(requestID: "req-default")
            Issue.record("Expected cancelRequest to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Request cancellation is not implemented for this control-plane client."
                )
            )
        }

        do {
            _ = try await client.runDoctor()
            Issue.record("Expected runDoctor to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Doctor is not implemented for this control-plane client."
                )
            )
        }

        do {
            _ = try await client.runBench()
            Issue.record("Expected runBench to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Bench is not implemented for this control-plane client."
                )
            )
        }
    }

    @Test("local client starts chat through the control plane and streams typed chat events")
    func localClientStartsChatAndStreamsTypedEvents() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")

        let textClient = XPCScriptedChatWorkerClient(events: [
            makeQueuedEvent(requestID: "chat-local"),
            makeReasoningEvent(requestID: "chat-local", text: "trace"),
            makeToolEvent(requestID: "chat-local", callID: "tool-1", toolName: "search", arguments: #"{"q":"melix"}"#),
            makeTokenEvent(requestID: "chat-local", text: "assistant"),
            makeUsageEvent(requestID: "chat-local", promptTokens: 4, completionTokens: 8),
            makeCompletedEvent(requestID: "chat-local", finishReason: "stop", assistant: "assistant", reasoning: "trace"),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient)
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let execution = try await client.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        var events: [ControlPlaneChatStreamEvent] = []
        for try await event in execution.stream {
            events.append(event)
        }

        #expect(execution.modelID == "melix-dev-text")
        #expect(events.contains(where: {
            if case .reasoningDelta("trace") = $0 { return true }
            return false
        }))
        #expect(events.contains(where: {
            if case .toolCallDelta(let callID, let toolName, _) = $0 {
                return callID == "tool-1" && toolName == "search"
            }
            return false
        }))
        #expect(events.contains(where: {
            if case .tokenDelta("assistant") = $0 { return true }
            return false
        }))
    }
}

private struct DefaultImagelessControlPlaneXPCClient: ControlPlaneXPCClient {
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
        ControlPlaneChatExecution(
            requestID: "req-default-chat",
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                continuation.finish()
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        Melix_Controlplane_V1_ServerSnapshot()
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        _ = values
        return Melix_Controlplane_V1_ModelSummary()
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

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
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

private actor RecordingExecuteControlPlaneService: ControlPlaneExecuting {
    private(set) var lastExecuteRequest: Melix_Controlplane_V1_ControlPlaneRequest?

    func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        _ = request
        return Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription {
        _ = request
        return ControlPlaneSubscription(
            subscriptionID: "recording",
            stream: AsyncStream { continuation in
                continuation.finish()
            }
        )
    }

    func unsubscribe(_ subscriptionID: String) async {
        _ = subscriptionID
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
    }

    func execute(_ request: Melix_Controlplane_V1_ControlPlaneRequest) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        lastExecuteRequest = request
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = true
        return response
    }
}

private actor XPCScriptedChatWorkerClient: WorkerRoutingClient {
    private let events: [Melix_Worker_V1_ExecuteEvent]

    init(events: [Melix_Worker_V1_ExecuteEvent]) {
        self.events = events
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        let events = self.events
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.modelHandle = request.model.modelID
        return response
    }
}

private actor XPCScriptedImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    private(set) var lastImageGenerateRequest: Melix_Worker_V1_ImageGenerateRequest?
    private(set) var lastImageEditRequest: Melix_Worker_V1_ImageEditRequest?
    private var imageGenerateResponse = Melix_Worker_V1_ImageGenerateResponse()
    private var imageEditResponse = Melix_Worker_V1_ImageEditResponse()

    func setImageGenerateResponse(_ response: Melix_Worker_V1_ImageGenerateResponse) {
        imageGenerateResponse = response
    }

    func setImageEditResponse(_ response: Melix_Worker_V1_ImageEditResponse) {
        imageEditResponse = response
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        _ = request
        return Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        _ = request
        return Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        _ = request
        return Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        _ = request
        return Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        lastImageGenerateRequest = request
        return imageGenerateResponse
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        lastImageEditRequest = request
        return imageEditResponse
    }
}

private func makeQueuedEvent(requestID: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.queued = Melix_Worker_V1_Queued()
    event.queued.lane = "text.decode.interactive"
    return event
}

private func makeReasoningEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.reasoningDelta = Melix_Worker_V1_ReasoningDelta()
    event.reasoningDelta.text = text
    return event
}

private func makeToolEvent(
    requestID: String,
    callID: String,
    toolName: String,
    arguments: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.toolCallDelta = Melix_Worker_V1_ToolCallDelta()
    event.toolCallDelta.callID = callID
    event.toolCallDelta.toolName = toolName
    event.toolCallDelta.argumentsJsonFragment = arguments
    return event
}

private func makeTokenEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    return event
}

private func makeUsageEvent(
    requestID: String,
    promptTokens: UInt32,
    completionTokens: UInt32
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.usageDelta = Melix_Worker_V1_UsageDelta()
    event.usageDelta.promptTokens = promptTokens
    event.usageDelta.completionTokens = completionTokens
    return event
}

private func makeCompletedEvent(
    requestID: String,
    finishReason: String,
    assistant: String,
    reasoning: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = finishReason
    event.completed.assistantText = assistant
    event.completed.reasoningText = reasoning
    return event
}

private actor XPCScriptedModelOperationsWorkerClient: WorkerRoutingClient, ModelOperationsWorkerClientProtocol {
    private var infoResponse = Melix_Worker_V1_GetModelInfoResponse()
    private var convertEvents: [Melix_Worker_V1_ConvertModelEvent] = []
    private var doctorResponse = Melix_Worker_V1_RunDoctorResponse()
    private var benchEvents: [Melix_Worker_V1_RunBenchEvent] = []

    func setInfoResponse(_ response: Melix_Worker_V1_GetModelInfoResponse) {
        infoResponse = response
    }

    func setConvertEvents(_ events: [Melix_Worker_V1_ConvertModelEvent]) {
        convertEvents = events
    }

    func setDoctorResponse(_ response: Melix_Worker_V1_RunDoctorResponse) {
        doctorResponse = response
    }

    func setBenchEvents(_ events: [Melix_Worker_V1_RunBenchEvent]) {
        benchEvents = events
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

    func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        _ = request
        return doctorResponse
    }

    func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        _ = request
        let events = benchEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }
}
