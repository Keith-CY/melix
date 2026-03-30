import Foundation
import SwiftProtobuf
import Testing

@testable import MelixControlPlaneCore
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
