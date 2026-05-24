import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol
import OSLog

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

    var rateLimitIdentity: String {
        switch self {
        case .localTrusted:
            return "local-trust"
        case let .credential(keyID, _):
            return "credential:\(keyID)"
        case let .session(_, metadata):
            return "credential:\(metadata.keyID)"
        }
    }
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

private struct OpenAIModelIdleSweepRequest: Sendable {
    let servedModelIDs: [String]
    let idleTimeoutSeconds: UInt32
}

private struct ResolvedOpenAITextRequest: Sendable {
    let translated: TranslatedChatRequest
    let idleSweepRequest: OpenAIModelIdleSweepRequest?

    var responseModelID: String {
        translated.responseModelID ?? translated.modelID
    }
}

private struct MediaAdmissionFailure: Sendable {
    let statusCode: Int
    let code: String
    let message: String
    let unsupportedReason: String
    let mediaCount: Int
    let routeKind: String
    let mediaKind: String?
    let toolsDisabledReason: String?
    let speculativeDisabledReason: String?

    var payload: [String: Any] {
        var error: [String: Any] = [
            "code": code,
            "message": message,
            "unsupported_reason": unsupportedReason,
            "media_count": mediaCount,
            "route_kind": routeKind,
        ]
        if let mediaKind {
            error["media_kind"] = mediaKind
        }
        if let toolsDisabledReason {
            error["tools_disabled_reason"] = toolsDisabledReason
        }
        if let speculativeDisabledReason {
            error["speculative_disabled_reason"] = speculativeDisabledReason
        }
        return ["error": error]
    }
}

private struct ResolvedServedModel: Sendable {
    let modelID: String
    let idleSweepRequest: OpenAIModelIdleSweepRequest?
}

