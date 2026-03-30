import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
}

public enum HTTPBody: Sendable {
    case data(Data)
    case stream(AsyncThrowingStream<Data, Error>)
}

public struct HTTPRequest: Sendable {
    public let method: HTTPMethod
    public let path: String
    public let headers: [String: String]
    public let body: Data

    public init(
        method: HTTPMethod,
        path: String,
        headers: [String: String],
        body: Data
    ) {
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
    }
}

public struct HTTPResponse: Sendable {
    public let statusCode: Int
    public let headers: [String: String]
    public let body: HTTPBody

    public init(
        statusCode: Int,
        headers: [String: String],
        body: HTTPBody
    ) {
        self.statusCode = statusCode
        self.headers = headers
        self.body = body
    }
}

public struct OpenAIHandler: Sendable {
    private let modelCatalog: ModelCatalog
    private let requestCoordinator: RequestCoordinator
    private let workerRegistry: WorkerRegistry?
    private let metricsStore: MetricsStore
    private let schedulerReadModel: SchedulerReadModel?
    private let imageJobReadModel: ImageJobReadModel?
    private let imageJobAdmissionController: any ImageJobAdmissionControlling
    private let cacheMetadataStore: CacheMetadataStore?
    private let translator: ChatRequestTranslator
    private let sseWriter: SSEStreamWriter
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    public init(
        modelCatalog: ModelCatalog,
        requestCoordinator: RequestCoordinator,
        workerRegistry: WorkerRegistry? = nil,
        metricsStore: MetricsStore = MetricsStore(),
        schedulerReadModel: SchedulerReadModel? = nil,
        imageJobReadModel: ImageJobReadModel? = nil,
        imageJobAdmissionController: (any ImageJobAdmissionControlling)? = nil,
        cacheMetadataStore: CacheMetadataStore? = nil,
        translator: ChatRequestTranslator = ChatRequestTranslator(),
        sseWriter: SSEStreamWriter = SSEStreamWriter()
    ) {
        self.modelCatalog = modelCatalog
        self.requestCoordinator = requestCoordinator
        self.workerRegistry = workerRegistry
        self.metricsStore = metricsStore
        self.schedulerReadModel = schedulerReadModel
        self.imageJobReadModel = imageJobReadModel
        self.imageJobAdmissionController = imageJobAdmissionController ?? ImageJobAdmissionController(
            schedulerReadModel: schedulerReadModel,
            metricsStore: metricsStore
        )
        self.cacheMetadataStore = cacheMetadataStore
        self.translator = translator
        self.sseWriter = sseWriter
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.sortedKeys]
    }

    public func handle(_ request: HTTPRequest) async throws -> HTTPResponse {
        switch (request.method, request.path) {
        case (.get, "/v1/models"):
            return try await handleModels()
        case (.get, "/health"):
            return try await handleHealth()
        case (.get, "/v1/cache/stats"):
            return try await handleCacheStats()
        case (.post, "/v1/chat/completions"):
            return try await handleChatCompletions(request)
        case (.post, "/v1/completions"):
            return try await handleCompletions(request)
        case (.post, "/v1/responses"):
            return try await handleResponses(request)
        case (.post, "/v1/messages"):
            return try await handleMessages(request)
        case (.post, "/v1/embeddings"):
            return try await handleEmbeddings(request)
        case (.post, "/v1/rerank"):
            return try await handleRerank(request)
        case (.post, "/v1/audio/transcriptions"):
            return try await handleAudioTranscriptions(request)
        case (.post, "/v1/audio/speech"):
            return try await handleAudioSpeech(request)
        case (.post, "/v1/images/generations"):
            return try await handleImageGenerations(request)
        case (.post, "/v1/images/edits"):
            return try await handleImageEdits(request)
        default:
            return jsonResponse(
                statusCode: 404,
                payload: ["error": ["code": "not_found", "message": "Unknown route."]]
            )
        }
    }

    private func handleModels() async throws -> HTTPResponse {
        let models = await modelCatalog.listModels().map { model in
            OpenAIModelDescriptor(
                id: model.modelID,
                object: "model",
                ownedBy: "melix",
                melixState: model.state.melixString
            )
        }

        let response = OpenAIModelsResponse(object: "list", data: models)
        let data = try encoder.encode(response)
        return HTTPResponse(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func handleHealth() async throws -> HTTPResponse {
        let startedAt = Date()
        let routes = await healthRoutes()
        let models = await modelCatalog.listModels()
        let readyCount = models.filter { $0.state == .modelWarm || $0.state == .modelPinned }.count
        let status = routes.values.allSatisfy { $0 } ? "ok" : "degraded"
        let response = HealthResponse(
            status: status,
            routes: routes,
            modelsReady: readyCount,
            modelsTotal: models.count
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "operator.health_latency_ms"
        )
        let data = try encoder.encode(response)
        return HTTPResponse(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func handleCacheStats() async throws -> HTTPResponse {
        let startedAt = Date()
        let summary = if let cacheMetadataStore {
            await cacheMetadataStore.cacheSummary()
        } else {
            CacheMetadataStore.emptySummary()
        }
        let response = CacheStatsResponse(
            l1Bytes: summary.l1Bytes,
            l2Bytes: summary.l2Bytes,
            l1HitRate: summary.l1HitRate,
            l2HitRate: summary.l2HitRate,
            checkpointCount: summary.checkpointCount,
            blockCount: summary.blockCount,
            quantizedBytes: summary.quantizedBytes,
            compressionRatio: summary.compressionRatio,
            l2RestoreHitRate: summary.l2RestoreHitRate,
            activeCacheMode: cacheModeLabel(summary.activeMode)
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "operator.cache_stats_latency_ms"
        )
        let data = try encoder.encode(response)
        return HTTPResponse(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func handleChatCompletions(_ request: HTTPRequest) async throws -> HTTPResponse {
        do {
            let chatRequest = try decoder.decode(OpenAIChatCompletionsRequest.self, from: request.body)
            let normalized = if chatRequest.messages.contains(where: \.hasMultimodalContent) {
                try translator.normalizeMultimodalChat(chatRequest)
            } else {
                translator.normalize(chatRequest)
            }
            let translated = try await translatedRequest(normalized)
            return try await streamResponse(
                translated: translated,
                shape: .chatCompletions
            )
        } catch let error as MultimodalRequestNormalizationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleCompletions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let completionsRequest = try decoder.decode(OpenAICompletionsRequest.self, from: request.body)
        let normalized = translator.normalize(completionsRequest)
        return try await streamNormalizedTextRequest(normalized, shape: .completions)
    }

    private func handleResponses(_ request: HTTPRequest) async throws -> HTTPResponse {
        let responsesRequest = try decoder.decode(OpenAIResponsesRequest.self, from: request.body)
        let normalized = translator.normalize(responsesRequest)
        return try await streamNormalizedTextRequest(normalized, shape: .responses)
    }

    private func handleMessages(_ request: HTTPRequest) async throws -> HTTPResponse {
        let messagesRequest = try decoder.decode(MelixMessagesRequest.self, from: request.body)
        let normalized = translator.normalize(messagesRequest)
        return try await streamNormalizedTextRequest(normalized, shape: .messages)
    }

    private func streamNormalizedTextRequest(
        _ normalized: NormalizedTextRequest,
        shape: SSEStreamWriter.StreamShape
    ) async throws -> HTTPResponse {
        do {
            let translated = try await translatedRequest(normalized)
            return try await streamResponse(translated: translated, shape: shape)
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleEmbeddings(_ request: HTTPRequest) async throws -> HTTPResponse {
        let embeddingsRequest = try decoder.decode(OpenAIEmbeddingsRequest.self, from: request.body)
        let inputs = embeddingsRequest.normalizedInputs

        guard let modelHandle = await modelCatalog.dispatchHandle(for: embeddingsRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: embeddingsRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }

        var workerRequest = Melix_Worker_V1_EmbedRequest()
        workerRequest.id.requestID = UUID().uuidString
        workerRequest.modelHandle = modelHandle
        workerRequest.inputs = inputs

        let startedAt = Date()
        do {
            let response = try await inferenceClient.embed(request: workerRequest)
            if !response.error.code.isEmpty {
                return workerErrorResponse(response.error)
            }

            let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
            await metricsStore.set(elapsedMs, forKey: "embeddings.request_latency_ms")
            await metricsStore.set(Double(inputs.count) / max(elapsedMs / 1000, 0.001), forKey: "embeddings.items_per_second")

            let payload = OpenAIEmbeddingsResponse(
                object: "list",
                data: response.embeddings.enumerated().map { index, embedding in
                    OpenAIEmbeddingDatum(object: "embedding", embedding: embedding.values, index: index)
                },
                model: embeddingsRequest.model,
                usage: OpenAIEmbeddingsUsage(
                    promptTokens: estimatedTokenCount(for: inputs),
                    totalTokens: estimatedTokenCount(for: inputs)
                )
            )
            let data = try encoder.encode(payload)
            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: .data(data)
            )
        } catch {
            return workerUnavailableResponse()
        }
    }

    private func handleRerank(_ request: HTTPRequest) async throws -> HTTPResponse {
        let rerankRequest = try decoder.decode(OpenAIRerankRequest.self, from: request.body)

        guard let modelHandle = await modelCatalog.dispatchHandle(for: rerankRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: rerankRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }

        var workerRequest = Melix_Worker_V1_RerankRequest()
        workerRequest.id.requestID = UUID().uuidString
        workerRequest.modelHandle = modelHandle
        workerRequest.query = rerankRequest.query
        workerRequest.documents = rerankRequest.documents
        workerRequest.topK = rerankRequest.topK

        let startedAt = Date()
        do {
            let response = try await inferenceClient.rerank(request: workerRequest)
            if !response.error.code.isEmpty {
                return workerErrorResponse(response.error)
            }

            let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
            await metricsStore.set(elapsedMs, forKey: "rerank.request_latency_ms")
            await metricsStore.set(
                Double(rerankRequest.documents.count) / max(elapsedMs / 1000, 0.001),
                forKey: "rerank.documents_per_second"
            )

            let payload = OpenAIRerankResponse(
                object: "list",
                data: response.items.map { OpenAIRerankDatum(index: Int($0.index), score: $0.score) },
                model: rerankRequest.model,
                topK: Int(rerankRequest.topK)
            )
            let data = try encoder.encode(payload)
            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: .data(data)
            )
        } catch {
            return workerUnavailableResponse()
        }
    }

    private func handleAudioTranscriptions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let transcriptionRequest = try decoder.decode(OpenAIAudioTranscriptionsRequest.self, from: request.body)
        let audioReference = transcriptionRequest.normalizedAudio

        guard let modelHandle = await modelCatalog.dispatchHandle(for: transcriptionRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: transcriptionRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }
        let routeKind = await routedWorkerKind(
            forModelID: transcriptionRequest.model,
            workerRegistry: workerRegistry,
            fallback: .pythonTranscription
        )

        var workerRequest = Melix_Worker_V1_TranscribeRequest()
        workerRequest.id.requestID = UUID().uuidString
        workerRequest.modelHandle = modelHandle
        workerRequest.format = audioReference.format ?? ""
        workerRequest.task = transcriptionRequest.task ?? "transcribe"
        workerRequest.language = transcriptionRequest.language ?? ""
        workerRequest.audio.mediaType = .audio
        workerRequest.audio.format = audioReference.format ?? ""
        workerRequest.audio.mimeType = audioReference.mimeType ?? ""
        workerRequest.audio.filename = audioReference.filename ?? ""

        if let audioBase64 = audioReference.data {
            guard let audioBytes = Data(base64Encoded: audioBase64) else {
                return invalidArgumentResponse(message: "audio_base64 must be valid base64.")
            }
            workerRequest.audioBytes = audioBytes
            workerRequest.audio.sourceKind = .mediaSourceInlineBytes
            workerRequest.audio.byteLength = UInt64(audioBytes.count)
        } else if let audioURL = audioReference.url, !audioURL.isEmpty {
            workerRequest.audioUri = audioURL
            workerRequest.audio.sourceKind = .mediaSourceUri
        } else {
            return invalidArgumentResponse(message: "input_audio or audio_base64/audio_url is required.")
        }

        let startedAt = Date()
        await beginMultimodalRequest(requestID: workerRequest.id.requestID, routeKind: routeKind)
        do {
            let response = try await inferenceClient.transcribe(request: workerRequest)
            if !response.error.code.isEmpty {
                await finishMultimodalRequest(
                    requestID: workerRequest.id.requestID,
                    routeKind: routeKind,
                    phase: .requestFailed
                )
                return workerErrorResponse(response.error)
            }

            let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
            await metricsStore.set(elapsedMs, forKey: "audio.transcription_request_latency_ms")
            await metricsStore.set(
                response.durationSeconds / max(elapsedMs / 1000, 0.001),
                forKey: "audio.seconds_processed_per_second"
            )
            await refreshMultimodalRuntimeObservability(using: workerClient, routeKind: routeKind)
            await finishMultimodalRequest(
                requestID: workerRequest.id.requestID,
                routeKind: routeKind,
                phase: .requestCompleted
            )

            let payload = OpenAIAudioTranscriptionsResponse(
                model: transcriptionRequest.model,
                text: response.text,
                language: response.language,
                durationSeconds: response.durationSeconds
            )
            let data = try encoder.encode(payload)
            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: .data(data)
            )
        } catch {
            await finishMultimodalRequest(
                requestID: workerRequest.id.requestID,
                routeKind: routeKind,
                phase: .requestFailed
            )
            return workerUnavailableResponse()
        }
    }

    private func handleAudioSpeech(_ request: HTTPRequest) async throws -> HTTPResponse {
        let speechRequest = try decoder.decode(OpenAIAudioSpeechRequest.self, from: request.body)

        guard let modelHandle = await modelCatalog.dispatchHandle(for: speechRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: speechRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }
        let routeKind = await routedWorkerKind(
            forModelID: speechRequest.model,
            workerRegistry: workerRegistry,
            fallback: .pythonSpeech
        )

        var workerRequest = Melix_Worker_V1_SpeakRequest()
        workerRequest.id.requestID = UUID().uuidString
        workerRequest.modelHandle = modelHandle
        workerRequest.input = speechRequest.input
        workerRequest.voice = speechRequest.voice ?? ""
        workerRequest.format = speechRequest.format ?? "wav"
        workerRequest.instructions = speechRequest.instructions ?? ""

        let startedAt = Date()
        await beginMultimodalRequest(requestID: workerRequest.id.requestID, routeKind: routeKind)
        do {
            let response = try await inferenceClient.speak(request: workerRequest)
            if !response.error.code.isEmpty {
                await finishMultimodalRequest(
                    requestID: workerRequest.id.requestID,
                    routeKind: routeKind,
                    phase: .requestFailed
                )
                return workerErrorResponse(response.error)
            }

            let resolvedFormat = response.format.isEmpty ? (speechRequest.format ?? "wav") : response.format
            let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
            await metricsStore.set(elapsedMs, forKey: "audio.speech_request_latency_ms")
            await metricsStore.set(Double(response.audioBytes.count), forKey: "audio.speech_output_bytes")
            await refreshMultimodalRuntimeObservability(using: workerClient, routeKind: routeKind)
            await finishMultimodalRequest(
                requestID: workerRequest.id.requestID,
                routeKind: routeKind,
                phase: .requestCompleted
            )

            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": audioContentType(for: resolvedFormat)],
                body: .data(response.audioBytes)
            )
        } catch {
            await finishMultimodalRequest(
                requestID: workerRequest.id.requestID,
                routeKind: routeKind,
                phase: .requestFailed
            )
            return workerUnavailableResponse()
        }
    }

    private func handleImageGenerations(_ request: HTTPRequest) async throws -> HTTPResponse {
        let imageRequest = try decoder.decode(OpenAIImageGenerationsRequest.self, from: request.body)

        guard let modelHandle = await modelCatalog.dispatchHandle(for: imageRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: imageRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }

        let routeKind = await routedWorkerKind(
            forModelID: imageRequest.model,
            workerRegistry: workerRegistry,
            fallback: .pythonImage
        )
        let requestID = imageRequest.requestID
        let jobID = "\(requestID)::image-generate"

        var workerRequest = Melix_Worker_V1_ImageGenerateRequest()
        workerRequest.id.requestID = requestID
        workerRequest.modelHandle = modelHandle
        workerRequest.prompt = imageRequest.prompt
        workerRequest.size = imageRequest.size ?? "1024x1024"
        workerRequest.n = UInt32(max(1, imageRequest.n ?? 1))
        workerRequest.responseFormat = imageRequest.responseFormat ?? "png"
        workerRequest.artifactNamespace = imageRequest.artifactNamespace ?? ""

        await imageJobReadModel?.recordQueued(
            requestID: requestID,
            jobID: jobID,
            modelID: imageRequest.model,
            operation: "image_generate",
            lane: routeKind.defaultSchedulingLane
        )
        do {
            try await imageJobAdmissionController.acquire(
                requestID: requestID,
                laneHint: routeKind.defaultSchedulingLane,
                workerID: routeKind.workerSourceID
            )
        } catch ImageJobAdmissionError.cancelled {
            await imageJobReadModel?.recordCanceled(jobID: jobID)
            return workerErrorResponse({
                var error = Melix_Worker_V1_ErrorStatus()
                error.code = "cancelled"
                error.message = "Image job was cancelled before execution."
                return error
            }())
        } catch ImageJobAdmissionError.saturated {
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: controlPlaneError(
                    code: "resource_exhausted",
                    message: "Image queue is saturated. Wait for the current job to finish."
                )
            )
            return jsonResponse(
                statusCode: 503,
                payload: ["error": ["code": "resource_exhausted", "message": "Image queue is saturated. Wait for the current job to finish."]]
            )
        } catch {
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "worker_unavailable", message: "Image admission failed: \(error)")
            )
            return workerUnavailableResponse()
        }
        await imageJobReadModel?.recordRunning(jobID: jobID, workerID: routeKind.workerSourceID, pct: 0)

        let startedAt = Date()
        do {
            let response = try await inferenceClient.imageGenerate(request: workerRequest)
            let resolvedJobID = response.job.jobID.isEmpty ? jobID : response.job.jobID
            let artifacts = response.job.artifacts.map(imageArtifactRef(from:))
            await recordImageJobTerminalState(
                jobID: resolvedJobID,
                workerJob: response.job,
                artifacts: artifacts,
                fallbackError: response.error
            )
            await finishMultimodalRequest(
                requestID: requestID,
                routeKind: routeKind,
                phase: imageJobPhase(for: response.job, error: response.error)
            )
            await refreshMultimodalRuntimeObservability(using: workerClient, routeKind: routeKind)
            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "images.request_latency_ms"
            )
            await metricsStore.set(
                Double(response.images.reduce(0) { $0 + $1.count }),
                forKey: "images.output_bytes"
            )
            await imageJobAdmissionController.finish(
                requestID: requestID,
                phase: imageJobPhase(for: response.job, error: response.error),
                workerID: routeKind.workerSourceID
            )
            if !response.error.code.isEmpty {
                return workerErrorResponse(response.error)
            }

            let payload = OpenAIImagesResponse(
                created: Int(Date().timeIntervalSince1970.rounded()),
                model: imageRequest.model,
                data: zip(response.images, response.job.artifacts).map { imageBytes, artifact in
                    OpenAIImageDatum(
                        b64JSON: imageBytes.base64EncodedString(),
                        artifact: OpenAIImageArtifactPayload(artifact: imageArtifactRef(from: artifact))
                    )
                },
                job: OpenAIImageJobPayload(job: controlPlaneImageJob(from: response.job, modelID: imageRequest.model))
            )
            let data = try encoder.encode(payload)
            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: .data(data)
            )
        } catch {
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "worker_unavailable", message: "The worker cannot accept requests.")
            )
            await imageJobAdmissionController.finish(
                requestID: requestID,
                phase: .requestFailed
            )
            return workerUnavailableResponse()
        }
    }

    private func handleImageEdits(_ request: HTTPRequest) async throws -> HTTPResponse {
        let imageRequest = try decoder.decode(OpenAIImageEditsRequest.self, from: request.body)

        let imageBytes: Data
        do {
            imageBytes = try imageRequest.normalizedImageBytes()
        } catch let error as ImageRequestNormalizationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        }

        let maskBytes: Data?
        do {
            maskBytes = try imageRequest.normalizedMaskBytes()
        } catch let error as ImageRequestNormalizationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        }

        guard let modelHandle = await modelCatalog.dispatchHandle(for: imageRequest.model) else {
            return httpErrorResponse(for: .modelNotReady)
        }
        guard
            let workerRegistry,
            let workerClient = await routedWorkerClient(forModelID: imageRequest.model, workerRegistry: workerRegistry),
            let inferenceClient = workerClient as? any NonTextInferenceWorkerClientProtocol
        else {
            return workerUnavailableResponse()
        }

        let routeKind = await routedWorkerKind(
            forModelID: imageRequest.model,
            workerRegistry: workerRegistry,
            fallback: .pythonImage
        )
        let requestID = imageRequest.requestID
        let jobID = "\(requestID)::image-edit"

        var workerRequest = Melix_Worker_V1_ImageEditRequest()
        workerRequest.id.requestID = requestID
        workerRequest.modelHandle = modelHandle
        workerRequest.prompt = imageRequest.prompt
        workerRequest.image = imageBytes
        workerRequest.imageUri = imageRequest.imageURL ?? ""
        workerRequest.mask = maskBytes ?? Data()
        workerRequest.maskUri = imageRequest.maskURL ?? ""
        workerRequest.strength = imageRequest.strength ?? 1
        workerRequest.size = imageRequest.size ?? "1024x1024"
        workerRequest.n = UInt32(max(1, imageRequest.n ?? 1))
        workerRequest.responseFormat = imageRequest.responseFormat ?? "png"

        await imageJobReadModel?.recordQueued(
            requestID: requestID,
            jobID: jobID,
            modelID: imageRequest.model,
            operation: "image_edit",
            lane: routeKind.defaultSchedulingLane
        )
        do {
            try await imageJobAdmissionController.acquire(
                requestID: requestID,
                laneHint: routeKind.defaultSchedulingLane,
                workerID: routeKind.workerSourceID
            )
        } catch ImageJobAdmissionError.cancelled {
            await imageJobReadModel?.recordCanceled(jobID: jobID)
            return workerErrorResponse({
                var error = Melix_Worker_V1_ErrorStatus()
                error.code = "cancelled"
                error.message = "Image job was cancelled before execution."
                return error
            }())
        } catch ImageJobAdmissionError.saturated {
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: controlPlaneError(
                    code: "resource_exhausted",
                    message: "Image queue is saturated. Wait for the current job to finish."
                )
            )
            return jsonResponse(
                statusCode: 503,
                payload: ["error": ["code": "resource_exhausted", "message": "Image queue is saturated. Wait for the current job to finish."]]
            )
        } catch {
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "worker_unavailable", message: "Image admission failed: \(error)")
            )
            return workerUnavailableResponse()
        }
        await imageJobReadModel?.recordRunning(jobID: jobID, workerID: routeKind.workerSourceID, pct: 0)

        let startedAt = Date()
        do {
            let response = try await inferenceClient.imageEdit(request: workerRequest)
            let resolvedJobID = response.job.jobID.isEmpty ? jobID : response.job.jobID
            let artifacts = response.job.artifacts.map(imageArtifactRef(from:))
            await recordImageJobTerminalState(
                jobID: resolvedJobID,
                workerJob: response.job,
                artifacts: artifacts,
                fallbackError: response.error
            )
            await finishMultimodalRequest(
                requestID: requestID,
                routeKind: routeKind,
                phase: imageJobPhase(for: response.job, error: response.error)
            )
            await refreshMultimodalRuntimeObservability(using: workerClient, routeKind: routeKind)
            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "images.request_latency_ms"
            )
            await metricsStore.set(
                Double(response.images.reduce(0) { $0 + $1.count }),
                forKey: "images.output_bytes"
            )
            await imageJobAdmissionController.finish(
                requestID: requestID,
                phase: imageJobPhase(for: response.job, error: response.error),
                workerID: routeKind.workerSourceID
            )
            if !response.error.code.isEmpty {
                return workerErrorResponse(response.error)
            }

            let outputArtifacts = Array(response.job.artifacts.suffix(response.images.count))
            let payload = OpenAIImagesResponse(
                created: Int(Date().timeIntervalSince1970.rounded()),
                model: imageRequest.model,
                data: zip(response.images, outputArtifacts).map { imageBytes, artifact in
                    OpenAIImageDatum(
                        b64JSON: imageBytes.base64EncodedString(),
                        artifact: OpenAIImageArtifactPayload(artifact: imageArtifactRef(from: artifact))
                    )
                },
                job: OpenAIImageJobPayload(job: controlPlaneImageJob(from: response.job, modelID: imageRequest.model))
            )
            let data = try encoder.encode(payload)
            return HTTPResponse(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: .data(data)
            )
        } catch {
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: controlPlaneError(code: "worker_unavailable", message: "The worker cannot accept requests.")
            )
            await imageJobAdmissionController.finish(
                requestID: requestID,
                phase: .requestFailed
            )
            return workerUnavailableResponse()
        }
    }

    private func translatedRequest(
        _ normalized: NormalizedTextRequest
    ) async throws -> TranslatedChatRequest {
        guard normalized.stream else {
            throw HTTPRequestHandlingError.streamRequired
        }
        let modelHandle: String
        do {
            modelHandle = try await OnDemandModelLoader.ensureTextModelReady(
                modelID: normalized.model,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
        } catch OnDemandModelLoadError.modelNotReady {
            throw HTTPRequestHandlingError.modelNotReady
        } catch OnDemandModelLoadError.workerUnavailable {
            throw HTTPRequestHandlingError.workerUnavailable
        } catch {
            throw HTTPRequestHandlingError.workerUnavailable
        }
        let shapingStartedAt = Date()
        let translated = try translator.translate(normalized, modelHandle: modelHandle)
        await recordShapingMetrics(for: translated, startedAt: shapingStartedAt)
        return translated
    }

    private func recordShapingMetrics(
        for translated: TranslatedChatRequest,
        startedAt: Date
    ) async {
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "http.shaping_ms"
        )
        if translated.workerRequest.execution.ext["melix.preset_id"] != nil {
            await metricsStore.increment("http.preset_shaped_count")
        }
        if translated.workerRequest.execution.ext["melix.workflow"] != nil {
            await metricsStore.increment("http.workflow_shaped_count")
        }
    }

    private func streamResponse(
        translated: TranslatedChatRequest,
        shape: SSEStreamWriter.StreamShape
    ) async throws -> HTTPResponse {
        let execution: CoordinatedChatExecution

        do {
            execution = try await requestCoordinator.startChatCompletion(translated)
        } catch let error as RequestCoordinatorError {
            return jsonResponse(statusCode: error.statusCode, payload: [
                "error": [
                    "code": error.errorCode,
                    "message": error.errorMessage,
                ],
            ])
        }

        let stream = sseWriter.encode(
            stream: execution.stream,
            requestID: execution.requestID,
            modelID: execution.modelID,
            shape: shape
        )

        return HTTPResponse(
            statusCode: 200,
            headers: [
                "content-type": "text/event-stream; charset=utf-8",
                "cache-control": "no-cache",
                "connection": "keep-alive",
            ],
            body: .stream(stream)
        )
    }

    private func jsonResponse(statusCode: Int, payload: [String: Any]) -> HTTPResponse {
        let data = (try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])) ?? Data("{}".utf8)
        return HTTPResponse(
            statusCode: statusCode,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func httpErrorResponse(for error: HTTPRequestHandlingError) -> HTTPResponse {
        switch error {
        case .streamRequired:
            return jsonResponse(
                statusCode: 400,
                payload: ["error": ["code": "stream_required", "message": "Phase 4 currently supports stream=true only."]]
            )
        case .modelNotReady:
            return jsonResponse(
                statusCode: 409,
                payload: ["error": ["code": "model_not_ready", "message": "Requested model is not loaded."]]
            )
        case .workerUnavailable:
            return workerUnavailableResponse()
        }
    }

    private func workerUnavailableResponse() -> HTTPResponse {
        jsonResponse(
            statusCode: 503,
            payload: ["error": ["code": "worker_unavailable", "message": "The worker cannot accept requests."]]
        )
    }

    private func invalidArgumentResponse(message: String) -> HTTPResponse {
        jsonResponse(
            statusCode: 400,
            payload: ["error": ["code": "invalid_argument", "message": message]]
        )
    }

    private func workerErrorResponse(_ error: Melix_Worker_V1_ErrorStatus) -> HTTPResponse {
        let statusCode: Int
        switch error.code {
        case "invalid_argument":
            statusCode = 400
        case "not_found":
            statusCode = 404
        case "cancelled":
            statusCode = 409
        default:
            statusCode = 500
        }

        return jsonResponse(
            statusCode: statusCode,
            payload: ["error": ["code": error.code, "message": error.message]]
        )
    }

    private func imageArtifactRef(
        from artifact: Melix_Worker_V1_ImageArtifactMetadata
    ) -> Melix_Controlplane_V1_ImageArtifactRef {
        var ref = Melix_Controlplane_V1_ImageArtifactRef()
        ref.artifactID = artifact.artifactID
        ref.jobID = artifact.jobID
        ref.role = Melix_Controlplane_V1_ImageArtifactRole(rawValue: artifact.role.rawValue) ?? .unspecified
        ref.mimeType = artifact.mimeType
        ref.format = artifact.format
        ref.width = artifact.width
        ref.height = artifact.height
        ref.byteLength = artifact.byteLength
        ref.storageUri = artifact.storageUri
        ref.sha256 = artifact.sha256
        ref.variantIndex = artifact.variantIndex
        ref.ext = artifact.ext
        return ref
    }

    private func controlPlaneImageJob(
        from workerJob: Melix_Worker_V1_ImageJobDescriptor,
        modelID: String
    ) -> Melix_Controlplane_V1_ImageJobSummary {
        var job = Melix_Controlplane_V1_ImageJobSummary()
        job.jobID = workerJob.jobID
        job.requestID = workerJob.requestID
        job.modelID = modelID
        job.operation = workerJob.operation
        job.state = Melix_Controlplane_V1_ImageJobState(rawValue: workerJob.state.rawValue) ?? .unspecified
        job.progress.stage = workerJob.progress.stage
        job.progress.pct = workerJob.progress.pct
        job.progress.completedSteps = workerJob.progress.completedSteps
        job.progress.totalSteps = workerJob.progress.totalSteps
        job.artifacts = workerJob.artifacts.map(imageArtifactRef(from:))
        job.error = controlPlaneError(from: workerJob.error)
        job.cancelable = workerJob.cancelable
        job.createdAtUnixMs = workerJob.createdAtUnixMs
        job.updatedAtUnixMs = workerJob.updatedAtUnixMs
        return job
    }

    private func controlPlaneError(from workerError: Melix_Worker_V1_ErrorStatus) -> Melix_Controlplane_V1_ErrorStatus {
        controlPlaneError(code: workerError.code, message: workerError.message)
    }

    private func controlPlaneError(code: String, message: String) -> Melix_Controlplane_V1_ErrorStatus {
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = code
        error.message = message
        return error
    }

    private func imageJobPhase(
        for workerJob: Melix_Worker_V1_ImageJobDescriptor,
        error: Melix_Worker_V1_ErrorStatus
    ) -> Melix_Controlplane_V1_RequestPhase {
        if !error.code.isEmpty {
            if error.code == "cancelled" || workerJob.state == .imageJobCanceled {
                return .requestAborted
            }
            return .requestFailed
        }

        switch workerJob.state {
        case .imageJobCompleted:
            return .requestCompleted
        case .imageJobCanceled:
            return .requestAborted
        case .imageJobFailed:
            return .requestFailed
        default:
            return .requestCompleted
        }
    }

    private func recordImageJobTerminalState(
        jobID: String,
        workerJob: Melix_Worker_V1_ImageJobDescriptor,
        artifacts: [Melix_Controlplane_V1_ImageArtifactRef],
        fallbackError: Melix_Worker_V1_ErrorStatus
    ) async {
        let resolvedError = if !workerJob.error.code.isEmpty {
            controlPlaneError(from: workerJob.error)
        } else {
            controlPlaneError(from: fallbackError)
        }

        switch workerJob.state {
        case .imageJobCompleted:
            await imageJobReadModel?.recordCompleted(jobID: jobID, artifacts: artifacts)
        case .imageJobCanceled:
            await imageJobReadModel?.recordCanceled(jobID: jobID)
        case .imageJobFailed, .unspecified:
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: resolvedError
            )
        default:
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: resolvedError.code.isEmpty
                    ? controlPlaneError(code: "runtime_error", message: "Image job finished in an invalid state.")
                    : resolvedError
            )
        }
    }

    private func healthRoutes() async -> [String: Bool] {
        let routes: [WorkerRouteKind] = [
            .swiftText,
            .pythonEmbedding,
            .pythonRerank,
            .pythonModelOperations,
            .pythonTranscription,
            .pythonSpeech,
            .pythonImage,
        ]
        guard let workerRegistry else {
            return Dictionary(uniqueKeysWithValues: routes.map { ($0.rawValue, false) })
        }

        var values: [String: Bool] = [:]
        for route in routes {
            if let client = await workerRegistry.client(for: route) {
                values[route.rawValue] = await client.canDispatchRequests()
            } else {
                values[route.rawValue] = false
            }
        }
        return values
    }

    private func routedWorkerClient(
        forModelID modelID: String,
        workerRegistry: WorkerRegistry
    ) async -> (any WorkerRoutingClient)? {
        if let model = await modelCatalog.model(id: modelID),
           let route = await workerRegistry.route(for: model) {
            return await workerRegistry.client(for: route)
        }
        return await workerRegistry.client(forModelID: modelID)
    }

    private func routedWorkerKind(
        forModelID modelID: String,
        workerRegistry: WorkerRegistry,
        fallback: WorkerRouteKind
    ) async -> WorkerRouteKind {
        if let model = await modelCatalog.model(id: modelID),
           let route = await workerRegistry.route(for: model) {
            return route
        }
        return fallback
    }

    private func beginMultimodalRequest(
        requestID: String,
        routeKind: WorkerRouteKind
    ) async {
        guard let schedulerReadModel else { return }
        await schedulerReadModel.recordQueued(
            requestID: requestID,
            laneHint: routeKind.defaultSchedulingLane,
            priority: 0,
            workerID: routeKind.workerSourceID
        )
        _ = await schedulerReadModel.recordAdmitted(
            requestID: requestID,
            laneHint: routeKind.defaultSchedulingLane,
            priority: 0,
            workerID: routeKind.workerSourceID
        )
    }

    private func finishMultimodalRequest(
        requestID: String,
        routeKind: WorkerRouteKind,
        phase: Melix_Controlplane_V1_RequestPhase
    ) async {
        await schedulerReadModel?.recordTerminalState(
            requestID: requestID,
            phase: phase,
            workerID: routeKind.workerSourceID
        )
    }

    private func refreshMultimodalRuntimeObservability(
        using workerClient: any WorkerRoutingClient,
        routeKind: WorkerRouteKind
    ) async {
        guard
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
        case .pythonVLM:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "vision.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "vision.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastFirstTokenLatencyMs, forKey: "vision.vlm_first_token_ms")
        case .pythonTranscription:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "audio.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastTranscriptionLatencyMs, forKey: "audio.transcription_latency_ms")
            await metricsStore.set(stats.lastAudioDurationSeconds, forKey: "audio.audio_duration_seconds")
            await metricsStore.set(Double(stats.lastAudioChunkCount), forKey: "audio.audio_chunk_count")
        case .pythonSpeech:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "audio.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastSpeechLatencyMs, forKey: "audio.speech_latency_ms")
            if stats.lastAudioOutputBytes > 0 {
                await metricsStore.set(Double(stats.lastAudioOutputBytes), forKey: "audio.speech_output_bytes")
            }
        case .pythonImage:
            await metricsStore.set(stats.lastImageJobLatencyMs, forKey: "images.job_latency_ms")
            await metricsStore.set(
                stats.lastImageArtifactPublishMs,
                forKey: "images.artifact_publish_ms"
            )
            await metricsStore.set(
                Double(stats.lastImagePeakMemoryBytes),
                forKey: "images.peak_memory_bytes"
            )
            if stats.lastImageOutputBytes > 0 {
                await metricsStore.set(Double(stats.lastImageOutputBytes), forKey: "images.output_bytes")
            }
        default:
            break
        }
    }

    private func estimatedTokenCount(for inputs: [String]) -> Int {
        let total = inputs.reduce(0) { partial, value in
            let count = value.split(whereSeparator: \.isWhitespace).count
            return partial + max(count, value.isEmpty ? 0 : 1)
        }
        return max(total, inputs.isEmpty ? 0 : 1)
    }

    private func audioContentType(for format: String) -> String {
        switch format.lowercased() {
        case "mp3":
            return "audio/mpeg"
        case "wav":
            return "audio/wav"
        default:
            return "audio/\(format.lowercased())"
        }
    }
}

