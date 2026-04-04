import Foundation
import SwiftProtobuf
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Python Bridge Worker Client", .serialized)
struct PythonBridgeWorkerClientTests {
    @Test("handshake responses drive dispatch availability")
    func handshakeResponsesDriveDispatchAvailability() async throws {
        var response = Melix_Worker_V1_HandshakeResponse()
        response.protocolVersion = "melix.worker.v1"
        response.runtimeVersion = "dev-runtime"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .handshake,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        #expect(await client.canDispatchRequests())
    }

    @Test("bootstrap worker preparation returns nil for unknown model summaries")
    func bootstrapWorkerPreparationReturnsNilForUnknownModelSummaries() {
        var summary = Melix_Controlplane_V1_ModelSummary()
        summary.modelID = "unknown-model"

        #expect(BootstrapWorkerPreparation.modelSpec(for: summary) == nil)
    }

    @Test("load model returns the worker handle from the bridge")
    func loadModelReturnsWorkerHandle() async throws {
        var request = Melix_Worker_V1_LoadModelRequest()
        request.model = devModel()
        request.pinOnLoad = true

        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let loaded = try await client.loadModel(request: request)

        #expect(loaded.ok)
        #expect(loaded.modelHandle == "melix-dev-text::bridge")
    }

    @Test("unload model returns the bridge acknowledgement")
    func unloadModelReturnsBridgeAcknowledgement() async throws {
        var request = Melix_Worker_V1_UnloadModelRequest()
        request.modelHandle = "melix-dev-text::bridge"

        var response = Melix_Worker_V1_UnloadModelResponse()
        response.ok = true

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .unloadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let unloaded = try await client.unloadModel(request: request)

        #expect(unloaded.ok)
    }

    @Test("generate decodes streamed execute events from the bridge")
    func generateDecodesStreamedExecuteEventsFromTheBridge() async throws {
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-bridge"
        request.execution.modelHandle = "melix-dev-text::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setStreamResponse(
            .generate,
            lines: [
                bridgeMessageLine(message: try makeTokenEvent(requestID: "req-bridge", seq: 1, text: "Echo").serializedData()),
                bridgeMessageLine(message: try makeCompletedEvent(requestID: "req-bridge", seq: 2, finishReason: "stop", assistantText: "Echo").serializedData()),
            ]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let stream = try await client.generate(request: request)
        let events = try await collect(stream)

        #expect(events.count == 2)
        #expect(events[0].tokenDelta.text == "Echo")
        #expect(events[1].completed.finishReason == "stop")
    }

    @Test("prefill and decode bridge methods expose phase-aware execution payloads")
    func prefillAndDecodeBridgeMethodsExposePhaseAwareExecutionPayloads() async throws {
        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-vlm-bridge"
        prefillRequest.execution.modelHandle = "melix-dev-vlm::bridge"
        prefillRequest.returnDecodeHandle = true

        var prefillResponse = Melix_Worker_V1_PrefillResponse()
        prefillResponse.ok = true
        prefillResponse.decodeHandle = "decode-req-vlm-bridge"
        prefillResponse.blockTableID = "vlm-block:req-vlm-bridge"
        prefillResponse.promptTokens = 32

        var decodeRequest = Melix_Worker_V1_DecodeRequest()
        decodeRequest.execution.id.requestID = "req-vlm-bridge"
        decodeRequest.execution.modelHandle = "melix-dev-vlm::bridge"
        decodeRequest.decodeHandle = "decode-req-vlm-bridge"
        decodeRequest.maxOutputTokens = 64

        var decodeStarted = Melix_Worker_V1_ExecuteEvent()
        decodeStarted.requestID = "req-vlm-bridge"
        decodeStarted.executionKind = "decode"
        decodeStarted.seq = 1
        decodeStarted.phase = .executionDecoding
        decodeStarted.decodeStarted = {
            var payload = Melix_Worker_V1_DecodeStarted()
            payload.decodeHandle = "decode-req-vlm-bridge"
            payload.maxOutputTokens = 64
            payload.resumedFromPrefill = true
            return payload
        }()

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .prefill,
            line: bridgeMessageLine(message: try prefillResponse.serializedData())
        )
        await runner.setStreamResponse(
            .decode,
            lines: [
                bridgeMessageLine(message: try decodeStarted.serializedData()),
                bridgeMessageLine(message: try makeTokenEvent(requestID: "req-vlm-bridge", seq: 2, text: "Vision").serializedData()),
                bridgeMessageLine(message: try makeCompletedEvent(requestID: "req-vlm-bridge", seq: 3, finishReason: "stop", assistantText: "Vision").serializedData()),
            ]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let prefilled = try await client.prefill(request: prefillRequest)
        let stream = try await client.decode(request: decodeRequest)
        let events = try await collect(stream)

        #expect(prefilled.ok)
        #expect(prefilled.decodeHandle == "decode-req-vlm-bridge")
        #expect(prefilled.promptTokens == 32)
        #expect(events.count == 3)
        #expect(events[0].decodeStarted.decodeHandle == "decode-req-vlm-bridge")
        #expect(events[1].tokenDelta.text == "Vision")
        #expect(events[2].completed.assistantText == "Vision")
    }

    @Test("abort returns the found bit from the bridge response")
    func abortReturnsFoundBitFromTheBridgeResponse() async throws {
        var response = Melix_Worker_V1_AbortResponse()
        response.ok = true
        response.found = true

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .abort,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let aborted = try await client.abort(requestID: "req-abort")

        #expect(aborted)
    }