private actor ModelIdleSweepScheduler {
    private let modelCatalog: ModelCatalog
    private let workerRegistry: WorkerRegistry?
    private let metricsStore: MetricsStore
    private let minimumIntervalSeconds: TimeInterval
    private let now: @Sendable () -> Date
    private var lastSweepStartedAt: Date?
    private var sweepInFlight = false

    init(
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore,
        minimumIntervalSeconds: TimeInterval,
        now: @escaping @Sendable () -> Date
    ) {
        self.modelCatalog = modelCatalog
        self.workerRegistry = workerRegistry
        self.metricsStore = metricsStore
        self.minimumIntervalSeconds = minimumIntervalSeconds
        self.now = now
    }

    func schedule(
        servedModelIDs: [String],
        idleTimeoutSeconds: UInt32
    ) {
        // The in-flight flag is a circuit breaker: request traffic can keep
        // scheduling, but only one sweep should hold worker/catalog resources.
        guard idleTimeoutSeconds > 0, servedModelIDs.isEmpty == false, sweepInFlight == false else {
            return
        }
        let startedAt = now()
        if let lastSweepStartedAt,
           startedAt.timeIntervalSince(lastSweepStartedAt) < minimumIntervalSeconds {
            return
        }
        self.lastSweepStartedAt = startedAt
        sweepInFlight = true
        Task.detached(priority: .background) { [modelCatalog, workerRegistry, metricsStore, servedModelIDs, idleTimeoutSeconds] in
            // sweepIdleModels is declared async (not async throws), so markSweepFinished
            // is always reached. If its signature ever gains `throws`, wrap the call in
            // do/catch and call markSweepFinished() in both branches to keep the circuit
            // breaker from getting permanently stuck.
            _ = await OnDemandModelLoader.sweepIdleModels(
                servedModelIDs: servedModelIDs,
                idleTimeoutSeconds: idleTimeoutSeconds,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
            await self.markSweepFinished()
        }
    }

    private func markSweepFinished() {
        sweepInFlight = false
    }
}

public struct OpenAIHandler: Sendable {
    private static let defaultSpeechStreamIntervalMs: UInt32 = 20
    private static let maxSpeechStreamIntervalMs: UInt32 = 1_000
    private static let modelIdleSweepDebounceSeconds: TimeInterval = 30
    private static let logger = Logger(subsystem: "Melix.ControlPlane", category: "OpenAIHandler")

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
    private let gatewayConfigStore: GatewayConfigStore
    private let gatewayServingDefaultsStore: GatewayServingDefaultsStore
    private let gatewayRuntimeBinding: GatewayRuntimeBinding
    private let gatewayRateLimiter: GatewayRateLimiter
    private let persistentAuthSessionStore: PersistentAuthSessionStore?
    private let environment: [String: String]
    private let imageRequestTimeoutSeconds: UInt32
    private let now: @Sendable () -> Date
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let idleSweepScheduler: ModelIdleSweepScheduler

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
        gatewayConfigStore: GatewayConfigStore? = nil,
        gatewayServingDefaultsStore: GatewayServingDefaultsStore? = nil,
        gatewayRuntimeBinding: GatewayRuntimeBinding = GatewayRuntimeBinding(
            host: MelixGatewayDefaults.host,
            port: UInt32(MelixGatewayDefaults.port)
        ),
        gatewayRateLimiter: GatewayRateLimiter? = nil,
        persistentAuthSessionStore: PersistentAuthSessionStore? = nil,
        now: @escaping @Sendable () -> Date = Date.init,
        environment: [String: String] = ProcessInfo.processInfo.environment
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
        self.gatewayConfigStore = gatewayConfigStore ?? Self.transientGatewayConfigStore(environment: environment)
        self.gatewayServingDefaultsStore = gatewayServingDefaultsStore ?? GatewayServingDefaultsStore(environment: environment)
        self.gatewayRuntimeBinding = gatewayRuntimeBinding
        self.gatewayRateLimiter = gatewayRateLimiter ?? GatewayRateLimiter()
        self.persistentAuthSessionStore = persistentAuthSessionStore
        self.environment = environment
        self.imageRequestTimeoutSeconds = Self.resolveImageRequestTimeoutSeconds(environment: environment)
        self.now = now
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.sortedKeys]
        self.idleSweepScheduler = ModelIdleSweepScheduler(
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            minimumIntervalSeconds: Self.modelIdleSweepDebounceSeconds,
            now: now
        )
    }

    private static func transientGatewayConfigStore(environment: [String: String]) -> GatewayConfigStore {
        GatewayConfigStore(
            storeURL: FileManager.default.temporaryDirectory
                .appendingPathComponent("melix-openai-gateway-config-\(UUID().uuidString).json"),
            defaults: environment
        )
    }

    public func handle(_ request: HTTPRequest) async throws -> HTTPResponse {
        let authorization = await authorizationContext(for: request)
        switch authorization {
        case .failure(let authorizationFailure):
            return authorizationFailure
        case .success(let authorizationContext):
            if let rateLimitFailure = await rateLimitFailureResponse(
                for: request,
                authorization: authorizationContext
            ) {
                return rateLimitFailure
            }
            switch (request.method, request.path) {
            case (.get, "/.well-known/melix.json"):
                return try await handleDiscoveryWellKnown()
            case (.get, "/api/capabilities"):
                return try await handleDiscoveryCapabilities()
            case (.get, "/api/instructions"):
                return try await handleDiscoveryInstructions()
            case (.get, "/api/config-metadata"):
                return try await handleDiscoveryConfigMetadata()
            case (.get, "/v1/models"):
                return try await handleModels()
            case (.get, "/health"):
                return try await handleHealth()
            case (.get, "/v1/melix/health"):
                return try await handleHealthDiagnostics()
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
        await metricsStore.set(gatewayAccessPolicy.metricModeCode, forKey: "route_auth_policy")
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
            metricsStore: metricsStore,
            rescan: true
        )
        let models = await modelCatalog.listModels()
            .filter(ModelCatalogPresentation.isUserVisible)
            .map { model in
                OpenAIModelDescriptor(
                    id: model.modelID,
                    object: "model",
                    ownedBy: "melix",
                    melixState: model.state.melixString,
                    metadata: ModelCatalogPresentation.publicAPIMetadata(for: model)
                )
            }

        let response = OpenAIModelsResponse(object: "list", data: models)
        return try encodedJSONResponse(response)
    }

    private func handleDiscoveryWellKnown() async throws -> HTTPResponse {
        let startedAt = DispatchTime.now()
        let payload = HTTPRuntimeDiscoveryPayloads(
            environment: environment,
            runtimeBinding: gatewayRuntimeBinding
        ).wellKnownPayload()
        await metricsStore.set(
            elapsedMilliseconds(since: startedAt),
            forKey: "operator.discovery_well_known_latency_ms"
        )
        return jsonResponse(statusCode: 200, payload: payload)
    }

    private func handleDiscoveryCapabilities() async throws -> HTTPResponse {
        let startedAt = DispatchTime.now()
        let payload = HTTPRuntimeDiscoveryPayloads(
            environment: environment,
            runtimeBinding: gatewayRuntimeBinding
        ).capabilitiesPayload(models: await modelCatalog.listModels())
        await metricsStore.set(
            elapsedMilliseconds(since: startedAt),
            forKey: "operator.discovery_capabilities_latency_ms"
        )
        return jsonResponse(statusCode: 200, payload: payload)
    }

    private func handleDiscoveryInstructions() async throws -> HTTPResponse {
        let startedAt = DispatchTime.now()
        let payload = HTTPRuntimeDiscoveryPayloads(
            environment: environment,
            runtimeBinding: gatewayRuntimeBinding
        ).instructionsPayload()
        await metricsStore.set(
            elapsedMilliseconds(since: startedAt),
            forKey: "operator.discovery_instructions_latency_ms"
        )
        return jsonResponse(statusCode: 200, payload: payload)
    }

    private func handleDiscoveryConfigMetadata() async throws -> HTTPResponse {
        let startedAt = DispatchTime.now()
        let payload = HTTPRuntimeDiscoveryPayloads(
            environment: environment,
            runtimeBinding: gatewayRuntimeBinding
        ).configMetadataPayload()
        await metricsStore.set(
            elapsedMilliseconds(since: startedAt),
            forKey: "operator.discovery_config_metadata_latency_ms"
        )
        return jsonResponse(statusCode: 200, payload: payload)
    }

    private func handleHealth() async throws -> HTTPResponse {
        let startedAt = Date()
        let response = HealthResponse(
            status: "ok",
            service: "melix-control-plane"
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "operator.health_latency_ms"
        )
        return try encodedJSONResponse(response)
    }

    private func handleHealthDiagnostics() async throws -> HTTPResponse {
        let startedAt = Date()
        let routes = await healthRoutes()
        let models = await modelCatalog.listModels()
        let readyCount = models.filter { $0.state == .modelWarm || $0.state == .modelPinned }.count
        let status = routes.values.allSatisfy { $0 } ? "ok" : "degraded"
        let response = HealthDiagnosticsResponse(
            status: status,
            routes: routes,
            modelsReady: readyCount,
            modelsTotal: models.count,
            models: models
                .filter(ModelCatalogPresentation.isUserVisible)
                .map(HealthDiagnosticsModelResponse.init(model:))
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "operator.health_diagnostics_latency_ms"
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

    private func rateLimitFailureResponse(
        for request: HTTPRequest,
        authorization: GatewayAuthorizationContext
    ) async -> HTTPResponse? {
        let route = authorizationRoute(for: request)
        guard route != .health else {
            return nil
        }
        let limit = await activeGatewayRateLimitPerMinute()
        let decision = await gatewayRateLimiter.admit(
            identity: authorization.rateLimitIdentity,
            limitPerMinute: limit
        )
        await metricsStore.set(Double(limit), forKey: "gateway.rate_limit_per_minute")
        await metricsStore.set(Double(decision.remaining), forKey: "gateway.rate_limit_remaining")
        await metricsStore.set(decision.allowed ? 1 : 0, forKey: "gateway.rate_limit_last_admission")
        guard !decision.allowed else {
            return nil
        }
        await metricsStore.increment("gateway.rate_limited_request_count")
        return HTTPResponse(
            statusCode: 429,
            headers: [
                "content-type": "application/json",
                "retry-after": String(decision.retryAfterSeconds),
                "x-ratelimit-limit": String(decision.limitPerMinute),
                "x-ratelimit-remaining": String(decision.remaining),
            ],
            body: .data(jsonData([
                "error": [
                    "code": "rate_limited",
                    "message": "Gateway rate limit exceeded.",
                    "rate_limit": [
                        "identity": decision.identity,
                        "limit_per_minute": decision.limitPerMinute,
                        "retry_after_seconds": decision.retryAfterSeconds,
                    ],
                ],
            ]))
        )
    }

    private func activeGatewayRateLimitPerMinute() async -> UInt32 {
        let models = await modelCatalog.listModels()
        let fallbackModelID = models.first?.modelID ?? "melix-dev-text"
        let summary = await gatewayConfigStore.summary(
            serverSessionIDs: [gatewayRuntimeBinding.activeServerSessionID],
            runtimeBinding: gatewayRuntimeBinding,
            fallbackDefaultModelID: fallbackModelID
        )
        return summary.listeners.first(where: { $0.activeBinding })?.rateLimitPerMinute
            ?? summary.listeners.first?.rateLimitPerMinute
            ?? 120
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
        let requestStartedAt = now()
        do {
            if let boundsFailure = generationBoundsValidationFailure(in: request.body) {
                return invalidGenerationBoundsResponse(boundsFailure)
            }
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
            let resolvedRequest = try await translatedRequest(normalized)
            if let mediaAdmissionFailure = mediaAdmissionFailureResponse(resolvedRequest.translated) {
                return mediaAdmissionFailure
            }
            guard resolvedRequest.translated.stream else {
                return try await nonStreamChatCompletionsResponse(
                    resolvedRequest: resolvedRequest,
                    requestStartedAt: requestStartedAt
                )
            }
            return try await streamResponse(
                translated: resolvedRequest.translated,
                shape: .chatCompletions,
                requestStartedAt: requestStartedAt,
                idleSweepRequest: resolvedRequest.idleSweepRequest
            )
        } catch let error as MultimodalRequestNormalizationError {
            if case .externalMediaURLBlocked = error {
                return invalidArgumentResponse(message: error.operatorMessage)
            }
            return mediaNormalizationErrorResponse(error)
        } catch is DecodingError {
            return invalidArgumentResponse(message: "Malformed multimodal chat payload.")
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
            if let boundsFailure = generationBoundsValidationFailure(in: request.body) {
                return invalidGenerationBoundsResponse(boundsFailure)
            }
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
            if let boundsFailure = generationBoundsValidationFailure(in: request.body) {
                return invalidGenerationBoundsResponse(boundsFailure)
            }
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
            if let boundsFailure = generationBoundsValidationFailure(in: request.body) {
                return invalidGenerationBoundsResponse(boundsFailure)
            }
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
            var resolvedRequest = try await translatedRequest(normalized)
            if shape == .messages, hasNonEmptyHeader(named: "x-api-key", in: headers) {
                var workerRequest = resolvedRequest.translated.workerRequest
                workerRequest.execution.ext["melix.messages.x_api_key_present"] = "true"
                resolvedRequest = ResolvedOpenAITextRequest(
                    translated: TranslatedChatRequest(
                        requestID: resolvedRequest.translated.requestID,
                        modelID: resolvedRequest.translated.modelID,
                        responseModelID: resolvedRequest.translated.responseModelID,
                        workerRequest: workerRequest,
                        stream: resolvedRequest.translated.stream
                    ),
                    idleSweepRequest: resolvedRequest.idleSweepRequest
                )
            }
            if let mediaAdmissionFailure = mediaAdmissionFailureResponse(resolvedRequest.translated) {
                return mediaAdmissionFailure
            }
            return try await streamResponse(
                translated: resolvedRequest.translated,
                shape: shape,
                requestStartedAt: requestStartedAt,
                idleSweepRequest: resolvedRequest.idleSweepRequest
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
            return jsonResponse(statusCode: error.statusCode, payload: error.openAIErrorPayload)
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
        if let validationFailure = await endpointCompatibilityFailureResponse(
            modelID: embeddingsRequest.model,
            endpoint: .embedding
        ) {
            return validationFailure
        }
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
        if let validationFailure = await endpointCompatibilityFailureResponse(
            modelID: rerankRequest.model,
            endpoint: .rerank
        ) {
            return validationFailure
        }

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
        if let validationFailure = await endpointCompatibilityFailureResponse(
            modelID: transcriptionRequest.model,
            endpoint: .transcription
        ) {
            return validationFailure
        }
        let audioReference = transcriptionRequest.normalizedAudio

        if let preflightFailure = await audioReadinessFailureResponse(for: transcriptionRequest.model) {
            return preflightFailure
        }

        let modelHandle: String
        do {
            modelHandle = try await ensureAudioModelReady(
                modelID: transcriptionRequest.model,
                loadReason: "lazy_audio_transcription_load",
                metricsPrefix: "audio_transcription"
            )
        } catch OnDemandModelLoadError.runtimeCacheMissing {
            return httpErrorResponse(for: .modelRuntimeMissing)
        } catch OnDemandModelLoadError.modelNotReady {
            return httpErrorResponse(for: .modelNotReady)
        } catch OnDemandModelLoadError.workerRejected(let error) {
            return workerErrorResponse(error)
        } catch OnDemandModelLoadError.workerUnavailable {
            return workerUnavailableResponse()
        } catch {
            return workerUnavailableResponse()
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
        if let validationFailure = await endpointCompatibilityFailureResponse(
            modelID: speechRequest.model,
            endpoint: .speech
        ) {
            return validationFailure
        }
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
        let speechContextResult = await resolvedSpeechContext(for: speechRequest)
        let speechContext: ResolvedAudioSpeechContext
        switch speechContextResult {
        case .failure(let response):
            return response
        case .success(let value):
            speechContext = value
        }

        let modelHandle: String
        do {
            modelHandle = try await ensureAudioModelReady(
                modelID: speechRequest.model,
                loadReason: "lazy_audio_speech_load",
                metricsPrefix: "audio_speech"
            )
        } catch OnDemandModelLoadError.runtimeCacheMissing {
            return httpErrorResponse(for: .modelRuntimeMissing)
        } catch OnDemandModelLoadError.modelNotReady {
            return httpErrorResponse(for: .modelNotReady)
        } catch OnDemandModelLoadError.workerRejected(let error) {
            return workerErrorResponse(error)
        } catch OnDemandModelLoadError.workerUnavailable {
            return workerUnavailableResponse()
        } catch {
            return workerUnavailableResponse()
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
        let speechStreamingEnabled = speechRequest.stream ?? false
        let speechStreamIntervalMs: UInt32
        if speechStreamingEnabled {
            let requestedInterval = speechRequest.streamIntervalMs ?? Self.defaultSpeechStreamIntervalMs
            guard requestedInterval > 0, requestedInterval <= Self.maxSpeechStreamIntervalMs else {
                return invalidArgumentResponse(
                    message: "stream_interval_ms must be between 1 and \(Self.maxSpeechStreamIntervalMs)."
                )
            }
            speechStreamIntervalMs = requestedInterval
        } else {
            speechStreamIntervalMs = 0
        }
        workerRequest.streamingEnabled = speechStreamingEnabled
        workerRequest.streamIntervalMs = speechStreamIntervalMs

        let startedAt = Date()
        await beginMultimodalRequest(requestID: workerRequest.id.requestID, routeKind: routeKind)
        do {
            if speechStreamingEnabled {
                let stream = try await inferenceClient.speakStream(request: workerRequest)
                return streamAudioSpeechResponse(
                    stream,
                    requestID: workerRequest.id.requestID,
                    routeKind: routeKind,
                    workerClient: workerClient,
                    speechContext: speechContext,
                    requestedFormat: requestedFormat,
                    streamIntervalMs: speechStreamIntervalMs,
                    startedAt: startedAt
                )
            }

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
            await metricsStore.set(0, forKey: "audio.speech_streaming_enabled")
            await metricsStore.set(0, forKey: "audio.speech_streaming_interval_ms")
            await metricsStore.set(0, forKey: "audio.speech_first_audio_latency_ms")
            await refreshMultimodalRuntimeObservability(using: workerClient, routeKind: routeKind)
            await finishMultimodalRequest(
                requestID: workerRequest.id.requestID,
                routeKind: routeKind,
                phase: .requestCompleted
            )
            return HTTPResponse(
                statusCode: 200,
                headers: speechResponseHeaders(for: speechContext, resolvedFormat: resolvedFormat),
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

    private func streamAudioSpeechResponse(
        _ workerStream: AsyncThrowingStream<Melix_Worker_V1_SpeakStreamEvent, Error>,
        requestID: String,
        routeKind: WorkerRouteKind,
        workerClient: any WorkerRoutingClient,
        speechContext: ResolvedAudioSpeechContext,
        requestedFormat: String,
        streamIntervalMs: UInt32,
        startedAt: Date
    ) -> HTTPResponse {
        let responseStream = AsyncThrowingStream<Data, Error> { continuation in
            let task = Task {
                var streamedOutputBytes = 0
                var streamedAudioChunkCount = 0
                var firstAudioLatencyMs = 0.0
                var firstAudioChunkSeen = false
                var finishSeen = false

                do {
                    for try await event in workerStream {
                        switch event.kind {
                        case .envelope:
                            streamedOutputBytes += event.audioBytes.count
                            continuation.yield(event.audioBytes)
                        case .audioChunk:
                            if !firstAudioChunkSeen {
                                firstAudioLatencyMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
                                firstAudioChunkSeen = true
                                await metricsStore.set(
                                    firstAudioLatencyMs,
                                    forKey: "audio.speech_first_audio_latency_ms"
                                )
                            }
                            streamedAudioChunkCount += 1
                            streamedOutputBytes += event.audioBytes.count
                            continuation.yield(event.audioBytes)
                        case .finish:
                            finishSeen = true
                            let finish = event.finish
                            let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
                            let outputBytes = finish.audioBytes > 0
                                ? Double(finish.audioBytes)
                                : Double(streamedOutputBytes)
                            let audioChunkCount = finish.audioChunkCount > 0
                                ? Double(finish.audioChunkCount)
                                : Double(streamedAudioChunkCount)
                            let runtimeFirstAudioLatencyMs = finish.speechFirstAudioLatencyMs > 0
                                ? finish.speechFirstAudioLatencyMs
                                : firstAudioLatencyMs
                            let runtimeSpeechLatencyMs = finish.speechLatencyMs > 0
                                ? finish.speechLatencyMs
                                : elapsedMs
                            let runtimeStreamIntervalMs = finish.speechStreamingIntervalMs > 0
                                ? finish.speechStreamingIntervalMs
                                : streamIntervalMs

                            await metricsStore.set(elapsedMs, forKey: "audio.speech_request_latency_ms")
                            await metricsStore.set(outputBytes, forKey: "audio.speech_output_bytes")
                            await metricsStore.set(audioChunkCount, forKey: "audio.speech_stream_chunk_count")
                            await metricsStore.set(1, forKey: "audio.speech_streaming_enabled")
                            await metricsStore.set(
                                Double(runtimeStreamIntervalMs),
                                forKey: "audio.speech_streaming_interval_ms"
                            )
                            await metricsStore.set(
                                runtimeFirstAudioLatencyMs,
                                forKey: "audio.speech_first_audio_latency_ms"
                            )
                            await metricsStore.set(runtimeSpeechLatencyMs, forKey: "audio.speech_latency_ms")
                        case .error:
                            await finishMultimodalRequest(
                                requestID: requestID,
                                routeKind: routeKind,
                                phase: .requestFailed
                            )
                            continuation.finish(
                                throwing: WorkerClientError.requestFailed(
                                    code: event.error.code,
                                    message: event.error.message
                                )
                            )
                            return
                        case .unspecified, .UNRECOGNIZED:
                            continue
                        }
                    }

                    if !finishSeen {
                        let elapsedMs = max(Date().timeIntervalSince(startedAt) * 1000, 0.001)
                        await metricsStore.set(elapsedMs, forKey: "audio.speech_request_latency_ms")
                        await metricsStore.set(Double(streamedOutputBytes), forKey: "audio.speech_output_bytes")
                        await metricsStore.set(
                            Double(streamedAudioChunkCount),
                            forKey: "audio.speech_stream_chunk_count"
                        )
                        await metricsStore.set(1, forKey: "audio.speech_streaming_enabled")
                        await metricsStore.set(
                            Double(streamIntervalMs),
                            forKey: "audio.speech_streaming_interval_ms"
                        )
                        await metricsStore.set(firstAudioLatencyMs, forKey: "audio.speech_first_audio_latency_ms")
                    }

                    await refreshMultimodalRuntimeObservability(using: workerClient, routeKind: routeKind)
                    await finishMultimodalRequest(
                        requestID: requestID,
                        routeKind: routeKind,
                        phase: .requestCompleted
                    )
                    continuation.finish()
                } catch {
                    await finishMultimodalRequest(
                        requestID: requestID,
                        routeKind: routeKind,
                        phase: .requestFailed
                    )
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }

        return HTTPResponse(
            statusCode: 200,
            headers: speechResponseHeaders(
                for: speechContext,
                resolvedFormat: requestedFormat,
                streaming: true,
                streamIntervalMs: streamIntervalMs
            ),
            body: .stream(responseStream)
        )
    }

    private func ensureAudioModelReady(
        modelID: String,
        loadReason: String,
        metricsPrefix: String
    ) async throws -> String {
        guard let selectedModel = await modelCatalog.model(id: modelID) else {
            throw OnDemandModelLoadError.modelNotReady
        }
        let hydratedModel = audioAssetManager.hydrate(selectedModel)
        return try await OnDemandModelLoader.ensureModelReady(
            modelID: modelID,
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            loadReason: loadReason,
            metricsPrefix: metricsPrefix,
            summaryOverride: hydratedModel
        )
    }

    private func handleImageGenerations(_ request: HTTPRequest) async throws -> HTTPResponse {
        let imageRequest = try decoder.decode(OpenAIImageGenerationsRequest.self, from: request.body)
        if let validationFailure = await endpointCompatibilityFailureResponse(
            modelID: imageRequest.model,
            endpoint: .imageGeneration
        ) {
            return validationFailure
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
            lane: routeKind.defaultSchedulingLane,
            recipe: imageJobRecipe(
                prompt: imageRequest.prompt,
                size: workerRequest.size,
                steps: 0,
                guidance: 0,
                strength: nil,
                negativePrompt: "",
                variantCount: workerRequest.n,
                responseFormat: workerRequest.responseFormat,
                artifactNamespace: workerRequest.artifactNamespace,
                sourceImageURI: "",
                maskURI: ""
            ),
            timeoutSeconds: imageRequestTimeoutSeconds
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

            let queuedReplyJob = await imageJobReadModel?.job(jobID: resolvedJobID)
            let persistedReplyJob: Melix_Controlplane_V1_ImageJobSummary?
            if let queuedReplyJob {
                persistedReplyJob = queuedReplyJob
            } else {
                persistedReplyJob = await imageJobReadModel?.job(requestID: requestID)
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
                job: OpenAIImageJobPayload(
                    job: persistedReplyJob ?? controlPlaneImageJob(from: response.job, modelID: imageRequest.model)
                )
            )
            return try encodedJSONResponse(payload)
        } catch {
            let failure = imageWorkerFailure(error: error, timeoutSeconds: imageRequestTimeoutSeconds)
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: failure
            )
            await imageJobAdmissionController.finish(
                requestID: requestID,
                phase: .requestFailed
            )
            return workerErrorResponse({
                var workerError = Melix_Worker_V1_ErrorStatus()
                workerError.code = failure.code
                workerError.message = failure.message
                return workerError
            }())
        }
    }

    private func handleImageEdits(_ request: HTTPRequest) async throws -> HTTPResponse {
        let imageRequest = try decoder.decode(OpenAIImageEditsRequest.self, from: request.body)
        if let validationFailure = await endpointCompatibilityFailureResponse(
            modelID: imageRequest.model,
            endpoint: .imageEdit
        ) {
            return validationFailure
        }
        let resolvedEditMode = resolvedImageEditMode(imageRequest.editMode)
        let sourceArtifactID = imageRequest.sourceArtifactID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let promptDelta = imageRequest.promptDelta?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        if (resolvedEditMode == .variation || resolvedEditMode == .iterate) && sourceArtifactID.isEmpty {
            return invalidArgumentResponse(message: "source_artifact_id is required for variation and iterate image requests.")
        }

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

        if (resolvedEditMode == .variation || resolvedEditMode == .iterate) && sourceArtifactID.isEmpty {
            return invalidArgumentResponse(message: "source_artifact_id is required for variation and iterate image requests.")
        }
        if resolvedEditMode != .iterate && promptDelta.isEmpty == false {
            return invalidArgumentResponse(message: "prompt_delta is only supported for iterate image requests.")
        }
        if resolvedEditMode == .iterate && promptDelta.isEmpty {
            return invalidArgumentResponse(message: "prompt_delta is required for iterate image requests.")
        }
        if sourceArtifactID.isEmpty == false && (imageBytes.isEmpty == false || imageRequest.imageURL != nil) {
            return invalidArgumentResponse(message: "source_artifact_id cannot be combined with image_base64 or image_url.")
        }

        let requestedImageURL = imageRequest.imageURL?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let requestedMaskURL = imageRequest.maskURL?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var imageURLReceipt: ExternalMediaURLAdmissionReceipt?
        var maskURLReceipt: ExternalMediaURLAdmissionReceipt?
        var resolvedImageURI = ""
        if !requestedImageURL.isEmpty {
            switch await admittedExternalMediaURI(requestedImageURL, mediaKind: "image") {
            case let .accepted(receipt):
                resolvedImageURI = requestedImageURL
                imageURLReceipt = receipt
            case let .rejected(response):
                return response
            }
        }
        let resolvedMaskURI: String
        if !requestedMaskURL.isEmpty {
            switch await admittedExternalMediaURI(requestedMaskURL, mediaKind: "mask") {
            case let .accepted(receipt):
                resolvedMaskURI = requestedMaskURL
                maskURLReceipt = receipt
            case let .rejected(response):
                return response
            }
        } else {
            resolvedMaskURI = ""
        }

        var sourceJobID = ""
        if sourceArtifactID.isEmpty == false {
            guard let imageJobReadModel, let sourceArtifact = await imageJobReadModel.artifact(artifactID: sourceArtifactID) else {
                return invalidArgumentResponse(message: "Unknown source_artifact_id for image edit.")
            }
            guard sourceArtifact.storageUri.isEmpty == false else {
                return invalidArgumentResponse(message: "Resolved source artifact does not expose a storage URI.")
            }
            resolvedImageURI = sourceArtifact.storageUri
            sourceJobID = sourceArtifact.jobID
        }
        let resolvedPrompt = resolvedEditPrompt(
            prompt: imageRequest.prompt,
            promptDelta: promptDelta,
            mode: resolvedEditMode
        )

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
        workerRequest.prompt = resolvedPrompt
        workerRequest.image = imageBytes
        workerRequest.imageUri = resolvedImageURI
        workerRequest.mask = maskBytes ?? Data()
        workerRequest.maskUri = resolvedMaskURI
        workerRequest.sourceArtifactID = sourceArtifactID
        workerRequest.promptDelta = promptDelta
        workerRequest.editMode = workerImageEditMode(resolvedEditMode)
        workerRequest.strength = imageRequest.strength ?? 1
        workerRequest.size = imageRequest.size ?? "1024x1024"
        workerRequest.n = UInt32(max(1, imageRequest.n ?? 1))
        workerRequest.responseFormat = imageRequest.responseFormat ?? "png"
        if let imageURLReceipt {
            applyExternalMediaURLReceipt(imageURLReceipt, to: &workerRequest, prefix: "melix.external_media.image")
        }
        if let maskURLReceipt {
            applyExternalMediaURLReceipt(maskURLReceipt, to: &workerRequest, prefix: "melix.external_media.mask")
        }
        if sourceJobID.isEmpty == false {
            workerRequest.ext["melix.image.source_job_id"] = sourceJobID
        }

        await imageJobReadModel?.recordQueued(
            requestID: requestID,
            jobID: jobID,
            modelID: imageRequest.model,
            operation: imageEditOperationName(for: resolvedEditMode),
            lane: routeKind.defaultSchedulingLane,
            recipe: imageJobRecipe(
                prompt: resolvedPrompt,
                size: workerRequest.size,
                steps: 0,
                guidance: 0,
                strength: workerRequest.strength,
                negativePrompt: "",
                variantCount: workerRequest.n,
                responseFormat: workerRequest.responseFormat,
                artifactNamespace: "",
                sourceImageURI: resolvedImageURI,
                maskURI: workerRequest.maskUri
            ),
            timeoutSeconds: imageRequestTimeoutSeconds,
            sourceArtifactID: sourceArtifactID,
            sourceJobID: sourceJobID,
            promptDelta: promptDelta,
            editMode: resolvedEditMode
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
            let queuedReplyJob = await imageJobReadModel?.job(jobID: resolvedJobID)
            let persistedReplyJob: Melix_Controlplane_V1_ImageJobSummary?
            if let queuedReplyJob {
                persistedReplyJob = queuedReplyJob
            } else {
                persistedReplyJob = await imageJobReadModel?.job(requestID: requestID)
            }
            let payload = OpenAIImagesResponse(
                created: Int(Date().timeIntervalSince1970.rounded()),
                model: imageRequest.model,
                data: zip(response.images, outputArtifacts).map { imageBytes, artifact in
                    OpenAIImageDatum(
                        b64JSON: imageBytes.base64EncodedString(),
                        artifact: OpenAIImageArtifactPayload(artifact: imageArtifactRef(from: artifact))
                    )
                },
                job: OpenAIImageJobPayload(
                    job: persistedReplyJob ?? controlPlaneImageJob(from: response.job, modelID: imageRequest.model)
                )
            )
            return try encodedJSONResponse(payload)
        } catch {
            let failure = imageWorkerFailure(error: error, timeoutSeconds: imageRequestTimeoutSeconds)
            await imageJobReadModel?.recordFailed(
                jobID: jobID,
                error: failure
            )
            await imageJobAdmissionController.finish(
                requestID: requestID,
                phase: .requestFailed
            )
            return workerErrorResponse({
                var workerError = Melix_Worker_V1_ErrorStatus()
                workerError.code = failure.code
                workerError.message = failure.message
                return workerError
            }())
        }
    }

    private func translatedRequest(
        _ normalized: NormalizedTextRequest
    ) async throws -> ResolvedOpenAITextRequest {
        guard normalized.stream || normalized.endpoint == .chatCompletions else {
            throw HTTPRequestHandlingError.streamRequired
        }
        let resolved = try await resolveServedModelID(
            requestedModelID: normalized.model,
            endpoint: .textGeneration
        )
        let routed = normalized.replacingModel(resolved.modelID)
        let originalModelID = routed.model
        if await shouldRefreshRegistryBeforeTextRequest(modelID: routed.model) {
            await RegistrySnapshotSync.syncModelsIfAvailable(
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore,
                rescan: true
            )
        }
        let originalModel = await modelCatalog.model(id: originalModelID)
        if let unsupportedMediaResponse = await unsupportedMultimodalRequestResponse(
            routed,
            model: originalModel
        ) {
            throw HTTPRequestHandlingError.gatewayResponse(unsupportedMediaResponse)
        }
        let executionModelID = await textExecutionModelID(
            for: routed,
            servedModelID: originalModelID
        )
        let executionRequest = routed.replacingModel(executionModelID)
        let resolvedModel = executionModelID == originalModelID
            ? originalModel
            : await modelCatalog.model(id: executionModelID)
        let requestedServingDefaults = await gatewayServingDefaultsStore.requestedDefaults(
            serverSessionID: gatewayRuntimeBinding.activeServerSessionID
        )
        let servingDefaults = requestedServingDefaults.resolvingAccelerationCompatibility(for: resolvedModel)
        if let unsupportedMediaResponse = await unsupportedMultimodalAccelerationResponse(
            routed,
            gatewayServingDefaults: servingDefaults
        ) {
            throw HTTPRequestHandlingError.gatewayResponse(unsupportedMediaResponse)
        }
        if let validationFailure = await endpointCompatibilityFailureResponse(
            modelID: routed.model,
            endpoint: .textGeneration
        ) {
            throw HTTPRequestHandlingError.gatewayResponse(validationFailure)
        }
        let modelSamplingPolicy: ModelSamplingPolicy? = if let resolvedModel {
            ModelSamplingPolicy(modelSettings: resolvedModel.settings)
        } else {
            nil
        }
        if let admissionFailure = promptBudgetAdmissionFailureResponse(
            normalized: executionRequest,
            model: resolvedModel,
            modelSamplingPolicy: modelSamplingPolicy,
            gatewayServingDefaults: servingDefaults
        ) {
            throw HTTPRequestHandlingError.gatewayResponse(admissionFailure)
        }
        if let mediaAdmissionFailure = mediaAdmissionFailure(
            for: routed,
            model: originalModel,
            requestedSpeculativeDecode: servingDefaults.accelerationMode == .speculativeDecode
        ) {
            await recordMediaAdmissionFailure(mediaAdmissionFailure)
            throw HTTPRequestHandlingError.gatewayResponse(mediaAdmissionFailureResponse(mediaAdmissionFailure))
        }
        let modelHandle: String
        do {
            modelHandle = try await OnDemandModelLoader.ensureTextModelReady(
                modelID: executionModelID,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
        } catch OnDemandModelLoadError.runtimeCacheMissing {
            throw HTTPRequestHandlingError.modelRuntimeMissing
        } catch OnDemandModelLoadError.modelNotReady {
            throw HTTPRequestHandlingError.modelNotReady
        } catch OnDemandModelLoadError.workerRejected(let error) {
            throw HTTPRequestHandlingError.workerRejected(error)
        } catch OnDemandModelLoadError.workerUnavailable {
            throw HTTPRequestHandlingError.workerUnavailable
        } catch {
            throw HTTPRequestHandlingError.workerUnavailable
        }
        let modelToolParser: ToolParserSelection? = if let resolvedModel {
            ToolParserSelection(modelSettings: resolvedModel.settings)
        } else {
            nil
        }
        let shapingModelToolParser = executionRequest.mediaTypes.isEmpty ? modelToolParser : nil
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
        let shapingStartedAt = Date()
        let translated = try translator.translate(
            executionRequest,
            modelHandle: modelHandle,
            modelToolParser: shapingModelToolParser,
            modelChatTemplatePolicy: modelChatTemplatePolicy,
            modelOCRPolicy: modelOCRPolicy,
            modelSamplingPolicy: modelSamplingPolicy,
            gatewayServingDefaults: servingDefaults,
            mcpToolCatalog: mcpToolCatalog
        )
        await recordShapingMetrics(for: translated, startedAt: shapingStartedAt)
        let responseModelID = executionModelID == originalModelID ? nil : originalModelID
        let responseTranslated = TranslatedChatRequest(
            requestID: translated.requestID,
            modelID: translated.modelID,
            responseModelID: responseModelID,
            workerRequest: translated.workerRequest,
            stream: translated.stream
        )
        var finalTranslated = if executionModelID == originalModelID {
            requestWithVLMTextOnlyBatchingMetadata(
                responseTranslated,
                model: originalModel ?? resolvedModel,
                normalizedRequest: routed
            )
        } else {
            responseTranslated
        }
        let mediaAdmissionFailure = mediaAdmissionFailure(
            for: finalTranslated,
            model: originalModel ?? resolvedModel,
            requestedSpeculativeDecode: servingDefaults.accelerationMode == .speculativeDecode
        )
        if let mediaAdmissionFailure {
            finalTranslated = translatedRequest(
                finalTranslated,
                addingMediaAdmissionFailureReceipts: mediaAdmissionFailure
            )
            await recordMediaAdmissionFailure(mediaAdmissionFailure)
        }
        return ResolvedOpenAITextRequest(
            translated: finalTranslated,
            idleSweepRequest: resolved.idleSweepRequest
        )
    }

    private func mediaAdmissionFailure(
        for normalized: NormalizedTextRequest,
        model: Melix_Controlplane_V1_ModelSummary?,
        requestedSpeculativeDecode: Bool
    ) -> MediaAdmissionFailure? {
        let mediaCount = normalized.mediaPartsSummary.count
        guard mediaCount > 0 else {
            return nil
        }

        let routeKind = model.map(mediaServingRouteKind(for:)) ?? nil
        return mediaAdmissionFailure(
            mediaCount: mediaCount,
            mediaKinds: Set(normalized.mediaPartsSummary.parts.map { normalizedIdentifier($0.mediaKind) }),
            model: model,
            routeKind: routeKind,
            toolsDisabledReason: mediaRequestUsesTools(normalized) ? "media_present" : nil,
            speculativeDisabledReason: requestedSpeculativeDecode ? "media_present" : nil
        )
    }

    private func mediaAdmissionFailure(
        for translated: TranslatedChatRequest,
        model: Melix_Controlplane_V1_ModelSummary?,
        requestedSpeculativeDecode: Bool
    ) -> MediaAdmissionFailure? {
        let workerRequest = translated.workerRequest
        let mediaCount = normalizedMediaPartCount(from: workerRequest.execution.ext)
        guard mediaCount > 0 else {
            return nil
        }

        return mediaAdmissionFailure(
            mediaCount: mediaCount,
            mediaKinds: normalizedMediaPartKinds(from: workerRequest.execution.ext),
            model: model,
            routeKind: model.map(mediaServingRouteKind(for:)) ?? nil,
            toolsDisabledReason: mediaRequestUsesTools(workerRequest) ? "media_present" : nil,
            speculativeDisabledReason: requestedSpeculativeDecode
                || gatewayAccelerationMode(from: workerRequest.execution.ext) == .speculativeDecode
                ? "media_present"
                : nil
        )
    }

    private func mediaAdmissionFailure(
        mediaCount: Int,
        mediaKinds: Set<String>,
        model: Melix_Controlplane_V1_ModelSummary?,
        routeKind: WorkerRouteKind?,
        toolsDisabledReason: String?,
        speculativeDisabledReason: String?
    ) -> MediaAdmissionFailure? {
        guard mediaCount > 0 else {
            return nil
        }

        let routeKindIdentifier = routeKind?.metadataIdentifier ?? "unknown"
        if !mediaServingRouteSupportsTextMedia(routeKind) {
            return MediaAdmissionFailure(
                statusCode: 400,
                code: "unsupported_media_for_model",
                message: "Media-bearing text requests require a multimodal runtime route.",
                unsupportedReason: "text_only_runtime",
                mediaCount: mediaCount,
                routeKind: routeKindIdentifier,
                mediaKind: mediaKinds.sorted().first,
                toolsDisabledReason: toolsDisabledReason,
                speculativeDisabledReason: speculativeDisabledReason
            )
        }

        if let unsupportedMedia = unsupportedMedia(mediaKinds, for: model) {
            return MediaAdmissionFailure(
                statusCode: 400,
                code: "unsupported_media_for_model",
                message: "The selected model does not advertise support for this media kind.",
                unsupportedReason: unsupportedMedia.reason,
                mediaCount: mediaCount,
                routeKind: routeKindIdentifier,
                mediaKind: unsupportedMedia.kind,
                toolsDisabledReason: toolsDisabledReason,
                speculativeDisabledReason: speculativeDisabledReason
            )
        }

        if let toolsDisabledReason {
            return MediaAdmissionFailure(
                statusCode: 400,
                code: "unsupported_media_for_tools",
                message: "OpenAI tools are disabled for media-bearing requests.",
                unsupportedReason: "tools_disabled_for_media",
                mediaCount: mediaCount,
                routeKind: routeKindIdentifier,
                mediaKind: mediaKinds.sorted().first,
                toolsDisabledReason: toolsDisabledReason,
                speculativeDisabledReason: speculativeDisabledReason
            )
        }

        if let speculativeDisabledReason {
            return MediaAdmissionFailure(
                statusCode: 400,
                code: "unsupported_media_for_speculative_decode",
                message: "Speculative decode is disabled for media-bearing requests.",
                unsupportedReason: "speculative_disabled_for_media",
                mediaCount: mediaCount,
                routeKind: routeKindIdentifier,
                mediaKind: mediaKinds.sorted().first,
                toolsDisabledReason: nil,
                speculativeDisabledReason: speculativeDisabledReason
            )
        }

        return nil
    }

    private func normalizedMediaPartCount(from executionExt: [String: String]) -> Int {
        guard let rawCount = executionExt["melix.media_parts.count"] else {
            return 0
        }
        return Int(rawCount.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
    }

    private func normalizedMediaPartKinds(from executionExt: [String: String]) -> Set<String> {
        let mediaCount = normalizedMediaPartCount(from: executionExt)
        guard mediaCount > 0 else {
            return []
        }
        var kinds: Set<String> = []
        for index in 0..<mediaCount {
            let kind = normalizedIdentifier(executionExt["melix.media_parts.\(index).kind"])
            if !kind.isEmpty {
                kinds.insert(kind)
            }
        }
        return kinds
    }

    private func unsupportedMedia(
        _ mediaKinds: Set<String>,
        for model: Melix_Controlplane_V1_ModelSummary?
    ) -> (kind: String, reason: String)? {
        guard let model else {
            return mediaKinds.sorted().first.map { ($0, "unknown_media_modalities") }
        }
        let supportedModalities = supportedMediaTypes(for: model)
        guard !supportedModalities.isEmpty else {
            return mediaKinds.sorted().first.map { ($0, "unknown_media_modalities") }
        }
        return mediaKinds
            .sorted()
            .first { !supportedModalities.contains($0) }
            .map { ($0, "unsupported_media_modality") }
    }

    private func mediaRequestUsesTools(_ request: Melix_Worker_V1_GenerateRequest) -> Bool {
        request.execution.hasToolConfig
            || request.execution.ext["melix.tool_config.source"] != nil
    }

    private func mediaRequestUsesTools(_ request: NormalizedTextRequest) -> Bool {
        !request.tools.isEmpty || request.toolChoice != nil
    }

    private func mediaServingRouteKind(for model: Melix_Controlplane_V1_ModelSummary) -> WorkerRouteKind? {
        if let routeKind = modelRouteKind(for: model) {
            return routeKind
        }
        if model.capabilityClass == .modelCapabilityVlm || normalizedIdentifier(model.kind) == "vlm" {
            return .pythonVLM
        }
        if model.capabilityClass == .modelCapabilityOcr || normalizedIdentifier(model.kind) == "ocr" {
            return .pythonOCR
        }
        return nil
    }

    private func mediaServingRouteSupportsTextMedia(_ routeKind: WorkerRouteKind?) -> Bool {
        switch routeKind {
        case .pythonOCR, .pythonVLM:
            return true
        default:
            return false
        }
    }

    private func gatewayAccelerationMode(
        from executionExt: [String: String]
    ) -> Melix_Worker_V1_AccelerationMode {
        switch executionExt["melix.gateway.acceleration_mode"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() {
        case "speculative_decode":
            return .speculativeDecode
        default:
            return .baseline
        }
    }

    private func translatedRequest(
        _ translated: TranslatedChatRequest,
        addingMediaAdmissionFailureReceipts failure: MediaAdmissionFailure
    ) -> TranslatedChatRequest {
        var workerRequest = translated.workerRequest
        workerRequest.execution.ext["melix.media_admission.status"] = "refused"
        workerRequest.execution.ext["melix.media_admission.unsupported_reason"] = failure.unsupportedReason
        workerRequest.execution.ext["melix.media_admission.error_code"] = failure.code
        workerRequest.execution.ext["melix.media_admission.route_kind"] = failure.routeKind
        if let mediaKind = failure.mediaKind {
            workerRequest.execution.ext["melix.media_admission.media_kind"] = mediaKind
        }
        if let toolsDisabledReason = failure.toolsDisabledReason {
            workerRequest.execution.ext["melix.media_admission.tools_disabled_reason"] = toolsDisabledReason
        }
        if let speculativeDisabledReason = failure.speculativeDisabledReason {
            workerRequest.execution.ext["melix.media_admission.speculative_disabled_reason"] = speculativeDisabledReason
        }
        return TranslatedChatRequest(
            requestID: translated.requestID,
            modelID: translated.modelID,
            responseModelID: translated.responseModelID,
            workerRequest: workerRequest,
            stream: translated.stream
        )
    }

    private func recordMediaAdmissionFailure(_ failure: MediaAdmissionFailure) async {
        await metricsStore.increment("http.media_admission_refusal_count")
        await metricsStore.increment("http.media_admission_refusal.\(failure.unsupportedReason)")
    }

    private func textExecutionModelID(
        for normalizedRequest: NormalizedTextRequest,
        servedModelID: String
    ) async -> String {
        guard
            let model = await modelCatalog.model(id: servedModelID),
            shouldRouteTextOnlyRequestToCompanion(
                model: model,
                normalizedRequest: normalizedRequest
            )
        else {
            return servedModelID
        }

        let companionID = textCompanionModelID(for: servedModelID)
        if await modelCatalog.model(id: companionID) == nil {
            await modelCatalog.registerModel(
                makeTextCompanionModel(from: model, companionID: companionID),
                reason: "text_companion_registered"
            )
        }
        return companionID
    }

    private func unsupportedMultimodalRequestResponse(
        _ request: NormalizedTextRequest,
        model: Melix_Controlplane_V1_ModelSummary?
    ) async -> HTTPResponse? {
        let mediaTypes = request.mediaTypes
        guard mediaTypes.isEmpty == false else {
            return nil
        }
        if mediaRequestHasToolPath(request) {
            return await unsupportedMultimodalRequestResponse(
                modelID: request.model,
                reason: "media_tools_unsupported",
                message: "Media-bearing chat requests cannot use tools until multimodal tool routing is supported.",
                mediaTypes: mediaTypes
            )
        }
        guard let model else {
            let mediaList = mediaTypes.sorted().joined(separator: ", ")
            return await unsupportedMultimodalRequestResponse(
                modelID: request.model,
                reason: "model_does_not_support_media",
                message: "Model \(request.model) does not advertise support for \(mediaList) media.",
                mediaTypes: mediaTypes
            )
        }
        let unsupportedTypes = mediaTypes.subtracting(supportedMediaTypes(for: model))
        guard unsupportedTypes.isEmpty == false else {
            return nil
        }
        let unsupportedList = unsupportedTypes.sorted().joined(separator: ", ")
        return await unsupportedMultimodalRequestResponse(
            modelID: request.model,
            reason: "model_does_not_support_media",
            message: "Model \(request.model) does not advertise support for \(unsupportedList) media.",
            mediaTypes: mediaTypes
        )
    }

    private func mediaRequestHasToolPath(_ request: NormalizedTextRequest) -> Bool {
        if request.tools.isEmpty == false || request.toolParser?.isExplicit == true {
            return true
        }
        return !mcpToolCatalog.resolvedNamespaces.isEmpty
    }

    private func unsupportedMultimodalAccelerationResponse(
        _ request: NormalizedTextRequest,
        gatewayServingDefaults: GatewayServingDefaultsPolicy
    ) async -> HTTPResponse? {
        let mediaTypes = request.mediaTypes
        guard mediaTypes.isEmpty == false else {
            return nil
        }
        guard gatewayServingDefaults.accelerationMode == .speculativeDecode else {
            return nil
        }
        return await unsupportedMultimodalRequestResponse(
            modelID: request.model,
            reason: "media_speculative_decode_unsupported",
            message: "Media-bearing chat requests cannot use speculative decoding until multimodal drafter routing is supported.",
            mediaTypes: mediaTypes
        )
    }

    private func unsupportedMultimodalRequestResponse(
        modelID: String,
        reason: String,
        message: String,
        mediaTypes: Set<String>
    ) async -> HTTPResponse {
        await metricsStore.increment("http.multimodal_admission_rejection_count")
        await metricsStore.increment("http.multimodal_admission_rejection.\(reason)")
        return jsonResponse(
            statusCode: 400,
            payload: [
                "error": [
                    "code": "unsupported_multimodal_request",
                    "message": message,
                    "model_id": modelID,
                    "reason": reason,
                    "media_types": mediaTypes.sorted(),
                ],
            ]
        )
    }

    private func supportedMediaTypes(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Set<String> {
        let configured = normalizedIdentifierList(
            model.supportedModalities,
            fallback: model.settings.ext["melix.capability.supported_modalities"]
        )
        var supported = Set(configured)
        if !supported.isEmpty {
            return supported
        }
        let capabilityIdentifier = ModelCatalogPresentation.capabilityIdentifier(for: model)
        switch capabilityIdentifier {
        case "vlm":
            supported.insert("image")
        case "ocr", "image_generation":
            supported.formUnion(["image"])
        case "transcription":
            supported.formUnion(["audio"])
        case "speech":
            supported.formUnion(["audio", "text"])
        default:
            break
        }
        return supported
    }

    private func shouldRouteTextOnlyRequestToCompanion(
        model: Melix_Controlplane_V1_ModelSummary,
        normalizedRequest: NormalizedTextRequest
    ) -> Bool {
        guard modelRouteKind(for: model) == .pythonVLM else {
            return false
        }
        guard !falseyModelMetadata(model.settings.ext["melix.vlm.text_companion.enabled"]) else {
            return false
        }
        guard !normalizedRequestContainsNonTextMedia(normalizedRequest) else {
            return false
        }
        guard normalizedIdentifier(model.settings.ext["vision_family_id"]) == "gemma4-v1" else {
            return false
        }
        guard normalizedIdentifier(model.settings.ext["melix.vlm.backend_id"]) == "mlx_vlm" else {
            return false
        }
        return true
    }

    private func textCompanionModelID(for modelID: String) -> String {
        "\(modelID)#text"
    }

    private func makeTextCompanionModel(
        from source: Melix_Controlplane_V1_ModelSummary,
        companionID: String
    ) -> Melix_Controlplane_V1_ModelSummary {
        var companion = source
        companion.modelID = companionID
        companion.kind = "text"
        companion.state = .modelDiscovered
        companion.pinned = false
        companion.inflightRequests = 0
        companion.estimatedBytes = 0
        companion.capabilityClass = .modelCapabilityText
        companion.routeClass = .workerRouteSwiftText
        companion.features = source.features.contains("chat") ? source.features : source.features + ["chat"]
        companion.supportedModalities = ["text"]
        companion.supportedTasks = ["generate"]
        companion.settings.alias = source.settings.alias.isEmpty
            ? "\(source.modelID) text"
            : "\(source.settings.alias) text"
        companion.settings.memoryPolicy = .memoryResidencyEvictable
        companion.settings.defaultAccelerationMode = .baseline
        companion.settings.accelerationProfileID = ""
        companion.settings.ext["melix.companion.source_model_id"] = source.modelID
        companion.settings.ext["melix.companion.role"] = "text_only"
        companion.settings.ext["melix.capability.route_kind"] = WorkerRouteKind.swiftText.metadataIdentifier
        companion.settings.ext["melix.capability.class"] = "text"
        companion.settings.ext["melix.capability.supported_modalities"] = "text"
        companion.settings.ext["melix.capability.supported_tasks"] = "generate"
        companion.settings.ext["melix.capability.supported_parsers"] = "text"
        companion.settings.ext["melix.acceleration.supported_modes"] = "baseline"
        companion.settings.ext.removeValue(forKey: "melix.acceleration.target_capability")
        companion.settings.ext.removeValue(forKey: "melix.acceleration.drafter_capability")
        companion.settings.ext.removeValue(forKey: "melix.acceleration.valid_draft_model_ids")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.configured")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.configured_layers")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.indexed_layers")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.runtime_available")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.artifact_available")
        return companion
    }

    private func requestWithVLMTextOnlyBatchingMetadata(
        _ translated: TranslatedChatRequest,
        model: Melix_Controlplane_V1_ModelSummary?,
        normalizedRequest: NormalizedTextRequest
    ) -> TranslatedChatRequest {
        guard
            let model,
            modelRouteKind(for: model) == .pythonVLM,
            !normalizedRequestContainsNonTextMedia(normalizedRequest)
        else {
            return translated
        }

        var workerRequest = translated.workerRequest
        if truthyModelMetadata(model.settings.ext["melix.vlm.text_only_step_cooperative"]) {
            workerRequest.execution.ext["melix.vlm.text_only_step_cooperative"] = "true"
        }
        let batchGeneratorEnabled = truthyModelMetadata(model.settings.ext["melix.vlm.text_only_batch_generator"])
            || shouldAutoEnableVLMTextOnlyBatchGenerator(
                model: model,
                normalizedRequest: normalizedRequest,
                workerRequest: workerRequest
            )
        if batchGeneratorEnabled {
            workerRequest.execution.ext["melix.vlm.text_only_batch_generator"] = "true"
            if shouldNormalizeVLMTextOnlyBatchGeneratorSampling(
                normalizedRequest: normalizedRequest,
                workerRequest: workerRequest
            ) {
                workerRequest.sampling.topP = 1
                workerRequest.sampling.topK = 0
            }
        }
        return TranslatedChatRequest(
            requestID: translated.requestID,
            modelID: translated.modelID,
            responseModelID: translated.responseModelID,
            workerRequest: workerRequest,
            stream: translated.stream
        )
    }

    private func shouldAutoEnableVLMTextOnlyBatchGenerator(
        model: Melix_Controlplane_V1_ModelSummary,
        normalizedRequest: NormalizedTextRequest,
        workerRequest: Melix_Worker_V1_GenerateRequest
    ) -> Bool {
        guard normalizedIdentifier(model.settings.ext["vision_family_id"]) == "gemma4-v1" else {
            return false
        }
        guard normalizedIdentifier(model.settings.ext["melix.vlm.backend_id"]) == "mlx_vlm" else {
            return false
        }
        guard normalizedRequest.structuredOutput == nil,
              normalizedRequest.toolParser == nil,
              normalizedRequest.tools.isEmpty,
              normalizedRequest.toolChoice == nil,
              normalizedRequest.reasoningEffort == nil,
              normalizedRequest.enableThinking != true,
              normalizedRequest.thinking?.isEnabled != true
        else {
            return false
        }
        // SamplingConfig.temperature is Float32; compare the translated worker
        // value with Float32-sized tolerance after request shaping.
        // Gate final worker sampling so future top-k shaping cannot enter this path.
        guard normalizedRequest.temperature != nil,
              abs(Double(workerRequest.sampling.temperature)) < 1e-6,
              workerRequest.sampling.topK == 0
        else {
            return false
        }
        if let requestedTopP = normalizedRequest.topP {
            return abs(requestedTopP - 1) < 1e-9
        }
        return true
    }

    private func shouldNormalizeVLMTextOnlyBatchGeneratorSampling(
        normalizedRequest: NormalizedTextRequest,
        workerRequest: Melix_Worker_V1_GenerateRequest
    ) -> Bool {
        guard normalizedRequest.topP == nil else {
            return false
        }
        guard normalizedRequest.temperature != nil else {
            return false
        }
        return abs(Double(workerRequest.sampling.temperature)) < 1e-6
    }

    private func truthyModelMetadata(_ value: String?) -> Bool {
        switch value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "1", "true", "yes", "on":
            return true
        default:
            return false
        }
    }

    private func falseyModelMetadata(_ value: String?) -> Bool {
        switch value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "0", "false", "no", "off":
            return true
        default:
            return false
        }
    }

    private func normalizedRequestContainsNonTextMedia(_ request: NormalizedTextRequest) -> Bool {
        request.messages.contains { message in
            message.parts.contains { part in
                switch part.part {
                case .text:
                    return false
                case nil:
                    return false
                default:
                    return true
                }
            }
        }
    }

    private func shouldRefreshRegistryBeforeTextRequest(modelID: String) async -> Bool {
        guard let model = await modelCatalog.model(id: modelID) else {
            return true
        }
        return ModelRuntimeAvailability.isRuntimeCacheMissing(model)
    }

    private func resolveServedModelID(
        requestedModelID: String,
        endpoint: HTTPGatewayEndpointFamily
    ) async throws -> ResolvedServedModel {
        let startedAt = Date()
        let roster: (defaultModelID: String, servedModelIDs: [String], modelIdleTimeoutSeconds: UInt32, explicit: Bool)
        if let configured = await gatewayConfigStore.activeModelRosterIfConfigured(runtimeBinding: gatewayRuntimeBinding) {
            roster = (
                defaultModelID: configured.defaultModelID,
                servedModelIDs: configured.servedModelIDs,
                modelIdleTimeoutSeconds: configured.modelIdleTimeoutSeconds,
                explicit: true
            )
        } else {
            let catalogModels = await modelCatalog.listModels()
            roster = await gatewayConfigStore.activeModelRoster(
                runtimeBinding: gatewayRuntimeBinding,
                fallbackDefaultModelID: defaultServedModelID(from: catalogModels),
                fallbackServedModelIDs: defaultServedModelIDs(from: catalogModels, endpoint: endpoint)
            )
        }
        let trimmedRequested = requestedModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedModelID = trimmedRequested.isEmpty ? roster.defaultModelID : trimmedRequested
        let servedModelIDs = Set(roster.servedModelIDs)
        await metricsStore.set(
            Double(roster.servedModelIDs.count),
            forKey: "gateway.server_served_model_count"
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "gateway.model_route_resolution_ms"
        )
        guard !roster.explicit || servedModelIDs.contains(resolvedModelID) else {
            await metricsStore.increment("gateway.model_not_served_count")
            throw HTTPRequestHandlingError.modelNotServed(resolvedModelID)
        }
        return ResolvedServedModel(
            modelID: resolvedModelID,
            idleSweepRequest: OpenAIModelIdleSweepRequest(
                servedModelIDs: roster.servedModelIDs,
                idleTimeoutSeconds: roster.modelIdleTimeoutSeconds
            )
        )
    }

    private func scheduleIdleSweepIfNeeded(_ request: OpenAIModelIdleSweepRequest?) async {
        guard let request else {
            return
        }
        await idleSweepScheduler.schedule(
            servedModelIDs: request.servedModelIDs,
            idleTimeoutSeconds: request.idleTimeoutSeconds
        )
    }

    private func promptBudgetAdmissionFailureResponse(
        normalized: NormalizedTextRequest,
        model: Melix_Controlplane_V1_ModelSummary?,
        modelSamplingPolicy: ModelSamplingPolicy?,
        gatewayServingDefaults: GatewayServingDefaultsPolicy?
    ) -> HTTPResponse? {
        let contextWindowTokens = model?.maxContext ?? 0
        guard contextWindowTokens > 0 else {
            return nil
        }
        let outputCapTokens = promptBudgetOutputCapTokens(
            normalized: normalized,
            modelSamplingPolicy: modelSamplingPolicy,
            gatewayServingDefaults: gatewayServingDefaults,
            contextWindowTokens: contextWindowTokens
        )
        let maxPromptTokens = contextWindowTokens > outputCapTokens
            ? contextWindowTokens - outputCapTokens
            : 0
        let promptTokensEstimated = estimatedPromptTokens(for: normalized.messages)
        guard promptTokensEstimated > maxPromptTokens else {
            return nil
        }
        let metadata: [String: Any] = [
            "max_prompt_tokens_requested": Int(maxPromptTokens),
            "max_prompt_tokens_effective": Int(maxPromptTokens),
            "prompt_tokens_estimated": Int(promptTokensEstimated),
            "context_window_tokens": Int(contextWindowTokens),
            "output_cap_tokens": Int(outputCapTokens),
            "admission_phase": "prompt_budget",
            "prefill_started": false,
        ]
        return jsonResponse(
            statusCode: 400,
            payload: [
                "error": [
                    "code": "prompt_budget_exceeded",
                    "status": "invalid_request_error",
                    "message": "Prompt token estimate exceeds the local prompt budget for this request.",
                    "prompt_token_metadata": metadata,
                ],
            ]
        )
    }

    private func promptBudgetOutputCapTokens(
        normalized: NormalizedTextRequest,
        modelSamplingPolicy: ModelSamplingPolicy?,
        gatewayServingDefaults: GatewayServingDefaultsPolicy?,
        contextWindowTokens: UInt32
    ) -> UInt32 {
        if let maxTokens = normalized.maxTokens,
           let maxCompletionTokens = normalized.maxCompletionTokens {
            return maxTokens == maxCompletionTokens ? maxTokens : max(maxTokens, maxCompletionTokens)
        }
        if let maxCompletionTokens = normalized.maxCompletionTokens {
            return maxCompletionTokens
        }
        if let maxTokens = normalized.maxTokens {
            return maxTokens
        }
        let fallbackOutputCapTokens = modelSamplingPolicy?.maxTokens
            ?? gatewayServingDefaults?.maxTokens
            ?? GatewayServingDefaultsStore.defaultMaxTokens
        return fallbackOutputCapTokens >= contextWindowTokens ? 0 : fallbackOutputCapTokens
    }

    private func estimatedPromptTokens(
        for messages: [NormalizedTextMessage]
    ) -> UInt32 {
        let total = messages.reduce(UInt32(0)) { partial, message in
            partial + estimatedPromptTokens(for: message)
        }
        if total > 0 {
            return total
        }
        return messages.isEmpty ? 0 : 1
    }

    private func estimatedPromptTokens(for message: NormalizedTextMessage) -> UInt32 {
        message.parts.reduce(tokenCount(in: message.name ?? "")) { partial, part in
            switch part.part {
            case .text(let text):
                return partial + tokenCount(in: text)
            case .imageUri, .imageBytes, .audioUri, .audioBytes:
                return partial + 256
            case .videoUri, .videoBytes:
                return partial + 1_024
            case nil:
                return partial
            }
        }
    }

    private func tokenCount(in text: String) -> UInt32 {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return 0
        }
        let whitespaceEstimate = trimmed.split(whereSeparator: \.isWhitespace).count
        let byteEstimate = max(1, (trimmed.utf8.count + 3) / 4)
        return UInt32(min(Int(UInt32.max), max(whitespaceEstimate, byteEstimate)))
    }

    private func defaultServedModelIDs(
        from models: [Melix_Controlplane_V1_ModelSummary],
        endpoint: HTTPGatewayEndpointFamily
    ) -> [String] {
        models
            .filter { endpointSupportsModel($0, endpoint: endpoint) }
            .map(\.modelID)
    }

    private func defaultServedModelID(
        from models: [Melix_Controlplane_V1_ModelSummary]
    ) -> String {
        models.first(where: { $0.kind == "text" || $0.features.contains("chat") })?.modelID
            ?? models.first?.modelID
            ?? ""
    }

    private func nonStreamChatCompletionsResponse(
        resolvedRequest: ResolvedOpenAITextRequest,
        requestStartedAt: Date
    ) async throws -> HTTPResponse {
        let translated = resolvedRequest.translated
        var workerRequest = translated.workerRequest
        workerRequest.stream = true
        workerRequest.returnUsage = true
        workerRequest.execution.ext["melix.stream.include_usage"] = "true"
        workerRequest.execution.ext["melix.http.response_mode"] = "chat_completions_non_stream"
        let streamingTranslated = TranslatedChatRequest(
            requestID: translated.requestID,
            modelID: translated.modelID,
            responseModelID: translated.responseModelID,
            workerRequest: workerRequest,
            stream: true
        )

        let execution: CoordinatedChatExecution
        do {
            execution = try await requestCoordinator.startChatCompletion(
                streamingTranslated,
                requestStartedAt: requestStartedAt
            )
        } catch let error as RequestCoordinatorError {
            return jsonResponse(statusCode: error.statusCode, payload: error.openAIErrorPayload)
        }

        do {
            let modelID = translated.modelID
            await modelCatalog.beginRequest(modelID: modelID)
            await scheduleIdleSweepIfNeeded(resolvedRequest.idleSweepRequest)
            defer {
                // `defer` cannot await; finish asynchronously so non-stream
                // aggregation always releases request activity on this model.
                Task { [modelCatalog, modelID] in
                    await modelCatalog.finishRequest(modelID: modelID)
                }
            }
            let aggregate = try await aggregateChatCompletion(
                stream: execution.stream
            )
            if let workerError = aggregate.error {
                return workerErrorResponse(workerError)
            }

            await metricsStore.increment("http.chat_completions_non_stream_request_count")
            await metricsStore.set(
                max(Date().timeIntervalSince(requestStartedAt) * 1000, 0.001),
                forKey: "http.chat_completions_non_stream_latency_ms"
            )
            if let usage = aggregate.usage {
                await metricsStore.increment(
                    "http.chat_completions_non_stream_completion_tokens",
                    by: Double(usage.completionTokens)
                )
            }

            let payload = chatCompletionJSONPayload(
                execution: execution,
                aggregate: aggregate,
                requestStartedAt: requestStartedAt,
                responseModelID: resolvedRequest.responseModelID
            )
            return jsonResponse(statusCode: 200, payload: payload)
        } catch {
            Self.logger.error(
                "Non-stream chat completion aggregation failed requestID=\(execution.requestID, privacy: .public): \(String(describing: error), privacy: .public)"
            )
            return workerUnavailableResponse()
        }
    }

    private struct NonStreamChatCompletionAggregate {
        struct Usage {
            let promptTokens: UInt32
            let completionTokens: UInt32
        }

        var assistantText = ""
        var finishReason = "stop"
        var usage: Usage?
        var error: Melix_Worker_V1_ErrorStatus?
    }

    private func aggregateChatCompletion(
        stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
    ) async throws -> NonStreamChatCompletionAggregate {
        var aggregate = NonStreamChatCompletionAggregate()
        var tokenText = ""

        for try await event in stream {
            switch event.payload {
            case .tokenDelta(let delta):
                tokenText += delta.text
            case .usageDelta(let usage):
                // Worker usage events report final cumulative counts, so the
                // latest event is authoritative if a runtime emits more than one.
                aggregate.usage = NonStreamChatCompletionAggregate.Usage(
                    promptTokens: usage.promptTokens,
                    completionTokens: usage.completionTokens
                )
            case .completed(let completed):
                aggregate.finishReason = completed.finishReason.isEmpty ? "stop" : completed.finishReason
                aggregate.assistantText = completed.assistantText.isEmpty ? tokenText : completed.assistantText
            case .error(let error):
                aggregate.error = error.error
                return aggregate
            default:
                continue
            }
        }

        if aggregate.assistantText.isEmpty {
            aggregate.assistantText = tokenText
        }
        return aggregate
    }

    private func chatCompletionJSONPayload(
        execution: CoordinatedChatExecution,
        aggregate: NonStreamChatCompletionAggregate,
        requestStartedAt: Date,
        responseModelID: String
    ) -> [String: Any] {
        var payload: [String: Any] = [
            "id": execution.requestID,
            "object": "chat.completion",
            "created": Int(requestStartedAt.timeIntervalSince1970),
            "model": responseModelID,
            "choices": [
                [
                    "index": 0,
                    "message": [
                        "role": "assistant",
                        "content": aggregate.assistantText,
                    ],
                    "finish_reason": aggregate.finishReason,
                ],
            ],
        ]

        if let usage = aggregate.usage {
            payload["usage"] = [
                "prompt_tokens": Int(usage.promptTokens),
                "completion_tokens": Int(usage.completionTokens),
                "total_tokens": Int(usage.promptTokens) + Int(usage.completionTokens),
            ]
        }

        return payload
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
        if translated.workerRequest.execution.ext["melix.tool_config.source"] == "openai_chat_tools" {
            await metricsStore.increment("http.openai_chat_tools_request_count")
            if let rawToolCount = translated.workerRequest.execution.ext["melix.tool_config.tool_count"],
               let toolCount = Double(rawToolCount) {
                await metricsStore.set(toolCount, forKey: "http.openai_chat_tools_configured_count")
            }
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
        if let rawStripCount = translated.workerRequest.execution.ext["melix.reasoning.history_strip_count"],
           let stripCount = Double(rawStripCount),
           stripCount > 0 {
            await metricsStore.increment("http.reasoning_history_strip_count", by: stripCount)
        }
        if let rawToolCallStripCount = translated.workerRequest.execution.ext["melix.tool_call_history_strip_count"],
           let toolCallStripCount = Double(rawToolCallStripCount),
           toolCallStripCount > 0 {
            await metricsStore.increment("http.tool_call_history_strip_count", by: toolCallStripCount)
        }
    }

    private func streamResponse(
        translated: TranslatedChatRequest,
        shape: SSEStreamWriter.StreamShape,
        requestStartedAt: Date,
        idleSweepRequest: OpenAIModelIdleSweepRequest? = nil
    ) async throws -> HTTPResponse {
        let execution: CoordinatedChatExecution

        do {
            execution = try await requestCoordinator.startChatCompletion(
                translated,
                requestStartedAt: requestStartedAt
            )
        } catch let error as RequestCoordinatorError {
            return jsonResponse(statusCode: error.statusCode, payload: error.openAIErrorPayload)
        }

        await modelCatalog.beginRequest(modelID: translated.modelID)
        await scheduleIdleSweepIfNeeded(idleSweepRequest)
        let stream = sseWriter.encode(
            stream: execution.stream,
            requestID: execution.requestID,
            modelID: translated.responseModelID ?? execution.modelID,
            shape: shape,
            toolParser: ToolParserSelection(executionExt: translated.workerRequest.execution.ext),
            options: SSEStreamWriter.StreamOptions(
                includeUsage: translated.workerRequest.execution.ext["melix.stream.include_usage"] == "true"
            ),
            onComplete: { [modelCatalog] in
                await modelCatalog.finishRequest(modelID: translated.modelID)
            }
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

    private func jsonData(_ payload: [String: Any]) -> Data {
        let sanitizedPayload = Self.sanitizeJSONValue(payload)
        recordSanitizedOutputMetrics(sanitizedPayload.metrics)
        return (try? JSONSerialization.data(withJSONObject: sanitizedPayload.value, options: [.sortedKeys]))
            ?? Data("{}".utf8)
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
        case .modelNotServed(let modelID):
            return jsonResponse(
                statusCode: 404,
                payload: [
                    "error": [
                        "code": "model_not_served_by_server",
                        "message": "Model \(modelID) is not served by the active Melix server session.",
                    ],
                ]
            )
        case .modelRuntimeMissing:
            return jsonResponse(
                statusCode: 409,
                payload: [
                    "error": [
                        "code": ModelRuntimeAvailability.missingRuntimeCacheCode,
                        "message": ModelRuntimeAvailability.missingRuntimeCacheMessage,
                    ],
                ]
            )
        case .workerUnavailable:
            return workerUnavailableResponse()
        case .workerRejected(let error):
            return workerErrorResponse(error)
        case .gatewayResponse(let response):
            return response
        }
    }

    private func mediaAdmissionFailureResponse(
        _ failure: MediaAdmissionFailure
    ) -> HTTPResponse {
        jsonResponse(statusCode: failure.statusCode, payload: failure.payload)
    }

    private func mediaAdmissionFailureResponse(
        _ translated: TranslatedChatRequest
    ) -> HTTPResponse? {
        guard
            translated.workerRequest.execution.ext["melix.media_admission.status"] == "refused",
            let code = translated.workerRequest.execution.ext["melix.media_admission.error_code"]
        else {
            return nil
        }

        let unsupportedReason = translated.workerRequest.execution.ext[
            "melix.media_admission.unsupported_reason"
        ] ?? "unsupported_media"
        let routeKind = translated.workerRequest.execution.ext[
            "melix.media_admission.route_kind"
        ] ?? "unknown"
        let mediaCount = normalizedMediaPartCount(from: translated.workerRequest.execution.ext)
        let failure = MediaAdmissionFailure(
            statusCode: 400,
            code: code,
            message: mediaAdmissionFailureMessage(for: code, unsupportedReason: unsupportedReason),
            unsupportedReason: unsupportedReason,
            mediaCount: mediaCount,
            routeKind: routeKind,
            mediaKind: translated.workerRequest.execution.ext[
                "melix.media_admission.media_kind"
            ],
            toolsDisabledReason: translated.workerRequest.execution.ext[
                "melix.media_admission.tools_disabled_reason"
            ],
            speculativeDisabledReason: translated.workerRequest.execution.ext[
                "melix.media_admission.speculative_disabled_reason"
            ]
        )
        return jsonResponse(statusCode: failure.statusCode, payload: failure.payload)
    }

    private func mediaNormalizationErrorResponse(
        _ error: MultimodalRequestNormalizationError
    ) -> HTTPResponse {
        let metadata = mediaNormalizationErrorMetadata(error)
        var payload: [String: Any] = [
            "code": "unsupported_media_payload",
            "message": error.operatorMessage,
            "unsupported_reason": metadata.unsupportedReason,
        ]
        if let mediaKind = metadata.mediaKind {
            payload["media_kind"] = mediaKind
        }
        if let field = metadata.field {
            payload["field"] = field
        }
        if let rejectedValue = metadata.rejectedValue {
            payload["rejected_value"] = rejectedValue
        }
        return jsonResponse(statusCode: 400, payload: ["error": payload])
    }

    private func mediaNormalizationErrorMetadata(
        _ error: MultimodalRequestNormalizationError
    ) -> (
        unsupportedReason: String,
        mediaKind: String?,
        field: String?,
        rejectedValue: String?
    ) {
        switch error {
        case let .missingValue(field):
            return ("missing_media_value", mediaKind(from: field), field, nil)
        case let .invalidBase64(kind):
            return ("invalid_base64", kind, nil, nil)
        case let .unsupportedPartType(kind):
            return ("unsupported_part_type", nil, "type", kind)
        case let .unsupportedURIScheme(kind, scheme):
            return ("unsupported_uri_scheme", kind, nil, scheme)
        case let .unsupportedMediaFormat(kind, format):
            return ("unsupported_media_format", kind, nil, format)
        case let .invalidPreprocessingBound(field, reason):
            return ("invalid_preprocessing_bound", mediaKind(from: field), field, reason)
        case .externalMediaURLBlocked:
            return ("external_media_url_blocked", nil, nil, nil)
        }
    }

    private func mediaKind(from field: String) -> String? {
        let normalizedField = field.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedField.contains("image") {
            return "image"
        }
        if normalizedField.contains("audio") {
            return "audio"
        }
        if normalizedField.contains("video") {
            return "video"
        }
        return nil
    }

    private func mediaAdmissionFailureMessage(for code: String, unsupportedReason: String) -> String {
        switch unsupportedReason {
        case "unsupported_media_modality":
            return "The selected model does not advertise support for this media kind."
        case "unknown_media_modalities":
            return "The selected model does not advertise media modality support."
        default:
            break
        }
        switch code {
        case "unsupported_media_for_model":
            return "Media-bearing text requests require a multimodal runtime route."
        case "unsupported_media_for_tools":
            return "OpenAI tools are disabled for media-bearing requests."
        case "unsupported_media_for_speculative_decode":
            return "Speculative decode is disabled for media-bearing requests."
        default:
            return "The selected model cannot serve this media-bearing request."
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

    private func invalidGenerationBoundsResponse(_ failure: GenerationBoundsValidationFailure) -> HTTPResponse {
        jsonResponse(
            statusCode: 400,
            payload: [
                "error": [
                    "code": "invalid_generation_bounds",
                    "message": failure.message,
                    "bounds_rejection_reason": failure.reason,
                ],
            ]
        )
    }

    private func generationBoundsValidationFailure(in body: Data) -> GenerationBoundsValidationFailure? {
        guard
            let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any]
        else {
            return rawGenerationBoundsValidationFailure(in: body)
        }
        let maxTokens = parsedGenerationBound(named: "max_tokens", in: object)
        if let failure = maxTokens.failure {
            return failure
        }
        let maxCompletionTokens = parsedGenerationBound(named: "max_completion_tokens", in: object)
        if let failure = maxCompletionTokens.failure {
            return failure
        }
        if let maxTokens = maxTokens.value,
           let maxCompletionTokens = maxCompletionTokens.value,
           maxTokens != maxCompletionTokens {
            return GenerationBoundsValidationFailure(
                reason: "output_cap_conflict",
                message: "max_tokens and max_completion_tokens must match when both are provided."
            )
        }
        return nil
    }

    private func rawGenerationBoundsValidationFailure(in body: Data) -> GenerationBoundsValidationFailure? {
        guard let rawJSON = String(data: body, encoding: .utf8) else {
            return nil
        }
        let maxTokens = parsedRawGenerationBound(named: "max_tokens", in: rawJSON)
        if let failure = maxTokens.failure {
            return failure
        }
        let maxCompletionTokens = parsedRawGenerationBound(named: "max_completion_tokens", in: rawJSON)
        if let failure = maxCompletionTokens.failure {
            return failure
        }
        if let maxTokens = maxTokens.value,
           let maxCompletionTokens = maxCompletionTokens.value,
           maxTokens != maxCompletionTokens {
            return GenerationBoundsValidationFailure(
                reason: "output_cap_conflict",
                message: "max_tokens and max_completion_tokens must match when both are provided."
            )
        }
        return nil
    }

    private func parsedRawGenerationBound(
        named fieldName: String,
        in rawJSON: String
    ) -> (value: UInt32?, failure: GenerationBoundsValidationFailure?) {
        guard let token = rawJSONValueToken(named: fieldName, in: rawJSON) else {
            return (nil, nil)
        }
        guard let doubleValue = Double(token) else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(fieldName)_malformed",
                message: "\(fieldName) must be a finite positive integer."
            ))
        }
        guard doubleValue.isFinite else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(fieldName)_non_finite",
                message: "\(fieldName) must be finite."
            ))
        }
        guard doubleValue > 0 else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(fieldName)_non_positive",
                message: "\(fieldName) must be greater than zero."
            ))
        }
        guard doubleValue.rounded(.towardZero) == doubleValue,
              doubleValue <= Double(UInt32.max)
        else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(fieldName)_malformed",
                message: "\(fieldName) must be a positive integer no greater than \(UInt32.max)."
            ))
        }
        return (UInt32(doubleValue), nil)
    }

    private func rawJSONValueToken(named fieldName: String, in rawJSON: String) -> String? {
        var cursor = rawJSON.startIndex
        var objectDepth = 0
        var arrayDepth = 0

        while cursor < rawJSON.endIndex {
            let character = rawJSON[cursor]
            switch character {
            case "{":
                objectDepth += 1
                cursor = rawJSON.index(after: cursor)
            case "}":
                objectDepth = max(0, objectDepth - 1)
                cursor = rawJSON.index(after: cursor)
            case "[":
                arrayDepth += 1
                cursor = rawJSON.index(after: cursor)
            case "]":
                arrayDepth = max(0, arrayDepth - 1)
                cursor = rawJSON.index(after: cursor)
            case "\"":
                let keyStart = rawJSON.index(after: cursor)
                guard let stringEnd = endOfRawJSONString(in: rawJSON, startingAt: keyStart) else {
                    return nil
                }
                let afterString = rawJSON.index(after: stringEnd)
                if objectDepth == 1, arrayDepth == 0 {
                    var lookahead = afterString
                    while lookahead < rawJSON.endIndex, rawJSON[lookahead].isWhitespace {
                        lookahead = rawJSON.index(after: lookahead)
                    }
                    if lookahead < rawJSON.endIndex, rawJSON[lookahead] == ":" {
                        let key = String(rawJSON[keyStart..<stringEnd])
                        if key == fieldName {
                            return rawJSONScalarToken(afterColon: lookahead, in: rawJSON)
                        }
                    }
                }
                cursor = afterString
            default:
                cursor = rawJSON.index(after: cursor)
            }
        }
        return nil
    }

    private func endOfRawJSONString(in rawJSON: String, startingAt start: String.Index) -> String.Index? {
        var cursor = start
        var escaping = false
        while cursor < rawJSON.endIndex {
            let character = rawJSON[cursor]
            if escaping {
                escaping = false
            } else if character == "\\" {
                escaping = true
            } else if character == "\"" {
                return cursor
            }
            cursor = rawJSON.index(after: cursor)
        }
        return nil
    }

    private func rawJSONScalarToken(afterColon colon: String.Index, in rawJSON: String) -> String? {
        var cursor = rawJSON.index(after: colon)
        while cursor < rawJSON.endIndex, rawJSON[cursor].isWhitespace {
            cursor = rawJSON.index(after: cursor)
        }
        guard cursor < rawJSON.endIndex else {
            return nil
        }
        if rawJSON[cursor] == "\"" || rawJSON[cursor] == "{" || rawJSON[cursor] == "[" {
            return ""
        }
        let tokenStart = cursor
        while cursor < rawJSON.endIndex {
            let character = rawJSON[cursor]
            if character == "," || character == "}" || character == "]" || character.isWhitespace {
                break
            }
            cursor = rawJSON.index(after: cursor)
        }
        return tokenStart < cursor ? String(rawJSON[tokenStart..<cursor]) : nil
    }

    private func parsedGenerationBound(
        named fieldName: String,
        in object: [String: Any]
    ) -> (value: UInt32?, failure: GenerationBoundsValidationFailure?) {
        guard let rawValue = object[fieldName],
              !(rawValue is NSNull)
        else {
            return (nil, nil)
        }
        let reasonPrefix = fieldName
        guard let number = rawValue as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID()
        else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(reasonPrefix)_malformed",
                message: "\(fieldName) must be a finite positive integer."
            ))
        }
        let doubleValue = number.doubleValue
        guard doubleValue.isFinite else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(reasonPrefix)_non_finite",
                message: "\(fieldName) must be finite."
            ))
        }
        guard doubleValue > 0 else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(reasonPrefix)_non_positive",
                message: "\(fieldName) must be greater than zero."
            ))
        }
        guard doubleValue.rounded(.towardZero) == doubleValue,
              doubleValue <= Double(UInt32.max)
        else {
            return (nil, GenerationBoundsValidationFailure(
                reason: "\(reasonPrefix)_malformed",
                message: "\(fieldName) must be a positive integer no greater than \(UInt32.max)."
            ))
        }
        return (UInt32(doubleValue), nil)
    }

    private enum ExternalMediaAdmissionOutcome {
        case accepted(ExternalMediaURLAdmissionReceipt)
        case rejected(HTTPResponse)
    }

    private func admittedExternalMediaURI(
        _ rawURL: String,
        mediaKind: String
    ) async -> ExternalMediaAdmissionOutcome {
        do {
            let receipt = try ExternalMediaURLAdmission.validate(rawURL, mediaKind: mediaKind)
            await recordExternalMediaURLAdmission(receipt)
            return .accepted(receipt)
        } catch let error as ExternalMediaURLAdmissionError {
            await recordExternalMediaURLRefusal(error)
            return .rejected(invalidArgumentResponse(message: error.operatorMessage))
        } catch {
            let admissionError = ExternalMediaURLAdmissionError.malformedURL(mediaKind)
            await recordExternalMediaURLRefusal(admissionError)
            return .rejected(invalidArgumentResponse(message: admissionError.operatorMessage))
        }
    }

    private func recordExternalMediaURLAdmission(_ receipt: ExternalMediaURLAdmissionReceipt) async {
        await metricsStore.increment("external_media.url_admission_count")
        if receipt.sourceKind == "remote" {
            await metricsStore.increment("external_media.remote_url_admission_count")
        } else {
            await metricsStore.increment("external_media.local_url_admission_count")
        }
    }

    private func recordExternalMediaURLRefusal(_ error: ExternalMediaURLAdmissionError) async {
        await metricsStore.increment("external_media.url_refusal_count")
        await metricsStore.increment("external_media.refusal.\(error.refusalReason)")
    }

    private func applyExternalMediaURLReceipt(
        _ receipt: ExternalMediaURLAdmissionReceipt,
        to request: inout Melix_Worker_V1_ImageEditRequest,
        prefix: String
    ) {
        request.ext["\(prefix).policy"] = receipt.policy
        request.ext["\(prefix).source_kind"] = receipt.sourceKind
        request.ext["\(prefix).scheme"] = receipt.scheme
        request.ext["\(prefix).reason"] = receipt.reason
        if !receipt.host.isEmpty {
            request.ext["\(prefix).host"] = receipt.host
        }
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
        case "audio_processor_validation_failed":
            statusCode = 409
        case "resource_exhausted":
            statusCode = 503
        case "deadline_exceeded":
            statusCode = 504
        case "unavailable", "worker_unavailable":
            statusCode = 503
        default:
            statusCode = 500
        }

        var payloadError: [String: Any] = ["code": error.code, "message": error.message]
        if !error.details.isEmpty {
            payloadError["details"] = Dictionary(uniqueKeysWithValues: error.details.map { ($0.key, $0.value) })
        }
        return jsonResponse(
            statusCode: statusCode,
            payload: ["error": payloadError]
        )
    }

    private func endpointCompatibilityFailureResponse(
        modelID: String,
        endpoint: HTTPGatewayEndpointFamily
    ) async -> HTTPResponse? {
        guard let model = await modelCatalog.model(id: modelID) else {
            return nil
        }
        if endpointSupportsModel(model, endpoint: endpoint) {
            await metricsStore.set(1, forKey: "endpoint_type_validation_result")
            return nil
        }

        await metricsStore.set(0, forKey: "endpoint_type_validation_result")
        await metricsStore.increment("endpoint_type_validation_rejection_count")

        let modelEndpoint = endpointFamilyHint(for: model)
        let correctEndpoint = modelEndpoint?.suggestedEndpoint ?? "/v1/models"
        let routeKind = modelRouteKind(for: model)?.metadataIdentifier ?? ""
        let supportedTasks = normalizedIdentifierList(
            model.supportedTasks,
            fallback: model.settings.ext["melix.capability.supported_tasks"]
        )
        let message = if let modelEndpoint {
            "Model \(modelID) is registered for \(modelEndpoint.displayName) and cannot serve \(endpoint.displayName) requests at \(endpoint.path). Use \(correctEndpoint) for this model."
        } else {
            "Model \(modelID) does not advertise support for \(endpoint.displayName) requests at \(endpoint.path). Inspect /v1/models for supported tasks before retrying."
        }

        return jsonResponse(
            statusCode: 400,
            payload: [
                "error": [
                    "code": "wrong_endpoint_for_model",
                    "message": message,
                    "model_id": modelID,
                    "requested_endpoint": endpoint.path,
                    "requested_endpoint_family": endpoint.rawValue,
                    "model_endpoint_family": modelEndpoint?.rawValue ?? "unknown",
                    "correct_endpoint": correctEndpoint,
                    "route_kind": routeKind,
                    "supported_tasks": supportedTasks,
                ],
            ]
        )
    }

    private func endpointSupportsModel(
        _ model: Melix_Controlplane_V1_ModelSummary,
        endpoint: HTTPGatewayEndpointFamily
    ) -> Bool {
        let kind = normalizedIdentifier(model.kind)
        let capability = model.capabilityClass
        let capabilityIdentifier = normalizedIdentifier(model.settings.ext["melix.capability.class"])
        let routeKind = modelRouteKind(for: model)
        let tasks = Set(normalizedIdentifierList(
            model.supportedTasks,
            fallback: model.settings.ext["melix.capability.supported_tasks"]
        ))

        switch endpoint {
        case .textGeneration:
            return tasks.contains("generate")
                || tasks.contains("ocr")
                || tasks.contains("vlm")
                || kind == "text"
                || kind == "ocr"
                || kind == "vlm"
                || capability == .modelCapabilityText
                || capability == .modelCapabilityOcr
                || capability == .modelCapabilityVlm
                || capabilityIdentifier == "text"
                || capabilityIdentifier == "ocr"
                || capabilityIdentifier == "vlm"
                || routeKind == .swiftText
                || routeKind == .pythonCompatibility
                || routeKind == .pythonOCR
                || routeKind == .pythonVLM
        case .embedding:
            return tasks.contains("embed")
                || kind == "embedding"
                || capability == .modelCapabilityEmbedding
                || capabilityIdentifier == "embedding"
                || routeKind == .pythonEmbedding
        case .rerank:
            return tasks.contains("rerank")
                || kind == "rerank"
                || capability == .modelCapabilityRerank
                || capabilityIdentifier == "rerank"
                || routeKind == .pythonRerank
        case .transcription:
            return tasks.contains("transcribe")
                || kind == "transcription"
                || capability == .modelCapabilityTranscription
                || capabilityIdentifier == "transcription"
                || routeKind == .pythonTranscription
        case .speech:
            return tasks.contains("speak")
                || kind == "speech"
                || capability == .modelCapabilitySpeech
                || capabilityIdentifier == "speech"
                || routeKind == .pythonSpeech
        case .imageGeneration:
            if explicitBool(model.settings.ext["melix.image.supports_generation"]) == false {
                return false
            }
            return tasks.contains("image_generate")
                || kind == "image"
                || kind == "image_generation"
                || capability == .modelCapabilityImageGeneration
                || capabilityIdentifier == "image_generation"
                || routeKind == .pythonImage
        case .imageEdit:
            if explicitBool(model.settings.ext["melix.image.supports_edit"]) == false {
                return false
            }
            return tasks.contains("image_edit")
                || kind == "image"
                || kind == "image_generation"
                || capability == .modelCapabilityImageGeneration
                || capabilityIdentifier == "image_generation"
                || routeKind == .pythonImage
        }
    }

    private func endpointFamilyHint(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> HTTPGatewayEndpointFamily? {
        if endpointSupportsModel(model, endpoint: .embedding) {
            return .embedding
        }
        if endpointSupportsModel(model, endpoint: .rerank) {
            return .rerank
        }
        if endpointSupportsModel(model, endpoint: .transcription) {
            return .transcription
        }
        if endpointSupportsModel(model, endpoint: .speech) {
            return .speech
        }
        if endpointSupportsModel(model, endpoint: .imageGeneration) {
            return .imageGeneration
        }
        if endpointSupportsModel(model, endpoint: .imageEdit) {
            return .imageEdit
        }
        if endpointSupportsModel(model, endpoint: .textGeneration) {
            return .textGeneration
        }
        return nil
    }

    private func modelRouteKind(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> WorkerRouteKind? {
        if let route = WorkerRouteKind(metadataIdentifier: model.settings.ext["melix.capability.route_kind"]) {
            return route
        }
        if let route = WorkerRouteKind(routeClass: model.routeClass) {
            return route
        }
        return WorkerRouteKind(capabilityIdentifier: model.settings.ext["melix.capability.class"])
    }

    private func normalizedIdentifierList(
        _ values: [String],
        fallback: String?
    ) -> [String] {
        let identifiers = values.map(normalizedIdentifier).filter { !$0.isEmpty }
        guard identifiers.isEmpty, let fallback else {
            return identifiers
        }
        return fallback
            .split(separator: ",")
            .map { normalizedIdentifier(String($0)) }
            .filter { !$0.isEmpty }
    }

    private func normalizedIdentifier(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func explicitBool(_ value: String?) -> Bool? {
        switch normalizedIdentifier(value) {
        case "true", "1", "yes", "on":
            return true
        case "false", "0", "no", "off":
            return false
        default:
            return nil
        }
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
        case (.get, "/.well-known/melix.json"),
             (.get, "/api/capabilities"),
             (.get, "/api/instructions"),
             (.get, "/api/config-metadata"):
            return .standard
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
        ref.parentArtifactID = artifact.parentArtifactID
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
        job.sourceArtifactID = workerJob.sourceArtifactID
        job.sourceJobID = workerJob.sourceJobID
        job.promptDelta = workerJob.promptDelta
        job.editMode = Melix_Controlplane_V1_ImageEditMode(rawValue: workerJob.editMode.rawValue) ?? .unspecified
        return job
    }

    private func resolvedImageEditMode(
        _ mode: OpenAIImageEditsRequest.EditMode?
    ) -> Melix_Controlplane_V1_ImageEditMode {
        switch mode {
        case .variation:
            return .variation
        case .iterate:
            return .iterate
        case .edit, .none:
            return .edit
        }
    }

    private func workerImageEditMode(
        _ mode: Melix_Controlplane_V1_ImageEditMode
    ) -> Melix_Worker_V1_ImageEditMode {
        switch mode {
        case .variation:
            return .variation
        case .iterate:
            return .iterate
        case .edit, .unspecified, .UNRECOGNIZED:
            return .edit
        }
    }

    private func imageEditOperationName(
        for mode: Melix_Controlplane_V1_ImageEditMode
    ) -> String {
        switch mode {
        case .variation:
            return "image_variation"
        case .iterate:
            return "image_iterate"
        case .edit, .unspecified, .UNRECOGNIZED:
            return "image_edit"
        }
    }

    private func resolvedEditPrompt(
        prompt: String,
        promptDelta: String,
        mode: Melix_Controlplane_V1_ImageEditMode
    ) -> String {
        let trimmedPrompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        if mode == .iterate && trimmedPrompt.isEmpty {
            return promptDelta
        }
        return prompt
    }

    private func imageJobRecipe(
        prompt: String,
        size: String,
        steps: UInt32,
        guidance: Float,
        strength: Float?,
        negativePrompt: String,
        variantCount: UInt32,
        responseFormat: String,
        artifactNamespace: String,
        sourceImageURI: String,
        maskURI: String
    ) -> Melix_Controlplane_V1_ImageJobRecipeSummary {
        var recipe = Melix_Controlplane_V1_ImageJobRecipeSummary()
        recipe.prompt = prompt
        recipe.size = size
        recipe.steps = steps
        recipe.guidance = guidance
        recipe.strength = strength ?? 0
        recipe.negativePrompt = negativePrompt
        recipe.variantCount = variantCount
        recipe.responseFormat = responseFormat
        recipe.artifactNamespace = artifactNamespace
        recipe.sourceImageUri = sourceImageURI
        recipe.maskUri = maskURI
        return recipe
    }

    private func imageWorkerFailure(
        error: Error,
        timeoutSeconds: UInt32
    ) -> Melix_Controlplane_V1_ErrorStatus {
        guard let workerError = error as? WorkerClientError else {
            if isImageDeadlineExceeded(code: "", message: String(describing: error)) {
                return imageDeadlineExceededError(timeoutSeconds: timeoutSeconds)
            }
            return controlPlaneError(code: "worker_unavailable", message: "The worker cannot accept requests.")
        }
        switch workerError {
        case .unavailable:
            return controlPlaneError(code: "worker_unavailable", message: "The worker cannot accept requests.")
        case let .requestFailed(code, message):
            let normalizedCode = normalizedBridgeErrorCode(code)
            if isImageDeadlineExceeded(code: normalizedCode, message: message) {
                return imageDeadlineExceededError(timeoutSeconds: timeoutSeconds)
            }
            switch normalizedCode {
            case "cancelled":
                return controlPlaneError(code: "cancelled", message: message.isEmpty ? "Image request was cancelled." : message)
            case "":
                return controlPlaneError(code: "worker_unavailable", message: "The worker cannot accept requests.")
            default:
                return controlPlaneError(
                    code: normalizedCode,
                    message: message.isEmpty ? "Image worker request failed." : message
                )
            }
        }
    }

    private func imageDeadlineExceededError(timeoutSeconds: UInt32) -> Melix_Controlplane_V1_ErrorStatus {
        controlPlaneError(
            code: "deadline_exceeded",
            message: "Image request exceeded the \(timeoutSeconds)-second creative workflow deadline."
        )
    }

    private func isImageDeadlineExceeded(code: String, message: String) -> Bool {
        let normalizedCode = normalizedBridgeErrorCode(code)
        if normalizedCode == "deadline_exceeded" {
            return true
        }
        guard normalizedCode.isEmpty || normalizedCode == "unknown" else {
            return false
        }
        let normalizedMessage = message
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        return normalizedMessage.contains("deadline")
            || normalizedMessage.contains("timed out")
            || normalizedMessage.contains("timeout")
    }

    private func normalizedBridgeErrorCode(_ rawValue: String) -> String {
        rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "_")
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
            .pythonOCR,
            .pythonVLM,
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

    private static func resolveImageRequestTimeoutSeconds(environment: [String: String]) -> UInt32 {
        let rawValue = environment["MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard let parsed = UInt32(rawValue), parsed > 0 else {
            return 1_800
        }
        return parsed
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
        await recordPythonWorkerStreamOwnershipMetrics(from: stats, metricsStore: metricsStore)
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
            await recordPythonVLMRuntimeProbeMetrics(from: stats, metricsStore: metricsStore)
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
            if stats.lastProbeKind == "speech" && stats.lastSpeechStreamingEnabled {
                await metricsStore.set(
                    1,
                    forKey: "audio.speech_streaming_enabled"
                )
                await metricsStore.set(
                    Double(stats.lastSpeechStreamingIntervalMs),
                    forKey: "audio.speech_streaming_interval_ms"
                )
                await metricsStore.set(
                    stats.lastSpeechFirstAudioLatencyMs,
                    forKey: "audio.speech_first_audio_latency_ms"
                )
            }
            if stats.lastAudioOutputBytes > 0 {
                await metricsStore.set(Double(stats.lastAudioOutputBytes), forKey: "audio.speech_output_bytes")
            }
            if stats.lastAudioChunkCount > 0 {
                await metricsStore.set(
                    Double(stats.lastAudioChunkCount),
                    forKey: "audio.speech_stream_chunk_count"
                )
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
        await metricsStore.flushExport()
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

    private func resolvedSpeechContext(
        for request: OpenAIAudioSpeechRequest
    ) async -> ResolvedAudioSpeechContextResult {
        guard let selectedModel = await modelCatalog.model(id: request.model) else {
            return .success(
                ResolvedAudioSpeechContext(
                    requestedLocale: normalizedAudioLocale(request.locale),
                    supportedLocales: [],
                    resolvedLocale: "",
                    localeSource: "",
                    localePolicy: "",
                    modelDefaultLocale: "",
                    packagedDefaultLocale: "",
                    installProfile: "",
                    runtimePackState: "",
                    runtimePackID: "",
                    modelState: ""
                )
            )
        }

        let hydratedModel = audioAssetManager.hydrate(selectedModel)
        let supportedLocales = advertisedSpeechLocales(for: hydratedModel)
        let requestedLocale = normalizedAudioLocale(request.locale)
        let localePolicy = trimmedAudioMetadata("melix.audio.locale_policy", from: hydratedModel)
        let modelDefaultLocale = canonicalAudioLocale(
            trimmedAudioMetadata("melix.audio.default_locale", from: hydratedModel),
            supportedLocales: supportedLocales
        )
        let packagedDefaultLocale = canonicalAudioLocale(
            trimmedAudioMetadata("melix.audio.packaged_default_locale", from: hydratedModel),
            supportedLocales: supportedLocales
        )

        let resolvedLocale: String
        let localeSource: String
        if !requestedLocale.isEmpty {
            let resolvedRequestedLocale = canonicalAudioLocale(requestedLocale, supportedLocales: supportedLocales)
            guard !resolvedRequestedLocale.isEmpty else {
                let supportedText = supportedLocales.isEmpty ? "none" : supportedLocales.joined(separator: ",")
                return .failure(
                    invalidArgumentResponse(
                        message: "Model \(request.model) does not advertise locale \(requestedLocale). Supported locales: \(supportedText)."
                    )
                )
            }
            resolvedLocale = resolvedRequestedLocale
            localeSource = "request"
        } else if !modelDefaultLocale.isEmpty {
            resolvedLocale = modelDefaultLocale
            localeSource = "model_default"
        } else if !packagedDefaultLocale.isEmpty {
            resolvedLocale = packagedDefaultLocale
            localeSource = "packaged_default"
        } else {
            resolvedLocale = ""
            localeSource = ""
        }

        return .success(
            ResolvedAudioSpeechContext(
                requestedLocale: requestedLocale,
                supportedLocales: supportedLocales,
                resolvedLocale: resolvedLocale,
                localeSource: localeSource,
                localePolicy: localePolicy,
                modelDefaultLocale: modelDefaultLocale,
                packagedDefaultLocale: packagedDefaultLocale,
                installProfile: trimmedAudioMetadata("melix.audio.install_profile", from: hydratedModel),
                runtimePackState: trimmedAudioMetadata("melix.audio.runtime_pack_state", from: hydratedModel),
                runtimePackID: trimmedAudioMetadata("melix.audio.runtime_pack_id", from: hydratedModel),
                modelState: trimmedAudioMetadata("melix.audio.model_state", from: hydratedModel)
            )
        )
    }

    private func speechResponseHeaders(
        for context: ResolvedAudioSpeechContext,
        resolvedFormat: String,
        streaming: Bool = false,
        streamIntervalMs: UInt32 = 0
    ) -> [String: String] {
        var headers = ["content-type": audioContentType(for: resolvedFormat)]
        if streaming {
            headers["x-melix-audio-streaming"] = "true"
            headers["x-melix-audio-stream-interval-ms"] = String(streamIntervalMs)
        }
        if !context.requestedLocale.isEmpty {
            headers["x-melix-audio-requested-locale"] = context.requestedLocale
        }
        if !context.resolvedLocale.isEmpty {
            headers["x-melix-audio-resolved-locale"] = context.resolvedLocale
        }
        if !context.localeSource.isEmpty {
            headers["x-melix-audio-locale-source"] = context.localeSource
        }
        if !context.localePolicy.isEmpty {
            headers["x-melix-audio-locale-policy"] = context.localePolicy
        }
        if !context.modelDefaultLocale.isEmpty {
            headers["x-melix-audio-model-default-locale"] = context.modelDefaultLocale
        }
        if !context.packagedDefaultLocale.isEmpty {
            headers["x-melix-audio-packaged-default-locale"] = context.packagedDefaultLocale
        }
        if !context.supportedLocales.isEmpty {
            headers["x-melix-audio-supported-locales"] = context.supportedLocales.joined(separator: ",")
        }
        if !context.installProfile.isEmpty {
            headers["x-melix-audio-install-profile"] = context.installProfile
        }
        if !context.runtimePackState.isEmpty {
            headers["x-melix-audio-runtime-pack-state"] = context.runtimePackState
        }
        if !context.runtimePackID.isEmpty {
            headers["x-melix-audio-runtime-pack-id"] = context.runtimePackID
        }
        if !context.modelState.isEmpty {
            headers["x-melix-audio-model-state"] = context.modelState
        }
        return headers
    }

    private func advertisedSpeechLocales(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String] {
        let primaryLocales = csvAudioMetadata("melix.audio.voice_locales", from: model)
        if !primaryLocales.isEmpty {
            return primaryLocales
        }
        return csvAudioMetadata("melix.audio.languages", from: model)
    }

    private func trimmedAudioMetadata(
        _ key: String,
        from model: Melix_Controlplane_V1_ModelSummary
    ) -> String {
        model.settings.ext[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private func csvAudioMetadata(
        _ key: String,
        from model: Melix_Controlplane_V1_ModelSummary
    ) -> [String] {
        let rawValue = trimmedAudioMetadata(key, from: model)
        guard !rawValue.isEmpty else {
            return []
        }
        var locales: [String] = []
        for item in rawValue.split(separator: ",") {
            let normalized = normalizedAudioLocale(String(item))
            if normalized.isEmpty || locales.contains(normalized) {
                continue
            }
            locales.append(normalized)
        }
        return locales
    }

    private func normalizedAudioLocale(_ rawValue: String?) -> String {
        let trimmed = (rawValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return ""
        }
        return trimmed
            .replacingOccurrences(of: "_", with: "-")
            .lowercased()
    }

    private func canonicalAudioLocale(
        _ locale: String,
        supportedLocales: [String]
    ) -> String {
        let normalized = normalizedAudioLocale(locale)
        guard !normalized.isEmpty else {
            return ""
        }
        guard
            !supportedLocales.isEmpty,
            !supportedLocales.contains("und"),
            !supportedLocales.contains("auto")
        else {
            return normalized
        }
        if supportedLocales.contains(normalized) {
            return normalized
        }
        let primaryLanguage = normalized.split(separator: "-").first.map(String.init) ?? normalized
        if let matchedLocale = supportedLocales.first(where: { locale in
            let localePrimaryLanguage = locale.split(separator: "-").first.map(String.init) ?? locale
            return localePrimaryLanguage == primaryLanguage
        }) {
            return matchedLocale
        }
        return ""
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
    case modelNotServed(String)
    case modelRuntimeMissing
    case workerUnavailable
    case workerRejected(Melix_Worker_V1_ErrorStatus)
    case gatewayResponse(HTTPResponse)
}

private struct GenerationBoundsValidationFailure {
    let reason: String
    let message: String
}

private enum HTTPGatewayEndpointFamily: String {
    case textGeneration = "text_generation"
    case embedding
    case rerank
    case transcription
    case speech
    case imageGeneration = "image_generation"
    case imageEdit = "image_edit"

    var displayName: String {
        switch self {
        case .textGeneration:
            return "text generation"
        case .embedding:
            return "embedding"
        case .rerank:
            return "rerank"
        case .transcription:
            return "audio transcription"
        case .speech:
            return "audio speech"
        case .imageGeneration:
            return "image generation"
        case .imageEdit:
            return "image edit"
        }
    }

    var path: String {
        switch self {
        case .textGeneration:
            return "/v1/chat/completions"
        case .embedding:
            return "/v1/embeddings"
        case .rerank:
            return "/v1/rerank"
        case .transcription:
            return "/v1/audio/transcriptions"
        case .speech:
            return "/v1/audio/speech"
        case .imageGeneration:
            return "/v1/images/generations"
        case .imageEdit:
            return "/v1/images/edits"
        }
    }

    var suggestedEndpoint: String {
        path
    }
}

private struct HealthResponse: Codable {
    let status: String
    let service: String
}

private struct HealthDiagnosticsResponse: Codable {
    let status: String
    let routes: [String: Bool]
    let modelsReady: Int
    let modelsTotal: Int
    let models: [HealthDiagnosticsModelResponse]

    enum CodingKeys: String, CodingKey {
        case status
        case routes
        case modelsReady = "models_ready"
        case modelsTotal = "models_total"
        case models
    }
}

private struct HealthDiagnosticsModelResponse: Codable {
    let modelID: String
    let supportedModalities: [String]
    let mediaRouteReceipt: ModelPublicMediaRouteReceipt

    init(model: Melix_Controlplane_V1_ModelSummary) {
        let receipt = ModelCatalogPresentation.publicMediaRouteReceipt(for: model)
        self.modelID = model.modelID
        self.supportedModalities = receipt.effectiveSupportedModalities
        self.mediaRouteReceipt = receipt
    }

    enum CodingKeys: String, CodingKey {
        case modelID = "model_id"
        case supportedModalities = "supported_modalities"
        case mediaRouteReceipt = "media_route_receipt"
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
    let locale: String?
    let stream: Bool?
    let streamIntervalMs: UInt32?

    enum CodingKeys: String, CodingKey {
        case model
        case input
        case voice
        case format
        case instructions
        case locale
        case stream
        case streamIntervalMs = "stream_interval_ms"
    }
}

private struct ResolvedAudioSpeechContext {
    let requestedLocale: String
    let supportedLocales: [String]
    let resolvedLocale: String
    let localeSource: String
    let localePolicy: String
    let modelDefaultLocale: String
    let packagedDefaultLocale: String
    let installProfile: String
    let runtimePackState: String
    let runtimePackID: String
    let modelState: String
}

private enum ResolvedAudioSpeechContextResult {
    case success(ResolvedAudioSpeechContext)
    case failure(HTTPResponse)
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
    enum EditMode: String, Codable {
        case edit
        case variation
        case iterate
    }

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
    let sourceArtifactID: String?
    let promptDelta: String?
    let editMode: EditMode?

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
        case sourceArtifactID = "source_artifact_id"
        case promptDelta = "prompt_delta"
        case editMode = "edit_mode"
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
        if sourceArtifactID?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false {
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
    let parentArtifactID: String
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
        parentArtifactID = artifact.parentArtifactID
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
        case parentArtifactID = "parent_artifact_id"
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
    let progress: OpenAIImageJobProgressPayload
    let lane: String
    let workerID: String
    let cancelable: Bool
    let createdAtUnixMs: Int64
    let updatedAtUnixMs: Int64
    let sourceArtifactID: String
    let sourceJobID: String
    let promptDelta: String
    let editMode: String
    let requestTimeoutSeconds: UInt32
    let recipe: OpenAIImageJobRecipePayload
    let artifacts: [OpenAIImageArtifactPayload]

    init(job: Melix_Controlplane_V1_ImageJobSummary) {
        jobID = job.jobID
        requestID = job.requestID
        modelID = job.modelID
        operation = job.operation
        state = job.state.melixString
        progress = OpenAIImageJobProgressPayload(progress: job.progress)
        lane = job.lane
        workerID = job.workerID
        cancelable = job.cancelable
        createdAtUnixMs = job.createdAtUnixMs
        updatedAtUnixMs = job.updatedAtUnixMs
        sourceArtifactID = job.sourceArtifactID
        sourceJobID = job.sourceJobID
        promptDelta = job.promptDelta
        editMode = job.editMode.melixString
        requestTimeoutSeconds = job.timeoutSeconds
        recipe = OpenAIImageJobRecipePayload(recipe: job.recipe)
        artifacts = job.artifacts.map(OpenAIImageArtifactPayload.init)
    }

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case requestID = "request_id"
        case modelID = "model_id"
        case operation
        case state
        case progress
        case lane
        case workerID = "worker_id"
        case cancelable
        case createdAtUnixMs = "created_at_unix_ms"
        case updatedAtUnixMs = "updated_at_unix_ms"
        case sourceArtifactID = "source_artifact_id"
        case sourceJobID = "source_job_id"
        case promptDelta = "prompt_delta"
        case editMode = "edit_mode"
        case requestTimeoutSeconds = "request_timeout_seconds"
        case recipe
        case artifacts
    }
}

private struct OpenAIImageJobProgressPayload: Codable {
    let stage: String
    let pct: Float
    let completedSteps: UInt32
    let totalSteps: UInt32

    init(progress: Melix_Controlplane_V1_ImageJobProgress) {
        stage = progress.stage
        pct = progress.pct
        completedSteps = progress.completedSteps
        totalSteps = progress.totalSteps
    }

    enum CodingKeys: String, CodingKey {
        case stage
        case pct
        case completedSteps = "completed_steps"
        case totalSteps = "total_steps"
    }
}

private struct OpenAIImageJobRecipePayload: Codable {
    let prompt: String
    let size: String
    let steps: UInt32
    let guidance: Float
    let strength: Float
    let negativePrompt: String
    let variantCount: UInt32
    let responseFormat: String
    let artifactNamespace: String
    let sourceImageURI: String
    let maskURI: String

    init(recipe: Melix_Controlplane_V1_ImageJobRecipeSummary) {
        prompt = recipe.prompt
        size = recipe.size
        steps = recipe.steps
        guidance = recipe.guidance
        strength = recipe.strength
        negativePrompt = recipe.negativePrompt
        variantCount = recipe.variantCount
        responseFormat = recipe.responseFormat
        artifactNamespace = recipe.artifactNamespace
        sourceImageURI = recipe.sourceImageUri
        maskURI = recipe.maskUri
    }

    enum CodingKeys: String, CodingKey {
        case prompt
        case size
        case steps
        case guidance
        case strength
        case negativePrompt = "negative_prompt"
        case variantCount = "variant_count"
        case responseFormat = "response_format"
        case artifactNamespace = "artifact_namespace"
        case sourceImageURI = "source_image_uri"
        case maskURI = "mask_uri"
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

private extension Melix_Controlplane_V1_ImageEditMode {
    var melixString: String {
        switch self {
        case .variation:
            return "variation"
        case .iterate:
            return "iterate"
        case .edit:
            return "edit"
        default:
            return "unspecified"
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
        case .unsupportedAcceleration:
            return 400
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
        case .unsupportedAcceleration:
            return "unsupported_acceleration"
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
        case .unsupportedAcceleration(_, let message, _):
            return message
        }
    }

    var openAIErrorPayload: [String: Any] {
        var error: [String: Any] = [
            "code": errorCode,
            "message": errorMessage,
        ]
        if case .unsupportedAcceleration(let reason, _, let recoveryHint) = self {
            error["unsupported_reason"] = ModelCapabilityReceipts.unsupportedReasonIdentifier(reason)
            error["recovery_hint"] = recoveryHint
        }
        return ["error": error]
    }
}

private func elapsedMilliseconds(since start: DispatchTime) -> Double {
    let end = DispatchTime.now()
    let nanos = end.uptimeNanoseconds - start.uptimeNanoseconds
    return Double(nanos) / 1_000_000
}
