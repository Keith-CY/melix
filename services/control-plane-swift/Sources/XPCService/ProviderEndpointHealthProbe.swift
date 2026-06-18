import Foundation

public struct ProviderEndpointProbeRequest: Equatable, Sendable {
    public let endpointID: String
    public let providerKind: String
    public let baseURL: String
    public let apiKey: String
    public let timeoutSeconds: UInt32
    public let toolSupportMode: ProviderEndpointToolSupportMode

    public init(
        endpointID: String,
        providerKind: String,
        baseURL: String,
        apiKey: String,
        timeoutSeconds: UInt32 = 30,
        toolSupportMode: ProviderEndpointToolSupportMode = .auto
    ) {
        self.endpointID = endpointID
        self.providerKind = providerKind
        self.baseURL = baseURL
        self.apiKey = apiKey
        self.timeoutSeconds = timeoutSeconds
        self.toolSupportMode = toolSupportMode
    }
}

public enum ProviderEndpointToolSupportMode: String, Codable, Equatable, Sendable, CaseIterable {
    case auto
    case forceOn = "force_on"
    case forceOff = "force_off"
}

public struct ProviderEndpointCapabilities: Codable, Equatable, Sendable {
    public let chat: Bool
    public let streaming: Bool
    public let tools: Bool
    public let structuredOutput: Bool
    public let embeddings: Bool

    public init(
        chat: Bool = false,
        streaming: Bool = false,
        tools: Bool = false,
        structuredOutput: Bool = false,
        embeddings: Bool = false
    ) {
        self.chat = chat
        self.streaming = streaming
        self.tools = tools
        self.structuredOutput = structuredOutput
        self.embeddings = embeddings
    }

    enum CodingKeys: String, CodingKey {
        case chat
        case streaming
        case tools
        case structuredOutput = "structured_output"
        case embeddings
    }
}

public struct ProviderEndpointHealthReceipt: Codable, Equatable, Sendable, CustomStringConvertible {
    public let schemaVersion: String
    public let endpointID: String
    public let providerKind: String
    public let baseURLRedacted: String
    public let normalizedBaseKind: String
    public let modelsEndpointKind: String
    public let probeStatus: String
    public let authRedacted: Bool
    public let fallbackAttempted: Bool
    public let modelCount: Int
    public let capabilities: ProviderEndpointCapabilities
    public let toolSupportMode: ProviderEndpointToolSupportMode
    public let detectedToolSupport: Bool
    public let overrideSource: String
    public let lastProbeStatus: String
    public let latencyMS: UInt32
    public let failureReason: String

    public init(
        schemaVersion: String = "melix.provider_endpoint_health.v1",
        endpointID: String,
        providerKind: String,
        baseURLRedacted: String,
        normalizedBaseKind: String = "base_url",
        modelsEndpointKind: String = "openai_models",
        probeStatus: String = "ok",
        authRedacted: Bool = false,
        fallbackAttempted: Bool = false,
        modelCount: Int,
        capabilities: ProviderEndpointCapabilities,
        toolSupportMode: ProviderEndpointToolSupportMode = .auto,
        detectedToolSupport: Bool = false,
        overrideSource: String = "probe_detection",
        lastProbeStatus: String = "ok",
        latencyMS: UInt32,
        failureReason: String = ""
    ) {
        self.schemaVersion = schemaVersion
        self.endpointID = endpointID
        self.providerKind = providerKind
        self.baseURLRedacted = baseURLRedacted
        self.normalizedBaseKind = normalizedBaseKind
        self.modelsEndpointKind = modelsEndpointKind
        self.probeStatus = probeStatus
        self.authRedacted = authRedacted
        self.fallbackAttempted = fallbackAttempted
        self.modelCount = modelCount
        self.capabilities = capabilities
        self.toolSupportMode = toolSupportMode
        self.detectedToolSupport = detectedToolSupport
        self.overrideSource = overrideSource
        self.lastProbeStatus = lastProbeStatus
        self.latencyMS = latencyMS
        self.failureReason = failureReason
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case endpointID = "endpoint_id"
        case providerKind = "provider_kind"
        case baseURLRedacted = "base_url_redacted"
        case normalizedBaseKind = "normalized_base_kind"
        case modelsEndpointKind = "models_endpoint_kind"
        case probeStatus = "probe_status"
        case authRedacted = "auth_redacted"
        case fallbackAttempted = "fallback_attempted"
        case modelCount = "model_count"
        case capabilities
        case toolSupportMode = "tool_support_mode"
        case detectedToolSupport = "detected_tool_support"
        case overrideSource = "override_source"
        case lastProbeStatus = "last_probe_status"
        case latencyMS = "latency_ms"
        case failureReason = "failure_reason"
    }