private enum HTTPRequestHandlingError: Error {
    case streamRequired
    case modelNotReady
    case workerUnavailable
}

private struct HealthResponse: Codable {
    let status: String
    let routes: [String: Bool]
    let modelsReady: Int
    let modelsTotal: Int

    enum CodingKeys: String, CodingKey {
        case status
        case routes
        case modelsReady = "models_ready"
        case modelsTotal = "models_total"
    }
}

private struct CacheStatsResponse: Codable {
    let l1Bytes: UInt64
    let l2Bytes: UInt64
    let l1HitRate: Double
    let l2HitRate: Double
    let checkpointCount: UInt64
    let blockCount: UInt64
    let quantizedBytes: UInt64
    let compressionRatio: Double
    let l2RestoreHitRate: Double
    let activeCacheMode: String

    enum CodingKeys: String, CodingKey {
        case l1Bytes = "l1_bytes"
        case l2Bytes = "l2_bytes"
        case l1HitRate = "l1_hit_rate"
        case l2HitRate = "l2_hit_rate"
        case checkpointCount = "checkpoint_count"
        case blockCount = "block_count"
        case quantizedBytes = "quantized_bytes"
        case compressionRatio = "compression_ratio"
        case l2RestoreHitRate = "l2_restore_hit_rate"
        case activeCacheMode = "active_cache_mode"
    }
}

