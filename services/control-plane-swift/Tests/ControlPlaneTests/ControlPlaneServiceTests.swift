import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

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
        #expect(response.features.contains("image-jobs"))
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

    @Test("execute handles model.set_policy and updates typed model settings")
    func executeHandlesModelSetPolicyAndUpdatesTypedModelSettings() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "alias": "Melix Text Turbo",
                    "pin_on_load": "true",
                    "memory_policy": "pinned",
                    "default_acceleration_mode": "speculative_decode",
                    "acceleration_profile_id": "draft-q4",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.settings.alias == "Melix Text Turbo")
        #expect(response.model.model.settings.pinOnLoad)
        #expect(response.model.model.settings.memoryPolicy == .memoryResidencyPinned)
        #expect(response.model.model.settings.defaultAccelerationMode == .speculativeDecode)
        #expect(response.model.model.settings.accelerationProfileID == "draft-q4")
    }

    @Test("execute handles model.get_info through the model-operations worker")
    func executeHandlesModelGetInfoThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = true
            response.modelKind = "text"
            response.maxContext = 8192
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

        let response = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let lastRequest = try #require(await modelOpsClient.lastInfoRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "melix-dev-text")
        #expect(response.model.info.ok)
        #expect(response.model.info.modelKind == "text")
        #expect(response.model.info.maxContext == 8192)
        #expect(response.model.info.supportedParsers == ["text", "json"])
    }

    @Test("execute handles model.run_operation through the model-operations worker")
    func executeHandlesModelRunOperationThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.progress = Melix_Worker_V1_ConvertProgress()
                event.progress.stage = "write_artifact"
                event.progress.pct = 0.75
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = #"{"operation":"quantize"}"#
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-ops/quantize.artifact"
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

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8",
                ext: ["target_repo": "melix/upload-target"]
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "melix-dev-text")
        #expect(lastRequest.ext["operation"] == "quantize")
        #expect(lastRequest.weightQuant == "q4")
        #expect(lastRequest.kvQuant == "q8")
        #expect(lastRequest.ext["target_repo"] == "melix/upload-target")
        #expect(response.model.operation.ok)
        #expect(response.model.operation.operation == "quantize")
        #expect(response.model.operation.jobID == "job-123")
        #expect(response.model.operation.stage == "write_artifact")
        #expect(response.model.operation.outputPath == "/tmp/melix-ops/quantize.artifact")
        #expect(response.model.operation.manifestJson == #"{"operation":"quantize"}"#)
    }

    @Test("execute handles image.generate through the image worker and records the image job")
    func executeHandlesImageGenerateThroughTheImageWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [makeWorkerArtifact(jobID: "req-image-generate::image-generate")]
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

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a neon fox",
                size: "512x512",
                n: 2
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageGenerateRequest)
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        #expect(response.ok)
        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Draw a neon fox")
        #expect(forwardedRequest.size == "512x512")
        #expect(forwardedRequest.n == 2)
        #expect(response.image.job.jobID == "req-image-generate::image-generate")
        #expect(response.image.job.state == .imageJobCompleted)
        #expect(snapshot.server.snapshot.imageJobs.contains(where: { $0.jobID == "req-image-generate::image-generate" }))
    }

    @Test("execute handles image.edit through the image worker and records artifact metadata")
    func executeHandlesImageEditThroughTheImageWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.job.requestID = "req-image-edit"
            response.job.jobID = "req-image-edit::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactEditSource, artifactID: "source"),
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactMask, artifactID: "mask"),
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactGenerated, artifactID: "output"),
            ]
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

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "file:///tmp/mask.png",
                strength: 0.6
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageEditRequest)

        #expect(response.ok)
        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Replace the sky")
        #expect(forwardedRequest.imageUri == "file:///tmp/source.png")
        #expect(forwardedRequest.maskUri == "file:///tmp/mask.png")
        #expect(forwardedRequest.strength == 0.6)
        #expect(response.image.job.jobID == "req-image-edit::image-edit")
        #expect(response.image.job.artifacts.count == 3)
        #expect(response.image.job.artifacts.last?.role == .imageArtifactGenerated)
    }

    @Test("execute returns unimplemented for image commands without a kind")
    func executeReturnsUnimplementedForEmptyImageCommands() async throws {
        let service = ControlPlaneService()
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-image-empty"
        request.commandType = "image.empty"
        request.image = Melix_Controlplane_V1_ImageCommand()

        let response = try await service.execute(request)

        #expect(response.ok == false)
        #expect(response.error.code == "unimplemented")
    }

    @Test("execute returns not_ready when image generation is requested before the model is loaded")
    func executeReturnsNotReadyForImageGenerateWithoutLoadedModel() async throws {
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_ready")
    }

    @Test("execute returns unavailable when the image worker is missing")
    func executeReturnsUnavailableForImageGenerateWithoutWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(modelCatalog: modelCatalog)

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
    }

    @Test("execute returns invalid_argument when image edits omit the source image")
    func executeReturnsInvalidArgumentForImageEditWithoutSource() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "",
                maskURI: "",
                strength: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "invalid_argument")
    }

    @Test("execute surfaces worker image.generate failures and records the failed job state")
    func executeSurfacesImageGenerateWorkerFailures() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobFailed
            response.job.error.code = "runtime_error"
            response.job.error.message = "GPU pressure"
            response.error.code = "runtime_error"
            response.error.message = "GPU pressure"
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

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "runtime_error")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "runtime_error")
    }

    @Test("execute fills an implicit image job identifier when the worker omits one")
    func executeFillsImplicitImageJobIdentifier() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate-empty-job"
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

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok)
        #expect(response.image.job.jobID == "req-image-generate::image-generate")
    }

    @Test("execute records a failed image edit when the worker throws")
    func executeRecordsFailedImageEditWhenWorkerThrows() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageEditError(ImageWorkerFailure.synthetic)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "file:///tmp/mask.png",
                strength: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(recordedJob.jobID == "req-image-edit::image-edit")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute records runtime_error when the image worker returns a non-terminal generate state")
    func executeMarksInvalidGenerateTerminalStatesAsRuntimeErrors() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobRunning
            response.job.progress.stage = "render"
            response.job.progress.pct = 0.4
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

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok)
        #expect(response.image.job.state == .imageJobRunning)
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "runtime_error")
    }

    @Test("startChat reuses the request coordinator and streams typed chat events")
    func startChatReusesTheRequestCoordinatorAndStreamsTypedChatEvents() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-service"),
            makeTokenExecuteEvent(requestID: "chat-service", text: "assistant"),
            makeReasoningExecuteEvent(requestID: "chat-service", text: "trace"),
            makeToolExecuteEvent(requestID: "chat-service", callID: "tool-1", toolName: "search", arguments: #"{"q":"melix"}"#),
            makeUsageExecuteEvent(requestID: "chat-service", promptTokens: 3, completionTokens: 5),
            makeCompletedExecuteEvent(requestID: "chat-service", finishReason: "stop", assistant: "assistant", reasoning: "trace"),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient)
        )

        let execution = try await service.startChat(
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
            if case .queued(let lane, _, _) = $0 { return lane == "text.decode.interactive" }
            return false
        }))
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
    }

    @Test("execute maps fallback model policy values")
    func executeMapsFallbackModelPolicyValues() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "type_override": "mlx-text",
                    "ttl_seconds": "600",
                    "pin_on_load": "no",
                    "memory_policy": "ttl",
                    "default_acceleration_mode": "active_kv_quantized",
                    "custom_hint": "prefetch",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.settings.typeOverride == "mlx-text")
        #expect(response.model.model.settings.ttlSeconds == 600)
        #expect(response.model.model.settings.pinOnLoad == false)
        #expect(response.model.model.settings.memoryPolicy == .memoryResidencyTtl)
        #expect(response.model.model.settings.defaultAccelerationMode == .activeKvQuantized)
        #expect(response.model.model.settings.ext["custom_hint"] == "prefetch")
    }

    @Test("execute surfaces structured errors for missing or unavailable model tools")
    func executeSurfacesStructuredErrorsForMissingOrUnavailableModelTools() async throws {
        let unavailableService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(defaultTextClient: NullWorkerClient())
        )

        let missingPolicy = try await unavailableService.execute(
            makeSetModelPolicyRequest(modelID: "missing-model", values: [:])
        )
        let missingInfo = try await unavailableService.execute(
            makeGetModelInfoRequest(modelID: "missing-model")
        )
        let unavailableInfo = try await unavailableService.execute(
            makeGetModelInfoRequest(modelID: "melix-dev-text")
        )
        let unavailableOperation = try await unavailableService.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8"
            )
        )

        #expect(!missingPolicy.ok)
        #expect(missingPolicy.error.code == "not_found")
        #expect(!missingInfo.ok)
        #expect(missingInfo.error.code == "not_found")
        #expect(!unavailableInfo.ok)
        #expect(unavailableInfo.error.code == "unavailable")
        #expect(!unavailableOperation.ok)
        #expect(unavailableOperation.error.code == "unavailable")
    }

    @Test("execute surfaces worker-side failures for model info and model operations")
    func executeSurfacesWorkerSideFailuresForModelInfoAndOperations() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = false
            response.error = Melix_Worker_V1_ErrorStatus()
            response.error.code = "invalid_model"
            response.error.message = "Model metadata unavailable."
            return response
        }())
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-failed"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.failed = Melix_Worker_V1_ConvertFailed()
                event.failed.error = Melix_Worker_V1_ErrorStatus()
                event.failed.error.code = "convert_failed"
                event.failed.error.message = "Quantization failed."
                event.failed.error.retriable = false
                return event
            }(),
            Melix_Worker_V1_ConvertModelEvent(),
        ])

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let infoResponse = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let operationResponse = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8"
            )
        )

        #expect(!infoResponse.ok)
        #expect(infoResponse.error.code == "invalid_model")
        #expect(infoResponse.error.message == "Model metadata unavailable.")
        #expect(!operationResponse.ok)
        #expect(operationResponse.error.code == "convert_failed")
        #expect(operationResponse.error.message == "Quantization failed.")
    }

    @Test("execute surfaces thrown model info and operation worker errors")
    func executeSurfacesThrownModelInfoAndOperationWorkerErrors() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoError(TestWorkerError(description: "info transport down"))
        await modelOpsClient.setConvertError(TestWorkerError(description: "operation transport down"))

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let infoResponse = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let operationResponse = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "upload",
                outputDir: "/tmp/melix-upload",
                weightQuant: "",
                kvQuant: ""
            )
        )

        #expect(!infoResponse.ok)
        #expect(infoResponse.error.code == "unavailable")
        #expect(infoResponse.error.message.contains("info transport down"))
        #expect(!operationResponse.ok)
        #expect(operationResponse.error.code == "unavailable")
        #expect(operationResponse.error.message.contains("operation transport down"))
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

    private func makeImageGenerateRequest(
        modelID: String,
        prompt: String,
        size: String,
        n: UInt32
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-image-generate"
        request.commandType = "image.generate"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.generate = Melix_Controlplane_V1_GenerateImage()
        request.image.generate.modelID = modelID
        request.image.generate.prompt = prompt
        request.image.generate.size = size
        request.image.generate.n = n
        request.image.generate.responseFormat = "png"
        return request
    }

    private func makeImageEditRequest(
        modelID: String,
        prompt: String,
        imageURI: String,
        maskURI: String,
        strength: Float
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-image-edit"
        request.commandType = "image.edit"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.edit = Melix_Controlplane_V1_EditImage()
        request.image.edit.modelID = modelID
        request.image.edit.prompt = prompt
        request.image.edit.imageUri = imageURI
        request.image.edit.maskUri = maskURI
        request.image.edit.strength = strength
        request.image.edit.size = "1024x1024"
        request.image.edit.n = 1
        request.image.edit.responseFormat = "png"
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

    private func makeSetModelPolicyRequest(
        modelID: String,
        values: [String: String]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-set-policy-\(modelID)"
        request.commandType = "model.set_policy"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.setPolicy = Melix_Controlplane_V1_SetModelPolicy()
        request.model.setPolicy.modelID = modelID
        request.model.setPolicy.values = values
        return request
    }

    private func makeGetModelInfoRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-get-info-\(modelID)"
        request.commandType = "model.get_info"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.getInfo = Melix_Controlplane_V1_GetModelInfo()
        request.model.getInfo.modelID = modelID
        return request
    }

    private func makeRunModelOperationRequest(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String] = [:]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-run-operation-\(modelID)-\(operation)"
        request.commandType = "model.run_operation"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.runOperation = Melix_Controlplane_V1_RunModelOperation()
        request.model.runOperation.modelID = modelID
        request.model.runOperation.operation = operation
        request.model.runOperation.outputDir = outputDir
        request.model.runOperation.weightQuant = weightQuant
        request.model.runOperation.kvQuant = kvQuant
        request.model.runOperation.generateManifest = true
        request.model.runOperation.runSmokeTest = true
        request.model.runOperation.ext = ext
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

