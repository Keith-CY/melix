import Foundation

public protocol RemoteProviderHTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionRemoteProviderHTTPTransport: RemoteProviderHTTPTransport {
    public init() {}

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw RemoteProviderError.invalidResponse("Remote provider response was not HTTP.")
        }
        return (data, httpResponse)
    }
}

public struct RemoteProviderChatRequest: Equatable, Sendable {
    public struct Message: Equatable, Sendable {
        public let role: String
        public let content: String

        public init(role: String, content: String) {
            self.role = role
            self.content = content
        }
    }

    public let serverID: String
    public let providerKind: String
    public let baseURL: String
    public let apiKey: String
    public let modelID: String
    public let messages: [Message]
    public let stream: Bool
    public let timeoutSeconds: UInt32

    public init(
        serverID: String,
        providerKind: String,
        baseURL: String,
        apiKey: String,
        modelID: String,
        messages: [Message],
        stream: Bool,
        timeoutSeconds: UInt32 = 60
    ) {
        self.serverID = serverID
        self.providerKind = providerKind
        self.baseURL = baseURL
        self.apiKey = apiKey
        self.modelID = modelID
        self.messages = messages
        self.stream = stream
        self.timeoutSeconds = timeoutSeconds
    }

    func withStream(_ stream: Bool) -> RemoteProviderChatRequest {
        RemoteProviderChatRequest(
            serverID: serverID,
            providerKind: providerKind,
            baseURL: baseURL,
            apiKey: apiKey,
            modelID: modelID,
            messages: messages,
            stream: stream,
            timeoutSeconds: timeoutSeconds
        )
    }
}

public struct RemoteProviderChatCompletion: Equatable, Sendable {
    public let assistantText: String
    public let finishReason: String
    public let promptTokens: UInt32
    public let completionTokens: UInt32

    public init(
        assistantText: String,
        finishReason: String,
        promptTokens: UInt32,
        completionTokens: UInt32
    ) {
        self.assistantText = assistantText
        self.finishReason = finishReason
        self.promptTokens = promptTokens
        self.completionTokens = completionTokens
    }
}

public enum RemoteProviderChatStreamEvent: Equatable, Sendable {
    case tokenDelta(String)
    case usage(promptTokens: UInt32, completionTokens: UInt32)
    case completed(finishReason: String, assistantText: String)
}

public protocol RemoteProviderChatClient: Sendable {
    func complete(_ request: RemoteProviderChatRequest) async throws -> RemoteProviderChatCompletion
    func stream(_ request: RemoteProviderChatRequest) async throws -> AsyncThrowingStream<RemoteProviderChatStreamEvent, Error>
}

public enum RemoteProviderError: Error, Equatable, CustomStringConvertible {
    case invalidRequest(String)
    case invalidResponse(String)
    case provider(statusCode: Int, message: String)

    public var description: String {
        switch self {
        case .invalidRequest(let message), .invalidResponse(let message):
            return message
        case .provider(let statusCode, let message):
            return "remote provider returned HTTP \(statusCode): \(message)"
        }
    }
}

public struct OpenAICompatibleRemoteProviderClient: RemoteProviderChatClient {
    private let transport: any RemoteProviderHTTPTransport

    public init(transport: any RemoteProviderHTTPTransport = URLSessionRemoteProviderHTTPTransport()) {
        self.transport = transport
    }

    public func complete(_ request: RemoteProviderChatRequest) async throws -> RemoteProviderChatCompletion {
        let (data, response) = try await transport.data(for: try makeHTTPRequest(request.withStream(false)))
        try validateHTTPResponse(data: data, response: response)
        let object = try parseJSONObject(data)
        if request.providerKind == "gemini-generative-language" {
            return try parseGeminiCompletion(object)
        }
        let choice = try firstChoice(from: object)
        let message = choice["message"] as? [String: Any]
        let usage = object["usage"] as? [String: Any]
        return RemoteProviderChatCompletion(
            assistantText: message?["content"] as? String ?? "",
            finishReason: choice["finish_reason"] as? String ?? "stop",
            promptTokens: uint32Value(usage?["prompt_tokens"]),
            completionTokens: uint32Value(usage?["completion_tokens"])
        )
    }