    public var description: String {
        "ProviderEndpointHealthReceipt(schemaVersion: \(schemaVersion), endpointID: \(endpointID), providerKind: \(providerKind), baseURLRedacted: \(baseURLRedacted), normalizedBaseKind: \(normalizedBaseKind), modelsEndpointKind: \(modelsEndpointKind), probeStatus: \(probeStatus), authRedacted: \(authRedacted), fallbackAttempted: \(fallbackAttempted), modelCount: \(modelCount), capabilities: \(capabilities), toolSupportMode: \(toolSupportMode.rawValue), detectedToolSupport: \(detectedToolSupport), overrideSource: \(overrideSource), lastProbeStatus: \(lastProbeStatus), latencyMS: \(latencyMS), failureReason: \(failureReason))"
    }

    public func jsonObject(encoder: JSONEncoder) throws -> [String: Any] {
        let data = try encoder.encode(self)
        let object = try JSONSerialization.jsonObject(with: data)
        return object as? [String: Any] ?? [:]
    }
}

public struct ProviderEndpointHealthProbe: Sendable {
    private let transport: any RemoteProviderHTTPTransport
    private let latencyClock: @Sendable () -> UInt64

    public init(
        transport: any RemoteProviderHTTPTransport = URLSessionRemoteProviderHTTPTransport(),
        latencyClock: @escaping @Sendable () -> UInt64 = {
            DispatchTime.now().uptimeNanoseconds / 1_000_000
        }
    ) {
        self.transport = transport
        self.latencyClock = latencyClock
    }

    public func probe(_ request: ProviderEndpointProbeRequest) async throws -> ProviderEndpointHealthReceipt {
        let trimmedAPIKey = request.apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let urlContext = try normalizedBaseURLContext(from: request.baseURL, apiKey: trimmedAPIKey)
        let providerKind = normalizedProviderKind(request.providerKind)
        let modelListTarget = try modelListTarget(baseURL: urlContext.normalizedBase, providerKind: providerKind)
        let fallbackAttempted = fallbackAttempted(
            normalizedBaseKind: urlContext.normalizedBaseKind,
            modelsEndpointKind: modelListTarget.endpointKind
        )
        var httpRequest = URLRequest(url: modelListTarget.url)
        httpRequest.httpMethod = "GET"
        httpRequest.timeoutInterval = TimeInterval(request.timeoutSeconds == 0 ? 30 : request.timeoutSeconds)
        httpRequest.setValue("application/json", forHTTPHeaderField: "Accept")
        // Keep OpenAI/Python first for providers that key compatibility behavior off SDK user agents.
        httpRequest.setValue("OpenAI/Python 1.0.0 Melix/0.1", forHTTPHeaderField: "User-Agent")
        configureAuthenticationHeaders(on: &httpRequest, providerKind: providerKind, apiKey: trimmedAPIKey)

        let startedAtMS = latencyClock()
        let data: Data
        let response: HTTPURLResponse
        do {
            (data, response) = try await transport.data(for: httpRequest)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            return failureReceipt(
                request: request,
                providerKind: providerKind,
                urlContext: urlContext,
                modelsEndpointKind: modelListTarget.endpointKind,
                fallbackAttempted: fallbackAttempted,
                latencyMS: elapsedMilliseconds(since: startedAtMS),
                reason: "transport_failed"
            )
        }
        guard (200..<300).contains(response.statusCode) else {
            return failureReceipt(
                request: request,
                providerKind: providerKind,
                urlContext: urlContext,
                modelsEndpointKind: modelListTarget.endpointKind,
                fallbackAttempted: fallbackAttempted,
                latencyMS: elapsedMilliseconds(since: startedAtMS),
                reason: response.statusCode == 401 || response.statusCode == 403 ? "auth_failed" : "model_list_failed"
            )
        }
        let summary: ProviderEndpointModelSummary
        do {
            summary = try parseModelSummary(from: data, providerKind: providerKind)
        } catch {
            return failureReceipt(
                request: request,
                providerKind: providerKind,
                urlContext: urlContext,
                modelsEndpointKind: modelListTarget.endpointKind,
                fallbackAttempted: fallbackAttempted,
                latencyMS: elapsedMilliseconds(since: startedAtMS),
                reason: "model_list_malformed"
            )
        }
        return ProviderEndpointHealthReceipt(
            endpointID: request.endpointID,
            providerKind: providerKind,
            baseURLRedacted: urlContext.normalizedBase.absoluteString,
            normalizedBaseKind: urlContext.normalizedBaseKind,
            modelsEndpointKind: modelListTarget.endpointKind,
            probeStatus: "ok",
            authRedacted: urlContext.authRedacted,
            fallbackAttempted: fallbackAttempted,
            modelCount: summary.chatModelCount,
            capabilities: effectiveCapabilities(
                summary.capabilities,
                toolSupportMode: request.toolSupportMode
            ),
            toolSupportMode: request.toolSupportMode,
            detectedToolSupport: summary.capabilities.tools,
            overrideSource: overrideSource(for: request.toolSupportMode),
            lastProbeStatus: "ok",
            latencyMS: elapsedMilliseconds(since: startedAtMS)
        )
    }