private actor ScriptedImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    private(set) var lastImageGenerateRequest: Melix_Worker_V1_ImageGenerateRequest?
    private(set) var lastImageEditRequest: Melix_Worker_V1_ImageEditRequest?
    private var imageGenerateResponse = Melix_Worker_V1_ImageGenerateResponse()
    private var imageEditResponse = Melix_Worker_V1_ImageEditResponse()
    private var imageGenerateError: Error?
    private var imageEditError: Error?

    func setImageGenerateResponse(_ response: Melix_Worker_V1_ImageGenerateResponse) {
        imageGenerateResponse = response
        imageGenerateError = nil
    }

    func setImageEditResponse(_ response: Melix_Worker_V1_ImageEditResponse) {
        imageEditResponse = response
        imageEditError = nil
    }

    func setImageGenerateError(_ error: Error) {
        imageGenerateError = error
    }

    func setImageEditError(_ error: Error) {
        imageEditError = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        lastImageGenerateRequest = request
        if let imageGenerateError {
            throw imageGenerateError
        }
        return imageGenerateResponse
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        lastImageEditRequest = request
        if let imageEditError {
            throw imageEditError
        }
        return imageEditResponse
    }
}

private enum ImageWorkerFailure: Error {
    case synthetic
}

private func makeWorkerArtifact(
    jobID: String,
    role: Melix_Worker_V1_ImageArtifactRole = .imageArtifactGenerated,
    artifactID: String = "artifact-0"
) -> Melix_Worker_V1_ImageArtifactMetadata {
    var artifact = Melix_Worker_V1_ImageArtifactMetadata()
    artifact.artifactID = "\(jobID)::\(artifactID)"
    artifact.jobID = jobID
    artifact.role = role
    artifact.mimeType = "image/png"
    artifact.format = "png"
    artifact.width = 512
    artifact.height = 512
    artifact.byteLength = 32
    artifact.storageUri = "/tmp/\(artifactID).png"
    artifact.sha256 = "sha256-\(artifactID)"
    artifact.variantIndex = 0
    return artifact
}