private struct OpenAIEmbeddingsRequest: Codable {
    enum Input: Sendable, Codable {
        case text(String)
        case texts([String])

        init(from decoder: Decoder) throws {
            let singleValue = try decoder.singleValueContainer()
            if let text = try? singleValue.decode(String.self) {
                self = .text(text)
                return
            }
            self = .texts(try singleValue.decode([String].self))
        }

        func encode(to encoder: Encoder) throws {
            var singleValue = encoder.singleValueContainer()
            switch self {
            case let .text(text):
                try singleValue.encode(text)
            case let .texts(texts):
                try singleValue.encode(texts)
            }
        }
    }

    let model: String
    let input: Input

    var normalizedInputs: [String] {
        switch input {
        case let .text(text):
            return [text]
        case let .texts(texts):
            return texts
        }
    }
}

private struct OpenAIEmbeddingsResponse: Codable {
    let object: String
    let data: [OpenAIEmbeddingDatum]
    let model: String
    let usage: OpenAIEmbeddingsUsage
}

private struct OpenAIEmbeddingDatum: Codable {
    let object: String
    let embedding: [Float]
    let index: Int
}

private struct OpenAIEmbeddingsUsage: Codable {
    let promptTokens: Int
    let totalTokens: Int

    enum CodingKeys: String, CodingKey {
        case promptTokens = "prompt_tokens"
        case totalTokens = "total_tokens"
    }
}

