import Foundation

public protocol RemoteProviderHTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
    func stream(for request: URLRequest) async throws -> RemoteProviderHTTPResponseStream
}

public struct RemoteProviderHTTPResponseStream: Sendable {
    public let response: HTTPURLResponse
    public let body: AsyncThrowingStream<Data, Error>
    public let cancel: @Sendable () -> Void

    public init(
        response: HTTPURLResponse,
        body: AsyncThrowingStream<Data, Error>,
        cancel: @escaping @Sendable () -> Void
    ) {
        self.response = response
        self.body = body
        self.cancel = cancel
    }
}

public extension RemoteProviderHTTPTransport {
    func stream(for request: URLRequest) async throws -> RemoteProviderHTTPResponseStream {
        let (data, response) = try await data(for: request)
        return RemoteProviderHTTPResponseStream(
            response: response,
            body: AsyncThrowingStream { continuation in
                continuation.yield(data)
                continuation.finish()
            },
            cancel: {}
        )
    }
}

public struct URLSessionRemoteProviderHTTPTransport: RemoteProviderHTTPTransport {
    private let bufferedSession: URLSession
    private let streamingConfiguration: URLSessionConfiguration

    public init(
        bufferedSession: URLSession = .shared,
        streamingConfiguration: URLSessionConfiguration = .default
    ) {
        self.bufferedSession = bufferedSession
        self.streamingConfiguration = streamingConfiguration
    }

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await bufferedSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw RemoteProviderError.invalidResponse("Remote provider response was not HTTP.")
        }
        return (data, httpResponse)
    }

    public func stream(for request: URLRequest) async throws -> RemoteProviderHTTPResponseStream {
        let delegate = URLSessionRemoteProviderStreamDelegate()
        delegate.start(request: request, configuration: streamingConfiguration)
        let response = try await delegate.waitForResponse()
        return RemoteProviderHTTPResponseStream(
            response: response,
            body: delegate.body,
            cancel: { delegate.cancel() }
        )
    }
}

public struct RemoteProviderToolDefinition: Equatable, Sendable {
    public let name: String
    public let description: String
    public let parametersJSON: String

    public init(name: String, description: String = "", parametersJSON: String) {
        self.name = name
        self.description = description
        self.parametersJSON = parametersJSON
    }
}

public struct RemoteProviderToolCall: Equatable, Sendable {
    public let callID: String
    public let type: String
    public let toolName: String
    public let argumentsJSON: String

    public init(
        callID: String,
        type: String = "function",
        toolName: String,
        argumentsJSON: String
    ) {
        self.callID = callID
        self.type = type
        self.toolName = toolName
        self.argumentsJSON = argumentsJSON
    }
}

public struct RemoteProviderToolCallDelta: Equatable, Sendable {
    public let index: Int
    public let callID: String
    public let toolName: String
    public let argumentsFragment: String

    public init(index: Int, callID: String, toolName: String, argumentsFragment: String) {
        self.index = index
        self.callID = callID
        self.toolName = toolName
        self.argumentsFragment = argumentsFragment
    }
}

public struct RemoteProviderChatRequest: Equatable, Sendable {
    public struct Message: Equatable, Sendable {
        public let role: String
        public let content: String
        public let name: String?
        public let toolCalls: [RemoteProviderToolCall]
        public let toolCallID: String?

        public init(
            role: String,
            content: String,
            name: String? = nil,
            toolCalls: [RemoteProviderToolCall] = [],
            toolCallID: String? = nil
        ) {
            self.role = role
            self.content = content
            self.name = name
            self.toolCalls = toolCalls
            self.toolCallID = toolCallID
        }
    }

    public let serverID: String
    public let providerKind: String
    public let baseURL: String
    public let apiKey: String
    public let modelID: String
    public let messages: [Message]
    public let tools: [RemoteProviderToolDefinition]
    public let toolChoice: String?
    public let parallelToolCalls: Bool
    public let stream: Bool
    public let enableThinking: Bool?
    public let reasoningEffort: String?
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let timeoutSeconds: UInt32

