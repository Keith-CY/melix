import Foundation

public enum OpenAIConformanceHarnessError: Error, Equatable, CustomStringConvertible {
    case invalidBaseURL(String)
    case transportFailed(String)

    public var description: String {
        switch self {
        case .invalidBaseURL(let value):
            return "invalid OpenAI conformance base_url: \(value)"
        case .transportFailed(let message):
            return "OpenAI conformance transport failed: \(message)"
        }
    }
}

public enum OpenAIConformanceHarnessTarget: Equatable, Sendable {
    case mockBackendCI(modelID: String)
    case realBackendSmoke(baseURL: String, modelID: String, apiKey: String, timeoutSeconds: UInt32)

    var modelID: String {
        switch self {
        case .mockBackendCI(let modelID), .realBackendSmoke(_, let modelID, _, _):
            return modelID
        }
    }

    var timeoutSeconds: UInt32 {
        switch self {
        case .mockBackendCI:
            return 30
        case .realBackendSmoke(_, _, _, let timeoutSeconds):
            return timeoutSeconds == 0 ? 30 : timeoutSeconds
        }
    }
}

public struct OpenAIConformanceHarness: Sendable {
    private let target: OpenAIConformanceHarnessTarget
    private let transport: any RemoteProviderHTTPTransport

    public init(
        target: OpenAIConformanceHarnessTarget,
        transport: (any RemoteProviderHTTPTransport)? = nil
    ) {
        self.target = target
        if let transport {
            self.transport = transport
        } else {
            switch target {
            case .mockBackendCI:
                self.transport = MockOpenAIConformanceTransport()
            case .realBackendSmoke:
                self.transport = URLSessionRemoteProviderHTTPTransport()
            }
        }
    }

    public func run() async throws -> OpenAIConformanceReport {
        let rows = try await Self.rows().asyncMap { row in
            try await execute(row)
        }
        return OpenAIConformanceReport(rows: rows)
    }

    private func execute(_ row: HarnessRow) async throws -> OpenAIConformanceRow {
        let request = try makeHTTPRequest(for: row)
        let data: Data
        let response: HTTPURLResponse
        do {
            (data, response) = try await transport.data(for: request)
        } catch is CancellationError {
            throw CancellationError()
        } catch let urlError as URLError where urlError.code == .cancelled {
            throw urlError
        } catch {
            return row.reportRow(
                status: .fail,
                reason: "transport_failed=\(String(describing: error))"
            )
        }
        let evaluation = row.evaluate(data: data, response: response)
        return row.reportRow(status: evaluation.status, reason: evaluation.reason)
    }

    private func makeHTTPRequest(for row: HarnessRow) throws -> URLRequest {
        let url = try normalizedChatCompletionsURL()
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = TimeInterval(target.timeoutSeconds)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(row.acceptHeader, forHTTPHeaderField: "Accept")
        request.setValue("OpenAI/Python 1.0.0 Melix/0.1", forHTTPHeaderField: "User-Agent")
        if case .realBackendSmoke(_, _, let apiKey, _) = target {
            let trimmed = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty == false {
                request.setValue("Bearer \(trimmed)", forHTTPHeaderField: "Authorization")
            }
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: row.body(modelID: target.modelID), options: [])
        return request
    }

    private func normalizedChatCompletionsURL() throws -> URL {
        switch target {
        case .mockBackendCI:
            return URL(string: "https://mock.melix.local/v1/chat/completions")!
        case .realBackendSmoke(let baseURL, _, _, _):
            let trimmed = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
            let normalized = trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
            guard normalized.isEmpty == false,
                  let url = URL(string: "\(normalized)/chat/completions")
            else {
                throw OpenAIConformanceHarnessError.invalidBaseURL(baseURL)
            }
            return url
        }
    }

