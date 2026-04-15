import Foundation
import Testing

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Control Plane XPC Client", .serialized)
struct ControlPlaneXPCClientTests {
    @Test("local client hydrates from handshake and loads the local fast path model")
    func localClientHydratesAndLoadsModel() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        let handshake = try await client.handshake()
        #expect(handshake.snapshot.serverState == .serverReady)
        #expect(handshake.snapshot.models.first?.modelID == "melix-dev-text")
        #expect(handshake.snapshot.models.first?.state == .modelDiscovered)

        let loaded = try await client.loadModel(modelID: "melix-dev-text")
        let snapshot = try await client.serverSnapshot()
        let hydrated = try #require(snapshot.models.first(where: { $0.modelID == "melix-dev-text" }))

        #expect(loaded.modelID == "melix-dev-text")
        #expect(loaded.state == .modelWarm)
        #expect(hydrated.state == .modelWarm)
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

    @Test("local client mutates server lifecycle and idle policy through control-plane execute")
    func localClientMutatesServerLifecycleAndIdlePolicy() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)
        let initialSnapshot = try await client.serverSnapshot()
        let serverSessionID = try #require(initialSnapshot.runtimeSessions.first?.serverSessionID)

        let pausedSnapshot = try await client.pauseServerSession(serverSessionID: serverSessionID)
        let pausedSession = try #require(
            pausedSnapshot.runtimeSessions.first(where: { $0.serverSessionID == serverSessionID })
        )
        #expect(pausedSession.lifecycleState == .paused)

        let idlePolicySnapshot = try await client.updateServerIdlePolicy(
            serverSessionID: serverSessionID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 300,
            deepSleepAfterSeconds: 900
        )
        let idlePolicySession = try #require(
            idlePolicySnapshot.runtimeSessions.first(where: { $0.serverSessionID == serverSessionID })
        )
        #expect(idlePolicySession.autoSleepEnabled)
        #expect(idlePolicySession.lightSleepAfterSeconds == 300)
        #expect(idlePolicySession.deepSleepAfterSeconds == 900)

        let resumedSnapshot = try await client.resumeServerSession(serverSessionID: serverSessionID)
        let resumedSession = try #require(
            resumedSnapshot.runtimeSessions.first(where: { $0.serverSessionID == serverSessionID })
        )
        #expect(resumedSession.lifecycleState == .ready)

        let stoppedSnapshot = try await client.stopServerSession(serverSessionID: serverSessionID)
        let stoppedSession = try #require(
            stoppedSnapshot.runtimeSessions.first(where: { $0.serverSessionID == serverSessionID })
        )
        #expect(stoppedSession.lifecycleState == .stopped)

        let startedSnapshot = try await client.startServerSession(serverSessionID: serverSessionID)
        let startedSession = try #require(
            startedSnapshot.runtimeSessions.first(where: { $0.serverSessionID == serverSessionID })
        )
        #expect(startedSession.lifecycleState == .ready)
    }

    @Test("local client bridges subscription streams and unsubscribes on termination")
    func localClientBridgesSubscriptionStreams() async {
        let service = StreamingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)
        let stream = await client.subscribe(lastSeenSeq: 12)
        var iterator = stream.makeAsyncIterator()

        let firstEvent = await iterator.next()
        _ = iterator

        #expect(await service.lastSubscriptionRequest == 12)
        #expect(firstEvent?.eventType == "bench.progress")
        try? await Task.sleep(nanoseconds: 10_000_000)
        #expect(await service.unsubscribedIDs == ["streaming"])
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

    @Test("protocol default evaluation helper reports an unimplemented error")
    func protocolDefaultEvaluationHelperReportsUnimplemented() async throws {
        let client = DefaultingControlPlaneXPCClient()

        do {
            _ = try await client.runEvaluation(
                ControlPlaneEvaluationRequest(
                    suiteID: "mmlu",
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 1
                )
            )
            Issue.record("Expected the protocol default runEvaluation implementation to throw.")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Evaluation is not implemented for this control-plane client."
                )
            )
        }
    }

    @Test("protocol default bench matrix helper reports an unimplemented error")
    func protocolDefaultBenchMatrixHelperReportsUnimplemented() async throws {
        let client = DefaultingControlPlaneXPCClient()

        do {
            _ = try await client.runBenchMatrix(
                ControlPlaneBenchMatrixRequest(
                    modelID: "melix-dev-text",
                    suites: ["smoke"],
                    contextLengths: [1024],
                    generationLengths: [128],
                    batchSizes: [2],
                    cacheProfiles: ["cold"],
                    reasoningModes: ["enabled"],
                    structuredOutputModes: ["plain_text"],
                    concurrencyLevels: [1],
                    requests: 8
                )
            )
            Issue.record("Expected the protocol default runBenchMatrix implementation to throw.")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Bench matrix is not implemented for this control-plane client."
                )
            )
        }
    }

    @Test("protocol default serving defaults helper reports an unimplemented error")
    func protocolDefaultServingDefaultsHelperReportsUnimplemented() async throws {
        let client = DefaultingControlPlaneXPCClient()

        do {
            _ = try await client.applyServerSessionServingDefaults(
                serverSessionID: "server-session-1",
                temperature: 0.7,
                topP: 1.0,
                maxTokens: 256,
                streamIntervalTokens: 1,
                maxConcurrentRequests: 4,
                concurrentProcessingEnabled: true,
                prefillBatchSize: 2,
                completionBatchSize: 2,
                accelerationMode: .baseline,
                draftModelID: "",
                numDraftTokens: 0
            )
            Issue.record("Expected the protocol default applyServerSessionServingDefaults implementation to throw.")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Serving defaults apply is not implemented for this control-plane client."
                )
            )
        }
    }

    @Test("protocol default image defaults helper reports an unimplemented error")
    func protocolDefaultImageDefaultsHelperReportsUnimplemented() async throws {
        let client = DefaultingControlPlaneXPCClient()

        do {
            _ = try await client.applyImageDefaults(
                ControlPlaneImageDefaultsRequest(
                    generateModelID: "melix-dev-image",
                    editModelID: "melix-dev-image",
                    size: "1024x1024",
                    steps: 28,
                    guidance: 7.5,
                    strength: 0.8,
                    negativePrompt: "noise"
                )
            )
            Issue.record("Expected the protocol default applyImageDefaults implementation to throw.")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Image defaults apply is not implemented for this control-plane client."
                )
            )
        }
    }

    @Test("protocol default load helper forwards to the legacy load entry point")
    func protocolDefaultLoadHelperForwardsToLegacyLoadEntryPoint() async throws {
        let client = DefaultingControlPlaneXPCClient()

        _ = try await client.loadModel(modelID: "melix-dev-text", memoryBudgetBytes: 65_536)

        #expect(await client.lastLoadModelID == "melix-dev-text")
        #expect(await client.loadCallCount == 1)
    }

    @Test("local client builds quantize requests with a typed quant profile")
    func localClientBuildsQuantizeRequestsWithTypedQuantProfile() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        _ = try await client.runModelOperation(
            modelID: "melix-dev-text",
            operation: "quantize",
            outputDir: "/tmp/melix-quantize",
            quantProfileID: "q6",
            weightQuant: "q6",
            kvQuant: "q4",
            ext: ["target_repo": "melix/demo-quantized"]
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.model.runOperation.generateManifest)
        #expect(request.model.runOperation.runSmokeTest)
        #expect(request.model.runOperation.quantProfile.algorithm == "oq")
        #expect(request.model.runOperation.quantProfile.schemaVersion == "melix.quant_profile.v1")
        #expect(request.model.runOperation.quantProfile.quantProfileID == "q6")
        #expect(request.model.runOperation.quantProfile.weightQuant == "q6")
        #expect(request.model.runOperation.quantProfile.kvQuant == "q4")
    }

    @Test("local client builds model load requests with explicit memory budgets")
    func localClientBuildsModelLoadRequestsWithExplicitMemoryBudgets() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        _ = try await client.loadModel(modelID: "melix-dev-text", memoryBudgetBytes: 65_536)
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.commandType == "model.load")
        #expect(request.model.load.modelID == "melix-dev-text")
        #expect(request.model.load.memoryBudgetBytes == 65_536)
    }

    @Test("local client builds model load requests with zero memory budgets by default")
    func localClientBuildsModelLoadRequestsWithZeroMemoryBudgetsByDefault() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        _ = try await client.loadModel(modelID: "melix-dev-text")
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.commandType == "model.load")
        #expect(request.model.load.modelID == "melix-dev-text")
        #expect(request.model.load.memoryBudgetBytes == 0)
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
            response.healthStatus = .healthy
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
        let textClient = XPCScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient
            )
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let doctor = try await client.runDoctor()
        let bench = try await client.runBench(
            ControlPlaneBenchRequest(
                suites: ["smoke"],
                contextLengths: [1024]
            )
        )

        #expect(doctor.markdown.contains("Melix Doctor"))
        #expect(doctor.healthStatus == .healthy)
        #expect(bench.reportPath == reportPath)
        #expect(bench.reportMarkdown.contains("Melix Bench"))
        #expect(bench.metrics["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("local client runs bench matrix through control-plane execute")
    func localClientRunsBenchMatrix() async throws {
        let modelOpsClient = XPCScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchMatrixResponse({
            var response = Melix_Worker_V1_RunBenchMatrixResponse()
            response.job.schemaVersion = "melix.benchmark_matrix_job.v1"
            response.job.jobID = "bench-matrix-456"
            response.job.modelID = "melix-dev-text"
            response.job.taskKind = "text-generation"
            response.job.sourceRepo = "melix-dev-text"
            response.job.suiteIds = ["smoke"]
            response.job.benchmarkMode = "matrix"
            response.job.status = "completed"
            response.job.outputDir = "/tmp/melix/bench/matrix-runs/bench-matrix-456"
            response.job.createdAtUnixMs = 1712200000000
            response.job.updatedAtUnixMs = 1712200005000

            var row = Melix_Worker_V1_BenchmarkMatrixSummaryRow()
            row.jobID = "bench-matrix-456"
            row.taskKind = "text-generation"
            row.sourceRepo = "melix-dev-text"
            row.modelID = "melix-dev-text"
            row.suiteID = "smoke"
            row.contextLength = 1024
            row.generationLength = 128
            row.batchSize = 2
            row.cacheProfile = "cold"
            row.reasoningMode = "enabled"
            row.structuredOutputMode = "plain_text"
            row.concurrencyLevel = 1
            row.repeats = 2
            row.requests = 8
            row.ttftMeanMs = 24.45
            response.summaryRows = [row]
            return response
        }())
        let textClient = XPCScriptedChatWorkerClient(events: [])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                modelOperationsClient: modelOpsClient
            )
        )
        let client = LocalControlPlaneXPCClient(service: service)

        let result = try await client.runBenchMatrix(
            ControlPlaneBenchMatrixRequest(
                modelID: "melix-dev-text",
                suites: ["smoke"],
                contextLengths: [1024],
                generationLengths: [128],
                batchSizes: [2],
                cacheProfiles: ["cold"],
                reasoningModes: ["enabled"],
                structuredOutputModes: ["plain_text"],
                concurrencyLevels: [1],
                repeats: 2,
                requests: 8
            )
        )
        let forwarded = try #require(await modelOpsClient.lastBenchMatrixRequest)

        #expect(forwarded.modelHandle == "melix-dev-text")
        #expect(forwarded.contextLengths == [1024])
        #expect(result.job.jobID == "bench-matrix-456")
        #expect(result.summaryRows.count == 1)
        #expect(result.summaryRows[0].ttftMeanMs == 24.45)
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
                steps: 36,
                guidance: 6.25,
                negativePrompt: "blur",
                n: 2
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageGenerateRequest)

        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Render a sunrise")
        #expect(forwardedRequest.size == "512x512")
        #expect(forwardedRequest.ext["melix.image.steps"] == "36")
        #expect(forwardedRequest.ext["melix.image.guidance"] == "6.25")
        #expect(forwardedRequest.ext["melix.image.negative_prompt"] == "blur")
        #expect(forwardedRequest.n == 2)
        #expect(job.jobID.hasPrefix("menubar-image-generate-"))
        #expect(job.jobID.hasSuffix("::image-generate"))
        #expect(job.state == .imageJobRunning)
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
                strength: 0.4,
                steps: 22,
                guidance: 5.5,
                negativePrompt: "washed out"
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageEditRequest)

        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Change the clouds")
        #expect(forwardedRequest.imageUri == "file:///tmp/source.png")
        #expect(forwardedRequest.maskUri == "file:///tmp/mask.png")
        #expect(forwardedRequest.strength == 0.4)
        #expect(forwardedRequest.ext["melix.image.steps"] == "22")
        #expect(forwardedRequest.ext["melix.image.guidance"] == "5.5")
        #expect(forwardedRequest.ext["melix.image.negative_prompt"] == "washed out")
        #expect(job.jobID.hasPrefix("menubar-image-edit-"))
        #expect(job.jobID.hasSuffix("::image-edit"))
        #expect(job.operation == "image_edit")
    }

    @Test("applyImageDefaults builds image.apply_defaults request")
    func applyImageDefaultsBuildsTypedRequest() async throws {
        let service = RecordingExecuteControlPlaneService()
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = true
        response.image = Melix_Controlplane_V1_ImageReply()
        response.image.imageDefaults = Melix_Controlplane_V1_ImageDefaultsSummary()
        response.image.imageDefaults.requestedGenerateModelID = "melix-qwen-image"
        response.image.imageDefaults.requestedEditModelID = "melix-fill-image"
        response.image.imageDefaults.requestedSize = "1536x1024"
        response.image.imageDefaults.requestedSteps = 40
        response.image.imageDefaults.requestedGuidance = 6.25
        response.image.imageDefaults.requestedStrength = 0.7
        response.image.imageDefaults.requestedNegativePrompt = "noise"
        response.image.imageDefaults.effectiveGenerateModelID = "melix-qwen-image"
        response.image.imageDefaults.effectiveEditModelID = "melix-fill-image"
        response.image.imageDefaults.effectiveSize = "1536x1024"
        response.image.imageDefaults.effectiveSteps = 40
        response.image.imageDefaults.effectiveGuidance = 6.25
        response.image.imageDefaults.effectiveStrength = 0.7
        response.image.imageDefaults.effectiveNegativePrompt = "noise"
        response.image.imageDefaults.source = .operatorOverride
        await service.setExecuteResponse(response)
        let client = LocalControlPlaneXPCClient(service: service)

        let summary = try await client.applyImageDefaults(
            ControlPlaneImageDefaultsRequest(
                generateModelID: "melix-qwen-image",
                editModelID: "melix-fill-image",
                size: "1536x1024",
                steps: 40,
                guidance: 6.25,
                strength: 0.7,
                negativePrompt: "noise"
            )
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID.hasPrefix("menubar-image-defaults-"))
        #expect(request.commandType == "image.apply_defaults")
        #expect(request.image.applyDefaults.generateModelID == "melix-qwen-image")
        #expect(request.image.applyDefaults.editModelID == "melix-fill-image")
        #expect(request.image.applyDefaults.size == "1536x1024")
        #expect(request.image.applyDefaults.steps == 40)
        #expect(request.image.applyDefaults.guidance == 6.25)
        #expect(request.image.applyDefaults.strength == 0.7)
        #expect(request.image.applyDefaults.negativePrompt == "noise")
        #expect(summary.effectiveGenerateModelID == "melix-qwen-image")
        #expect(summary.effectiveEditModelID == "melix-fill-image")
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

    @Test("applyServerSessionGatewayAccess builds server.apply_gateway_access request")
    func applyServerSessionGatewayAccessBuildsTypedRequest() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        try await client.applyServerSessionGatewayAccess(
            serverSessionID: "server-session-123",
            primaryKey: "melix_sk_primary_123",
            keyID: "primary",
            label: "primary",
            tokenHint: "primary"
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID == "menubar-apply-gateway-access-server-session-123")
        #expect(request.commandType == "server.apply_gateway_access")
        #expect(request.targetID == "server-session-123")
        #expect(request.server.applyGatewayAccess.serverSessionID == "server-session-123")
        #expect(request.server.applyGatewayAccess.mode == .apiKeys)
        #expect(request.server.applyGatewayAccess.sharedAccessEnabled)
        #expect(request.server.applyGatewayAccess.primaryKey.keyID == "primary")
        #expect(request.server.applyGatewayAccess.primaryKey.label == "primary")
        #expect(request.server.applyGatewayAccess.primaryKey.tokenHint == "primary")
        #expect(request.server.applyGatewayAccess.primaryKey.token == "melix_sk_primary_123")
    }

    @Test("clearServerSessionGatewayAccess builds server.apply_gateway_access none request")
    func clearServerSessionGatewayAccessBuildsTypedRequest() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        try await client.clearServerSessionGatewayAccess(serverSessionID: "server-session-123")
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID == "menubar-clear-gateway-access-server-session-123")
        #expect(request.commandType == "server.apply_gateway_access")
        #expect(request.targetID == "server-session-123")
        #expect(request.server.applyGatewayAccess.serverSessionID == "server-session-123")
        #expect(request.server.applyGatewayAccess.mode == .none)
        #expect(request.server.applyGatewayAccess.sharedAccessEnabled == false)
        #expect(request.server.applyGatewayAccess.hasPrimaryKey == false)
    }

    @Test("applyServerSessionGatewayConfig builds server.apply_gateway_config request")
    func applyServerSessionGatewayConfigBuildsTypedRequest() async throws {
        let service = RecordingExecuteControlPlaneService()
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = true
        response.server = Melix_Controlplane_V1_ServerReply()
        response.server.snapshot.serverState = .serverReady
        var listener = Melix_Controlplane_V1_GatewayListenerConfigSummary()
        listener.serverSessionID = "server-session-123"
        listener.requestedHost = "0.0.0.0"
        listener.requestedPort = 18080
        listener.effectiveHost = "127.0.0.1"
        listener.effectivePort = 11_434
        listener.servedModelID = "melix-dev-text"
        listener.rateLimitPerMinute = 240
        listener.timeoutSeconds = 90
        listener.source = .operatorOverride
        listener.activeBinding = true
        listener.requiresRestart = true
        response.server.snapshot.gatewayConfig.listeners = [listener]
        await service.setExecuteResponse(response)
        let client = LocalControlPlaneXPCClient(service: service)

        let snapshot = try await client.applyServerSessionGatewayConfig(
            serverSessionID: "server-session-123",
            host: "0.0.0.0",
            port: 18080,
            servedModelID: "melix-dev-text",
            rateLimitPerMinute: 240,
            timeoutSeconds: 90
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID == "menubar-apply-gateway-config-server-session-123")
        #expect(request.commandType == "server.apply_gateway_config")
        #expect(request.targetID == "server-session-123")
        #expect(request.server.applyGatewayConfig.serverSessionID == "server-session-123")
        #expect(request.server.applyGatewayConfig.host == "0.0.0.0")
        #expect(request.server.applyGatewayConfig.port == 18_080)
        #expect(request.server.applyGatewayConfig.servedModelID == "melix-dev-text")
        #expect(request.server.applyGatewayConfig.rateLimitPerMinute == 240)
        #expect(request.server.applyGatewayConfig.timeoutSeconds == 90)
        #expect(snapshot.gatewayConfig.listeners.first?.effectiveHost == "127.0.0.1")
        #expect(snapshot.gatewayConfig.listeners.first?.requiresRestart == true)
    }

    @Test("applyServerSessionServingDefaults builds server.apply_serving_defaults request")
    func applyServerSessionServingDefaultsBuildsTypedRequest() async throws {
        let service = RecordingExecuteControlPlaneService()
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = true
        response.server = Melix_Controlplane_V1_ServerReply()
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-123"
        servingDefaults.requestedTemperature = 0.33
        servingDefaults.requestedTopP = 0.92
        servingDefaults.requestedMaxTokens = 384
        servingDefaults.requestedStreamIntervalTokens = 3
        servingDefaults.requestedMaxConcurrentRequests = 5
        servingDefaults.requestedConcurrentProcessingEnabled = true
        servingDefaults.requestedPrefillBatchSize = 3
        servingDefaults.requestedCompletionBatchSize = 2
        servingDefaults.requestedAccelerationMode = .speculativeDecode
        servingDefaults.requestedDraftModelID = "melix-dev-draft"
        servingDefaults.requestedNumDraftTokens = 6
        response.server.snapshot.servingDefaults.sessions = [servingDefaults]
        await service.setExecuteResponse(response)
        let client = LocalControlPlaneXPCClient(service: service)

        let snapshot = try await client.applyServerSessionServingDefaults(
            serverSessionID: "server-session-123",
            temperature: 0.33,
            topP: 0.92,
            maxTokens: 384,
            streamIntervalTokens: 3,
            maxConcurrentRequests: 5,
            concurrentProcessingEnabled: true,
            prefillBatchSize: 3,
            completionBatchSize: 2,
            accelerationMode: .speculativeDecode,
            draftModelID: "melix-dev-draft",
            numDraftTokens: 6
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID == "menubar-apply-serving-defaults-server-session-123")
        #expect(request.commandType == "server.apply_serving_defaults")
        #expect(request.targetID == "server-session-123")
        #expect(request.server.applyServingDefaults.serverSessionID == "server-session-123")
        #expect(request.server.applyServingDefaults.temperature == 0.33)
        #expect(request.server.applyServingDefaults.topP == 0.92)
        #expect(request.server.applyServingDefaults.maxTokens == 384)
        #expect(request.server.applyServingDefaults.streamIntervalTokens == 3)
        #expect(request.server.applyServingDefaults.maxConcurrentRequests == 5)
        #expect(request.server.applyServingDefaults.concurrentProcessingEnabled == true)
        #expect(request.server.applyServingDefaults.prefillBatchSize == 3)
        #expect(request.server.applyServingDefaults.completionBatchSize == 2)
        #expect(request.server.applyServingDefaults.accelerationMode == .speculativeDecode)
        #expect(request.server.applyServingDefaults.draftModelID == "melix-dev-draft")
        #expect(request.server.applyServingDefaults.numDraftTokens == 6)
        #expect(snapshot.servingDefaults.sessions.first?.requestedTemperature == 0.33)
    }

    @Test("runBench builds ops.run_bench request with explicit model suites and parameters")
    func runBenchBuildsTypedRequestWithExplicitModelSuitesAndParameters() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        _ = try await client.runBench(
            ControlPlaneBenchRequest(
                modelID: "melix-dev-text",
                suites: ["smoke", "latency"],
                parameters: [
                    "sample_size": "8",
                    "batch_factor": "2",
                ]
            )
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID == "menubar-run-bench")
        #expect(request.commandType == "ops.run_bench")
        #expect(request.ops.runBench.modelID == "melix-dev-text")
        #expect(request.ops.runBench.suites == ["smoke", "latency"])
        #expect(request.ops.runBench.parameters["sample_size"] == "8")
        #expect(request.ops.runBench.parameters["batch_factor"] == "2")
    }

    @Test("runBench builds ops.run_bench request with a direct Hugging Face repo target")
    func runBenchBuildsTypedRequestWithDirectHFRepoTarget() async throws {
        let service = RecordingExecuteControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        _ = try await client.runBench(
            ControlPlaneBenchRequest(
                hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                suites: ["smoke"],
                parameters: [
                    "sample_size": "1",
                ]
            )
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.ops.runBench.modelID.isEmpty)
        #expect(request.ops.runBench.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(request.ops.runBench.suites == ["smoke"])
        #expect(request.ops.runBench.parameters["sample_size"] == "1")
    }

    @Test("runEvaluation builds ops.run_evaluation request with direct repo targeting")
    func runEvaluationBuildsTypedRequest() async throws {
        let service = RecordingExecuteControlPlaneService()
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = true
        response.ops = Melix_Controlplane_V1_OpsReply()
        response.ops.evaluationJob = Melix_Controlplane_V1_EvaluationJobSummary()
        response.ops.evaluationJob.jobID = "eval-1"
        response.ops.evaluationJob.suiteID = "mmlu"
        await service.setExecuteResponse(response)
        let client = LocalControlPlaneXPCClient(service: service)

        let result = try await client.runEvaluation(
            ControlPlaneEvaluationRequest(
                hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                sampleSize: 8,
                source: .localCSV(path: "/tmp/eval/mmlu.csv"),
                fieldMapping: .init(
                    systemPath: "system_prompt",
                    inputTextPath: "question",
                    targetPath: "gold_answer",
                    sampleIDPath: "sample_id"
                ),
                profile: .init(
                    profileType: "final_result",
                    resultKind: "text",
                    extractionMode: "heuristic_final",
                    scoringMode: "normalized_exact_match",
                    threshold: 1.0
                ),
                parameters: [
                    "batch_factor": "2",
                    "few_shot": "4",
                ]
            )
        )
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID == "menubar-run-eval-mmlu")
        #expect(request.commandType == "ops.run_evaluation")
        #expect(request.ops.runEvaluation.modelID.isEmpty)
        #expect(request.ops.runEvaluation.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(request.ops.runEvaluation.suiteID == "mmlu")
        #expect(request.ops.runEvaluation.datasetID == "mmlu.dev.v1")
        #expect(request.ops.runEvaluation.sampleSize == 8)
        guard case .localCsv(let source)? = request.ops.runEvaluation.source.kind else {
            Issue.record("Expected the control-plane request to carry a localCsv evaluation source.")
            return
        }

        #expect(source.path == "/tmp/eval/mmlu.csv")
        #expect(request.ops.runEvaluation.fieldMapping.systemPath == "system_prompt")
        #expect(request.ops.runEvaluation.fieldMapping.inputTextPath == "question")
        #expect(request.ops.runEvaluation.fieldMapping.targetPath == "gold_answer")
        #expect(request.ops.runEvaluation.fieldMapping.sampleIDPath == "sample_id")
        #expect(request.ops.runEvaluation.profile.profileType == "final_result")
        #expect(request.ops.runEvaluation.profile.resultKind == "text")
        #expect(request.ops.runEvaluation.profile.extractionMode == "heuristic_final")
        #expect(request.ops.runEvaluation.profile.scoringMode == "normalized_exact_match")
        #expect(request.ops.runEvaluation.profile.threshold == 1.0)
        #expect(request.ops.runEvaluation.parameters["batch_factor"] == "2")
        #expect(result.job.jobID == "eval-1")
        #expect(result.job.suiteID == "mmlu")
    }

    @Test("exportResults builds ops.export_results request and returns the export bundle json")
    func exportResultsBuildsTypedRequest() async throws {
        let service = RecordingExecuteControlPlaneService()
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = true
        response.ops = Melix_Controlplane_V1_OpsReply()
        response.ops.exportBundleJson = #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[],"benchmark_results":[]}"#
        await service.setExecuteResponse(response)
        let client = LocalControlPlaneXPCClient(service: service)

        let result = try await client.exportResults(outputDir: "/tmp/melix-export")
        let request = try #require(await service.lastExecuteRequest)

        #expect(request.requestID == "menubar-export-results")
        #expect(request.commandType == "ops.export_results")
        #expect(request.ops.exportResults.outputDir == "/tmp/melix-export")
        #expect(result.exportBundleJSON.contains("\"export_schema_version\":\"melix.benchmark_export.v1\""))
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

    @Test("default image ops doctor bench export and cancel client methods throw unimplemented errors")
    func defaultImageOpsDoctorBenchExportAndCancelClientMethodsThrowUnimplementedErrors() async throws {
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
            try await client.applyServerSessionGatewayAccess(
                serverSessionID: "server-session-default",
                primaryKey: "melix_sk_default",
                keyID: "primary",
                label: "primary",
                tokenHint: "primary"
            )
            Issue.record("Expected applyServerSessionGatewayAccess to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Gateway access apply is not implemented for this control-plane client."
                )
            )
        }

        do {
            try await client.clearServerSessionGatewayAccess(serverSessionID: "server-session-default")
            Issue.record("Expected clearServerSessionGatewayAccess to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Gateway access clear is not implemented for this control-plane client."
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

        do {
            _ = try await client.exportResults()
            Issue.record("Expected exportResults to throw for the default protocol implementation")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unimplemented",
                    message: "Export results is not implemented for this control-plane client."
                )
            )
        }
    }

    @Test("fake control-plane client records bench actions")
    func fakeControlPlaneClientRecordsBenchActions() async throws {
        let client = FakeControlPlaneXPCClient()

        _ = try await client.runBench(
            ControlPlaneBenchRequest(
                modelID: "melix-dev-text",
                suites: ["smoke"],
                parameters: ["sample_size": "8"]
            )
        )

        #expect(await client.recordedActions.contains("bench"))
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

private actor DefaultingControlPlaneXPCClient: ControlPlaneXPCClient {
    private(set) var lastLoadModelID: String?
    private(set) var loadCallCount = 0

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
        _ = request
        return ControlPlaneChatExecution(
            requestID: "noop",
            modelID: "",
            stream: AsyncThrowingStream { continuation in
                continuation.finish()
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        Melix_Controlplane_V1_ServerSnapshot()
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        lastLoadModelID = modelID
        loadCallCount += 1
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

    func cancelRequest(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func applyServerSessionGatewayAccess(
        serverSessionID: String,
        primaryKey: String,
        keyID: String,
        label: String,
        tokenHint: String
    ) async throws {
        _ = serverSessionID
        _ = primaryKey
        _ = keyID
        _ = label
        _ = tokenHint
    }

    func clearServerSessionGatewayAccess(serverSessionID: String) async throws {
        _ = serverSessionID
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
    private var executeResponse = Melix_Controlplane_V1_ControlPlaneResponse()

    func setExecuteResponse(_ response: Melix_Controlplane_V1_ControlPlaneResponse) {
        executeResponse = response
    }

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
        if executeResponse.ok == false && executeResponse.error.code.isEmpty && executeResponse.error.message.isEmpty {
            executeResponse.ok = true
        }
        return executeResponse
    }
}

private actor StreamingExecuteControlPlaneService: ControlPlaneExecuting {
    private(set) var lastSubscriptionRequest: UInt64?
    private(set) var unsubscribedIDs: [String] = []

    func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        _ = request
        return Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription {
        lastSubscriptionRequest = request.lastSeenSeq
        return ControlPlaneSubscription(
            subscriptionID: "streaming",
            stream: AsyncStream { continuation in
                var event = Melix_Controlplane_V1_ControlPlaneEvent()
                event.eventType = "bench.progress"
                continuation.yield(event)
                continuation.finish()
            }
        )
    }

    func unsubscribe(_ subscriptionID: String) async {
        unsubscribedIDs.append(subscriptionID)
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
    }

    func execute(_ request: Melix_Controlplane_V1_ControlPlaneRequest) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        _ = request
        return Melix_Controlplane_V1_ControlPlaneResponse()
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
        response.ok = true
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
    private var benchMatrixResponse = Melix_Worker_V1_RunBenchMatrixResponse()
    private(set) var lastBenchMatrixRequest: Melix_Worker_V1_RunBenchMatrixRequest?

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

    func setBenchMatrixResponse(_ response: Melix_Worker_V1_RunBenchMatrixResponse) {
        benchMatrixResponse = response
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

    func searchHubModels(
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func getHubModelCard(
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse {
        _ = request
        throw WorkerClientError.unavailable
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

    func runBenchMatrix(
        request: Melix_Worker_V1_RunBenchMatrixRequest
    ) async throws -> Melix_Worker_V1_RunBenchMatrixResponse {
        lastBenchMatrixRequest = request
        return benchMatrixResponse
    }

    func runEvaluation(
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func exportResults(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }
}