private struct OpenAIRerankRequest: Codable {
    let model: String
    let query: String
    let documents: [String]
    let topK: UInt32

    enum CodingKeys: String, CodingKey {
        case model
        case query
        case documents
        case topK = "top_k"
    }
}

private struct OpenAIRerankResponse: Codable {
    let object: String
    let data: [OpenAIRerankDatum]
    let model: String
    let topK: Int

    enum CodingKeys: String, CodingKey {
        case object
        case data
        case model
        case topK = "top_k"
    }
}

private struct OpenAIRerankDatum: Codable {
    let index: Int
    let score: Float
}

private struct OpenAIAudioTranscriptionsRequest: Codable {
    let model: String
    let inputAudio: OpenAIMultimodalAudioReference?
    let audioBase64: String?
    let audioURL: String?
    let format: String?
    let language: String?
    let task: String?

    enum CodingKeys: String, CodingKey {
        case model
        case inputAudio = "input_audio"
        case audioBase64 = "audio_base64"
        case audioURL = "audio_url"
        case format
        case language
        case task
    }

    var normalizedAudio: OpenAIMultimodalAudioReference {
        if let inputAudio {
            return OpenAIMultimodalAudioReference(
                data: inputAudio.data ?? audioBase64,
                url: inputAudio.url ?? audioURL,
                format: inputAudio.format ?? format,
                mimeType: inputAudio.mimeType,
                filename: inputAudio.filename
            )
        }
        return OpenAIMultimodalAudioReference(data: audioBase64, url: audioURL, format: format)
    }
}