    private static func rows() -> [HarnessRow] {
        [
            HarnessRow(
                field: "chat.completions.response_shape",
                route: "/v1/chat/completions -> non-streaming response",
                expectedBehavior: "Non-streaming chat completions return one assistant message choice and usage-compatible JSON.",
                requestKind: .nonStreamingChat
            ),
            HarnessRow(
                field: "chat.completions.streaming_tool_call_shape",
                route: "/v1/chat/completions -> streaming tool-call chunks",
                expectedBehavior: "Streaming tool-call responses use OpenAI SSE chunk shape and terminate with [DONE].",
                requestKind: .streamingToolCall
            ),
            HarnessRow(
                field: "chat.completions.error_shape",
                route: "/v1/chat/completions -> typed error payload",
                expectedBehavior: "Unsupported request fields return a typed error naming field and phase.",
                requestKind: .errorShape
            ),
        ]
    }
}

public struct MockOpenAIConformanceTransport: RemoteProviderHTTPTransport {
    public init() {}

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let body = try requestJSONObject(request)
        let stream = body["stream"] as? Bool ?? false
        let statusCode: Int
        let payload: String
        let contentType: String
        if body["best_of"] != nil {
            statusCode = 400
            contentType = "application/json"
            payload = """
            {"error":{"message":"Unsupported request field","type":"invalid_request_error","code":"unsupported_request_field","field":"best_of","phase":"openai_request_validation"}}
            """
        } else if stream {
            statusCode = 200
            contentType = "text/event-stream"
            payload = """
            data: {"object":"chat.completion.chunk","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call-1","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":\\"Tokyo\\"}"}}]},"finish_reason":null}]}

            data: {"object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}

            data: [DONE]

            """
        } else {
            statusCode = 200
            contentType = "application/json"
            payload = """
            {"id":"chatcmpl-mock","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"pong"},"finish_reason":"stop"}],"usage":{"prompt_tokens":4,"completion_tokens":1,"total_tokens":5}}
            """
        }
        let response = HTTPURLResponse(
            url: request.url ?? URL(string: "https://mock.melix.local/v1/chat/completions")!,
            statusCode: statusCode,
            httpVersion: "HTTP/1.1",
            headerFields: ["content-type": contentType]
        )!
        return (Data(payload.utf8), response)
    }

    private func requestJSONObject(_ request: URLRequest) throws -> [String: Any] {
        guard let body = request.httpBody,
              let object = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        else {
            throw OpenAIConformanceHarnessError.transportFailed("mock request body was not JSON")
        }
        return object
    }
}

public enum OpenAIConformanceHarnessCLIError: Error, Equatable, CustomStringConvertible {
    case unknownOption(String)
    case missingValue(String)
    case invalidMode(String)
    case invalidTimeout(String)

    public var description: String {
        switch self {
        case .unknownOption(let option):
            return "unknown option: \(option)"
        case .missingValue(let option):
            return "missing value for \(option)"
        case .invalidMode(let value):
            return "invalid --mode: \(value)"
        case .invalidTimeout(let value):
            return "invalid --timeout-seconds: \(value)"
        }
    }
}

public struct OpenAIConformanceHarnessCLI: Sendable {
    public let target: OpenAIConformanceHarnessTarget
    public let outputURL: URL

    public init(target: OpenAIConformanceHarnessTarget, outputURL: URL) {
        self.target = target
        self.outputURL = outputURL
    }