    private func elapsedMilliseconds(since startedAtMS: UInt64) -> UInt32 {
        let endedAtMS = latencyClock()
        let elapsed = endedAtMS >= startedAtMS ? endedAtMS - startedAtMS : 0
        return UInt32(clamping: elapsed)
    }

    private func failureReceipt(
        request: ProviderEndpointProbeRequest,
        providerKind: String,
        urlContext: ProviderEndpointURLContext,
        modelsEndpointKind: String,
        fallbackAttempted: Bool,
        latencyMS: UInt32,
        reason: String
    ) -> ProviderEndpointHealthReceipt {
        ProviderEndpointHealthReceipt(
            endpointID: request.endpointID,
            providerKind: providerKind,
            baseURLRedacted: urlContext.normalizedBase.absoluteString,
            normalizedBaseKind: urlContext.normalizedBaseKind,
            modelsEndpointKind: modelsEndpointKind,
            probeStatus: reason,
            authRedacted: urlContext.authRedacted,
            fallbackAttempted: fallbackAttempted,
            modelCount: 0,
            capabilities: ProviderEndpointCapabilities(),
            toolSupportMode: request.toolSupportMode,
            detectedToolSupport: false,
            overrideSource: overrideSource(for: request.toolSupportMode),
            lastProbeStatus: reason,
            latencyMS: latencyMS,
            failureReason: reason
        )
    }

    private func effectiveCapabilities(
        _ capabilities: ProviderEndpointCapabilities,
        toolSupportMode: ProviderEndpointToolSupportMode
    ) -> ProviderEndpointCapabilities {
        let effectiveToolSupport: Bool
        switch toolSupportMode {
        case .auto:
            effectiveToolSupport = capabilities.tools
        case .forceOn:
            effectiveToolSupport = true
        case .forceOff:
            effectiveToolSupport = false
        }
        return ProviderEndpointCapabilities(
            chat: capabilities.chat,
            streaming: capabilities.streaming,
            tools: effectiveToolSupport,
            structuredOutput: capabilities.structuredOutput,
            embeddings: capabilities.embeddings
        )
    }

    private func overrideSource(for toolSupportMode: ProviderEndpointToolSupportMode) -> String {
        switch toolSupportMode {
        case .auto:
            return "probe_detection"
        case .forceOn, .forceOff:
            return "endpoint_config"
        }
    }

    private func normalizedBaseURLContext(from rawValue: String, apiKey: String) throws -> ProviderEndpointURLContext {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            throw RemoteProviderError.invalidRequest("provider endpoint base_url is empty")
        }
        guard var components = URLComponents(string: trimmed),
              let scheme = components.scheme,
              let host = components.host,
              scheme.isEmpty == false,
              host.isEmpty == false
        else {
            throw RemoteProviderError.invalidRequest("provider endpoint base_url is invalid: \(rawValue)")
        }