private struct OpenAIAudioTranscriptionsResponse: Codable {
    let model: String
    let text: String
    let language: String
    let durationSeconds: Double

    enum CodingKeys: String, CodingKey {
        case model
        case text
        case language
        case durationSeconds = "duration_seconds"
    }
}

private struct OpenAIAudioSpeechRequest: Codable {
    let model: String
    let input: String
    let voice: String?
    let format: String?
    let instructions: String?
}

private enum ImageRequestNormalizationError: Error {
    case missingImage
    case invalidImageBase64
    case invalidMaskBase64

    var operatorMessage: String {
        switch self {
        case .missingImage:
            return "image_base64 or image_url is required."
        case .invalidImageBase64:
            return "image_base64 must be valid base64."
        case .invalidMaskBase64:
            return "mask_base64 must be valid base64."
        }
    }
}

private struct OpenAIImageGenerationsRequest: Codable {
    let id: String?
    let model: String
    let prompt: String
    let size: String?
    let n: Int?
    let responseFormat: String?
    let artifactNamespace: String?

    enum CodingKeys: String, CodingKey {
        case id
        case model
        case prompt
        case size
        case n
        case responseFormat = "response_format"
        case artifactNamespace = "artifact_namespace"
    }

    var requestID: String {
        id?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? id! : UUID().uuidString
    }
}