    public init(
        serverID: String,
        providerKind: String,
        baseURL: String,
        apiKey: String,
        modelID: String,
        messages: [Message],
        tools: [RemoteProviderToolDefinition] = [],
        toolChoice: String? = nil,
        parallelToolCalls: Bool = false,
        stream: Bool,
        enableThinking: Bool? = nil,
        reasoningEffort: String? = nil,
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil,
        timeoutSeconds: UInt32 = 60
    ) {
        self.serverID = serverID
        self.providerKind = providerKind
        self.baseURL = baseURL
        self.apiKey = apiKey
        self.modelID = modelID
        self.messages = messages
        self.tools = tools
        self.toolChoice = toolChoice
        self.parallelToolCalls = parallelToolCalls
        self.stream = stream
        self.enableThinking = enableThinking
        self.reasoningEffort = reasoningEffort
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
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
            tools: tools,
            toolChoice: toolChoice,
            parallelToolCalls: parallelToolCalls,
            stream: stream,
            enableThinking: enableThinking,
            reasoningEffort: reasoningEffort,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            timeoutSeconds: timeoutSeconds
        )
    }
}

public struct RemoteProviderChatCompletion: Equatable, Sendable {
    public let assistantText: String
    public let finishReason: String
    public let promptTokens: UInt32
    public let completionTokens: UInt32
    public let toolCalls: [RemoteProviderToolCall]

    public init(
        assistantText: String,
        finishReason: String,
        promptTokens: UInt32,
        completionTokens: UInt32,
        toolCalls: [RemoteProviderToolCall] = []
    ) {
        self.assistantText = assistantText
        self.finishReason = finishReason
        self.promptTokens = promptTokens
        self.completionTokens = completionTokens
        self.toolCalls = toolCalls
    }
}

public enum RemoteProviderChatStreamEvent: Equatable, Sendable {
    case tokenDelta(String)
    case reasoningDelta(String)
    case toolCallDelta(RemoteProviderToolCallDelta)
    case toolCallsCompleted([RemoteProviderToolCall])
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
            completionTokens: uint32Value(usage?["completion_tokens"]),
            toolCalls: try parseToolCalls(message?["tool_calls"])
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
        let responseStream = try await transport.stream(for: try makeHTTPRequest(request.withStream(true)))
        guard (200..<300).contains(responseStream.response.statusCode) else {
            let errorData = try await boundedBody(from: responseStream, byteLimit: 64 * 1024)
            throw RemoteProviderError.provider(
                statusCode: responseStream.response.statusCode,
                message: String(decoding: errorData, as: UTF8.self)
            )
        }

        let pair = AsyncThrowingStream<RemoteProviderChatStreamEvent, Error>.makeStream()
        let producer = Task {
            var parser = OpenAICompatibleSSEParser()
            do {
                for try await chunk in responseStream.body {
                    try Task.checkCancellation()
                    for event in try parser.consume(chunk) {
                        pair.continuation.yield(event)
                    }
                    if parser.isTerminal {
                        break
                    }
                }
                if parser.isTerminal == false {
                    for event in try parser.finish() {
                        pair.continuation.yield(event)
                    }
                }
                pair.continuation.finish()
            } catch is CancellationError {
                pair.continuation.finish(throwing: CancellationError())
            } catch {
                pair.continuation.finish(throwing: error)
            }
            responseStream.cancel()
        }
        pair.continuation.onTermination = { _ in
            producer.cancel()
            responseStream.cancel()
        }
        return pair.stream
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
        var body: [String: Any] = [
            "model": request.modelID,
            "messages": request.messages.map(openAIMessageObject),
            "stream": request.stream,
        ]
        if request.stream {
            body["stream_options"] = ["include_usage": true]
        }
        if request.tools.isEmpty == false {
            body["tools"] = try request.tools.map(openAIToolObject)
            body["parallel_tool_calls"] = request.parallelToolCalls
            if let toolChoice = normalizedOptionalString(request.toolChoice) {
                body["tool_choice"] = toolChoice
            }
        }
        // `enable_thinking` is a vendor extension rather than an OpenAI-compatible
        // field. Send only the explicit opt-out because `true` is the default for
        // endpoints that support it and strict endpoints may reject unknown keys.
        if request.enableThinking == false {
            body["enable_thinking"] = false
        }
        if let reasoningEffort = normalizedOptionalString(request.reasoningEffort) {
            body["reasoning_effort"] = reasoningEffort
        }
        if let temperature = request.temperature {
            guard temperature.isFinite else {
                throw RemoteProviderError.invalidRequest("remote provider temperature must be finite")
            }
            body["temperature"] = temperature
        }
        if let topP = request.topP {
            guard topP.isFinite else {
                throw RemoteProviderError.invalidRequest("remote provider top_p must be finite")
            }
            body["top_p"] = topP
        }
        if let maxTokens = request.maxTokens, maxTokens > 0 {
            body["max_tokens"] = maxTokens
        }
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
        guard request.tools.isEmpty,
              request.messages.allSatisfy({ $0.toolCalls.isEmpty && $0.toolCallID == nil })
        else {
            throw RemoteProviderError.invalidRequest(
                "structured tools are currently supported only by openai-compatible remote providers"
            )
        }
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

