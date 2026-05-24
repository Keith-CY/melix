import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix
import NIOPosix
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

    @Test("default initializer bridges worker RPCs over a unix domain socket without a process bridge")
    func defaultInitializerBridgesWorkerRPCsOverUnixDomainSocket() async throws {
        let fixture = try await LivePythonWorkerFixture.start(
            handshakeResponse: {
                var response = Melix_Worker_V1_HandshakeResponse()
                response.protocolVersion = "melix.worker.v1"
                response.runtimeVersion = "python-worker/test"
                return response
            }(),
            runtimeStatsResponse: {
                var response = Melix_Worker_V1_GetRuntimeStatsResponse()
                response.stats.residentBytes = 12_288
                response.stats.lastFirstTokenLatencyMs = 27.5
                return response
            }(),
            cacheStatsResponse: {
                var response = Melix_Worker_V1_GetCacheStatsResponse()
                response.stats.l1Bytes = 4_096
                return response
            }(),
            generateEvents: [
                makeTokenEvent(requestID: "req-python-live", seq: 1, text: "Py"),
                makeCompletedEvent(
                    requestID: "req-python-live",
                    seq: 2,
                    finishReason: "stop",
                    assistantText: "Py"
                ),
            ]
        )
        do {
            let client = PythonBridgeWorkerClient(socketPath: fixture.socketPath)

            #expect(await client.canDispatchRequests())
            #expect(try await client.runtimeStats().stats.residentBytes == 12_288)
            #expect(try await client.cacheStats().stats.l1Bytes == 4_096)

            var request = Melix_Worker_V1_GenerateRequest()
            request.execution.id.requestID = "req-python-live"
            request.execution.modelHandle = "melix-dev-vlm::python-live"
            let events = try await collect(try await client.generate(request: request))
            #expect(events.count == 2)
            #expect(events[0].tokenDelta.text == "Py")
            #expect(events[1].completed.assistantText == "Py")
        } catch {
            await fixture.stop()
            throw error
        }

        await fixture.stop()
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
        runtimeResponse.stats.generationStreamOwnerMode = "executor_owned"
        runtimeResponse.stats.workerThreadInitLatencyMs = 3
        runtimeResponse.stats.streamSyncFallbackCount = 1
        runtimeResponse.stats.textBatchGeneratorStepCount = 9

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
        #expect(runtimeStats.stats.generationStreamOwnerMode == "executor_owned")
        #expect(runtimeStats.stats.workerThreadInitLatencyMs == 3)
        #expect(runtimeStats.stats.streamSyncFallbackCount == 1)
        #expect(runtimeStats.stats.textBatchGeneratorStepCount == 9)
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

    @Test("speak stream decodes progressive speech events from the bridge")
    func speakStreamDecodesProgressiveSpeechEventsFromTheBridge() async throws {
        var speakRequest = Melix_Worker_V1_SpeakRequest()
        speakRequest.id.requestID = "speak-stream-bridge"
        speakRequest.modelHandle = "melix-dev-speech::bridge"
        speakRequest.input = "hello streamed speech"
        speakRequest.voice = "alloy"
        speakRequest.format = "wav"
        speakRequest.streamingEnabled = true
        speakRequest.streamIntervalMs = 20

        var envelope = Melix_Worker_V1_SpeakStreamEvent()
        envelope.kind = .envelope
        envelope.audioBytes = Data("RIFF-envelope".utf8)
        envelope.envelope.format = "wav"
        envelope.envelope.codec = "pcm_s16le"
        envelope.envelope.streamIntervalMs = 20

        var chunk = Melix_Worker_V1_SpeakStreamEvent()
        chunk.kind = .audioChunk
        chunk.audioBytes = Data([0, 0, 1, 0])

        var finish = Melix_Worker_V1_SpeakStreamEvent()
        finish.kind = .finish
        finish.finish.speechStreamingEnabled = true
        finish.finish.speechStreamingIntervalMs = 20
        finish.finish.speechFirstAudioLatencyMs = 3
        finish.finish.audioChunkCount = 1

        let runner = ScriptedBridgeRunner()
        await runner.setStreamResponse(
            .speakStream,
            lines: [
                bridgeMessageLine(message: try envelope.serializedData()),
                bridgeMessageLine(message: try chunk.serializedData()),
                bridgeMessageLine(message: try finish.serializedData()),
            ]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let stream = try await client.speakStream(request: speakRequest)
        let events = try await collect(stream)

        #expect(events.map(\.kind) == [.envelope, .audioChunk, .finish])
        #expect(events[0].audioBytes == Data("RIFF-envelope".utf8))
        #expect(events[0].envelope.codec == "pcm_s16le")
        #expect(events[1].audioBytes == Data([0, 0, 1, 0]))
        #expect(events[2].finish.speechStreamingEnabled)
        #expect(events[2].finish.speechFirstAudioLatencyMs == 3)
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

    @Test("phase-seven preload uses catalog-aware image metadata when the seed model is overridden")
    func phaseSevenPreloadUsesCatalogAwareImageMetadataWhenSeedModelIsOverridden() async throws {
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

        var fillImage = ModelCatalog.devImageModel(
            environment: [
                "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
                "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
                "MELIX_DEV_IMAGE_MODEL_PATH": "models/flux-fill-dev",
            ]
        )
        fillImage.modelID = "melix-dev-image"
        let seedModels = ModelCatalog.phaseSixContractSeedModels() + [fillImage]
        let catalog = ModelCatalog(seedModels: seedModels)
        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        try await BootstrapWorkerPreparation.preloadPhaseSevenPythonModels(
            workerClient: client,
            modelCatalog: catalog,
            memoryBudgetBytes: 4096
        )

        let loadRequests = try await runner.recordedLoadModelRequests()
        #expect(loadRequests.count == 7)
        let imageRequest = try #require(loadRequests.last)
        #expect(imageRequest.model.modelID == "melix-dev-image")
        #expect(imageRequest.model.modelPath == "models/flux-fill-dev")
        #expect(imageRequest.model.ext["melix.image.family_id"] == "fill-v1")
        #expect(imageRequest.model.ext["melix.image.supports_generation"] == "false")
        #expect(imageRequest.model.ext["melix.image.supports_edit"] == "true")
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
            #expect(error == .requestFailed(code: "UNAVAILABLE", message: "embed down"))
        }

        do {
            _ = try await client.rerank(request: rerankRequest)
            Issue.record("Expected rerank bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .requestFailed(code: "UNAVAILABLE", message: "rerank down"))
        }

        do {
            _ = try await client.getModelInfo(request: infoRequest)
            Issue.record("Expected get-model-info bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .requestFailed(code: "UNAVAILABLE", message: "info down"))
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
            #expect(error == .requestFailed(code: "UNAVAILABLE", message: "transcribe down"))
        }

        do {
            _ = try await client.speak(request: speakRequest)
            Issue.record("Expected speak bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .requestFailed(code: "UNAVAILABLE", message: "speech down"))
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
            #expect(error == .requestFailed(code: "UNAVAILABLE", message: "image generate down"))
        }

        do {
            _ = try await client.imageEdit(request: editRequest)
            Issue.record("Expected image-edit bridge call to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .requestFailed(code: "UNAVAILABLE", message: "image edit down"))
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

    @Test("bootstrap worker preparation maps residency and disk streaming settings into worker specs")
    func bootstrapWorkerPreparationMapsResidencyAndDiskStreamingSettingsIntoWorkerSpecs() throws {
        var pinnedSummary = ModelCatalog.devTextModel()
        pinnedSummary.settings.memoryPolicy = .memoryResidencyPinned
        pinnedSummary.settings.diskStreamingMode = .diskStreamingDisabled

        let pinnedSpec = try #require(BootstrapWorkerPreparation.modelSpec(for: pinnedSummary))
        #expect(pinnedSpec.settings.memoryPolicy == .memoryResidencyPinned)
        #expect(pinnedSpec.settings.diskStreamingMode == .diskStreamingDisabled)

        var ttlSummary = ModelCatalog.devTextModel()
        ttlSummary.settings.memoryPolicy = .memoryResidencyTtl

        let ttlSpec = try #require(BootstrapWorkerPreparation.modelSpec(for: ttlSummary))
        #expect(ttlSpec.settings.memoryPolicy == .memoryResidencyTtl)
    }

    @Test("bootstrap worker preparation maps cache settings into worker specs")
    func bootstrapWorkerPreparationMapsCacheSettingsIntoWorkerSpecs() throws {
        var tieredSummary = ModelCatalog.devTextModel()
        tieredSummary.settings.cacheMode = .tiered
        tieredSummary.settings.cacheMemoryBudgetBytes = 4_096
        tieredSummary.settings.cacheMemoryBudgetPct = 25
        tieredSummary.settings.cacheBlockSizeTokens = 64
        tieredSummary.settings.cacheDirectory = "/tmp/melix-cache"
        tieredSummary.settings.multimodalCacheBudgetBytes = 2_048

        let tieredSpec = try #require(BootstrapWorkerPreparation.modelSpec(for: tieredSummary))
        #expect(tieredSpec.settings.cacheMode == .tiered)
        #expect(tieredSpec.settings.cacheMemoryBudgetBytes == 4_096)
        #expect(tieredSpec.settings.cacheMemoryBudgetPct == 25)
        #expect(tieredSpec.settings.cacheBlockSizeTokens == 64)
        #expect(tieredSpec.settings.cacheDirectory == "/tmp/melix-cache")
        #expect(tieredSpec.settings.multimodalCacheBudgetBytes == 2_048)

        var rotatingSummary = ModelCatalog.devTextModel()
        rotatingSummary.settings.cacheMode = .rotating
        let rotatingSpec = try #require(BootstrapWorkerPreparation.modelSpec(for: rotatingSummary))
        #expect(rotatingSpec.settings.cacheMode == .rotating)

        var hybridSummary = ModelCatalog.devTextModel()
        hybridSummary.settings.cacheMode = .hybrid
        let hybridSpec = try #require(BootstrapWorkerPreparation.modelSpec(for: hybridSummary))
        #expect(hybridSpec.settings.cacheMode == .hybrid)
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

    @Test("bootstrap worker preparation infers generic VLM context from nested text config")
    func bootstrapWorkerPreparationInfersGenericVLMContextFromNestedTextConfig() throws {
        let modelDirectory = try makeModelConfigDirectory(
            config: """
            {
              "model_type": "gemma4",
              "text_config": {
                "model_type": "gemma4_text",
                "max_position_embeddings": 131072
              }
            }
            """
        )

        var summary = Melix_Controlplane_V1_ModelSummary()
        summary.modelID = "mlx-community/gemma-4-31b-it-8bit"
        summary.kind = "vlm"
        summary.maxContext = 8_192
        summary.settings.ext["melix.model_path"] = modelDirectory.path
        summary.settings.ext["vision_family_id"] = "gemma4-v1"
        summary.settings.ext["melix.vlm.backend_id"] = "mlx_vlm"
        summary.settings.ext["melix.capability.route_kind"] = "python_vlm"
        summary.settings.ext["melix.capability.class"] = "vlm"
        summary.settings.ext["melix.capability.supported_modalities"] = "text,image"
        summary.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelKind == "vlm")
        #expect(spec.maxContext == 131_072)
    }

    @Test("bootstrap worker preparation preserves adapter-backed runtime metadata for activated derived models")
    func bootstrapWorkerPreparationPreservesAdapterBackedRuntimeMetadataForActivatedDerivedModels() throws {
        var summary = ModelCatalog.devTextModel()
        summary.modelID = "melix-dev-text-lora-runtime"
        summary.settings.alias = "Runtime Adapter"
        summary.settings.ext["melix.model_path"] = "models/dev-text"
        summary.settings.ext["melix.model_revision"] = "dev"
        summary.settings.ext["melix.parser_mode"] = "text"
        summary.settings.ext["melix.reasoning_mode"] = "off"
        summary.settings.ext["melix.adapter_set_hash"] = "adapter-runtime-alpha"
        summary.settings.ext["melix.derived_from_adapter"] = "true"
        summary.settings.ext["melix.derived_from_model_id"] = "melix-dev-text"
        summary.settings.ext["melix.activation_mode"] = "adapter_backed_runtime"
        summary.settings.ext["melix.adapter_manifest_path"] = "/tmp/melix-train/train_lora.adapter.json"
        summary.settings.ext["melix.adapter_weights_path"] = "/tmp/melix-train/weights/adapters.safetensors"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "melix-dev-text-lora-runtime")
        #expect(spec.modelPath == "models/dev-text")
        #expect(spec.ext["melix.activation_mode"] == "adapter_backed_runtime")
        #expect(spec.ext["melix.adapter_manifest_path"] == "/tmp/melix-train/train_lora.adapter.json")
        #expect(spec.ext["melix.adapter_weights_path"] == "/tmp/melix-train/weights/adapters.safetensors")
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

    @Test("bootstrap worker preparation builds generic OCR specs and carries generation-config metadata")
    func bootstrapWorkerPreparationBuildsGenericOCRSpecsAndCarriesGenerationConfigMetadata() throws {
        var summary = Melix_Controlplane_V1_ModelSummary()
        summary.modelID = "mlx-community/Vision-OCR/8bit"
        summary.kind = "ocr"
        summary.maxContext = 4096
        summary.quantProfileID = "q8"
        summary.settings.alias = "Vision OCR"
        summary.settings.ext["melix.model_path"] = "/tmp/registry-root/mlx-community/Vision-OCR/8bit"
        summary.settings.ext["melix.model_revision"] = "registry"
        summary.settings.ext["melix.tokenizer_hash"] = "tok-ocr-imported"
        summary.settings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        summary.settings.ext["melix.generation_config.source"] = "/tmp/registry-root/mlx-community/Vision-OCR/8bit/generation_config.json"
        summary.settings.ext["melix.generation_config.temperature"] = "0.15"
        summary.settings.ext["melix.generation_config.top_p"] = "0.92"
        summary.settings.ext["melix.generation_config.max_tokens"] = "384"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))

        #expect(spec.modelID == "mlx-community/Vision-OCR/8bit")
        #expect(spec.modelKind == "ocr")
        #expect(spec.modelPath == "/tmp/registry-root/mlx-community/Vision-OCR/8bit")
        #expect(spec.ext["melix.generation_config.temperature"] == "0.15")
        #expect(spec.ext["melix.generation_config.top_p"] == "0.92")
        #expect(spec.ext["melix.generation_config.max_tokens"] == "384")
    }

    @Test("bootstrap worker preparation skips generic OCR specs without a concrete model path")
    func bootstrapWorkerPreparationSkipsGenericOCRSpecsWithoutConcreteModelPath() {
        var summary = Melix_Controlplane_V1_ModelSummary()
        summary.modelID = "mlx-community/Vision-OCR/8bit"
        summary.kind = "ocr"
        summary.maxContext = 4096
        summary.quantProfileID = "q8"
        summary.settings.alias = "Vision OCR"
        summary.settings.ext["melix.model_revision"] = "registry"

        #expect(BootstrapWorkerPreparation.modelSpec(for: summary) == nil)
    }

    @Test("bootstrap worker preparation lets built-in audio models override model path from summary metadata")
    func bootstrapWorkerPreparationLetsBuiltInAudioModelsOverrideModelPathFromSummaryMetadata() throws {
        var summary = ModelCatalog.mlxWhisperModel()
        summary.settings.ext["melix.model_path"] = "/tmp/melix-managed-audio/whisper"
        var parakeetSummary = ModelCatalog.mlxParakeetModel()
        parakeetSummary.settings.ext["melix.model_path"] = "/tmp/melix-managed-audio/parakeet"

        let spec = try #require(BootstrapWorkerPreparation.modelSpec(for: summary))
        let parakeetSpec = try #require(BootstrapWorkerPreparation.modelSpec(for: parakeetSummary))

        #expect(spec.modelID == "melix-whisper-mlx")
        #expect(spec.modelPath == "/tmp/melix-managed-audio/whisper")
        #expect(spec.ext["melix.audio.backend_id"] == "mlx_audio.stt")
        #expect(parakeetSpec.modelID == "melix-parakeet-mlx")
        #expect(parakeetSpec.modelPath == "/tmp/melix-managed-audio/parakeet")
        #expect(parakeetSpec.ext["melix.audio.family_id"] == "parakeet")
    }

    @Test("bootstrap worker preparation carries VLM family metadata into worker model specs")
    func bootstrapWorkerPreparationCarriesVLMFamilyMetadataIntoWorkerModelSpecs() throws {
        var summary = ModelCatalog.devVLMModel()
        let defaultSpec = try #require(BootstrapWorkerPreparation.modelSpec(for: "melix-dev-vlm"))
        #expect(defaultSpec.ext["melix.capability.supported_modalities"] == "text,image,video")

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
        summary.settings.ext["melix.image.family_id"] = "qwenimage-v1"
        summary.settings.ext["melix.image.task_kind"] = "text-to-image"
        summary.settings.ext["melix.image.default_workflow_role"] = "generate"
        summary.settings.ext["melix.image.supports_generation"] = "true"
        summary.settings.ext["melix.image.supports_edit"] = "false"
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
        #expect(spec.ext["melix.image.family_id"] == "qwenimage-v1")
        #expect(spec.ext["melix.image.task_kind"] == "text-to-image")
        #expect(spec.ext["melix.image.default_workflow_role"] == "generate")
        #expect(spec.ext["melix.image.supports_generation"] == "true")
        #expect(spec.ext["melix.image.supports_edit"] == "false")
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
        let parakeet = try #require(BootstrapWorkerPreparation.modelSpec(for: ModelCatalog.mlxParakeetModel()))
        let kokoro = try #require(BootstrapWorkerPreparation.modelSpec(for: ModelCatalog.mlxKokoroModel()))
        let qwen3TTS = try #require(BootstrapWorkerPreparation.modelSpec(for: ModelCatalog.mlxQwen3TTSModel()))

        #expect(deterministicSpeech.modelID == "melix-dev-speech")
        #expect(deterministicSpeech.ext["melix.audio.backend_id"] == "deterministic")
        #expect(deterministicSpeech.ext["melix.audio.family_id"] == "deterministic-speech")
        #expect(deterministicSpeech.ext["melix.audio.output_formats"] == "wav,mp3")

        #expect(whisper.modelID == "melix-whisper-mlx")
        #expect(whisper.modelKind == "transcription")
        #expect(whisper.ext["melix.audio.backend_id"] == "mlx_audio.stt")
        #expect(whisper.ext["melix.audio.family_id"] == "whisper")
        #expect(whisper.ext["melix.audio.install_profile"] == "audio-stt")

        #expect(parakeet.modelID == "melix-parakeet-mlx")
        #expect(parakeet.modelKind == "transcription")
        #expect(parakeet.ext["melix.audio.backend_id"] == "mlx_audio.stt")
        #expect(parakeet.ext["melix.audio.family_id"] == "parakeet")
        #expect(parakeet.ext["melix.audio.install_profile"] == "audio-stt")

        #expect(kokoro.modelID == "melix-kokoro-mlx")
        #expect(kokoro.modelKind == "speech")
        #expect(kokoro.ext["melix.audio.backend_id"] == "mlx_audio.tts")
        #expect(kokoro.ext["melix.audio.family_id"] == "kokoro")
        #expect(kokoro.ext["melix.audio.output_formats"] == "wav")
        #expect(kokoro.ext["melix.audio.voice_catalog_summary"] == "Named English voices exposed by the Kokoro speaker catalog.")
        #expect(kokoro.ext["melix.audio.voice_locales"] == "en")
        #expect(kokoro.ext["melix.audio.default_locale"] == "en")
        #expect(kokoro.ext["melix.audio.packaged_default_locale"] == "en")
        #expect(kokoro.ext["melix.audio.locale_policy"] == "request>model_default>packaged_default")

        #expect(qwen3TTS.modelID == "melix-qwen3-tts-mlx")
        #expect(qwen3TTS.modelKind == "speech")
        #expect(qwen3TTS.ext["melix.audio.backend_id"] == "mlx_audio.tts")
        #expect(qwen3TTS.ext["melix.audio.family_id"] == "qwen3-tts")
        #expect(qwen3TTS.ext["melix.audio.install_profile"] == "audio-tts")
        #expect(qwen3TTS.ext["melix.audio.voice_mode"] == "hybrid")
        #expect(qwen3TTS.ext["melix.audio.supports_instructions"] == "true")
        #expect(
            qwen3TTS.ext["melix.audio.voice_catalog_summary"]
                == "Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis."
        )
        #expect(qwen3TTS.ext["melix.audio.voice_locales"] == "zh,en")
        #expect(qwen3TTS.ext["melix.audio.default_locale"] == "zh")
        #expect(qwen3TTS.ext["melix.audio.packaged_default_locale"] == "zh")
        #expect(qwen3TTS.ext["melix.audio.locale_policy"] == "request>model_default>packaged_default")
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
        let environment = processBridgeFixtureEnvironment(
            fixtureRoot: fixtureRoot,
            extra: ["PYTHONPATH": "/tmp/existing-python-path"]
        )
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
            environment: processBridgeFixtureEnvironment(fixtureRoot: fixtureRoot)
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

    @Test("process bridge runner drains large unary payloads without deadlocking")
    func processBridgeRunnerDrainsLargeUnaryPayloadsWithoutDeadlocking() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: processBridgeFixtureEnvironment(fixtureRoot: fixtureRoot)
        )

        let line = try await runner.runUnary(
            command: BridgeCommand(
                kind: .exportResults,
                socketPath: "/tmp/unused.sock",
                requestData: Data("large-unary".utf8)
            )
        )

        #expect(line.contains("\"kind\""))
        #expect(line.count > 70_000)
    }

    @Test("process bridge runner preserves unary error payloads from non-zero exits")
    func processBridgeRunnerPreservesUnaryErrorPayloadsFromNonZeroExits() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: processBridgeFixtureEnvironment(fixtureRoot: fixtureRoot)
        )

        let errorLine = try await runner.runUnary(
            command: BridgeCommand(
                kind: .imageGenerate,
                socketPath: "/tmp/unused.sock",
                requestData: Data("rpc-error".utf8)
            )
        )

        #expect(errorLine.contains("\"kind\": \"error\""))
        #expect(errorLine.contains("\"code\": \"DEADLINE_EXCEEDED\""))
    }

    @Test("process bridge runner surfaces non-zero stream exits as unavailable")
    func processBridgeRunnerSurfacesNonZeroStreamExitsAsUnavailable() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: processBridgeFixtureEnvironment(fixtureRoot: fixtureRoot)
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
            environment: processBridgeFixtureEnvironment(fixtureRoot: fixtureRoot)
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
    private var recordedCommands: [BridgeCommandKind: [BridgeCommand]] = [:]

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
        recordedCommands[command.kind, default: []].append(command)
        if var lines = unary[command.kind], let line = lines.first {
            lines.removeFirst()
            unary[command.kind] = lines
            return line
        }
        return bridgeErrorLine(code: "missing_fixture", message: "No unary fixture.")
    }

    func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error> {
        recordedCommands[command.kind, default: []].append(command)
        let lines = streams[command.kind] ?? []
        return AsyncThrowingStream { continuation in
            for line in lines {
                continuation.yield(line)
            }
            continuation.finish()
        }
    }

    func recordedLoadModelRequests() throws -> [Melix_Worker_V1_LoadModelRequest] {
        try recordedCommands[.loadModel, default: []].map {
            try Melix_Worker_V1_LoadModelRequest(serializedBytes: $0.requestData)
        }
    }
}