private struct OpenAIImageEditsRequest: Codable {
    let id: String?
    let model: String
    let prompt: String
    let imageBase64: String?
    let imageURL: String?
    let maskBase64: String?
    let maskURL: String?
    let strength: Float?
    let size: String?
    let n: Int?
    let responseFormat: String?

    enum CodingKeys: String, CodingKey {
        case id
        case model
        case prompt
        case imageBase64 = "image_base64"
        case imageURL = "image_url"
        case maskBase64 = "mask_base64"
        case maskURL = "mask_url"
        case strength
        case size
        case n
        case responseFormat = "response_format"
    }

    var requestID: String {
        id?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? id! : UUID().uuidString
    }

    func normalizedImageBytes() throws -> Data {
        if let imageBase64 {
            guard let data = Data(base64Encoded: imageBase64) else {
                throw ImageRequestNormalizationError.invalidImageBase64
            }
            return data
        }
        if imageURL != nil {
            return Data()
        }
        throw ImageRequestNormalizationError.missingImage
    }

    func normalizedMaskBytes() throws -> Data? {
        guard let maskBase64 else {
            return nil
        }
        guard let data = Data(base64Encoded: maskBase64) else {
            throw ImageRequestNormalizationError.invalidMaskBase64
        }
        return data
    }
}