    public static func parse(arguments: [String]) throws -> OpenAIConformanceHarnessCLI {
        var values: [String: String] = [:]
        var index = 0
        while index < arguments.count {
            let option = arguments[index]
            guard option.hasPrefix("--") else {
                throw OpenAIConformanceHarnessCLIError.unknownOption(option)
            }
            guard index + 1 < arguments.count else {
                throw OpenAIConformanceHarnessCLIError.missingValue(option)
            }
            values[option] = arguments[index + 1]
            index += 2
        }

        let supportedOptions: Set<String> = [
            "--api-key",
            "--base-url",
            "--mode",
            "--model",
            "--output",
            "--timeout-seconds",
        ]
        for option in values.keys where supportedOptions.contains(option) == false {
            throw OpenAIConformanceHarnessCLIError.unknownOption(option)
        }

        let mode = values["--mode"] ?? "mock-backend-ci"
        guard let output = values["--output"], output.isEmpty == false else {
            throw OpenAIConformanceHarnessCLIError.missingValue("--output")
        }
        let outputURL = URL(fileURLWithPath: output)
        switch mode {
        case "mock-backend-ci":
            let modelID = values["--model"] ?? "melix-dev-text"
            return OpenAIConformanceHarnessCLI(
                target: .mockBackendCI(modelID: modelID),
                outputURL: outputURL
            )
        case "real-backend-smoke":
            guard let baseURL = values["--base-url"], baseURL.isEmpty == false else {
                throw OpenAIConformanceHarnessCLIError.missingValue("--base-url")
            }
            guard let modelID = values["--model"], modelID.isEmpty == false else {
                throw OpenAIConformanceHarnessCLIError.missingValue("--model")
            }
            let timeoutSeconds: UInt32
            if let timeout = values["--timeout-seconds"] {
                guard let parsed = UInt32(timeout), parsed > 0 else {
                    throw OpenAIConformanceHarnessCLIError.invalidTimeout(timeout)
                }
                timeoutSeconds = parsed
            } else {
                timeoutSeconds = 30
            }
            return OpenAIConformanceHarnessCLI(
                target: .realBackendSmoke(
                    baseURL: baseURL,
                    modelID: modelID,
                    apiKey: values["--api-key"] ?? "",
                    timeoutSeconds: timeoutSeconds
                ),
                outputURL: outputURL
            )
        default:
            throw OpenAIConformanceHarnessCLIError.invalidMode(mode)
        }
    }

    public func run(transport: (any RemoteProviderHTTPTransport)? = nil) async throws -> OpenAIConformanceReport {
        let report = try await OpenAIConformanceHarness(target: target, transport: transport).run()
        let outputDirectory = outputURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        try report.jsonData().write(to: outputURL, options: [.atomic])
        return report
    }
}

private struct HarnessRow: Sendable {
    let field: String
    let route: String
    let expectedBehavior: String
    let requestKind: HarnessRequestKind

    var acceptHeader: String {
        switch requestKind {
        case .streamingToolCall:
            return "text/event-stream"
        case .nonStreamingChat, .errorShape:
            return "application/json"
        }
    }

    func body(modelID: String) -> [String: Any] {
        switch requestKind {
        case .nonStreamingChat:
            return [
                "model": modelID,
                "messages": [["role": "user", "content": "Reply with pong."]],
                "stream": false,
                "max_completion_tokens": 8,
            ]
        case .streamingToolCall:
            return [
                "model": modelID,
                "messages": [["role": "user", "content": "Call get_weather for Tokyo."]],
                "stream": true,
                "tools": [[
                    "type": "function",
                    "function": [
                        "name": "get_weather",
                        "description": "Return weather for a city.",
                        "parameters": [
                            "type": "object",
                            "properties": ["city": ["type": "string"]],
                            "required": ["city"],
                        ],
                    ],
                ]],
                "tool_choice": [
                    "type": "function",
                    "function": ["name": "get_weather"],
                ],
            ]
        case .errorShape:
            return [
                "model": modelID,
                "messages": [["role": "user", "content": "Reject unsupported field."]],
                "stream": false,
                "best_of": 2,
            ]
        }
    }

    func evaluate(data: Data, response: HTTPURLResponse) -> (status: OpenAIConformanceObservedStatus, reason: String) {
        switch requestKind {
        case .nonStreamingChat:
            return evaluateNonStreaming(data: data, response: response)
        case .streamingToolCall:
            return evaluateStreamingToolCall(data: data, response: response)
        case .errorShape:
            return evaluateErrorShape(data: data, response: response)
        }
    }