    public func stream(
        _ request: RemoteProviderChatRequest
    ) async throws -> AsyncThrowingStream<RemoteProviderChatStreamEvent, Error> {
        if request.providerKind == "gemini-generative-language" {
            let completion = try await complete(request.withStream(false))
            return AsyncThrowingStream { continuation in
                if completion.assistantText.isEmpty == false {
                    continuation.yield(.tokenDelta(completion.assistantText))
                }
                if completion.promptTokens > 0 || completion.completionTokens > 0 {
                    continuation.yield(
                        .usage(
                            promptTokens: completion.promptTokens,
                            completionTokens: completion.completionTokens
                        )
                    )
                }
                continuation.yield(
                    .completed(
                        finishReason: completion.finishReason,
                        assistantText: completion.assistantText
                    )
                )
                continuation.finish()
            }
        }
        let (data, response) = try await transport.data(for: try makeHTTPRequest(request.withStream(true)))
        try validateHTTPResponse(data: data, response: response)
        let events = try parseSSEEvents(data)
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    private func makeHTTPRequest(_ request: RemoteProviderChatRequest) throws -> URLRequest {
        switch request.providerKind {
        case "openai-compatible":
            return try makeOpenAICompatibleHTTPRequest(request)
        case "gemini-generative-language":
            return try makeGeminiHTTPRequest(request)
        default:
            throw RemoteProviderError.invalidRequest("unsupported remote provider kind: \(request.providerKind)")
        }
    }

    private func makeOpenAICompatibleHTTPRequest(_ request: RemoteProviderChatRequest) throws -> URLRequest {
        let endpoint = request.baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard endpoint.isEmpty == false else {
            throw RemoteProviderError.invalidRequest("remote provider base_url is empty")
        }
        let normalizedBase = endpoint.hasSuffix("/") ? String(endpoint.dropLast()) : endpoint
        guard let url = URL(string: normalizedBase + "/chat/completions") else {
            throw RemoteProviderError.invalidRequest("remote provider base_url is invalid: \(request.baseURL)")
        }
        let body: [String: Any] = [
            "model": request.modelID,
            "messages": request.messages.map { ["role": $0.role, "content": $0.content] },
            "stream": request.stream,
        ]
        var httpRequest = URLRequest(url: url)
        httpRequest.httpMethod = "POST"
        httpRequest.timeoutInterval = TimeInterval(request.timeoutSeconds == 0 ? 60 : request.timeoutSeconds)
        httpRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        httpRequest.setValue("application/json", forHTTPHeaderField: "Accept")
        httpRequest.setValue("OpenAI/Python 1.0.0 Melix/0.1", forHTTPHeaderField: "User-Agent")
        httpRequest.setValue("Bearer \(request.apiKey)", forHTTPHeaderField: "Authorization")
        httpRequest.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])
        return httpRequest
    }

    private func makeGeminiHTTPRequest(_ request: RemoteProviderChatRequest) throws -> URLRequest {
        let endpoint = request.baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard endpoint.isEmpty == false else {
            throw RemoteProviderError.invalidRequest("remote provider base_url is empty")
        }
        let normalizedBase = endpoint.hasSuffix("/") ? String(endpoint.dropLast()) : endpoint
        let modelPath = normalizedGeminiModelPath(request.modelID)
        let queryAllowed = CharacterSet.urlQueryAllowed.subtracting(CharacterSet(charactersIn: "&=+?"))
        guard let encodedModelPath = percentEncodedPath(modelPath),
              let encodedKey = request.apiKey.addingPercentEncoding(withAllowedCharacters: queryAllowed),
              let url = URL(string: "\(normalizedBase)/\(encodedModelPath):generateContent?key=\(encodedKey)")
        else {
            throw RemoteProviderError.invalidRequest("remote provider gemini model or base_url is invalid")
        }

        var contents: [[String: Any]] = []
        var systemParts: [[String: String]] = []
        for message in request.messages {
            let content = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
            guard content.isEmpty == false else {
                continue
            }
            if message.role == "system" {
                systemParts.append(["text": content])
                continue
            }
            let role = message.role == "assistant" || message.role == "model" ? "model" : "user"
            contents.append(
                [
                    "role": role,
                    "parts": [["text": content]],
                ]
            )
        }

        var body: [String: Any] = [
            "contents": contents,
        ]
        if systemParts.isEmpty == false {
            body["systemInstruction"] = ["parts": systemParts]
        }

        var httpRequest = URLRequest(url: url)
        httpRequest.httpMethod = "POST"
        httpRequest.timeoutInterval = TimeInterval(request.timeoutSeconds == 0 ? 60 : request.timeoutSeconds)
        httpRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        httpRequest.setValue("application/json", forHTTPHeaderField: "Accept")
        httpRequest.setValue("OpenAI/Python 1.0.0 Melix/0.1", forHTTPHeaderField: "User-Agent")
        httpRequest.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])
        return httpRequest
    }

    private func validateHTTPResponse(data: Data, response: HTTPURLResponse) throws {
        guard (200..<300).contains(response.statusCode) else {
            let text = String(decoding: data, as: UTF8.self)
            throw RemoteProviderError.provider(statusCode: response.statusCode, message: text)
        }
    }

    private func parseSSEEvents(_ data: Data) throws -> [RemoteProviderChatStreamEvent] {
        let text = String(decoding: data, as: UTF8.self)
        var events: [RemoteProviderChatStreamEvent] = []
        var assistantText = ""
        var finishReason = ""
        var sawDone = false

        for rawLine in text.split(whereSeparator: \.isNewline) {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.hasPrefix("data:") else {
                continue
            }
            let payload = line.dropFirst("data:".count).trimmingCharacters(in: .whitespacesAndNewlines)
            if payload == "[DONE]" {
                sawDone = true
                break
            }
            guard let payloadData = payload.data(using: .utf8) else {
                continue
            }
            let object = try parseJSONObject(payloadData)
            let choice = try firstChoice(from: object)
            if let delta = choice["delta"] as? [String: Any],
               let content = delta["content"] as? String,
               content.isEmpty == false
            {
                assistantText += content
                events.append(.tokenDelta(content))
            }
            if let usage = object["usage"] as? [String: Any] {
                events.append(
                    .usage(
                        promptTokens: uint32Value(usage["prompt_tokens"]),
                        completionTokens: uint32Value(usage["completion_tokens"])
                    )
                )
            }
            if let parsedFinishReason = choice["finish_reason"] as? String,
               parsedFinishReason.isEmpty == false
            {
                finishReason = parsedFinishReason
            }
        }

        if sawDone || finishReason.isEmpty == false {
            events.append(.completed(finishReason: finishReason.isEmpty ? "stop" : finishReason, assistantText: assistantText))
        }
        return events
    }

    private func parseJSONObject(_ data: Data) throws -> [String: Any] {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw RemoteProviderError.invalidResponse("remote provider response was not a JSON object")
        }
        return object
    }

    private func firstChoice(from object: [String: Any]) throws -> [String: Any] {
        guard
            let choices = object["choices"] as? [[String: Any]],
            let choice = choices.first
        else {
            throw RemoteProviderError.invalidResponse("remote provider response did not include choices")
        }
        return choice
    }

    private func parseGeminiCompletion(_ object: [String: Any]) throws -> RemoteProviderChatCompletion {
        guard
            let candidates = object["candidates"] as? [[String: Any]],
            let candidate = candidates.first
        else {
            throw RemoteProviderError.invalidResponse("remote provider response did not include candidates")
        }
        let content = candidate["content"] as? [String: Any]
        let parts = content?["parts"] as? [[String: Any]] ?? []
        let assistantText = parts.compactMap { $0["text"] as? String }.joined()
        let usage = object["usageMetadata"] as? [String: Any]
        return RemoteProviderChatCompletion(
            assistantText: assistantText,
            finishReason: normalizedGeminiFinishReason(candidate["finishReason"] as? String),
            promptTokens: uint32Value(usage?["promptTokenCount"]),
            completionTokens: uint32Value(usage?["candidatesTokenCount"])
        )
    }

    private func normalizedGeminiFinishReason(_ value: String?) -> String {
        switch value?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() {
        case "STOP":
            return "stop"
        case "MAX_TOKENS":
            return "length"
        case .some(let value) where value.isEmpty == false:
            return value.lowercased()
        default:
            return "stop"
        }
    }

    private func normalizedGeminiModelPath(_ modelID: String) -> String {
        let trimmed = modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.hasPrefix("models/") {
            return trimmed
        }
        return "models/\(trimmed)"
    }

    private func percentEncodedPath(_ path: String) -> String? {
        let allowed = CharacterSet.urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))
        var encodedComponents: [String] = []
        for component in path.split(separator: "/") {
            guard let encoded = String(component).addingPercentEncoding(withAllowedCharacters: allowed) else {
                return nil
            }
            encodedComponents.append(encoded)
        }
        return encodedComponents.joined(separator: "/")
    }

    private func uint32Value(_ value: Any?) -> UInt32 {
        if let value = value as? UInt32 {
            return value
        }
        if let value = value as? Int {
            return UInt32(max(value, 0))
        }
        if let value = value as? Double {
            return UInt32(max(value, 0))
        }
        if let value = value as? String, let parsed = UInt32(value) {
            return parsed
        }
        return 0
    }
}