private struct OpenAIImagesResponse: Codable {
    let created: Int
    let model: String
    let data: [OpenAIImageDatum]
    let job: OpenAIImageJobPayload
}

private struct OpenAIImageDatum: Codable {
    let b64JSON: String
    let artifact: OpenAIImageArtifactPayload

    enum CodingKeys: String, CodingKey {
        case b64JSON = "b64_json"
        case artifact
    }
}

private struct OpenAIImageArtifactPayload: Codable {
    let artifactID: String
    let jobID: String
    let role: String
    let mimeType: String
    let format: String
    let width: UInt32
    let height: UInt32
    let byteLength: UInt64
    let storageURI: String
    let sha256: String
    let variantIndex: UInt32

    init(artifact: Melix_Controlplane_V1_ImageArtifactRef) {
        artifactID = artifact.artifactID
        jobID = artifact.jobID
        role = artifact.role.melixString
        mimeType = artifact.mimeType
        format = artifact.format
        width = artifact.width
        height = artifact.height
        byteLength = artifact.byteLength
        storageURI = artifact.storageUri
        sha256 = artifact.sha256
        variantIndex = artifact.variantIndex
    }

    enum CodingKeys: String, CodingKey {
        case artifactID = "artifact_id"
        case jobID = "job_id"
        case role
        case mimeType = "mime_type"
        case format
        case width
        case height
        case byteLength = "byte_length"
        case storageURI = "storage_uri"
        case sha256
        case variantIndex = "variant_index"
    }
}