    private func boundedBody(
        from responseStream: RemoteProviderHTTPResponseStream,
        byteLimit: Int
    ) async throws -> Data {
        var data = Data()
        defer { responseStream.cancel() }
        for try await chunk in responseStream.body {
            guard data.count < byteLimit else {
                break
            }
            data.append(chunk.prefix(byteLimit - data.count))
            if data.count >= byteLimit {
                break
            }
        }
        return data
    }

    private func openAIMessageObject(_ message: RemoteProviderChatRequest.Message) -> [String: Any] {
        var object: [String: Any] = [
            "role": message.role,
            "content": message.content,
        ]
        if let name = normalizedOptionalString(message.name) {
            object["name"] = name
        }
        if let toolCallID = normalizedOptionalString(message.toolCallID) {
            object["tool_call_id"] = toolCallID
        }
        if message.toolCalls.isEmpty == false {
            object["tool_calls"] = message.toolCalls.map { call in
                [
                    "id": call.callID,
                    "type": call.type,
                    "function": [
                        "name": call.toolName,
                        "arguments": call.argumentsJSON,
                    ],
                ]
            }
        }
        return object
    }

    private func openAIToolObject(_ tool: RemoteProviderToolDefinition) throws -> [String: Any] {
        let name = tool.name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard name.isEmpty == false else {
            throw RemoteProviderError.invalidRequest("remote provider tool name is empty")
        }
        guard let parametersData = tool.parametersJSON.data(using: .utf8),
              let parameters = try? JSONSerialization.jsonObject(with: parametersData),
              parameters is [String: Any]
        else {
            throw RemoteProviderError.invalidRequest(
                "remote provider tool \(name) parameters must be a JSON object"
            )
        }
        var function: [String: Any] = [
            "name": name,
            "parameters": parameters,
        ]
        if let description = normalizedOptionalString(tool.description) {
            function["description"] = description
        }
        return [
            "type": "function",
            "function": function,
        ]
    }

    private func parseToolCalls(_ value: Any?) throws -> [RemoteProviderToolCall] {
        guard let value else {
            return []
        }
        guard let objects = value as? [[String: Any]] else {
            throw RemoteProviderError.invalidResponse("remote provider tool_calls was not an array")
        }
        let calls = try objects.map { object in
            guard let callID = normalizedOptionalString(object["id"] as? String),
                  let function = object["function"] as? [String: Any],
                  let toolName = normalizedOptionalString(function["name"] as? String),
                  let argumentsJSON = function["arguments"] as? String
            else {
                throw RemoteProviderError.invalidResponse("remote provider tool call was malformed")
            }
            return RemoteProviderToolCall(
                callID: callID,
                type: normalizedOptionalString(object["type"] as? String) ?? "function",
                toolName: toolName,
                argumentsJSON: argumentsJSON
            )
        }
        guard Set(calls.map(\.callID)).count == calls.count else {
            throw RemoteProviderError.invalidResponse(
                "remote provider returned duplicate tool call IDs"
            )
        }
        return calls
    }