    func reportRow(
        status: OpenAIConformanceObservedStatus,
        reason: String
    ) -> OpenAIConformanceRow {
        OpenAIConformanceRow(
            field: field,
            route: route,
            expectedBehavior: expectedBehavior,
            observedStatus: status,
            observedReason: reason
        )
    }

    private func evaluateNonStreaming(
        data: Data,
        response: HTTPURLResponse
    ) -> (status: OpenAIConformanceObservedStatus, reason: String) {
        guard response.statusCode == 200 else {
            return (.fail, "status=\(response.statusCode)")
        }
        guard let object = try? jsonObject(data),
              let choices = object["choices"] as? [[String: Any]],
              let firstChoice = choices.first,
              let message = firstChoice["message"] as? [String: Any],
              message["role"] as? String == "assistant",
              message["content"] is String
        else {
            return (.fail, "status=200 missing=choices[0].message")
        }
        return (.pass, "status=200")
    }

    private func evaluateStreamingToolCall(
        data: Data,
        response: HTTPURLResponse
    ) -> (status: OpenAIConformanceObservedStatus, reason: String) {
        guard response.statusCode == 200 else {
            return (.fail, "status=\(response.statusCode)")
        }
        let text = String(decoding: data, as: UTF8.self)
        let events = sseDataEvents(in: text)
        guard events.contains("[DONE]") else {
            return (.fail, "status=200 missing=done")
        }
        var hasToolCalls = false
        var hasToolCallsFinishReason = false
        for event in events where event != "[DONE]" {
            guard let eventData = event.data(using: .utf8),
                  let object = try? jsonObject(eventData),
                  let choices = object["choices"] as? [[String: Any]]
            else {
                continue
            }
            for choice in choices {
                if let delta = choice["delta"] as? [String: Any],
                   delta["tool_calls"] != nil {
                    hasToolCalls = true
                }
                if choice["finish_reason"] as? String == "tool_calls" {
                    hasToolCallsFinishReason = true
                }
            }
        }
        guard hasToolCalls, hasToolCallsFinishReason else {
            return (.fail, "status=200 missing=tool_call_chunk")
        }
        return (.pass, "status=200")
    }

    private func evaluateErrorShape(
        data: Data,
        response: HTTPURLResponse
    ) -> (status: OpenAIConformanceObservedStatus, reason: String) {
        guard response.statusCode >= 400 else {
            return (.fail, "status=\(response.statusCode) expected_error=true")
        }
        let errorObject = (try? jsonObject(data))?["error"] as? [String: Any]
        let field = errorObject?["field"] as? String
        let phase = errorObject?["phase"] as? String
        guard let field, field.isEmpty == false,
              let phase, phase.isEmpty == false
        else {
            return (.fail, "status=\(response.statusCode) missing=field_or_phase")
        }
        return (.pass, "status=\(response.statusCode) field=\(field) phase=\(phase)")
    }

    private func jsonObject(_ data: Data) throws -> [String: Any] {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw OpenAIConformanceHarnessError.transportFailed("response was not a JSON object")
        }
        return object
    }

    private func sseDataEvents(in text: String) -> [String] {
        text.components(separatedBy: .newlines).compactMap { line in
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.hasPrefix("data:") else {
                return nil
            }
            return String(trimmed.dropFirst("data:".count)).trimmingCharacters(in: .whitespaces)
        }
    }
}

private enum HarnessRequestKind: Sendable {
    case nonStreamingChat
    case streamingToolCall
    case errorShape
}

private extension Array {
    func asyncMap<T: Sendable>(
        _ transform: @Sendable (Element) async throws -> T
    ) async throws -> [T] {
        var values: [T] = []
        values.reserveCapacity(count)
        for element in self {
            try await values.append(transform(element))
        }
        return values
    }
}