        let authRedacted = apiKey.isEmpty == false
            || components.user != nil
            || components.password != nil
            || components.query != nil
            || components.fragment != nil
        let normalizedBaseKind = normalizedBaseKind(for: components.path)

        components.user = nil
        components.password = nil
        components.query = nil
        components.fragment = nil
        components.path = normalizedPath(components.path)

        guard let url = components.url else {
            throw RemoteProviderError.invalidRequest("provider endpoint base_url is invalid: \(rawValue)")
        }
        return ProviderEndpointURLContext(
            normalizedBase: url,
            normalizedBaseKind: normalizedBaseKind,
            authRedacted: authRedacted
        )
    }

    private func normalizedBaseKind(for path: String) -> String {
        var normalized = path
        while normalized.hasSuffix("/") {
            normalized.removeLast()
        }
        if normalized.hasSuffix("/chat/completions") {
            return "chat_completions_endpoint"
        }
        if normalized.hasSuffix("/messages") {
            return "messages_endpoint"
        }
        if normalized.hasSuffix("/api/chat") {
            return "ollama_chat_endpoint"
        }
        if normalized.hasSuffix("/api/generate") {
            return "ollama_generate_endpoint"
        }
        if normalized.hasSuffix("/api/tags") {
            return "ollama_tags_endpoint"
        }
        if normalized.hasSuffix("/models") {
            return "models_endpoint"
        }
        if normalized == "/v1" || normalized.hasSuffix("/v1") {
            return "versioned_base"
        }
        return "base_url"
    }

    private func normalizedPath(_ path: String) -> String {
        var normalized = path
        while normalized.hasSuffix("/") {
            normalized.removeLast()
        }
        for suffix in ["/api/chat", "/api/generate", "/api/tags"] {
            if normalized.hasSuffix(suffix) {
                normalized.removeLast(suffix.count - "/api".count)
                return normalized.isEmpty ? "" : normalized
            }
        }
        // Strip one endpoint suffix only; keep this list ordered from most specific to broadest.
        for suffix in ["/chat/completions", "/messages", "/models"] {
            if normalized.hasSuffix(suffix) {
                normalized.removeLast(suffix.count)
                break
            }
        }
        return normalized.isEmpty ? "" : normalized
    }

    private func modelListTarget(baseURL: URL, providerKind: String) throws -> ProviderEndpointModelListTarget {
        switch providerKind {
        case "openai-compatible":
            return ProviderEndpointModelListTarget(
                url: baseURL.appendingPathComponent("models"),
                endpointKind: "openai_models"
            )
        case "anthropic":
            return ProviderEndpointModelListTarget(
                url: baseURL.appendingPathComponent("models"),
                endpointKind: "anthropic_models"
            )
        case "ollama-native":
            let root = droppingAPISuffix(from: baseURL)
            return ProviderEndpointModelListTarget(
                url: root.appendingPathComponent("api/tags"),
                endpointKind: "ollama_tags"
            )
        case "local-runtime":
            let root = droppingV1Suffix(from: baseURL)
            return ProviderEndpointModelListTarget(
                url: root.appendingPathComponent("v1/models"),
                endpointKind: "local_runtime_models"
            )
        default:
            throw RemoteProviderError.invalidRequest("unsupported provider endpoint probe kind: \(providerKind)")
        }
    }

    private func fallbackAttempted(normalizedBaseKind: String, modelsEndpointKind: String) -> Bool {
        if modelsEndpointKind == "ollama_tags" {
            return normalizedBaseKind != "ollama_tags_endpoint"
        }
        return normalizedBaseKind != "models_endpoint"
    }

    private func configureAuthenticationHeaders(on request: inout URLRequest, providerKind: String, apiKey: String) {
        guard apiKey.isEmpty == false else {
            return
        }
        if providerKind == "anthropic" {
            request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
            return
        }
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    }

    private func droppingAPISuffix(from url: URL) -> URL {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return url
        }
        if components.path == "/api" {
            components.path = ""
        }
        return components.url ?? url
    }

    private func droppingV1Suffix(from url: URL) -> URL {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return url
        }
        if components.path == "/v1" {
            components.path = ""
        }
        return components.url ?? url
    }

    private func parseModelSummary(from data: Data, providerKind: String) throws -> ProviderEndpointModelSummary {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw RemoteProviderError.invalidResponse("provider endpoint model list was malformed")
        }
        let models: [[String: Any]]
        switch providerKind {
        case "ollama-native":
            guard let parsedModels = object["models"] as? [[String: Any]] else {
                throw RemoteProviderError.invalidResponse("provider endpoint model list was malformed")
            }
            models = parsedModels
        default:
            guard let parsedModels = object["data"] as? [[String: Any]] else {
                throw RemoteProviderError.invalidResponse("provider endpoint model list was malformed")
            }
            models = parsedModels
        }
        return summarizeModels(models)
    }

    private func summarizeModels(_ models: [[String: Any]]) -> ProviderEndpointModelSummary {
        var chatModelCount = 0
        var hasStreaming = false
        var hasTools = false
        var hasStructuredOutput = false
        var hasEmbeddings = false

        for model in models {
            let kind = normalizedString(model["kind"] ?? model["type"] ?? model["capability_class"])
            let capabilities = normalizedStringList(model["capabilities"] ?? model["features"] ?? model["supported_parameters"])
            if kind == "embedding" || kind == "embeddings" || capabilities.contains("embedding") || capabilities.contains("embeddings") {
                hasEmbeddings = true
            }
            guard isAutomaticChatCandidate(model: model, kind: kind, capabilities: capabilities) else {
                continue
            }
            chatModelCount += 1
            hasStreaming = true
            hasTools = hasTools || capabilities.contains("tools") || capabilities.contains("tool_calls")
            hasStructuredOutput = hasStructuredOutput
                || capabilities.contains("json_schema")
                || capabilities.contains("structured_output")
                || capabilities.contains("response_format")
        }

        return ProviderEndpointModelSummary(
            chatModelCount: chatModelCount,
            capabilities: ProviderEndpointCapabilities(
                chat: chatModelCount > 0,
                streaming: chatModelCount > 0 && hasStreaming,
                tools: hasTools,
                structuredOutput: hasStructuredOutput,
                embeddings: hasEmbeddings
            )
        )
    }

    private func isAutomaticChatCandidate(
        model: [String: Any],
        kind: String,
        capabilities: Set<String>
    ) -> Bool {
        if boolValue(model["hidden"]) || boolValue(model["disabled"]) {
            return false
        }
        if let state = normalizedOptionalString(model["state"] ?? model["status"]),
           state == "disabled" || state == "hidden"
        {
            return false
        }
        if kind == "embedding" || kind == "embeddings" || kind == "rerank" || kind == "audio" || kind == "speech" {
            return false
        }
        if capabilities.contains("embedding") || capabilities.contains("embeddings") || capabilities.contains("rerank") {
            return capabilities.contains("chat") || capabilities.contains("text-generation") || capabilities.contains("text_generation")
        }
        return true
    }

    private func normalizedStringList(_ value: Any?) -> Set<String> {
        if let values = value as? [String] {
            return Set(values.map(normalizedString).filter { !$0.isEmpty })
        }
        if let values = value as? [Any] {
            return Set(values.map(normalizedString).filter { !$0.isEmpty })
        }
        let normalized = normalizedString(value)
        return normalized.isEmpty ? [] : [normalized]
    }

    private func normalizedOptionalString(_ value: Any?) -> String? {
        let normalized = normalizedString(value)
        return normalized.isEmpty ? nil : normalized
    }

    private func normalizedString(_ value: Any?) -> String {
        guard let value else {
            return ""
        }
        return String(describing: value)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

    private func normalizedProviderKind(_ providerKind: String) -> String {
        providerKind
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

    private func boolValue(_ value: Any?) -> Bool {
        if let value = value as? Bool {
            return value
        }
        let normalized = normalizedString(value)
        return normalized == "true" || normalized == "1" || normalized == "yes"
    }
}

private struct ProviderEndpointModelSummary {
    let chatModelCount: Int
    let capabilities: ProviderEndpointCapabilities
}

private struct ProviderEndpointURLContext {
    let normalizedBase: URL
    let normalizedBaseKind: String
    let authRedacted: Bool
}

private struct ProviderEndpointModelListTarget {
    let url: URL
    let endpointKind: String
}