    private func normalizedOptionalString(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
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

private final class URLSessionRemoteProviderStreamDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    let body: AsyncThrowingStream<Data, Error>

    private let lock = NSLock()
    private var bodyContinuation: AsyncThrowingStream<Data, Error>.Continuation?
    private var responseContinuation: CheckedContinuation<HTTPURLResponse, Error>?
    private var responseResult: Result<HTTPURLResponse, Error>?
    private var session: URLSession?
    private var task: URLSessionDataTask?
    private var terminal = false

    override init() {
        let pair = AsyncThrowingStream<Data, Error>.makeStream()
        body = pair.stream
        bodyContinuation = pair.continuation
        super.init()
        pair.continuation.onTermination = { [weak self] _ in
            self?.cancel()
        }
    }

    func start(request: URLRequest, configuration: URLSessionConfiguration) {
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        let task = session.dataTask(with: request)
        lock.lock()
        let shouldCancel = terminal
        if shouldCancel == false {
            self.session = session
            self.task = task
        }
        lock.unlock()

        if shouldCancel {
            task.cancel()
            session.invalidateAndCancel()
        } else {
            task.resume()
        }
    }

    func waitForResponse() async throws -> HTTPURLResponse {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                lock.lock()
                if let responseResult {
                    lock.unlock()
                    continuation.resume(with: responseResult)
                } else {
                    responseContinuation = continuation
                    lock.unlock()
                }
            }
        } onCancel: {
            cancel()
        }
    }

    func cancel() {
        terminate(error: CancellationError(), cancelSession: true)
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        guard let httpResponse = response as? HTTPURLResponse else {
            completionHandler(.cancel)
            terminate(
                error: RemoteProviderError.invalidResponse("Remote provider response was not HTTP."),
                cancelSession: true
            )
            return
        }

        lock.lock()
        guard terminal == false else {
            lock.unlock()
            completionHandler(.cancel)
            return
        }
        responseResult = .success(httpResponse)
        let continuation = responseContinuation
        responseContinuation = nil
        lock.unlock()
        continuation?.resume(returning: httpResponse)
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        lock.lock()
        let continuation = terminal ? nil : bodyContinuation
        lock.unlock()
        if case .terminated = continuation?.yield(data) {
            cancel()
        }
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didCompleteWithError error: Error?
    ) {
        if let error {
            let normalizedError: Error
            if (error as? URLError)?.code == .cancelled {
                normalizedError = CancellationError()
            } else {
                normalizedError = error
            }
            terminate(error: normalizedError, cancelSession: false)
        } else {
            terminate(error: nil, cancelSession: false)
        }
    }

    private func terminate(error: Error?, cancelSession: Bool) {
        lock.lock()
        guard terminal == false else {
            lock.unlock()
            return
        }
        terminal = true
        let task = self.task
        self.task = nil
        let session = self.session
        self.session = nil
        let responseContinuation = self.responseContinuation
        self.responseContinuation = nil
        let bodyContinuation = self.bodyContinuation
        self.bodyContinuation = nil
        if responseResult == nil {
            responseResult = .failure(
                error ?? RemoteProviderError.invalidResponse(
                    "remote provider stream ended before response headers"
                )
            )
        }
        let responseResult = self.responseResult
        lock.unlock()

        if cancelSession {
            task?.cancel()
            session?.invalidateAndCancel()
        } else {
            session?.finishTasksAndInvalidate()
        }
        if let responseContinuation, let responseResult {
            responseContinuation.resume(with: responseResult)
        }
        if let error {
            bodyContinuation?.finish(throwing: error)
        } else {
            bodyContinuation?.finish()
        }
    }
}

private struct OpenAICompatibleSSEParser {
    private static let maximumTransportBytes = 16 * 1_024 * 1_024
    private static let maximumChunkBytes = 1 * 1_024 * 1_024
    private static let maximumEventBytes = 1 * 1_024 * 1_024
    private static let maximumAssistantBytes = 4 * 1_024 * 1_024
    private static let maximumToolArgumentBytes = 512 * 1_024
    private static let maximumToolCallCount = 16
    private static let maximumIdentityBytes = 256