private actor ScriptedModelOperationsWorkerClient: WorkerRoutingClient, ModelOperationsWorkerClientProtocol {
    private(set) var lastInfoRequest: Melix_Worker_V1_GetModelInfoRequest?
    private(set) var lastConvertRequest: Melix_Worker_V1_ConvertModelRequest?
    private var infoResponse = Melix_Worker_V1_GetModelInfoResponse()
    private var convertEvents: [Melix_Worker_V1_ConvertModelEvent] = []
    private var infoError: Error?
    private var convertError: Error?

    func setInfoResponse(_ response: Melix_Worker_V1_GetModelInfoResponse) {
        infoResponse = response
    }

    func setConvertEvents(_ events: [Melix_Worker_V1_ConvertModelEvent]) {
        convertEvents = events
    }

    func setInfoError(_ error: Error?) {
        infoError = error
    }

    func setConvertError(_ error: Error?) {
        convertError = error
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
        lastInfoRequest = request
        if let infoError {
            throw infoError
        }
        return infoResponse
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        lastConvertRequest = request
        if let convertError {
            throw convertError
        }
        let events = convertEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }
}

private actor ScriptedChatWorkerClient: WorkerRoutingClient {
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

private func makeQueuedExecuteEvent(requestID: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.queued = Melix_Worker_V1_Queued()
    event.queued.lane = "text.decode.interactive"
    return event
}

private func makeTokenExecuteEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    return event
}

private func makeReasoningExecuteEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.reasoningDelta = Melix_Worker_V1_ReasoningDelta()
    event.reasoningDelta.text = text
    return event
}

private func makeToolExecuteEvent(
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

private func makeUsageExecuteEvent(
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

private func makeCompletedExecuteEvent(
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

private struct TestWorkerError: Error, CustomStringConvertible {
    let description: String
}