private final class LivePythonWorkerRuntime: @unchecked Sendable {
    let server: GRPCServer<HTTP2ServerTransport.Posix>
    let serveTask: Task<Void, Error>

    init(
        server: GRPCServer<HTTP2ServerTransport.Posix>,
        serveTask: Task<Void, Error>
    ) {
        self.server = server
        self.serveTask = serveTask
    }
}

private actor LivePythonWorkerFixture {
    let socketPath: String
    private let eventLoopGroup: MultiThreadedEventLoopGroup
    private var runtime: LivePythonWorkerRuntime?

    private init(
        socketPath: String,
        eventLoopGroup: MultiThreadedEventLoopGroup,
        runtime: LivePythonWorkerRuntime
    ) {
        self.socketPath = socketPath
        self.eventLoopGroup = eventLoopGroup
        self.runtime = runtime
    }

    static func start(
        handshakeResponse: Melix_Worker_V1_HandshakeResponse,
        runtimeStatsResponse: Melix_Worker_V1_GetRuntimeStatsResponse,
        cacheStatsResponse: Melix_Worker_V1_GetCacheStatsResponse,
        generateEvents: [Melix_Worker_V1_ExecuteEvent]
    ) async throws -> LivePythonWorkerFixture {
        let socketPath = "/tmp/melix-python-\(UUID().uuidString.prefix(8)).sock"
        try? FileManager.default.removeItem(atPath: socketPath)

        let eventLoopGroup = MultiThreadedEventLoopGroup(numberOfThreads: 1)
        let server = GRPCServer(
            transport: .http2NIOPosix(
                address: .unixDomainSocket(path: socketPath),
                transportSecurity: .plaintext,
                eventLoopGroup: eventLoopGroup
            ),
            services: [
                PythonTestRuntimeService(
                    handshakeResponse: handshakeResponse,
                    runtimeStatsResponse: runtimeStatsResponse
                ),
                PythonTestInferenceService(generateEvents: generateEvents),
                PythonTestCacheService(cacheStatsResponse: cacheStatsResponse),
            ]
        )
        let serveTask = Task {
            try await server.serve()
        }
        _ = try await server.listeningAddress
        let runtime = LivePythonWorkerRuntime(server: server, serveTask: serveTask)
        return LivePythonWorkerFixture(
            socketPath: socketPath,
            eventLoopGroup: eventLoopGroup,
            runtime: runtime
        )
    }

    func stop() async {
        if let runtime {
            self.runtime = nil
            runtime.server.beginGracefulShutdown()
            _ = try? await runtime.serveTask.value
        }
        try? await eventLoopGroup.shutdownGracefully()
        try? FileManager.default.removeItem(atPath: socketPath)
    }
}