    private struct PartialToolCall {
        var callID = ""
        var type = ""
        var toolName = ""
        var argumentsJSON = ""
        var emittedArgumentByteCount = 0
        var emittedCallID: String?
        var emittedType: String?
        var emittedToolName: String?

        static func mergeIdentity(
            _ fragment: String,
            into value: inout String
        ) throws {
            guard fragment.isEmpty == false else {
                return
            }
            guard fragment.utf8.count <= OpenAICompatibleSSEParser.maximumIdentityBytes else {
                throw RemoteProviderError.invalidResponse(
                    "remote provider streamed an oversized tool identity"
                )
            }
            if value.isEmpty {
                value = fragment
            } else if fragment == value || value.hasPrefix(fragment) {
                return
            } else if fragment.hasPrefix(value) {
                value = fragment
            } else {
                guard value.utf8.count
                    <= OpenAICompatibleSSEParser.maximumIdentityBytes - fragment.utf8.count
                else {
                    throw RemoteProviderError.invalidResponse(
                        "remote provider streamed an oversized tool identity"
                    )
                }
                value += fragment
            }
            guard value.utf8.count <= OpenAICompatibleSSEParser.maximumIdentityBytes else {
                throw RemoteProviderError.invalidResponse(
                    "remote provider streamed an oversized tool identity"
                )
            }
        }

        mutating func merge(_ object: [String: Any]) throws -> String? {
            let callIDFragment = object["id"] as? String ?? ""
            try Self.mergeIdentity(callIDFragment, into: &callID)
            try Self.mergeIdentity(object["type"] as? String ?? "", into: &type)
            let function = object["function"] as? [String: Any]
            let toolNameFragment = function?["name"] as? String ?? ""
            if function != nil {
                try Self.mergeIdentity(
                    toolNameFragment,
                    into: &toolName
                )
            }
            let argumentsFragment = function?["arguments"] as? String ?? ""
            guard argumentsFragment.utf8.count
                <= OpenAICompatibleSSEParser.maximumToolArgumentBytes,
                argumentsJSON.utf8.count
                <= OpenAICompatibleSSEParser.maximumToolArgumentBytes
                    - argumentsFragment.utf8.count
            else {
                throw RemoteProviderError.invalidResponse(
                    "remote provider streamed oversized tool arguments"
                )
            }
            argumentsJSON += argumentsFragment
            let normalizedType = type.isEmpty ? "function" : type

            if let emittedCallID,
               emittedCallID != callID
                || emittedType != normalizedType
                || emittedToolName != toolName
            {
                throw RemoteProviderError.invalidResponse(
                    "remote provider changed a published tool identity"
                )
            }

            guard callID.trimmingCharacters(
                in: .whitespacesAndNewlines
            ).isEmpty == false,
            toolName.trimmingCharacters(
                in: .whitespacesAndNewlines
            ).isEmpty == false
            else {
                return nil
            }
            // OpenAI-compatible providers may split both the call ID and
            // function name. Identity fragments have no explicit "complete"
            // bit, so emit arguments only on a later arguments-only delta.
            // The terminal toolCallsCompleted event reconciles single-delta
            // calls without ever publishing an incomplete identity.
            guard callIDFragment.isEmpty, toolNameFragment.isEmpty else {
                return nil
            }
            let emittedIndex = argumentsJSON.utf8.index(
                argumentsJSON.utf8.startIndex,
                offsetBy: emittedArgumentByteCount
            )
            let remaining = String(
                decoding: argumentsJSON.utf8[emittedIndex...],
                as: UTF8.self
            )
            guard remaining.isEmpty == false else {
                return nil
            }
            emittedCallID = callID
            emittedType = normalizedType
            emittedToolName = toolName
            emittedArgumentByteCount = argumentsJSON.utf8.count
            return remaining
        }

        func completed() throws -> RemoteProviderToolCall {
            guard callID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false,
                  toolName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            else {
                throw RemoteProviderError.invalidResponse("remote provider streamed a malformed tool call")
            }
            return RemoteProviderToolCall(
                callID: callID,
                type: type.isEmpty ? "function" : type,
                toolName: toolName,
                argumentsJSON: argumentsJSON
            )
        }
    }