private struct OpenAIImageJobPayload: Codable {
    let jobID: String
    let requestID: String
    let modelID: String
    let operation: String
    let state: String
    let lane: String
    let workerID: String
    let cancelable: Bool
    let createdAtUnixMs: Int64
    let updatedAtUnixMs: Int64
    let artifacts: [OpenAIImageArtifactPayload]

    init(job: Melix_Controlplane_V1_ImageJobSummary) {
        jobID = job.jobID
        requestID = job.requestID
        modelID = job.modelID
        operation = job.operation
        state = job.state.melixString
        lane = job.lane
        workerID = job.workerID
        cancelable = job.cancelable
        createdAtUnixMs = job.createdAtUnixMs
        updatedAtUnixMs = job.updatedAtUnixMs
        artifacts = job.artifacts.map(OpenAIImageArtifactPayload.init)
    }

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case requestID = "request_id"
        case modelID = "model_id"
        case operation
        case state
        case lane
        case workerID = "worker_id"
        case cancelable
        case createdAtUnixMs = "created_at_unix_ms"
        case updatedAtUnixMs = "updated_at_unix_ms"
        case artifacts
    }
}

private struct OpenAIModelsResponse: Codable {
    let object: String
    let data: [OpenAIModelDescriptor]
}

private struct OpenAIModelDescriptor: Codable {
    let id: String
    let object: String
    let ownedBy: String
    let melixState: String

    enum CodingKeys: String, CodingKey {
        case id
        case object
        case ownedBy = "owned_by"
        case melixState = "melix_state"
    }
}

private extension Melix_Controlplane_V1_ModelState {
    var melixString: String {
        switch self {
        case .modelWarm:
            return "warm"
        case .modelPinned:
            return "pinned"
        case .modelUnloaded:
            return "unloaded"
        case .modelLoading:
            return "loading"
        case .modelDiscovered:
            return "discovered"
        case .modelFailed:
            return "failed"
        case .modelEvicting:
            return "evicting"
        default:
            return "unknown"
        }
    }
}

private extension Melix_Controlplane_V1_ImageJobState {
    var melixString: String {
        switch self {
        case .imageJobQueued:
            return "queued"
        case .imageJobRunning:
            return "running"
        case .imageJobCanceled:
            return "canceled"
        case .imageJobFailed:
            return "failed"
        case .imageJobCompleted:
            return "completed"
        default:
            return "unknown"
        }
    }
}

private extension Melix_Controlplane_V1_ImageArtifactRole {
    var melixString: String {
        switch self {
        case .imageArtifactInput:
            return "input"
        case .imageArtifactMask:
            return "mask"
        case .imageArtifactGenerated:
            return "generated"
        case .imageArtifactEditSource:
            return "edit_source"
        case .imageArtifactPreview:
            return "preview"
        default:
            return "unspecified"
        }
    }
}

private extension RequestCoordinatorError {
    var statusCode: Int {
        switch self {
        case .requestAlreadyActive:
            return 409
        case .workerUnavailable:
            return 503
        }
    }

    var errorCode: String {
        switch self {
        case .requestAlreadyActive:
            return "request_already_active"
        case .workerUnavailable:
            return "worker_unavailable"
        }
    }

    var errorMessage: String {
        switch self {
        case .requestAlreadyActive:
            return "A text generation request is already active."
        case .workerUnavailable:
            return "The worker cannot accept requests."
        }
    }
}
