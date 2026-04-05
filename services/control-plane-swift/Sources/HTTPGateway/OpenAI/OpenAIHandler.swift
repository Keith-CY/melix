import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public struct RichOutputSanitizationResult: Equatable, Sendable {
    public let text: String
    public let didSanitize: Bool
    public let blockedHTMLFragmentCount: Int
    public let unsafeURIRejectionCount: Int

    public init(
        text: String,
        didSanitize: Bool,
        blockedHTMLFragmentCount: Int,
        unsafeURIRejectionCount: Int
    ) {
        self.text = text
        self.didSanitize = didSanitize
        self.blockedHTMLFragmentCount = blockedHTMLFragmentCount
        self.unsafeURIRejectionCount = unsafeURIRejectionCount
    }
}

public enum RichOutputSanitizer {
    public static func sanitized(_ text: String) -> String {
        sanitize(text).text
    }

    public static func sanitize(_ text: String) -> RichOutputSanitizationResult {
        guard text.isEmpty == false else {
            return RichOutputSanitizationResult(
                text: text,
                didSanitize: false,
                blockedHTMLFragmentCount: 0,
                unsafeURIRejectionCount: 0
            )
        }

        var output = ""
        var blockedHTMLFragmentCount = 0
        var unsafeURIRejectionCount = 0
        var cursor = text.startIndex

        while let fenceStart = text[cursor...].range(of: "```") {
            let plainSegment = String(text[cursor..<fenceStart.lowerBound])
            let sanitizedSegment = sanitizePlainSegment(plainSegment)
            output += sanitizedSegment.text
            blockedHTMLFragmentCount += sanitizedSegment.blockedHTMLFragmentCount
            unsafeURIRejectionCount += sanitizedSegment.unsafeURIRejectionCount

            if let fenceEnd = text[fenceStart.upperBound...].range(of: "```") {
                output += String(text[fenceStart.lowerBound..<fenceEnd.upperBound])
                cursor = fenceEnd.upperBound
            } else {
                output += String(text[fenceStart.lowerBound...])
                cursor = text.endIndex
                break
            }
        }

        if cursor < text.endIndex {
            let trailingSegment = sanitizePlainSegment(String(text[cursor...]))
            output += trailingSegment.text
            blockedHTMLFragmentCount += trailingSegment.blockedHTMLFragmentCount
            unsafeURIRejectionCount += trailingSegment.unsafeURIRejectionCount
        }

        return RichOutputSanitizationResult(
            text: output,
            didSanitize: output != text,
            blockedHTMLFragmentCount: blockedHTMLFragmentCount,
            unsafeURIRejectionCount: unsafeURIRejectionCount
        )
    }

    private static func sanitizePlainSegment(_ text: String) -> RichOutputSanitizationResult {
        guard text.isEmpty == false else {
            return RichOutputSanitizationResult(
                text: text,
                didSanitize: false,
                blockedHTMLFragmentCount: 0,
                unsafeURIRejectionCount: 0
            )
        }

        var sanitized = text
        var blockedHTMLFragmentCount = 0
        var unsafeURIRejectionCount = 0

        for regex in activeFragmentRegexes {
            let matches = regex.matches(
                in: sanitized,
                options: [],
                range: NSRange(location: 0, length: NSString(string: sanitized).length)
            )
            blockedHTMLFragmentCount += matches.count
            sanitized = regex.stringByReplacingMatches(
                in: sanitized,
                options: [],
                range: NSRange(location: 0, length: NSString(string: sanitized).length),
                withTemplate: ""
            )
        }

        let markdownLinkMatches = unsafeMarkdownLinkRegex.matches(
            in: sanitized,
            options: [],
            range: NSRange(location: 0, length: NSString(string: sanitized).length)
        )
        if markdownLinkMatches.isEmpty == false {
            let mutable = NSMutableString(string: sanitized)
            for match in markdownLinkMatches.reversed() {
                guard match.numberOfRanges >= 3 else {
                    continue
                }
                let label = mutable.substring(with: match.range(at: 1))
                let rawTarget = mutable.substring(with: match.range(at: 2))
                if isUnsafeLinkTarget(rawTarget) {
                    mutable.replaceCharacters(in: match.range, with: label)
                    unsafeURIRejectionCount += 1
                }
            }
            sanitized = String(mutable)
        }

        let rawUnsafeMatches = rawUnsafeURIRegex.matches(
            in: sanitized,
            options: [],
            range: NSRange(location: 0, length: NSString(string: sanitized).length)
        )
        if rawUnsafeMatches.isEmpty == false {
            unsafeURIRejectionCount += rawUnsafeMatches.count
            sanitized = rawUnsafeURIRegex.stringByReplacingMatches(
                in: sanitized,
                options: [],
                range: NSRange(location: 0, length: NSString(string: sanitized).length),
                withTemplate: "[unsafe link removed]"
            )
        }

        let genericMatches = genericHTMLTagRegex.matches(
            in: sanitized,
            options: [],
            range: NSRange(location: 0, length: NSString(string: sanitized).length)
        )
        blockedHTMLFragmentCount += genericMatches.count
        sanitized = genericHTMLTagRegex.stringByReplacingMatches(
            in: sanitized,
            options: [],
            range: NSRange(location: 0, length: NSString(string: sanitized).length),
            withTemplate: ""
        )

        return RichOutputSanitizationResult(
            text: sanitized,
            didSanitize: sanitized != text,
            blockedHTMLFragmentCount: blockedHTMLFragmentCount,
            unsafeURIRejectionCount: unsafeURIRejectionCount
        )
    }