private final class PythonTestRuntimeService: Melix_Worker_V1_RuntimeService.SimpleServiceProtocol, @unchecked Sendable {
    private let handshakeResponse: Melix_Worker_V1_HandshakeResponse
    private let runtimeStatsResponse: Melix_Worker_V1_GetRuntimeStatsResponse

    init(
        handshakeResponse: Melix_Worker_V1_HandshakeResponse,
        runtimeStatsResponse: Melix_Worker_V1_GetRuntimeStatsResponse
    ) {
        self.handshakeResponse = handshakeResponse
        self.runtimeStatsResponse = runtimeStatsResponse
    }

    func handshake(
        request: Melix_Worker_V1_HandshakeRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_HandshakeResponse {
        handshakeResponse
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        Melix_Worker_V1_LoadModelResponse()
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        Melix_Worker_V1_UnloadModelResponse()
    }

    func warmupModel(
        request: Melix_Worker_V1_WarmupModelRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_WarmupModelResponse {
        Melix_Worker_V1_WarmupModelResponse()
    }

    func getRuntimeStats(
        request: Melix_Worker_V1_GetRuntimeStatsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        runtimeStatsResponse
    }

    func listLoadedModels(
        request: Melix_Worker_V1_ListLoadedModelsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ListLoadedModelsResponse {
        Melix_Worker_V1_ListLoadedModelsResponse()
    }

    func drain(
        request: Melix_Worker_V1_DrainRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_DrainResponse {
        Melix_Worker_V1_DrainResponse()
    }

    func shutdown(
        request: Melix_Worker_V1_ShutdownRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ShutdownResponse {
        Melix_Worker_V1_ShutdownResponse()
    }
}

private final class PythonTestCacheService: Melix_Worker_V1_CacheService.SimpleServiceProtocol, @unchecked Sendable {
    private let cacheStatsResponse: Melix_Worker_V1_GetCacheStatsResponse

    init(cacheStatsResponse: Melix_Worker_V1_GetCacheStatsResponse) {
        self.cacheStatsResponse = cacheStatsResponse
    }

    func getCacheStats(
        request: Melix_Worker_V1_GetCacheStatsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        cacheStatsResponse
    }

    func pinPrefix(
        request: Melix_Worker_V1_PinPrefixRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_PinPrefixResponse {
        Melix_Worker_V1_PinPrefixResponse()
    }

    func unpinPrefix(
        request: Melix_Worker_V1_UnpinPrefixRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_UnpinPrefixResponse {
        Melix_Worker_V1_UnpinPrefixResponse()
    }

    func saveBoundarySnapshot(
        request: Melix_Worker_V1_SaveBoundarySnapshotRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_SaveBoundarySnapshotResponse {
        Melix_Worker_V1_SaveBoundarySnapshotResponse()
    }

    func restoreBoundarySnapshot(
        request: Melix_Worker_V1_RestoreBoundarySnapshotRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_RestoreBoundarySnapshotResponse {
        Melix_Worker_V1_RestoreBoundarySnapshotResponse()
    }

    func purgeCache(
        request: Melix_Worker_V1_PurgeCacheRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_PurgeCacheResponse {
        Melix_Worker_V1_PurgeCacheResponse()
    }
}

private final class PythonTestInferenceService: Melix_Worker_V1_InferenceService.SimpleServiceProtocol, @unchecked Sendable {
    private let generateEvents: [Melix_Worker_V1_ExecuteEvent]

    init(generateEvents: [Melix_Worker_V1_ExecuteEvent]) {
        self.generateEvents = generateEvents
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest,
        response: RPCWriter<Melix_Worker_V1_ExecuteEvent>,
        context: ServerContext
    ) async throws {
        for event in generateEvents {
            try await response.write(event)
        }
    }

    func prefill(
        request: Melix_Worker_V1_PrefillRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        Melix_Worker_V1_PrefillResponse()
    }

    func decode(
        request: Melix_Worker_V1_DecodeRequest,
        response: RPCWriter<Melix_Worker_V1_ExecuteEvent>,
        context: ServerContext
    ) async throws {
        _ = (request, response, context)
    }

    func abort(
        request: Melix_Worker_V1_AbortRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_AbortResponse {
        Melix_Worker_V1_AbortResponse()
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_RerankResponse {
        Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        Melix_Worker_V1_SpeakResponse()
    }

    func speakStream(
        request: Melix_Worker_V1_SpeakRequest,
        response: RPCWriter<Melix_Worker_V1_SpeakStreamEvent>,
        context: ServerContext
    ) async throws {
        _ = (request, response, context)
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        Melix_Worker_V1_ImageGenerateResponse()
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        Melix_Worker_V1_ImageEditResponse()
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

private func makeModelConfigDirectory(config: String) throws -> URL {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("melix-model-config-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try config.write(
        to: root.appendingPathComponent("config.json"),
        atomically: true,
        encoding: .utf8
    )
    return root
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
    requires-python = ">=3.11"
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
    elif payload == b"large-unary":
        huge = base64.b64encode(b"x" * 70000).decode("ascii")
        print(json.dumps({"kind": "message", "message_b64": huge}), flush=True)
    elif args.command == "handshake":
        print(json.dumps({"kind": "message", "message_b64": ""}), flush=True)
    elif payload == b"rpc-error":
        print(json.dumps({"kind": "error", "code": "DEADLINE_EXCEEDED", "message": "timed out"}), flush=True)
        sys.exit(1)
    else:
        print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"ok").decode("ascii")}), flush=True)
    """.write(
        to: workerDir.appendingPathComponent("control_plane_bridge.py"),
        atomically: true,
        encoding: .utf8
    )
    return root
}

private func processBridgeFixtureEnvironment(
    fixtureRoot: URL,
    extra: [String: String] = [:]
) -> [String: String] {
    ProcessInfo.processInfo.environment.merging([
        "MELIX_PYTHON_BRIDGE_EXECUTABLE": "/usr/bin/python3",
        "UV_CACHE_DIR": "\(fixtureRoot.path)/.custom-cache",
    ].merging(extra) { _, new in new }) { _, new in new }
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