    @Test("runtime and cache stats decode unary payloads from the bridge")
    func runtimeAndCacheStatsDecodeUnaryPayloadsFromTheBridge() async throws {
        var runtimeResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
        runtimeResponse.stats.workerState = "idle"
        runtimeResponse.stats.l1CacheBytes = 2_048
        runtimeResponse.stats.l1HitRate = 0.5

        var cacheResponse = Melix_Worker_V1_GetCacheStatsResponse()
        cacheResponse.stats.l1Bytes = 2_048
        cacheResponse.stats.blockCount = 1
        cacheResponse.stats.l1HitRate = 0.5

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .getRuntimeStats,
            line: bridgeMessageLine(message: try runtimeResponse.serializedData())
        )
        await runner.setUnaryResponse(
            .getCacheStats,
            line: bridgeMessageLine(message: try cacheResponse.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let runtimeStats = try await client.runtimeStats()
        let cacheStats = try await client.cacheStats()

        #expect(runtimeStats.stats.l1CacheBytes == 2_048)
        #expect(runtimeStats.stats.l1HitRate == 0.5)
        #expect(cacheStats.stats.l1Bytes == 2_048)
        #expect(cacheStats.stats.blockCount == 1)
        #expect(cacheStats.stats.l1HitRate == 0.5)
    }

    @Test("embed and rerank decode unary payloads from the bridge")
    func embedAndRerankDecodeUnaryPayloadsFromTheBridge() async throws {
        var embedRequest = Melix_Worker_V1_EmbedRequest()
        embedRequest.id.requestID = "embed-bridge"
        embedRequest.modelHandle = "melix-dev-embed::bridge"
        embedRequest.inputs = ["alpha", "beta"]

        var embedResponse = Melix_Worker_V1_EmbedResponse()
        embedResponse.embeddings = [
            {
                var embedding = Melix_Worker_V1_Embedding()
                embedding.values = [0.1, 0.2]
                return embedding
            }(),
            {
                var embedding = Melix_Worker_V1_Embedding()
                embedding.values = [0.3, 0.4]
                return embedding
            }(),
        ]

        var rerankRequest = Melix_Worker_V1_RerankRequest()
        rerankRequest.id.requestID = "rerank-bridge"
        rerankRequest.modelHandle = "melix-dev-rerank::bridge"
        rerankRequest.query = "swift worker"
        rerankRequest.documents = ["swift worker", "python bridge"]
        rerankRequest.topK = 1

        var rerankResponse = Melix_Worker_V1_RerankResponse()
        rerankResponse.items = [
            {
                var item = Melix_Worker_V1_RerankItem()
                item.index = 0
                item.score = 0.95
                return item
            }(),
        ]

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .embed,
            line: bridgeMessageLine(message: try embedResponse.serializedData())
        )
        await runner.setUnaryResponse(
            .rerank,
            line: bridgeMessageLine(message: try rerankResponse.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let embedded = try await client.embed(request: embedRequest)
        let reranked = try await client.rerank(request: rerankRequest)

        #expect(embedded.embeddings.count == 2)
        #expect(embedded.embeddings[0].values == [0.1, 0.2])
        #expect(reranked.items.count == 1)
        #expect(reranked.items[0].index == 0)
        #expect(reranked.items[0].score == 0.95)
    }

    @Test("transcribe and speak decode unary payloads from the bridge")
    func transcribeAndSpeakDecodeUnaryPayloadsFromTheBridge() async throws {
        var transcribeRequest = Melix_Worker_V1_TranscribeRequest()
        transcribeRequest.id.requestID = "transcribe-bridge"
        transcribeRequest.modelHandle = "melix-dev-transcribe::bridge"
        transcribeRequest.audioBytes = Data("hello audio".utf8)
        transcribeRequest.format = "wav"
        transcribeRequest.language = "en"

        var transcribeResponse = Melix_Worker_V1_TranscribeResponse()
        transcribeResponse.text = "hello audio"
        transcribeResponse.language = "en"
        transcribeResponse.durationSeconds = 0.25

        var speakRequest = Melix_Worker_V1_SpeakRequest()
        speakRequest.id.requestID = "speak-bridge"
        speakRequest.modelHandle = "melix-dev-speech::bridge"
        speakRequest.input = "hello speech"
        speakRequest.voice = "alloy"
        speakRequest.format = "wav"

        var speakResponse = Melix_Worker_V1_SpeakResponse()
        speakResponse.audioBytes = Data("speech-bytes".utf8)
        speakResponse.format = "wav"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .transcribe,
            line: bridgeMessageLine(message: try transcribeResponse.serializedData())
        )
        await runner.setUnaryResponse(
            .speak,
            line: bridgeMessageLine(message: try speakResponse.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let transcribed = try await client.transcribe(request: transcribeRequest)
        let spoken = try await client.speak(request: speakRequest)

        #expect(transcribed.text == "hello audio")
        #expect(transcribed.language == "en")
        #expect(transcribed.durationSeconds == 0.25)
        #expect(spoken.audioBytes == Data("speech-bytes".utf8))
        #expect(spoken.format == "wav")
    }

    @Test("image generate and image edit decode unary payloads from the bridge")
    func imageGenerateAndEditDecodeUnaryPayloadsFromTheBridge() async throws {
        var generateRequest = Melix_Worker_V1_ImageGenerateRequest()
        generateRequest.id.requestID = "image-generate-bridge"
        generateRequest.modelHandle = "melix-dev-image::bridge"
        generateRequest.prompt = "red fox"
        generateRequest.size = "256x256"
        generateRequest.responseFormat = "png"

        var generateResponse = Melix_Worker_V1_ImageGenerateResponse()
        generateResponse.images = [Data("generated-image".utf8)]
        generateResponse.job.requestID = "image-generate-bridge"
        generateResponse.job.jobID = "image-generate-bridge::image-generate"
        generateResponse.job.modelHandle = "melix-dev-image::bridge"
        generateResponse.job.operation = "image_generate"

        var editRequest = Melix_Worker_V1_ImageEditRequest()
        editRequest.id.requestID = "image-edit-bridge"
        editRequest.modelHandle = "melix-dev-image::bridge"
        editRequest.prompt = "add glow"
        editRequest.image = Data("source".utf8)
        editRequest.mask = Data("mask".utf8)
        editRequest.size = "256x256"
        editRequest.responseFormat = "png"

        var editResponse = Melix_Worker_V1_ImageEditResponse()
        editResponse.images = [Data("edited-image".utf8)]
        editResponse.job.requestID = "image-edit-bridge"
        editResponse.job.jobID = "image-edit-bridge::image-edit"
        editResponse.job.modelHandle = "melix-dev-image::bridge"
        editResponse.job.operation = "image_edit"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .imageGenerate,
            line: bridgeMessageLine(message: try generateResponse.serializedData())
        )
        await runner.setUnaryResponse(
            .imageEdit,
            line: bridgeMessageLine(message: try editResponse.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let generated = try await client.imageGenerate(request: generateRequest)
        let edited = try await client.imageEdit(request: editRequest)

        #expect(generated.job.jobID == "image-generate-bridge::image-generate")
        #expect(generated.images == [Data("generated-image".utf8)])
        #expect(edited.job.jobID == "image-edit-bridge::image-edit")
        #expect(edited.images == [Data("edited-image".utf8)])
    }

    @Test("model-ops bridge methods decode info doctor and streamed convert or bench events")
    func modelOpsBridgeMethodsDecodeInfoDoctorAndStreamedBenchEvents() async throws {
        var infoRequest = Melix_Worker_V1_GetModelInfoRequest()
        infoRequest.sourceModel = "melix-dev-text"

        var infoResponse = Melix_Worker_V1_GetModelInfoResponse()
        infoResponse.ok = true
        infoResponse.modelKind = "text"
        infoResponse.maxContext = 8192
        infoResponse.supportedParsers = ["text"]

        var convertRequest = Melix_Worker_V1_ConvertModelRequest()
        convertRequest.sourceModel = "melix-dev-text"
        convertRequest.outputDir = "/tmp/model-ops"
        convertRequest.ext["operation"] = "quantize"

        var doctorRequest = Melix_Worker_V1_RunDoctorRequest()
        doctorRequest.modelHandle = "melix-dev-text::bridge"
        doctorRequest.includeCacheDiagnostics = true

        var doctorResponse = Melix_Worker_V1_RunDoctorResponse()
        doctorResponse.ok = true
        doctorResponse.reportMarkdown = "# Melix Doctor\n"

        var started = Melix_Worker_V1_ConvertModelEvent()
        started.started = Melix_Worker_V1_ConvertStarted()
        started.started.jobID = "job-1"

        var completed = Melix_Worker_V1_ConvertModelEvent()
        completed.completed = Melix_Worker_V1_ConvertCompleted()
        completed.completed.outputPath = "/tmp/model-ops/quantize.artifact"

        var benchRequest = Melix_Worker_V1_RunBenchRequest()
        benchRequest.modelHandle = "melix-dev-text::bridge"
        benchRequest.suites = ["smoke"]

        var benchStarted = Melix_Worker_V1_RunBenchEvent()
        benchStarted.started = Melix_Worker_V1_BenchStarted()
        benchStarted.started.jobID = "bench-1"

        var benchCompleted = Melix_Worker_V1_RunBenchEvent()
        benchCompleted.completed = Melix_Worker_V1_BenchCompleted()
        benchCompleted.completed.reportPath = "/tmp/model-ops/bench-report.md"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .getModelInfo,
            line: bridgeMessageLine(message: try infoResponse.serializedData())
        )
        await runner.setUnaryResponse(
            .runDoctor,
            line: bridgeMessageLine(message: try doctorResponse.serializedData())
        )
        await runner.setStreamResponse(
            .convertModel,
            lines: [
                bridgeMessageLine(message: try started.serializedData()),
                bridgeMessageLine(message: try completed.serializedData()),
            ]
        )
        await runner.setStreamResponse(
            .runBench,
            lines: [
                bridgeMessageLine(message: try benchStarted.serializedData()),
                bridgeMessageLine(message: try benchCompleted.serializedData()),
            ]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let info = try await client.getModelInfo(request: infoRequest)
        let doctor = try await client.runDoctor(request: doctorRequest)
        let convertStream = try await client.convertModel(request: convertRequest)
        let events = try await collect(convertStream)
        let benchStream = try await client.runBench(request: benchRequest)
        let benchEvents = try await collect(benchStream)

        #expect(info.ok)
        #expect(info.modelKind == "text")
        #expect(doctor.ok)
        #expect(doctor.reportMarkdown.contains("Melix Doctor"))
        #expect(events.count == 2)
        #expect(events[0].started.jobID == "job-1")
        #expect(events[1].completed.outputPath == "/tmp/model-ops/quantize.artifact")
        #expect(benchEvents.count == 2)
        #expect(benchEvents[0].started.jobID == "bench-1")
        #expect(benchEvents[1].completed.reportPath == "/tmp/model-ops/bench-report.md")
    }

    @Test("model-ops bridge methods decode bench matrix responses")
    func modelOpsBridgeMethodsDecodeBenchMatrixResponses() async throws {
        var request = Melix_Worker_V1_RunBenchMatrixRequest()
        request.modelHandle = "melix-dev-text::bridge"
        request.suiteIds = ["smoke"]
        request.contextLengths = [1024]
        request.generationLengths = [128]
        request.batchSizes = [2]
        request.cacheProfiles = ["cold"]
        request.reasoningModes = ["enabled"]
        request.structuredOutputModes = ["plain_text"]
        request.concurrencyLevels = [1]
        request.repeats = 3
        request.requests = 24

        var response = Melix_Worker_V1_RunBenchMatrixResponse()
        response.job = Melix_Worker_V1_BenchmarkMatrixJobSummary()
        response.job.jobID = "bench-matrix-1"
        response.job.modelID = "melix-dev-text"
        response.job.taskKind = "text-generation"
        response.job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
        response.job.benchmarkMode = "matrix"
        response.job.status = "completed"
        var row = Melix_Worker_V1_BenchmarkMatrixSummaryRow()
        row.jobID = "bench-matrix-1"
        row.suiteID = "smoke"
        row.contextLength = 1024
        row.generationLength = 128
        row.batchSize = 2
        row.cacheProfile = "cold"
        row.reasoningMode = "enabled"
        row.structuredOutputMode = "plain_text"
        row.concurrencyLevel = 1
        row.requests = 24
        row.ttftMeanMs = 24.45
        response.summaryRows = [row]

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .runBenchMatrix,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let matrix = try await client.runBenchMatrix(request: request)

        #expect(matrix.job.jobID == "bench-matrix-1")
        #expect(matrix.job.benchmarkMode == "matrix")
        #expect(matrix.summaryRows.count == 1)
        #expect(matrix.summaryRows[0].ttftMeanMs == 24.45)
    }

    @Test("model-ops bridge methods decode export and submit responses")
    func modelOpsBridgeMethodsDecodeExportAndSubmitResponses() async throws {
        var exportRequest = Melix_Worker_V1_ExportResultsRequest()
        exportRequest.outputDir = "/tmp/model-ops/export"

        var exportResponse = Melix_Worker_V1_ExportResultsResponse()
        exportResponse.ok = true
        exportResponse.exportJson = "{\"kind\":\"benchmark\"}"
        exportResponse.exportPath = "/tmp/model-ops/export.json"

        var submitRequest = Melix_Worker_V1_SubmitResultsRequest()
        submitRequest.outputDir = "/tmp/model-ops/export"
        submitRequest.deviceMetadata["chip"] = "M4 Max"

        var submitResponse = Melix_Worker_V1_SubmitResultsResponse()
        submitResponse.ok = true
        submitResponse.submissionJson = "{\"uploaded\":true}"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .exportResults,
            line: bridgeMessageLine(message: try exportResponse.serializedData())
        )
        await runner.setUnaryResponse(
            .submitResults,
            line: bridgeMessageLine(message: try submitResponse.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let exported = try await client.exportResults(request: exportRequest)
        let submitted = try await client.submitResults(request: submitRequest)

        #expect(exported.ok)
        #expect(exported.exportPath == "/tmp/model-ops/export.json")
        #expect(exported.exportJson.contains("benchmark"))
        #expect(submitted.ok)
        #expect(submitted.submissionJson.contains("uploaded"))
    }

    @Test("model-ops bridge methods decode hub search and model card responses")
    func modelOpsBridgeMethodsDecodeHubSearchAndModelCardResponses() async throws {
        var searchRequest = Melix_Worker_V1_SearchHubModelsRequest()
        searchRequest.query = "qwen"
        searchRequest.pageSize = 5
        searchRequest.cursor = "cursor:page-1"
        searchRequest.mlxOnly = true

        var searchResponse = Melix_Worker_V1_SearchHubModelsResponse()
        searchResponse.ok = true
        searchResponse.nextCursor = "cursor:page-2"
        var searchModel = Melix_Worker_V1_HubModelSummary()
        searchModel.repoID = "mlx-community/Qwen2.5-7B-Instruct-4bit"
        searchModel.author = "mlx-community"
        searchModel.modelName = "Qwen2.5-7B-Instruct-4bit"
        searchModel.summary = "MLX text-generation build"
        searchModel.pipelineTag = "text-generation"
        searchModel.tags = ["mlx", "chat"]
        searchModel.downloads = 321
        searchModel.likes = 12
        searchModel.mlxCompatible = true
        searchModel.libraryName = "transformers"
        searchModel.siblingFiles = ["README.md", "config.json"]
        searchModel.lastModified = "2025-01-26T19:49:28Z"
        searchResponse.models = [searchModel]

        var cardRequest = Melix_Worker_V1_GetHubModelCardRequest()
        cardRequest.repoID = "mlx-community/Qwen2.5-7B-Instruct-4bit"

        var cardResponse = Melix_Worker_V1_GetHubModelCardResponse()
        cardResponse.ok = true
        cardResponse.card.repoID = "mlx-community/Qwen2.5-7B-Instruct-4bit"
        cardResponse.card.author = "mlx-community"
        cardResponse.card.modelName = "Qwen2.5-7B-Instruct-4bit"
        cardResponse.card.summary = "MLX text-generation build"
        cardResponse.card.license = "apache-2.0"
        cardResponse.card.pipelineTag = "text-generation"
        cardResponse.card.tags = ["mlx", "chat"]
        cardResponse.card.downloads = 321
        cardResponse.card.likes = 12
        cardResponse.card.mlxCompatible = true
        cardResponse.card.libraryName = "transformers"
        cardResponse.card.siblingFiles = ["README.md", "config.json", "model.safetensors"]
        cardResponse.card.baseModels = ["Qwen/Qwen2.5-7B-Instruct"]
        cardResponse.card.lastModified = "2025-01-26T19:49:28Z"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .searchHubModels,
            line: bridgeMessageLine(message: try searchResponse.serializedData())
        )
        await runner.setUnaryResponse(
            .getHubModelCard,
            line: bridgeMessageLine(message: try cardResponse.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let search = try await client.searchHubModels(request: searchRequest)
        let card = try await client.getHubModelCard(request: cardRequest)

        #expect(search.ok)
        #expect(search.nextCursor == "cursor:page-2")
        #expect(search.models.count == 1)
        #expect(search.models[0].repoID == "mlx-community/Qwen2.5-7B-Instruct-4bit")
        #expect(search.models[0].mlxCompatible)
        #expect(card.ok)
        #expect(card.card.repoID == "mlx-community/Qwen2.5-7B-Instruct-4bit")
        #expect(card.card.license == "apache-2.0")
        #expect(card.card.baseModels == ["Qwen/Qwen2.5-7B-Instruct"])
    }

    @Test("phase-five preload writes embedding and rerank handles into the model catalog")
    func phaseFivePreloadWritesEmbeddingAndRerankHandlesIntoTheModelCatalog() async throws {
        let runner = ScriptedBridgeRunner()

        var embedLoadResponse = Melix_Worker_V1_LoadModelResponse()
        embedLoadResponse.ok = true
        embedLoadResponse.modelHandle = "melix-dev-embed::bridge"
        await runner.enqueueUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try embedLoadResponse.serializedData())
        )

        var rerankLoadResponse = Melix_Worker_V1_LoadModelResponse()
        rerankLoadResponse.ok = true
        rerankLoadResponse.modelHandle = "melix-dev-rerank::bridge"
        await runner.enqueueUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try rerankLoadResponse.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())

        try await BootstrapWorkerPreparation.preloadPhaseFivePythonModels(
            workerClient: client,
            modelCatalog: catalog
        )

        #expect(await catalog.dispatchHandle(for: "melix-dev-embed") == "melix-dev-embed::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-rerank") == "melix-dev-rerank::bridge")
    }

    @Test("phase-six preload writes multimodal handles into the model catalog")
    func phaseSixPreloadWritesMultimodalHandlesIntoTheModelCatalog() async throws {
        let runner = ScriptedBridgeRunner()
        for handle in [
            "melix-dev-embed::bridge",
            "melix-dev-rerank::bridge",
            "melix-dev-ocr::bridge",
            "melix-dev-vlm::bridge",
            "melix-dev-transcribe::bridge",
            "melix-dev-speech::bridge",
        ] {
            var response = Melix_Worker_V1_LoadModelResponse()
            response.ok = true
            response.modelHandle = handle
            await runner.enqueueUnaryResponse(
                .loadModel,
                line: bridgeMessageLine(message: try response.serializedData())
            )
        }

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSixContractSeedModels())

        try await BootstrapWorkerPreparation.preloadPhaseSixPythonModels(
            workerClient: client,
            modelCatalog: catalog,
            memoryBudgetBytes: 4096
        )

        #expect(await catalog.dispatchHandle(for: "melix-dev-embed") == "melix-dev-embed::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-rerank") == "melix-dev-rerank::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-ocr") == "melix-dev-ocr::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-vlm") == "melix-dev-vlm::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-transcribe") == "melix-dev-transcribe::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-speech") == "melix-dev-speech::bridge")
    }

    @Test("phase-seven preload writes image handles into the model catalog")
    func phaseSevenPreloadWritesImageHandlesIntoTheModelCatalog() async throws {
        let runner = ScriptedBridgeRunner()
        for handle in [
            "melix-dev-embed::bridge",
            "melix-dev-rerank::bridge",
            "melix-dev-ocr::bridge",
            "melix-dev-vlm::bridge",
            "melix-dev-transcribe::bridge",
            "melix-dev-speech::bridge",
            "melix-dev-image::bridge",
        ] {
            var response = Melix_Worker_V1_LoadModelResponse()
            response.ok = true
            response.modelHandle = handle
            await runner.enqueueUnaryResponse(
                .loadModel,
                line: bridgeMessageLine(message: try response.serializedData())
            )
        }

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())

        try await BootstrapWorkerPreparation.preloadPhaseSevenPythonModels(
            workerClient: client,
            modelCatalog: catalog,
            memoryBudgetBytes: 4096
        )

        #expect(await catalog.dispatchHandle(for: "melix-dev-image") == "melix-dev-image::bridge")
    }

    @Test("phase-five unary methods surface helper errors as unavailable")
    func phaseFiveUnaryMethodsSurfaceHelperErrorsAsUnavailable() async throws {
        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(.embed, line: bridgeErrorLine(code: "UNAVAILABLE", message: "embed down"))
        await runner.setUnaryResponse(.rerank, line: bridgeErrorLine(code: "UNAVAILABLE", message: "rerank down"))
        await runner.setUnaryResponse(.getModelInfo, line: bridgeErrorLine(code: "UNAVAILABLE", message: "info down"))

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        var embedRequest = Melix_Worker_V1_EmbedRequest()
        embedRequest.id.requestID = "embed-error"
        embedRequest.modelHandle = "melix-dev-embed::bridge"
        embedRequest.inputs = ["alpha"]

        var rerankRequest = Melix_Worker_V1_RerankRequest()
        rerankRequest.id.requestID = "rerank-error"
        rerankRequest.modelHandle = "melix-dev-rerank::bridge"
        rerankRequest.query = "swift"
        rerankRequest.documents = ["swift", "python"]

        var infoRequest = Melix_Worker_V1_GetModelInfoRequest()
        infoRequest.sourceModel = "melix-dev-text"

        do {
            _ = try await client.embed(request: embedRequest)
            Issue.record("Expected embed bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }

        do {
            _ = try await client.rerank(request: rerankRequest)
            Issue.record("Expected rerank bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }

        do {
            _ = try await client.getModelInfo(request: infoRequest)
            Issue.record("Expected get-model-info bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("audio unary methods surface helper errors as unavailable")
    func audioUnaryMethodsSurfaceHelperErrorsAsUnavailable() async throws {
        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(.transcribe, line: bridgeErrorLine(code: "UNAVAILABLE", message: "transcribe down"))
        await runner.setUnaryResponse(.speak, line: bridgeErrorLine(code: "UNAVAILABLE", message: "speech down"))

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        var transcribeRequest = Melix_Worker_V1_TranscribeRequest()
        transcribeRequest.id.requestID = "transcribe-error"
        transcribeRequest.modelHandle = "melix-dev-transcribe::bridge"
        transcribeRequest.audioBytes = Data("audio".utf8)

        var speakRequest = Melix_Worker_V1_SpeakRequest()
        speakRequest.id.requestID = "speak-error"
        speakRequest.modelHandle = "melix-dev-speech::bridge"
        speakRequest.input = "hello"

        do {
            _ = try await client.transcribe(request: transcribeRequest)
            Issue.record("Expected transcribe bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }

        do {
            _ = try await client.speak(request: speakRequest)
            Issue.record("Expected speak bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("image unary methods surface helper errors as unavailable")
    func imageUnaryMethodsSurfaceHelperErrorsAsUnavailable() async throws {
        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(.imageGenerate, line: bridgeErrorLine(code: "UNAVAILABLE", message: "image generate down"))
        await runner.setUnaryResponse(.imageEdit, line: bridgeErrorLine(code: "UNAVAILABLE", message: "image edit down"))

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        var generateRequest = Melix_Worker_V1_ImageGenerateRequest()
        generateRequest.id.requestID = "image-generate-error"
        generateRequest.modelHandle = "melix-dev-image::bridge"
        generateRequest.prompt = "red fox"
        generateRequest.size = "256x256"

        var editRequest = Melix_Worker_V1_ImageEditRequest()
        editRequest.id.requestID = "image-edit-error"
        editRequest.modelHandle = "melix-dev-image::bridge"
        editRequest.prompt = "add glow"
        editRequest.image = Data("source".utf8)
        editRequest.size = "256x256"

        do {
            _ = try await client.imageGenerate(request: generateRequest)
            Issue.record("Expected image-generate bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }

        do {
            _ = try await client.imageEdit(request: editRequest)
            Issue.record("Expected image-edit bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("unknown bridge payload kinds surface unavailable")
    func unknownBridgePayloadKindsSurfaceUnavailable() async throws {
        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(.transcribe, line: #"{"kind":"mystery"}"#)

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        var request = Melix_Worker_V1_TranscribeRequest()
        request.id.requestID = "transcribe-mystery"
        request.modelHandle = "melix-dev-transcribe::bridge"
        request.audioBytes = Data("audio".utf8)

        do {
            _ = try await client.transcribe(request: request)
            Issue.record("Expected the unknown payload kind to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("convert-model stream surfaces malformed bridge payloads as unavailable")
    func convertModelStreamSurfacesMalformedBridgePayloadsAsUnavailable() async throws {
        let runner = ScriptedBridgeRunner()
        await runner.setStreamResponse(
            .convertModel,
            lines: [#"{"kind":"message","message_b64":"%%%"}"#]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        var convertRequest = Melix_Worker_V1_ConvertModelRequest()
        convertRequest.sourceModel = "melix-dev-text"
        convertRequest.outputDir = "/tmp/model-ops"

        do {
            let stream = try await client.convertModel(request: convertRequest)
            _ = try await collect(stream)
            Issue.record("Expected malformed convert stream to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("bootstrap preload writes the worker handle into the model catalog")
    func bootstrapPreloadWritesTheWorkerHandleIntoTheModelCatalog() async throws {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog()

        let preloaded = try await BootstrapWorkerPreparation.preloadDevTextModel(
            workerClient: client,
            modelCatalog: catalog
        )

        #expect(preloaded)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::bridge")
    }

    @Test("bootstrap worker preparation carries adapter-set hash into worker model specs")
    func bootstrapWorkerPreparationCarriesAdapterSetHashIntoWorkerModelSpecs() throws {
        var summary = ModelCatalog.devTextModel()
        summary.settings.ext["melix.adapter_set_hash"] = "adapter-alpha"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-dev-text")
        #expect(spec.reasoningMode == "adaptive")
        #expect(spec.ext["melix.adapter_set_hash"] == "adapter-alpha")
        #expect(spec.ext["melix.adaptive_thinking.budget_tokens"] == "192")
    }

    @Test("bootstrap worker preparation builds generic text specs for activated derived models")
    func bootstrapWorkerPreparationBuildsGenericTextSpecsForActivatedDerivedModels() throws {
        var summary = ModelCatalog.devTextModel()
        summary.modelID = "melix-dev-text-lora-abcd1234"
        summary.settings.alias = "Melix Dev Adapter Activated"
        summary.settings.ext["melix.model_path"] = "/tmp/melix-derived/model"
        summary.settings.ext["melix.model_revision"] = "derived"
        summary.settings.ext["melix.parser_mode"] = "text"
        summary.settings.ext["melix.reasoning_mode"] = "off"
        summary.settings.ext["melix.adapter_set_hash"] = "adapter-derived-alpha"
        summary.settings.ext["melix.derived_from_adapter"] = "true"
        summary.settings.ext["melix.derived_from_model_id"] = "melix-dev-text"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-dev-text-lora-abcd1234")
        #expect(spec.modelPath == "/tmp/melix-derived/model")
        #expect(spec.modelKind == "text")
        #expect(spec.ext["melix.adapter_set_hash"] == "adapter-derived-alpha")
        #expect(spec.ext["melix.derived_from_adapter"] == "true")
        #expect(spec.ext["melix.derived_from_model_id"] == "melix-dev-text")
    }

    @Test("bootstrap worker preparation carries OCR profile metadata into worker model specs")
    func bootstrapWorkerPreparationCarriesOCRProfileMetadataIntoWorkerModelSpecs() throws {
        let summary = ModelCatalog.devOCRModel()

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-dev-ocr")
        #expect(spec.ext["ocr_prompt_profile_id"] == "ocr-default-v1")
        #expect(spec.ext["ocr_prompt_template"] == "OCR instruction: {prompt}")
        #expect(spec.ext["ocr_auto_prompt"] == "Extract the text from the image exactly as written.")
        #expect(spec.ext["ocr_stop_sequences"] == "<ocr:end>")
        #expect(spec.ext["ocr_sampling_profile_id"] == "ocr-deterministic")
    }

    @Test("bootstrap worker preparation lets built-in audio models override model path from summary metadata")
    func bootstrapWorkerPreparationLetsBuiltInAudioModelsOverrideModelPathFromSummaryMetadata() throws {
        var summary = ModelCatalog.mlxWhisperModel()
        summary.settings.ext["melix.model_path"] = "/tmp/melix-managed-audio/whisper"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-whisper-mlx")
        #expect(spec.modelPath == "/tmp/melix-managed-audio/whisper")
        #expect(spec.ext["melix.audio.backend_id"] == "mlx_audio.stt")
    }

    @Test("bootstrap worker preparation carries VLM family metadata into worker model specs")
    func bootstrapWorkerPreparationCarriesVLMFamilyMetadataIntoWorkerModelSpecs() throws {
        var summary = ModelCatalog.devVLMModel()
        summary.settings.ext["vision_family_id"] = "paligemma-v1"
        summary.settings.ext["vision_prompt_profile_id"] = "paligemma-caption-v1"
        summary.settings.ext["vision_tokenization_mode"] = "prefix"
        summary.settings.ext["vision_max_images_per_prompt"] = "1"
        summary.settings.ext["vision_supports_tool_calls"] = "false"
        summary.settings.ext["melix.multimodal_adapter_hash"] = "vision-family-paligemma-v1"
        summary.settings.ext["melix.adapter_set_hash"] = "vision-family-paligemma-v1"
        summary.settings.ext["melix.capability.route_kind"] = "python_vlm"
        summary.settings.ext["melix.capability.class"] = "vlm"
        summary.settings.ext["melix.capability.supported_modalities"] = "text,image"
        summary.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"
        summary.settings.ext["melix.capability.supported_parsers"] = "text"
        summary.settings.ext["tool_parser_mode"] = ""
        summary.settings.ext["tool_parser_namespaces"] = ""
        summary.settings.ext["tool_parser_xml_fallback"] = ""

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-dev-vlm")
        #expect(spec.ext["vision_family_id"] == "paligemma-v1")
        #expect(spec.ext["vision_prompt_profile_id"] == "paligemma-caption-v1")
        #expect(spec.ext["vision_tokenization_mode"] == "prefix")
        #expect(spec.ext["vision_max_images_per_prompt"] == "1")
        #expect(spec.ext["vision_supports_tool_calls"] == "false")
        #expect(spec.ext["melix.multimodal_adapter_hash"] == "vision-family-paligemma-v1")
        #expect(spec.ext["melix.adapter_set_hash"] == "vision-family-paligemma-v1")
        #expect(spec.ext["melix.capability.route_kind"] == "python_vlm")
        #expect(spec.ext["melix.capability.class"] == "vlm")
        #expect(spec.ext["tool_parser_mode"] == nil)
    }

    @Test("bootstrap worker preparation builds generic VLM specs for imported Hugging Face models")
    func bootstrapWorkerPreparationBuildsGenericVLMSpecsForImportedHuggingFaceModels() throws {
        var summary = Melix_Controlplane_V1_ModelSummary()
        summary.modelID = "unsloth/gemma-4-E4B-it-MLX-8bit"
        summary.kind = "vlm"
        summary.maxContext = 4096
        summary.settings.alias = "gemma-4-E4B-it-MLX-8bit"
        summary.settings.ext["melix.model_path"] = "unsloth/gemma-4-E4B-it-MLX-8bit"
        summary.settings.ext["melix.model_revision"] = "main"
        summary.settings.ext["melix.tokenizer_hash"] = "hf.unsloth.gemma-4-E4B-it-MLX-8bit"
        summary.settings.ext["melix.vlm.backend_id"] = "mlx_vlm"
        summary.settings.ext["melix.hf_repo_id"] = "unsloth/gemma-4-E4B-it-MLX-8bit"
        summary.settings.ext["melix.task_kind"] = "image-text-to-text"
        summary.settings.ext["vision_family_id"] = "gemma4-v1"
        summary.settings.ext["vision_prompt_profile_id"] = "gemma4-chatml-v1"
        summary.settings.ext["vision_tokenization_mode"] = "interleaved"
        summary.settings.ext["vision_max_images_per_prompt"] = "8"
        summary.settings.ext["vision_supports_tool_calls"] = "true"
        summary.settings.ext["melix.multimodal_adapter_hash"] = "vision-family-gemma4-v1"
        summary.settings.ext["melix.capability.route_kind"] = "python_vlm"
        summary.settings.ext["melix.capability.class"] = "vlm"
        summary.settings.ext["melix.capability.supported_modalities"] = "text,image"
        summary.settings.ext["melix.capability.supported_tasks"] = "vlm,generate,image_text_to_text"
        summary.settings.ext["melix.capability.supported_parsers"] = "text,qwen"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(spec.modelPath == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(spec.modelKind == "vlm")
        #expect(spec.revision == "main")
        #expect(spec.ext["melix.vlm.backend_id"] == "mlx_vlm")
        #expect(spec.ext["vision_family_id"] == "gemma4-v1")
        #expect(spec.ext["melix.task_kind"] == "image-text-to-text")
    }

    @Test("bootstrap worker preparation builds generic image specs for imported Hugging Face models")
    func bootstrapWorkerPreparationBuildsGenericImageSpecsForImportedHuggingFaceModels() throws {
        var summary = Melix_Controlplane_V1_ModelSummary()
        summary.modelID = "mlx-community/sdxl-turbo"
        summary.kind = "image"
        summary.maxContext = 4096
        summary.settings.alias = "sdxl-turbo"
        summary.settings.ext["melix.model_path"] = "mlx-community/sdxl-turbo"
        summary.settings.ext["melix.model_revision"] = "main"
        summary.settings.ext["melix.tokenizer_hash"] = "hf.mlx-community.sdxl-turbo"
        summary.settings.ext["melix.image.backend_id"] = "deterministic"
        summary.settings.ext["melix.image.task_kind"] = "text-to-image"
        summary.settings.ext["melix.hf_repo_id"] = "mlx-community/sdxl-turbo"
        summary.settings.ext["melix.capability.route_kind"] = "python_image"
        summary.settings.ext["melix.capability.class"] = "image_generation"
        summary.settings.ext["melix.capability.supported_modalities"] = "text,image"
        summary.settings.ext["melix.capability.supported_tasks"] = "image_generate"
        summary.settings.ext["melix.capability.supported_parsers"] = "text"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "mlx-community/sdxl-turbo")
        #expect(spec.modelPath == "mlx-community/sdxl-turbo")
        #expect(spec.modelKind == "image")
        #expect(spec.ext["melix.image.backend_id"] == "deterministic")
        #expect(spec.ext["melix.image.task_kind"] == "text-to-image")
    }

    @Test("bootstrap worker preparation carries embedding family metadata into worker model specs")
    func bootstrapWorkerPreparationCarriesEmbeddingFamilyMetadataIntoWorkerModelSpecs() throws {
        var summary = ModelCatalog.devEmbeddingModel()
        summary.settings.ext["embedding_backend_id"] = "bert-v1"
        summary.settings.ext["embedding_family_id"] = "mxbai-embed"
        summary.settings.ext["embedding_pooling_mode"] = "mean"
        summary.settings.ext["embedding_normalization"] = "l2"
        summary.settings.ext["embedding_dimensions"] = "10"
        summary.settings.ext["melix.adapter_set_hash"] = "embedding-family-mxbai-embed"
        summary.settings.ext["melix.capability.route_kind"] = "python_embedding"
        summary.settings.ext["melix.capability.class"] = "embedding"
        summary.settings.ext["melix.capability.supported_modalities"] = "text"
        summary.settings.ext["melix.capability.supported_tasks"] = "embed"
        summary.settings.ext["melix.capability.supported_parsers"] = "text"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-dev-embed")
        #expect(spec.ext["embedding_backend_id"] == "bert-v1")
        #expect(spec.ext["embedding_family_id"] == "mxbai-embed")
        #expect(spec.ext["embedding_pooling_mode"] == "mean")
        #expect(spec.ext["embedding_normalization"] == "l2")
        #expect(spec.ext["embedding_dimensions"] == "10")
        #expect(spec.ext["melix.adapter_set_hash"] == "embedding-family-mxbai-embed")
        #expect(spec.ext["melix.capability.route_kind"] == "python_embedding")
        #expect(spec.ext["melix.capability.class"] == "embedding")
    }

    @Test("bootstrap worker preparation carries causal-lm rerank metadata into worker model specs")
    func bootstrapWorkerPreparationCarriesCausalLMRerankMetadataIntoWorkerModelSpecs() throws {
        var summary = ModelCatalog.devRerankModel(environment: [
            "MELIX_DEV_RERANK_FAMILY_ID": "causal-lm",
        ])
        summary.settings.ext["rerank_backend_id"] = "token-overlap-v1"
        summary.settings.ext["rerank_family_id"] = "causal-lm"
        summary.settings.ext["rerank_scoring_mode"] = "yes-no-logits"
        summary.settings.ext["rerank_yes_no_labels"] = "yes,no"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-dev-rerank")
        #expect(spec.ext["rerank_backend_id"] == "token-overlap-v1")
        #expect(spec.ext["rerank_family_id"] == "causal-lm")
        #expect(spec.ext["rerank_scoring_mode"] == "yes-no-logits")
        #expect(spec.ext["rerank_yes_no_labels"] == "yes,no")
        #expect(spec.ext["melix.adapter_set_hash"] == "rerank-family-causal-lm")
        #expect(spec.ext["melix.capability.route_kind"] == "python_rerank")
        #expect(spec.ext["melix.capability.class"] == "rerank")
    }

    @Test("bootstrap worker preparation carries deterministic and mlx-audio metadata into worker model specs")
    func bootstrapWorkerPreparationCarriesAudioMetadataIntoWorkerModelSpecs() throws {
        let deterministicSpeech = try #require(BootstrapWorkerPreparation.modelSpec(for: ModelCatalog.devSpeechModel()))
        let whisper = try #require(BootstrapWorkerPreparation.modelSpec(for: ModelCatalog.mlxWhisperModel()))
        let kokoro = try #require(BootstrapWorkerPreparation.modelSpec(for: ModelCatalog.mlxKokoroModel()))

        #expect(deterministicSpeech.modelID == "melix-dev-speech")
        #expect(deterministicSpeech.ext["melix.audio.backend_id"] == "deterministic")
        #expect(deterministicSpeech.ext["melix.audio.family_id"] == "deterministic-speech")
        #expect(deterministicSpeech.ext["melix.audio.output_formats"] == "wav,mp3")

        #expect(whisper.modelID == "melix-whisper-mlx")
        #expect(whisper.modelKind == "transcription")
        #expect(whisper.ext["melix.audio.backend_id"] == "mlx_audio.stt")
        #expect(whisper.ext["melix.audio.family_id"] == "whisper")
        #expect(whisper.ext["melix.audio.install_profile"] == "audio-stt")

        #expect(kokoro.modelID == "melix-kokoro-mlx")
        #expect(kokoro.modelKind == "speech")
        #expect(kokoro.ext["melix.audio.backend_id"] == "mlx_audio.tts")
        #expect(kokoro.ext["melix.audio.family_id"] == "kokoro")
        #expect(kokoro.ext["melix.audio.output_formats"] == "wav")
    }

    @Test("bridge client treats helper errors as unavailable")
    func bridgeClientTreatsHelperErrorsAsUnavailable() async throws {
        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(.handshake, line: bridgeErrorLine(code: "UNAVAILABLE", message: "worker down"))
        await runner.setStreamResponse(
            .generate,
            lines: [#"{"kind":"message","message_b64":"%%%"}"#]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        #expect(!(await client.canDispatchRequests()))

        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-bad"
        request.execution.modelHandle = "melix-dev-text::bridge"

        do {
            let stream = try await client.generate(request: request)
            _ = try await collect(stream)
            Issue.record("Expected the malformed bridge payload to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("bootstrap preload returns false when the worker does not hand back a handle")
    func bootstrapPreloadReturnsFalseWithoutAHandle() async throws {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = false

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog()
        let preloaded = try await BootstrapWorkerPreparation.preloadDevTextModel(
            workerClient: client,
            modelCatalog: catalog
        )

        #expect(!preloaded)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("text-ready preload records both legacy and text-ready bootstrap metrics")
    func textReadyPreloadRecordsLegacyAndTextReadyBootstrapMetrics() async throws {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog()
        let metricsStore = MetricsStore()

        await BootstrapPreloadCoordinator.preloadTextReadyModel(
            workerClient: client,
            modelCatalog: catalog,
            metricsStore: metricsStore
        )

        let metrics = await metricsStore.snapshot().values
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::bridge")
        #expect(metrics["control_plane.worker_preload_ms", default: -1] >= 0)
        #expect(
            metrics["control_plane.worker_preload_ms", default: -1]
            == metrics["control_plane.text_ready_preload_ms", default: -2]
        )
    }

    @Test("background python preload warms phase-seven models and records completion metrics")
    func backgroundPythonPreloadWarmsPhaseSevenModelsAndRecordsCompletionMetrics() async throws {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true

        let runner = ScriptedBridgeRunner()
        for modelID in [
            "melix-dev-embed",
            "melix-dev-rerank",
            "melix-dev-ocr",
            "melix-dev-vlm",
            "melix-dev-transcribe",
            "melix-dev-speech",
            "melix-dev-image",
        ] {
            response.modelHandle = "\(modelID)::bridge"
            await runner.enqueueUnaryResponse(
                .loadModel,
                line: bridgeMessageLine(message: try response.serializedData())
            )
        }

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let metricsStore = MetricsStore()

        let task = BootstrapPreloadCoordinator.startBackgroundPhaseSevenPythonPreload(
            workerClient: client,
            modelCatalog: catalog,
            metricsStore: metricsStore
        )
        await task.value

        let metrics = await metricsStore.snapshot().values
        #expect(await catalog.dispatchHandle(for: "melix-dev-image") == "melix-dev-image::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-transcribe") == "melix-dev-transcribe::bridge")
        #expect(metrics["control_plane.background_preload_ms", default: -1] >= 0)
        #expect(metrics["control_plane.background_preload_success", default: -1] == 1)
    }

    @Test("background python preload records a failure metric when preload aborts early")
    func backgroundPythonPreloadRecordsAFailureMetricWhenPreloadAbortsEarly() async throws {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-embed::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let metricsStore = MetricsStore()

        let task = BootstrapPreloadCoordinator.startBackgroundPhaseSevenPythonPreload(
            workerClient: client,
            modelCatalog: catalog,
            metricsStore: metricsStore
        )
        await task.value

        let metrics = await metricsStore.snapshot().values
        #expect(await catalog.dispatchHandle(for: "melix-dev-embed") == "melix-dev-embed::bridge")
        #expect(await catalog.dispatchHandle(for: "melix-dev-image") == nil)
        #expect(metrics["control_plane.background_preload_ms", default: -1] >= 0)
        #expect(metrics["control_plane.background_preload_success", default: -1] == 0)
    }

    @Test("repo-root initializer can dispatch with an existing python path")
    func repoRootInitializerCanDispatchWithAnExistingPythonPath() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let environment = ProcessInfo.processInfo.environment.merging([
            "PYTHONPATH": "/tmp/existing-python-path",
            "UV_CACHE_DIR": "\(fixtureRoot.path)/.custom-cache",
        ]) { _, new in new }
        let client = PythonBridgeWorkerClient(
            socketPath: "/tmp/fixture.sock",
            repoRoot: fixtureRoot.path,
            processEnvironment: environment
        )

        #expect(await client.canDispatchRequests())
    }

    @Test("process bridge runner executes unary, stream, and failure paths")
    func processBridgeRunnerExecutesUnaryStreamAndFailurePaths() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: ProcessInfo.processInfo.environment
        )

        let unaryLine = try await runner.runUnary(
            command: BridgeCommand(kind: .handshake, socketPath: "/tmp/unused.sock", requestData: Data("hello".utf8))
        )
        #expect(unaryLine.contains("\"kind\""))

        let stream = try await runner.runStream(
            command: BridgeCommand(kind: .generate, socketPath: "/tmp/unused.sock", requestData: Data("stream".utf8))
        )
        let lines = try await collect(stream)
        #expect(lines.count == 2)

        let embedLine = try await runner.runUnary(
            command: BridgeCommand(kind: .embed, socketPath: "/tmp/unused.sock", requestData: Data("embed".utf8))
        )
        #expect(embedLine.contains("\"kind\""))

        let transcribeLine = try await runner.runUnary(
            command: BridgeCommand(kind: .transcribe, socketPath: "/tmp/unused.sock", requestData: Data("transcribe".utf8))
        )
        #expect(transcribeLine.contains("\"kind\""))

        let speakLine = try await runner.runUnary(
            command: BridgeCommand(kind: .speak, socketPath: "/tmp/unused.sock", requestData: Data("speak".utf8))
        )
        #expect(speakLine.contains("\"kind\""))

        let convertLines = try await collect(
            try await runner.runStream(
                command: BridgeCommand(kind: .convertModel, socketPath: "/tmp/unused.sock", requestData: Data("convert".utf8))
            )
        )
        #expect(convertLines.count == 2)

        do {
            _ = try await runner.runUnary(
                command: BridgeCommand(kind: .abort, socketPath: "/tmp/unused.sock", requestData: Data())
            )
            Issue.record("Expected the abort fixture to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("process bridge runner surfaces non-zero stream exits as unavailable")
    func processBridgeRunnerSurfacesNonZeroStreamExitsAsUnavailable() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: ProcessInfo.processInfo.environment
        )

        do {
            let stream = try await runner.runStream(
                command: BridgeCommand(
                    kind: .generate,
                    socketPath: "/tmp/unused.sock",
                    requestData: Data("stream-error".utf8)
                )
            )
            _ = try await collect(stream)
            Issue.record("Expected the stream-error fixture to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("process bridge runner supports direct python executable override")
    func processBridgeRunnerSupportsDirectPythonExecutableOverride() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let environment = ProcessInfo.processInfo.environment.merging([
            "MELIX_PYTHON_BRIDGE_EXECUTABLE": "/usr/bin/python3",
        ]) { _, new in new }
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: environment
        )

        let unaryLine = try await runner.runUnary(
            command: BridgeCommand(kind: .handshake, socketPath: "/tmp/unused.sock", requestData: Data("hello".utf8))
        )

        #expect(unaryLine.contains("\"kind\""))
    }

    @Test("process bridge runner cancels hanging streams without leaking the child process")
    func processBridgeRunnerCancelsHangingStreamsWithoutLeakingTheChildProcess() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: ProcessInfo.processInfo.environment
        )

        do {
            let stream = try await runner.runStream(
                command: BridgeCommand(
                    kind: .generate,
                    socketPath: "/tmp/unused.sock",
                    requestData: Data("hang".utf8)
                )
            )
            let task = Task {
                var iterator = stream.makeAsyncIterator()
                return try await iterator.next()
            }
            let firstLine = try await task.value
            #expect(firstLine != nil)
        }
        try await Task.sleep(for: .milliseconds(50))
    }

    private func devModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-text"
        model.modelPath = "models/melix-dev-text"
        model.modelKind = "text"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev"
        model.quantProfileID = "q4"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8192
        return model
    }
}

private actor ScriptedBridgeRunner: WorkerBridgeRunning {
    private var unary: [BridgeCommandKind: [String]] = [:]
    private var streams: [BridgeCommandKind: [String]] = [:]

    func setUnaryResponse(_ kind: BridgeCommandKind, line: String) {
        unary[kind] = [line]
    }

    func enqueueUnaryResponse(_ kind: BridgeCommandKind, line: String) {
        unary[kind, default: []].append(line)
    }

    func setStreamResponse(_ kind: BridgeCommandKind, lines: [String]) {
        streams[kind] = lines
    }

    func runUnary(command: BridgeCommand) async throws -> String {
        if var lines = unary[command.kind], let line = lines.first {
            lines.removeFirst()
            unary[command.kind] = lines
            return line
        }
        return bridgeErrorLine(code: "missing_fixture", message: "No unary fixture.")
    }

    func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error> {
        let lines = streams[command.kind] ?? []
        return AsyncThrowingStream { continuation in
            for line in lines {
                continuation.yield(line)
            }
            continuation.finish()
        }
    }
}

private func bridgeMessageLine(message: Data) -> String {
    let payload = ["kind": "message", "message_b64": message.base64EncodedString()]
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return String(decoding: data, as: UTF8.self)
}

private func bridgeErrorLine(code: String, message: String) -> String {
    let payload = [
        "kind": "error",
        "code": code,
        "message": message,
    ]
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return String(decoding: data, as: UTF8.self)
}

private func makeProcessBridgeFixtureRepo() throws -> URL {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("melix-bridge-fixture-\(UUID().uuidString)", isDirectory: true)
    let workerDir = root.appendingPathComponent("services/mlx-worker-python/worker", isDirectory: true)
    try FileManager.default.createDirectory(at: workerDir, withIntermediateDirectories: true)
    try """
    [project]
    name = "fixture-worker"
    version = "0.1.0"
    requires-python = ">=3.12"
    dependencies = []

    [project.optional-dependencies]
    mlx = []
    """.write(
        to: root.appendingPathComponent("services/mlx-worker-python/pyproject.toml"),
        atomically: true,
        encoding: .utf8
    )
    try """
    import argparse
    import base64
    import json
    import sys
    import time

    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--request-b64", required=True)
    args = parser.parse_args()
    payload = base64.b64decode(args.request_b64)

    if args.command == "abort":
        sys.exit(1)

    if args.command in {"generate", "convert-model"}:
        if payload == b"stream-error":
            print("stream failure", file=sys.stderr, flush=True)
            sys.exit(1)
        if payload == b"hang":
            print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"first").decode("ascii")}), flush=True)
            time.sleep(2)
            sys.exit(0)
        print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"first").decode("ascii")}), flush=True)
        time.sleep(0.01)
        print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"second").decode("ascii")}), flush=True)
    elif args.command == "handshake":
        print(json.dumps({"kind": "message", "message_b64": ""}), flush=True)
    else:
        print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"ok").decode("ascii")}), flush=True)
    """.write(
        to: workerDir.appendingPathComponent("control_plane_bridge.py"),
        atomically: true,
        encoding: .utf8
    )
    return root
}

private func makeTokenEvent(
    requestID: String,
    seq: UInt64,
    text: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    return event
}

private func makeCompletedEvent(
    requestID: String,
    seq: UInt64,
    finishReason: String,
    assistantText: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = finishReason
    event.completed.assistantText = assistantText
    return event
}

private func collect<T: Sendable>(_ stream: AsyncThrowingStream<T, Error>) async throws -> [T] {
    var values: [T] = []
    for try await value in stream {
        values.append(value)
    }
    return values
}