    private static func isUnsafeLinkTarget(_ rawTarget: String) -> Bool {
        let candidate = rawTarget
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
            .first
            .map(String.init) ?? rawTarget
        let normalized = candidate
            .trimmingCharacters(in: CharacterSet(charactersIn: "<>\"'"))
            .lowercased()
        return unsafeSchemes.contains { normalized.hasPrefix($0) }
    }

    private static let unsafeSchemes = ["javascript:", "data:", "vbscript:", "file:"]

    private static let activeFragmentRegexes = [
        regex(#"(?is)<!--.*?-->"#),
        regex(#"(?is)<(script|style|iframe|object|embed|svg|math)\b[^>]*>.*?</\1\s*>"#),
    ]

    private static let genericHTMLTagRegex = regex(#"(?is)</?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]*?)?/?>"#)
    private static let unsafeMarkdownLinkRegex = regex(#"\[([^\]]+)\]\(((?:[^()]|\([^)]*\))+)\)"#)
    private static let rawUnsafeURIRegex = regex(#"(?i)\b(?:javascript|data|vbscript|file):[^\s)\]]+"#)

    private static func regex(_ pattern: String) -> NSRegularExpression {
        try! NSRegularExpression(pattern: pattern, options: [])
    }
}

public enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case delete = "DELETE"
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

private enum GatewayAuthorizationContext: Sendable {
    case localTrusted
    case credential(keyID: String, via: GatewayAccessPolicy.RequiredHeader)
    case session(token: String, metadata: PersistentAuthSessionMetadata)
}

private enum GatewayAuthorizationRoute {
    case health
    case standard
    case createSession
    case currentSession
}

private enum GatewayAuthorizationResolution {
    case success(GatewayAuthorizationContext)
    case failure(HTTPResponse)
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
    private let mcpToolCatalog: MCPToolCatalog
    private let audioAssetManager: AudioAssetManager
    private let gatewayAccessPolicyStore: GatewayAccessPolicyStore
    private let gatewayServingDefaultsStore: GatewayServingDefaultsStore
    private let gatewayRuntimeBinding: GatewayRuntimeBinding
    private let persistentAuthSessionStore: PersistentAuthSessionStore?
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
        sseWriter: SSEStreamWriter? = nil,
        mcpToolCatalog: MCPToolCatalog = .empty,
        gatewayAccessPolicy: GatewayAccessPolicy = .localTrust,
        audioAssetManager: AudioAssetManager = AudioAssetManager(),
        gatewayAccessPolicyStore: GatewayAccessPolicyStore? = nil,
        gatewayServingDefaultsStore: GatewayServingDefaultsStore? = nil,
        gatewayRuntimeBinding: GatewayRuntimeBinding = GatewayRuntimeBinding(host: "127.0.0.1", port: 11_434),
        persistentAuthSessionStore: PersistentAuthSessionStore? = nil
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
        self.sseWriter = sseWriter ?? SSEStreamWriter(metricsStore: metricsStore)
        self.mcpToolCatalog = mcpToolCatalog
        self.audioAssetManager = audioAssetManager
        self.gatewayAccessPolicyStore = gatewayAccessPolicyStore ?? GatewayAccessPolicyStore(gatewayAccessPolicy)
        self.gatewayServingDefaultsStore = gatewayServingDefaultsStore ?? GatewayServingDefaultsStore()
        self.gatewayRuntimeBinding = gatewayRuntimeBinding
        self.persistentAuthSessionStore = persistentAuthSessionStore
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.sortedKeys]
    }

    public func handle(_ request: HTTPRequest) async throws -> HTTPResponse {
        let authorization = await authorizationContext(for: request)
        switch authorization {
        case .failure(let authorizationFailure):
            return authorizationFailure
        case .success(let authorizationContext):
            switch (request.method, request.path) {
            case (.get, "/v1/models"):
                return try await handleModels()
            case (.get, "/health"):
                return try await handleHealth()
            case (.get, "/v1/cache/stats"):
                return try await handleCacheStats()
            case (.post, "/v1/melix/auth/session"):
                return try await handleCreateAuthSession(request, authorization: authorizationContext)
            case (.get, "/v1/melix/auth/session"):
                return try await handleCurrentAuthSession(authorization: authorizationContext)
            case (.delete, "/v1/melix/auth/session"):
                return try await handleDeleteAuthSession(authorization: authorizationContext)
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
    }

    private func authorizationContext(
        for request: HTTPRequest
    ) async -> GatewayAuthorizationResolution {
        let route = authorizationRoute(for: request)
        guard route != .health else {
            return .success(.localTrusted)
        }
        let gatewayAccessPolicy = await gatewayAccessPolicyStore.currentPolicy()
        if
            route != .createSession,
            let sessionToken = header(named: PersistentAuthSessionStore.sessionHeaderName, in: request.headers),
            let persistentAuthSessionStore
        {
            switch await persistentAuthSessionStore.validateSessionToken(sessionToken, policy: gatewayAccessPolicy) {
            case .success(let metadata):
                return .success(.session(token: sessionToken, metadata: metadata))
            case .failure(let failure):
                return .failure(await authSessionFailureResponse(for: failure))
            }
        } else if route == .currentSession {
            return .failure(missingAuthSessionResponse())
        }

        switch gatewayAccessPolicy.authorize(headers: request.headers) {
        case .success(let outcome):
            switch outcome {
            case .localTrusted:
                if route == .createSession {
                    return .failure(authSessionUnsupportedResponse())
                }
                return .success(.localTrusted)
            case let .authenticated(keyID, via):
                if gatewayAccessPolicy.mode == .apiKeys, gatewayAccessPolicy.sharedAccessEnabled {
                    await metricsStore.increment("shared_access.accepted_client_count")
                }
                return .success(.credential(keyID: keyID, via: via))
            }
        case .failure(let failure):
            await metricsStore.increment("gateway.auth_validation_failures")
            if gatewayAccessPolicy.mode == .apiKeys || hasNonEmptyHeader(named: "x-api-key", in: request.headers) {
                await metricsStore.increment("shared_access.rejected_request_count")
            }
            return .failure(jsonResponse(
                statusCode: failure.statusCode,
                payload: [
                    "error": [
                        "code": failure.errorCode,
                        "message": failure.message,
                    ],
                ]
            ))
        }
    }

    private func handleModels() async throws -> HTTPResponse {
        await RegistrySnapshotSync.syncModelsIfAvailable(
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore
        )
        let models = await modelCatalog.listModels().map { model in
            OpenAIModelDescriptor(
                id: model.modelID,
                object: "model",
                ownedBy: "melix",
                melixState: model.state.melixString,
                metadata: RegistrySnapshotSync.publicMetadata(from: model.settings.ext)
            )
        }

        let response = OpenAIModelsResponse(object: "list", data: models)
        return try encodedJSONResponse(response)
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
        return try encodedJSONResponse(response)
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
        return try encodedJSONResponse(response)
    }

    private func handleCreateAuthSession(
        _ request: HTTPRequest,
        authorization: GatewayAuthorizationContext
    ) async throws -> HTTPResponse {
        guard case let .credential(keyID, _) = authorization else {
            return authSessionUnsupportedResponse()
        }
        guard let persistentAuthSessionStore else {
            return jsonResponse(
                statusCode: 503,
                payload: [
                    "error": [
                        "code": "auth_session_unavailable",
                        "message": "Persistent auth sessions are unavailable.",
                    ]
                ]
            )
        }

        let createRequest = try decoder.decode(OpenAICreateAuthSessionRequest.self, from: request.body)
        let issued = try await persistentAuthSessionStore.issueSession(
            keyID: keyID,
            rememberMe: createRequest.rememberMe
        )
        let response = OpenAIAuthSessionResponse(
            session: OpenAIAuthSessionPayload(metadata: issued.metadata),
            resume: OpenAIAuthSessionResumePayload(
                header: PersistentAuthSessionStore.sessionHeaderName,
                token: issued.token
            )
        )
        return try encodedJSONResponse(response)
    }

    private func handleCurrentAuthSession(
        authorization: GatewayAuthorizationContext
    ) async throws -> HTTPResponse {
        guard case let .session(_, metadata) = authorization else {
            return missingAuthSessionResponse()
        }
        let response = OpenAIAuthSessionResponse(
            session: OpenAIAuthSessionPayload(metadata: metadata),
            resume: nil
        )
        return try encodedJSONResponse(response)
    }

    private func handleDeleteAuthSession(
        authorization: GatewayAuthorizationContext
    ) async throws -> HTTPResponse {
        guard case let .session(token, _) = authorization else {
            return missingAuthSessionResponse()
        }
        guard let persistentAuthSessionStore else {
            return missingAuthSessionResponse()
        }
        switch try await persistentAuthSessionStore.revokeSessionToken(token) {
        case .success(let metadata):
            let response = OpenAIAuthSessionResponse(
                session: OpenAIAuthSessionPayload(metadata: metadata),
                resume: nil
            )
            return try encodedJSONResponse(response)
        case .failure(let failure):
            return await authSessionFailureResponse(for: failure)
        }
    }

    private func handleChatCompletions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let requestStartedAt = Date()
        do {
            let chatRequest = try decoder.decode(OpenAIChatCompletionsRequest.self, from: request.body)
            if let resumeRequestID = chatRequest.resumeRequestID?.trimmingCharacters(in: .whitespacesAndNewlines),
               !resumeRequestID.isEmpty {
                return try await resumeStreamResponse(
                    requestID: resumeRequestID,
                    modelID: chatRequest.model,
                    shape: .chatCompletions
                )
            }
            let normalized = if chatRequest.messages.contains(where: \.hasMultimodalContent) {
                try translator.normalizeMultimodalChat(chatRequest)
            } else {
                try translator.normalize(chatRequest)
            }
            let translated = try await translatedRequest(normalized)
            return try await streamResponse(
                translated: translated,
                shape: .chatCompletions,
                requestStartedAt: requestStartedAt
            )
        } catch let error as MultimodalRequestNormalizationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as StructuredOutputFormatError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ToolParserConfigurationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ChatTemplatePolicyError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleCompletions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let requestStartedAt = Date()
        do {
            let completionsRequest = try decoder.decode(OpenAICompletionsRequest.self, from: request.body)
            let normalized = try translator.normalize(completionsRequest)
            return try await streamNormalizedTextRequest(
                normalized,
                shape: .completions,
                requestStartedAt: requestStartedAt
            )
        } catch let error as StructuredOutputFormatError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ToolParserConfigurationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ChatTemplatePolicyError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleResponses(_ request: HTTPRequest) async throws -> HTTPResponse {
        let requestStartedAt = Date()
        do {
            let responsesRequest = try decoder.decode(OpenAIResponsesRequest.self, from: request.body)
            let normalized = try translator.normalize(responsesRequest)
            return try await streamNormalizedTextRequest(
                normalized,
                shape: .responses,
                requestStartedAt: requestStartedAt
            )
        } catch let error as StructuredOutputFormatError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ToolParserConfigurationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ChatTemplatePolicyError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func handleMessages(_ request: HTTPRequest) async throws -> HTTPResponse {
        let requestStartedAt = Date()
        do {
            let messagesRequest = try decoder.decode(MelixMessagesRequest.self, from: request.body)
            let normalized = try translator.normalize(messagesRequest)
            return try await streamNormalizedTextRequest(
                normalized,
                shape: .messages,
                headers: request.headers,
                requestStartedAt: requestStartedAt
            )
        } catch let error as StructuredOutputFormatError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ToolParserConfigurationError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as ChatTemplatePolicyError {
            return invalidArgumentResponse(message: error.operatorMessage)
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func streamNormalizedTextRequest(
        _ normalized: NormalizedTextRequest,
        shape: SSEStreamWriter.StreamShape,
        headers: [String: String] = [:],
        requestStartedAt: Date
    ) async throws -> HTTPResponse {
        do {
            var translated = try await translatedRequest(normalized)
            if shape == .messages, hasNonEmptyHeader(named: "x-api-key", in: headers) {
                var workerRequest = translated.workerRequest
                workerRequest.execution.ext["melix.messages.x_api_key_present"] = "true"
                translated = TranslatedChatRequest(
                    requestID: translated.requestID,
                    modelID: translated.modelID,
                    workerRequest: workerRequest,
                    stream: translated.stream
                )
            }
            return try await streamResponse(
                translated: translated,
                shape: shape,
                requestStartedAt: requestStartedAt
            )
        } catch let error as HTTPRequestHandlingError {
            return httpErrorResponse(for: error)
        }
    }

    private func resumeStreamResponse(
        requestID: String,
        modelID: String,
        shape: SSEStreamWriter.StreamShape
    ) async throws -> HTTPResponse {
        let execution: CoordinatedChatExecution

        do {
            execution = try await requestCoordinator.resumeChatCompletion(requestID: requestID)
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
            modelID: execution.modelID.isEmpty ? modelID : execution.modelID,
            shape: shape,
            options: SSEStreamWriter.StreamOptions(includeUsage: true)
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
            return try encodedJSONResponse(payload)
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
            return try encodedJSONResponse(payload)
        } catch {
            return workerUnavailableResponse()
        }
    }

    private func handleAudioTranscriptions(_ request: HTTPRequest) async throws -> HTTPResponse {
        let transcriptionRequest = try decoder.decode(OpenAIAudioTranscriptionsRequest.self, from: request.body)
        let audioReference = transcriptionRequest.normalizedAudio

        if let preflightFailure = await audioReadinessFailureResponse(for: transcriptionRequest.model) {
            return preflightFailure
        }

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
            return try encodedJSONResponse(payload)
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
        let requestedFormat = (speechRequest.format ?? "wav").lowercased()
        if let selectedModel = await modelCatalog.model(id: speechRequest.model),
           !supportsSpeechFormat(requestedFormat, for: selectedModel) {
            return invalidArgumentResponse(
                message: "Model \(speechRequest.model) does not support format \(requestedFormat)."
            )
        }

        if let preflightFailure = await audioReadinessFailureResponse(for: speechRequest.model) {
            return preflightFailure
        }

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
        workerRequest.format = requestedFormat
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
            return try encodedJSONResponse(payload)
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
            return try encodedJSONResponse(payload)
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
        let resolvedModel = await modelCatalog.model(id: normalized.model)
        let modelToolParser: ToolParserSelection? = if let resolvedModel {
            ToolParserSelection(modelSettings: resolvedModel.settings)
        } else {
            nil
        }
        let modelChatTemplatePolicy: ModelChatTemplatePolicy? = if let resolvedModel {
            try ModelChatTemplatePolicy(modelSettings: resolvedModel.settings)
        } else {
            nil
        }
        let modelOCRPolicy: OCRExecutionPolicy? = if let resolvedModel {
            OCRExecutionPolicy(modelSettings: resolvedModel.settings)
        } else {
            nil
        }
        let modelSamplingPolicy: ModelSamplingPolicy? = if let resolvedModel {
            ModelSamplingPolicy(modelSettings: resolvedModel.settings)
        } else {
            nil
        }
        let shapingStartedAt = Date()
        let translated = try translator.translate(
            normalized,
            modelHandle: modelHandle,
            modelToolParser: modelToolParser,
            modelChatTemplatePolicy: modelChatTemplatePolicy,
            modelOCRPolicy: modelOCRPolicy,
            modelSamplingPolicy: modelSamplingPolicy,
            gatewayServingDefaults: await gatewayServingDefaultsStore.requestedDefaults(
                serverSessionID: gatewayRuntimeBinding.activeServerSessionID
            ),
            mcpToolCatalog: mcpToolCatalog
        )
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
        if translated.workerRequest.execution.ext["melix.harmony"] == "true" {
            await metricsStore.increment("http.harmony_shaped_count")
        }
        if translated.workerRequest.execution.ext["melix.structured_output.mode"] != nil {
            await metricsStore.increment("http.structured_output_request_count")
        }
        if let parserMode = translated.workerRequest.execution.ext["melix.tool_parser.mode"] {
            await metricsStore.increment("http.tool_parser_request_count")
            await metricsStore.increment("http.tool_parser_\(parserMode)_request_count")
        }
        if translated.workerRequest.execution.ext["melix.mcp.source_ids"] != nil {
            await metricsStore.increment("mcp.tool_injection_count")
            let namespaceCount = translated.workerRequest.execution.ext["melix.tool_parser.namespaces"]?
                .split(separator: ",")
                .count ?? 0
            await metricsStore.set(Double(namespaceCount), forKey: "mcp.configured_tool_count")
            await metricsStore.set(1, forKey: "mcp.tool_injection_success_rate")
        }
        if translated.workerRequest.execution.ext["melix.chat_template_kwargs.effective_json"] != nil {
            await metricsStore.increment("http.chat_template_kwargs_request_count")
        }
        if translated.workerRequest.execution.ext["melix.chat_template_kwargs.forced_json"] != nil {
            await metricsStore.increment("http.chat_template_kwargs_forced_request_count")
        }
    }

    private func streamResponse(
        translated: TranslatedChatRequest,
        shape: SSEStreamWriter.StreamShape,
        requestStartedAt: Date
    ) async throws -> HTTPResponse {
        let execution: CoordinatedChatExecution

        do {
            execution = try await requestCoordinator.startChatCompletion(
                translated,
                requestStartedAt: requestStartedAt
            )
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
            shape: shape,
            toolParser: ToolParserSelection(executionExt: translated.workerRequest.execution.ext),
            options: SSEStreamWriter.StreamOptions(
                includeUsage: translated.workerRequest.execution.ext["melix.stream.include_usage"] == "true"
            )
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

    private func encodedJSONResponse<T: Encodable>(_ payload: T, statusCode: Int = 200) throws -> HTTPResponse {
        let encoded = try encoder.encode(payload)
        let jsonObject = try JSONSerialization.jsonObject(with: encoded)
        let sanitizedPayload = Self.sanitizeJSONValue(jsonObject)
        let data: Data
        if sanitizedPayload.metrics.isEmpty {
            data = encoded
        } else {
            recordSanitizedOutputMetrics(sanitizedPayload.metrics)
            data = try JSONSerialization.data(withJSONObject: sanitizedPayload.value, options: [.sortedKeys])
        }
        return HTTPResponse(
            statusCode: statusCode,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func jsonResponse(statusCode: Int, payload: [String: Any]) -> HTTPResponse {
        let sanitizedPayload = Self.sanitizeJSONValue(payload)
        recordSanitizedOutputMetrics(sanitizedPayload.metrics)
        let data = (try? JSONSerialization.data(withJSONObject: sanitizedPayload.value, options: [.sortedKeys]))
            ?? Data("{}".utf8)
        return HTTPResponse(
            statusCode: statusCode,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private func recordSanitizedOutputMetrics(_ metrics: SanitizedOutputMetrics) {
        guard metrics.isEmpty == false else {
            return
        }
        let metricsStore = self.metricsStore
        Task {
            if metrics.enforcementCount > 0 {
                await metricsStore.increment(
                    "sanitized_output.enforcement_count",
                    by: Double(metrics.enforcementCount)
                )
            }
            if metrics.blockedHTMLFragmentCount > 0 {
                await metricsStore.increment(
                    "sanitized_output.blocked_html_fragment_count",
                    by: Double(metrics.blockedHTMLFragmentCount)
                )
            }
            if metrics.unsafeURIRejectionCount > 0 {
                await metricsStore.increment(
                    "sanitized_output.unsafe_uri_rejection_count",
                    by: Double(metrics.unsafeURIRejectionCount)
                )
            }
        }
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

    private func audioReadinessFailureResponse(for modelID: String) async -> HTTPResponse? {
        guard let selectedModel = await modelCatalog.model(id: modelID) else {
            return nil
        }

        let hydratedModel = audioAssetManager.hydrate(selectedModel)
        let backendID = hydratedModel.settings.ext["melix.audio.backend_id"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard backendID.hasPrefix("mlx_audio.") else {
            return nil
        }

        let runtimePackState = hydratedModel.settings.ext["melix.audio.runtime_pack_state"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if runtimePackState != "installed" {
            await metricsStore.increment("audio_first_use_blocked_runtime_pack_count")
            return jsonResponse(
                statusCode: 409,
                payload: [
                    "error": [
                        "code": "audio_runtime_pack_required",
                        "message": "Audio runtime support must be installed before this model can serve requests.",
                        "model_id": hydratedModel.modelID,
                        "runtime_pack_id": hydratedModel.settings.ext["melix.audio.runtime_pack_id"] ?? "",
                        "install_profile": hydratedModel.settings.ext["melix.audio.install_profile"] ?? "",
                        "required_action": "install_audio_runtime",
                    ],
                ]
            )
        }

        let modelState = hydratedModel.settings.ext["melix.audio.model_state"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if modelState != "managed_local" {
            await metricsStore.increment("audio_first_use_blocked_model_count")
            return jsonResponse(
                statusCode: 409,
                payload: [
                    "error": [
                        "code": "audio_model_download_required",
                        "message": "The requested audio model must be downloaded into Melix managed storage before it can serve requests.",
                        "model_id": hydratedModel.modelID,
                        "managed_model_root": hydratedModel.settings.ext["melix.audio.managed_model_root"] ?? "",
                        "required_action": "download",
                    ],
                ]
            )
        }

        return nil
    }

    private func hasNonEmptyHeader(
        named expectedName: String,
        in headers: [String: String]
    ) -> Bool {
        headers.contains { key, value in
            key.caseInsensitiveCompare(expectedName) == .orderedSame && !value.isEmpty
        }
    }

    private func header(
        named expectedName: String,
        in headers: [String: String]
    ) -> String? {
        headers.first { key, value in
            key.caseInsensitiveCompare(expectedName) == .orderedSame && value.isEmpty == false
        }?.value
    }

    private func authorizationRoute(for request: HTTPRequest) -> GatewayAuthorizationRoute {
        switch (request.method, request.path) {
        case (.get, "/health"):
            return .health
        case (.post, "/v1/melix/auth/session"):
            return .createSession
        case (.get, "/v1/melix/auth/session"), (.delete, "/v1/melix/auth/session"):
            return .currentSession
        default:
            return .standard
        }
    }

    private func authSessionUnsupportedResponse() -> HTTPResponse {
        jsonResponse(
            statusCode: 403,
            payload: [
                "error": [
                    "code": "auth_session_requires_configured_gateway_auth",
                    "message": "Remember-me sessions require a configured gateway credential.",
                ]
            ]
        )
    }

    private func missingAuthSessionResponse() -> HTTPResponse {
        jsonResponse(
            statusCode: 401,
            payload: [
                "error": [
                    "code": "missing_session",
                    "message": "The requested gateway session is missing.",
                    "session_state": [
                        "state": "missing",
                    ],
                ]
            ]
        )
    }

    private func authSessionFailureResponse(
        for failure: PersistentAuthSessionValidationFailure
    ) async -> HTTPResponse {
        await metricsStore.increment("gateway.auth_validation_failures")
        let payload: [String: Any]
        switch failure {
        case .missingSession:
            payload = [
                "error": [
                    "code": "missing_session",
                    "message": "The requested gateway session is missing.",
                    "session_state": [
                        "state": "missing",
                    ],
                ]
            ]
        case let .revokedSession(sessionID, keyID, rememberMe):
            payload = [
                "error": [
                    "code": "revoked_session",
                    "message": "The requested gateway session has been revoked.",
                    "session_state": [
                        "state": "revoked",
                        "session_id": sessionID,
                        "key_id": keyID,
                        "remember_me": rememberMe,
                    ],
                ]
            ]
        case let .expiredSession(sessionID, keyID, rememberMe):
            payload = [
                "error": [
                    "code": "expired_session",
                    "message": "The requested gateway session has expired.",
                    "session_state": [
                        "state": "expired",
                        "session_id": sessionID,
                        "key_id": keyID,
                        "remember_me": rememberMe,
                    ],
                ]
            ]
        }
        return jsonResponse(statusCode: 401, payload: payload)
    }

    private static func sanitizeJSONValue(_ value: Any) -> SanitizedJSONValue {
        switch value {
        case let string as String:
            let result = RichOutputSanitizer.sanitize(string)
            return SanitizedJSONValue(
                value: result.text,
                metrics: SanitizedOutputMetrics(
                    enforcementCount: result.didSanitize ? 1 : 0,
                    blockedHTMLFragmentCount: result.blockedHTMLFragmentCount,
                    unsafeURIRejectionCount: result.unsafeURIRejectionCount
                )
            )
        case let dictionary as [String: Any]:
            var sanitizedDictionary: [String: Any] = [:]
            var metrics = SanitizedOutputMetrics()
            for (key, nestedValue) in dictionary {
                let sanitizedValue = sanitizeJSONValue(nestedValue)
                sanitizedDictionary[key] = sanitizedValue.value
                metrics.formUnion(sanitizedValue.metrics)
            }
            return SanitizedJSONValue(value: sanitizedDictionary, metrics: metrics)
        case let array as [Any]:
            var sanitizedArray: [Any] = []
            var metrics = SanitizedOutputMetrics()
            for nestedValue in array {
                let sanitizedValue = sanitizeJSONValue(nestedValue)
                sanitizedArray.append(sanitizedValue.value)
                metrics.formUnion(sanitizedValue.metrics)
            }
            return SanitizedJSONValue(value: sanitizedArray, metrics: metrics)
        default:
            return SanitizedJSONValue(value: value, metrics: SanitizedOutputMetrics())
        }
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
                Double(stats.lastPreprocessInputBytes),
                forKey: "audio.preprocess_input_bytes"
            )
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastTranscriptionLatencyMs, forKey: "audio.transcription_latency_ms")
            await metricsStore.set(stats.lastAudioDurationSeconds, forKey: "audio.estimated_duration_seconds")
            await metricsStore.set(stats.lastAudioDurationSeconds, forKey: "audio.audio_duration_seconds")
            await metricsStore.set(Double(stats.lastAudioChunkCount), forKey: "audio.chunk_count")
            await metricsStore.set(Double(stats.lastAudioChunkCount), forKey: "audio.audio_chunk_count")
            await metricsStore.set(stats.lastAudioModelLoadLatencyMs, forKey: "audio.model_load_latency_ms")
            await metricsStore.set(
                Double(stats.lastAudioBackendUnavailableCount),
                forKey: "audio.backend_unavailable_count"
            )
            await metricsStore.set(
                Double(stats.lastLanguageFallbackCount),
                forKey: "audio.language_fallback_count"
            )
        case .pythonSpeech:
            await metricsStore.set(stats.lastPreprocessLatencyMs, forKey: "audio.preprocess_latency_ms")
            await metricsStore.set(
                Double(stats.lastPreprocessInputBytes),
                forKey: "audio.preprocess_input_bytes"
            )
            await metricsStore.set(
                Double(stats.lastPreprocessPeakMemoryBytes),
                forKey: "audio.preprocess_peak_memory_bytes"
            )
            await metricsStore.set(stats.lastSpeechLatencyMs, forKey: "audio.speech_latency_ms")
            await metricsStore.set(stats.lastAudioModelLoadLatencyMs, forKey: "audio.model_load_latency_ms")
            await metricsStore.set(
                Double(stats.lastAudioBackendUnavailableCount),
                forKey: "audio.backend_unavailable_count"
            )
            await metricsStore.set(
                Double(stats.lastVoiceFallbackCount),
                forKey: "audio.voice_fallback_count"
            )
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

    private func supportsSpeechFormat(
        _ format: String,
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        supportedSpeechFormats(for: model).contains(format.lowercased())
    }

    private func supportedSpeechFormats(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Set<String> {
        let rawValue = model.settings.ext["melix.audio.output_formats"]?
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
            .filter { !$0.isEmpty } ?? []
        if !rawValue.isEmpty {
            return Set(rawValue)
        }
        if model.kind == "speech" {
            return ["wav", "mp3"]
        }
        return []
    }
}

private struct SanitizedJSONValue {
    let value: Any
    let metrics: SanitizedOutputMetrics
}

private struct SanitizedOutputMetrics {
    var enforcementCount = 0
    var blockedHTMLFragmentCount = 0
    var unsafeURIRejectionCount = 0

    var isEmpty: Bool {
        enforcementCount == 0 && blockedHTMLFragmentCount == 0 && unsafeURIRejectionCount == 0
    }

    mutating func formUnion(_ other: SanitizedOutputMetrics) {
        enforcementCount += other.enforcementCount
        blockedHTMLFragmentCount += other.blockedHTMLFragmentCount
        unsafeURIRejectionCount += other.unsafeURIRejectionCount
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

private struct OpenAICreateAuthSessionRequest: Codable {
    let rememberMe: Bool

    enum CodingKeys: String, CodingKey {
        case rememberMe = "remember_me"
    }
}

private struct OpenAIAuthSessionResponse: Codable {
    let session: OpenAIAuthSessionPayload
    let resume: OpenAIAuthSessionResumePayload?
}

private struct OpenAIAuthSessionPayload: Codable {
    let sessionID: String
    let keyID: String
    let rememberMe: Bool
    let createdAtUnixMs: Int64
    let expiresAtUnixMs: Int64
    let revokedAtUnixMs: Int64
    let lastRestoredAtUnixMs: Int64
    let state: String

    init(metadata: PersistentAuthSessionMetadata) {
        sessionID = metadata.sessionID
        keyID = metadata.keyID
        rememberMe = metadata.rememberMe
        createdAtUnixMs = metadata.createdAtUnixMs
        expiresAtUnixMs = metadata.expiresAtUnixMs
        revokedAtUnixMs = metadata.revokedAtUnixMs
        lastRestoredAtUnixMs = metadata.lastRestoredAtUnixMs
        state = metadata.state
    }

    enum CodingKeys: String, CodingKey {
        case sessionID = "session_id"
        case keyID = "key_id"
        case rememberMe = "remember_me"
        case createdAtUnixMs = "created_at_unix_ms"
        case expiresAtUnixMs = "expires_at_unix_ms"
        case revokedAtUnixMs = "revoked_at_unix_ms"
        case lastRestoredAtUnixMs = "last_restored_at_unix_ms"
        case state
    }
}

private struct OpenAIAuthSessionResumePayload: Codable {
    let header: String
    let token: String
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
    let metadata: [String: String]?

    enum CodingKeys: String, CodingKey {
        case id
        case object
        case ownedBy = "owned_by"
        case melixState = "melix_state"
        case metadata
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
        case .requestNotResumable:
            return 409
        case .workerUnavailable:
            return 503
        }
    }

    var errorCode: String {
        switch self {
        case .requestAlreadyActive:
            return "request_already_active"
        case .requestNotResumable:
            return "request_not_resumable"
        case .workerUnavailable:
            return "worker_unavailable"
        }
    }

    var errorMessage: String {
        switch self {
        case .requestAlreadyActive:
            return "A text generation request is already active."
        case .requestNotResumable:
            return "The disconnected request is no longer eligible for resume."
        case .workerUnavailable:
            return "The worker cannot accept requests."
        }
    }
}