    private var lineBuffer = Data()
    private var eventDataLines: [String] = []
    private var assistantText = ""
    private var finishReason = ""
    private var toolCalls: [Int: PartialToolCall] = [:]
    private var terminal = false
    private var consumedTransportBytes = 0
    private var eventDataByteCount = 0

    var isTerminal: Bool {
        terminal
    }

    mutating func consume(_ chunk: Data) throws -> [RemoteProviderChatStreamEvent] {
        guard terminal == false else {
            return []
        }
        guard chunk.count <= Self.maximumChunkBytes,
              consumedTransportBytes <= Self.maximumTransportBytes - chunk.count,
              lineBuffer.count <= Self.maximumEventBytes - chunk.count
        else {
            throw RemoteProviderError.invalidResponse(
                "remote provider SSE exceeded its bounded transport budget"
            )
        }
        consumedTransportBytes += chunk.count
        lineBuffer.append(chunk)
        var events: [RemoteProviderChatStreamEvent] = []
        while let newlineIndex = lineBuffer.firstIndex(of: 0x0A) {
            var lineData = Data(lineBuffer[..<newlineIndex])
            lineBuffer.removeSubrange(...newlineIndex)
            if lineData.last == 0x0D {
                lineData.removeLast()
            }
            guard lineData.count <= Self.maximumEventBytes else {
                throw RemoteProviderError.invalidResponse(
                    "remote provider SSE line exceeded its bounded size"
                )
            }
            guard let line = String(data: lineData, encoding: .utf8) else {
                throw RemoteProviderError.invalidResponse("remote provider SSE contained invalid UTF-8")
            }
            events.append(contentsOf: try consumeLine(line))
        }
        return events
    }

    mutating func finish() throws -> [RemoteProviderChatStreamEvent] {
        guard terminal == false else {
            return []
        }
        var events: [RemoteProviderChatStreamEvent] = []
        if lineBuffer.isEmpty == false {
            guard let line = String(data: lineBuffer, encoding: .utf8) else {
                throw RemoteProviderError.invalidResponse("remote provider SSE contained invalid UTF-8")
            }
            lineBuffer.removeAll(keepingCapacity: false)
            events.append(contentsOf: try consumeLine(line))
        }
        if eventDataLines.isEmpty == false {
            events.append(contentsOf: try dispatchEvent())
        }
        if terminal == false, finishReason.isEmpty == false {
            events.append(contentsOf: try terminalEvents())
        }
        guard terminal else {
            throw RemoteProviderError.invalidResponse(
                "remote provider SSE ended before a finish reason or [DONE] marker"
            )
        }
        return events
    }

    private mutating func consumeLine(_ line: String) throws -> [RemoteProviderChatStreamEvent] {
        if line.isEmpty {
            return try dispatchEvent()
        }
        guard line.hasPrefix(":" ) == false else {
            return []
        }
        guard line.hasPrefix("data:") else {
            return []
        }
        var value = String(line.dropFirst("data:".count))
        if value.first == " " {
            value.removeFirst()
        }
        let valueBytes = value.utf8.count
        guard eventDataLines.count < 128,
              valueBytes <= Self.maximumEventBytes,
              eventDataByteCount <= Self.maximumEventBytes - valueBytes
        else {
            throw RemoteProviderError.invalidResponse(
                "remote provider SSE event exceeded its bounded size"
            )
        }
        eventDataLines.append(value)
        eventDataByteCount += valueBytes
        return []
    }

    private mutating func dispatchEvent() throws -> [RemoteProviderChatStreamEvent] {
        guard eventDataLines.isEmpty == false else {
            return []
        }
        let payload = eventDataLines.joined(separator: "\n")
        eventDataLines.removeAll(keepingCapacity: true)
        eventDataByteCount = 0
        if payload.trimmingCharacters(in: .whitespacesAndNewlines) == "[DONE]" {
            return try terminalEvents()
        }
        guard let data = payload.data(using: .utf8),
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            throw RemoteProviderError.invalidResponse("remote provider SSE data was not a JSON object")
        }

        var events: [RemoteProviderChatStreamEvent] = []
        let usageEvent: RemoteProviderChatStreamEvent? = if let usage = object["usage"] as? [String: Any] {
            .usage(
                promptTokens: Self.uint32Value(usage["prompt_tokens"]),
                completionTokens: Self.uint32Value(usage["completion_tokens"])
            )
        } else {
            nil
        }

        guard let choices = object["choices"] as? [[String: Any]] else {
            throw RemoteProviderError.invalidResponse("remote provider response did not include choices")
        }
        guard let choice = choices.first else {
            guard let usageEvent else {
                throw RemoteProviderError.invalidResponse(
                    "remote provider response did not include choices"
                )
            }
            events.append(usageEvent)
            return events
        }
        if let delta = choice["delta"] as? [String: Any] {
            if let reasoningContent = delta["reasoning_content"] as? String,
               reasoningContent.isEmpty == false
            {
                guard reasoningContent.utf8.count <= Self.maximumEventBytes else {
                    throw RemoteProviderError.invalidResponse(
                        "remote provider streamed an oversized reasoning delta"
                    )
                }
                events.append(.reasoningDelta(reasoningContent))
            }
            if let content = delta["content"] as? String, content.isEmpty == false {
                guard content.utf8.count <= Self.maximumAssistantBytes,
                      assistantText.utf8.count
                        <= Self.maximumAssistantBytes - content.utf8.count
                else {
                    throw RemoteProviderError.invalidResponse(
                        "remote provider streamed oversized assistant text"
                    )
                }
                assistantText += content
                events.append(.tokenDelta(content))
            }
            if let fragments = delta["tool_calls"] as? [[String: Any]] {
                for fragment in fragments {
                    guard let index = Self.intValue(fragment["index"]),
                          index >= 0,
                          index < Self.maximumToolCallCount
                    else {
                        throw RemoteProviderError.invalidResponse(
                            "remote provider tool call delta did not include a valid index"
                        )
                    }
                    guard toolCalls[index] != nil
                        || toolCalls.count < Self.maximumToolCallCount
                    else {
                        throw RemoteProviderError.invalidResponse(
                            "remote provider streamed too many tool calls"
                        )
                    }
                    var partial = toolCalls[index] ?? PartialToolCall()
                    let argumentsFragment = try partial.merge(fragment)
                    toolCalls[index] = partial
                    if let argumentsFragment {
                        events.append(
                            .toolCallDelta(
                                RemoteProviderToolCallDelta(
                                    index: index,
                                    callID: partial.callID,
                                    toolName: partial.toolName,
                                    argumentsFragment: argumentsFragment
                                )
                            )
                        )
                    }
                }
            } else if delta["tool_calls"] != nil && delta["tool_calls"] is NSNull == false {
                throw RemoteProviderError.invalidResponse("remote provider tool call delta was malformed")
            }
        }
        if let parsedFinishReason = choice["finish_reason"] as? String,
           parsedFinishReason.isEmpty == false
        {
            finishReason = parsedFinishReason
        }
        if let usageEvent {
            events.append(usageEvent)
        }
        return events
    }

    private mutating func terminalEvents() throws -> [RemoteProviderChatStreamEvent] {
        guard terminal == false else {
            return []
        }
        terminal = true
        let completedToolCalls = try toolCalls.keys.sorted().map { index in
            try toolCalls[index]!.completed()
        }
        guard Set(completedToolCalls.map(\.callID)).count
            == completedToolCalls.count
        else {
            throw RemoteProviderError.invalidResponse(
                "remote provider streamed duplicate tool call IDs"
            )
        }
        var events: [RemoteProviderChatStreamEvent] = []
        if completedToolCalls.isEmpty == false {
            events.append(.toolCallsCompleted(completedToolCalls))
        }
        events.append(
            .completed(
                finishReason: finishReason.isEmpty ? "stop" : finishReason,
                assistantText: assistantText
            )
        )
        return events
    }

    private static func intValue(_ value: Any?) -> Int? {
        if let value = value as? Int {
            return value
        }
        if let value = value as? NSNumber {
            return value.intValue
        }
        return nil
    }

    private static func uint32Value(_ value: Any?) -> UInt32 {
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
