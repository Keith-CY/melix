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
            return try makeNormalizedChatCompletionsURL(baseURL: baseURL)
        }
    }

    fileprivate static func rows() -> [HarnessRow] {
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

public struct OpenAIProxyParityTarget: Equatable, Sendable {
    public let localBaseURL: String
    public let localModelID: String
    public let localAPIKey: String
    public let remoteBaseURL: String
    public let remoteModelID: String
    public let remoteAPIKey: String
    public let timeoutSeconds: UInt32

    public init(
        localBaseURL: String,
        localModelID: String,
        localAPIKey: String,
        remoteBaseURL: String,
        remoteModelID: String,
        remoteAPIKey: String,
        timeoutSeconds: UInt32
    ) {
        self.localBaseURL = localBaseURL
        self.localModelID = localModelID
        self.localAPIKey = localAPIKey
        self.remoteBaseURL = remoteBaseURL
        self.remoteModelID = remoteModelID
        self.remoteAPIKey = remoteAPIKey
        self.timeoutSeconds = timeoutSeconds == 0 ? 30 : timeoutSeconds
    }
}

public struct OpenAIProxyParityHarness: Sendable {
    private let target: OpenAIProxyParityTarget
    private let localTransport: any RemoteProviderHTTPTransport
    private let remoteTransport: any RemoteProviderHTTPTransport

    public init(
        target: OpenAIProxyParityTarget,
        localTransport: (any RemoteProviderHTTPTransport)? = nil,
        remoteTransport: (any RemoteProviderHTTPTransport)? = nil
    ) {
        self.target = target
        self.localTransport = localTransport ?? URLSessionRemoteProviderHTTPTransport()
        self.remoteTransport = remoteTransport ?? URLSessionRemoteProviderHTTPTransport()
    }

    public func run() async throws -> OpenAIConformanceReport {
        let rows = try await OpenAIConformanceHarness.rows().asyncMap { row in
            try await execute(row)
        }
        return OpenAIConformanceReport(rows: rows)
    }

    private func execute(_ row: HarnessRow) async throws -> OpenAIConformanceRow {
        let localRequest = try makeHTTPRequest(
            for: row,
            baseURL: target.localBaseURL,
            modelID: target.localModelID,
            apiKey: target.localAPIKey
        )
        let remoteRequest = try makeHTTPRequest(
            for: row,
            baseURL: target.remoteBaseURL,
            modelID: target.remoteModelID,
            apiKey: target.remoteAPIKey
        )

        async let localResult = execute(row, request: localRequest, transport: localTransport)
        async let remoteResult = execute(row, request: remoteRequest, transport: remoteTransport)
        let local = try await localResult
        let remote = try await remoteResult

        if let mismatch = local.requestReceipt.firstMismatch(against: remote.requestReceipt) {
            return parityRow(row, status: .fail, reason: mismatch)
        }
        guard local.responseEvaluation.status == .pass else {
            return parityRow(row, status: .fail, reason: "local_response=\(local.responseEvaluation.reason)")
        }
        guard remote.responseEvaluation.status == .pass else {
            return parityRow(row, status: .fail, reason: "remote_response=\(remote.responseEvaluation.reason)")
        }
        guard local.responseEvaluation.reason == remote.responseEvaluation.reason else {
            return parityRow(
                row,
                status: .fail,
                reason: "response_shape local=\(local.responseEvaluation.reason) remote=\(remote.responseEvaluation.reason)"
            )
        }
        return parityRow(
            row,
            status: .pass,
            reason: "request_receipt=equivalent response_shape=equivalent"
        )
    }

    private func execute(
        _ row: HarnessRow,
        request: URLRequest,
        transport: any RemoteProviderHTTPTransport
    ) async throws -> ProxyParityExecution {
        let requestReceipt = try OpenAIProxyParityRequestReceipt(row: row, request: request)
        do {
            let (data, response) = try await transport.data(for: request)
            return ProxyParityExecution(
                requestReceipt: requestReceipt,
                responseEvaluation: row.evaluate(data: data, response: response)
            )
        } catch is CancellationError {
            throw CancellationError()
        } catch let urlError as URLError where urlError.code == .cancelled {
            throw urlError
        } catch {
            return ProxyParityExecution(
                requestReceipt: requestReceipt,
                responseEvaluation: (.fail, "transport_failed=\(String(describing: error))")
            )
        }
    }

    private func makeHTTPRequest(
        for row: HarnessRow,
        baseURL: String,
        modelID: String,
        apiKey: String
    ) throws -> URLRequest {
        let url = try makeNormalizedChatCompletionsURL(baseURL: baseURL)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = TimeInterval(target.timeoutSeconds)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(row.acceptHeader, forHTTPHeaderField: "Accept")
        request.setValue("OpenAI/Python 1.0.0 Melix/0.1", forHTTPHeaderField: "User-Agent")
        let trimmedAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedAPIKey.isEmpty == false {
            request.setValue("Bearer \(trimmedAPIKey)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: row.body(modelID: modelID), options: [])
        return request
    }

    private func parityRow(
        _ row: HarnessRow,
        status: OpenAIConformanceObservedStatus,
        reason: String
    ) -> OpenAIConformanceRow {
        OpenAIConformanceRow(
            field: "proxy_parity.\(row.field)",
            route: "local and remote \(row.route)",
            expectedBehavior: "Local backend and configured remote Server Profile produce equivalent request receipts and response shapes for \(row.expectedBehavior)",
            observedStatus: status,
            observedReason: reason
        )
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
    public let target: OpenAIConformanceHarnessTarget?
    public let proxyParityTarget: OpenAIProxyParityTarget?
    public let outputURL: URL

    public init(target: OpenAIConformanceHarnessTarget, outputURL: URL) {
        self.target = target
        self.proxyParityTarget = nil
        self.outputURL = outputURL
    }

    public init(proxyParityTarget: OpenAIProxyParityTarget, outputURL: URL) {
        self.target = nil
        self.proxyParityTarget = proxyParityTarget
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
            "--local-api-key",
            "--local-base-url",
            "--local-model",
            "--mode",
            "--model",
            "--output",
            "--remote-api-key",
            "--remote-base-url",
            "--remote-model",
            "--timeout-seconds",
        ]
        for option in values.keys where supportedOptions.contains(option) == false {
            throw OpenAIConformanceHarnessCLIError.unknownOption(option)
        }

        let mode = values["--mode"] ?? "mock-backend-ci"
        guard let output = values["--output"], output.isEmpty == false else {
            throw OpenAIConformanceHarnessCLIError.missingValue("--output")
        }
        try validateModeSpecificOptions(mode: mode, values: values)
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
        case "proxy-parity":
            guard let localBaseURL = values["--local-base-url"], localBaseURL.isEmpty == false else {
                throw OpenAIConformanceHarnessCLIError.missingValue("--local-base-url")
            }
            guard let localModelID = values["--local-model"], localModelID.isEmpty == false else {
                throw OpenAIConformanceHarnessCLIError.missingValue("--local-model")
            }
            guard let remoteBaseURL = values["--remote-base-url"], remoteBaseURL.isEmpty == false else {
                throw OpenAIConformanceHarnessCLIError.missingValue("--remote-base-url")
            }
            guard let remoteModelID = values["--remote-model"], remoteModelID.isEmpty == false else {
                throw OpenAIConformanceHarnessCLIError.missingValue("--remote-model")
            }
            let timeoutSeconds = try parseTimeoutSeconds(values["--timeout-seconds"])
            return OpenAIConformanceHarnessCLI(
                proxyParityTarget: OpenAIProxyParityTarget(
                    localBaseURL: localBaseURL,
                    localModelID: localModelID,
                    localAPIKey: values["--local-api-key"] ?? "",
                    remoteBaseURL: remoteBaseURL,
                    remoteModelID: remoteModelID,
                    remoteAPIKey: values["--remote-api-key"] ?? "",
                    timeoutSeconds: timeoutSeconds
                ),
                outputURL: outputURL
            )
        default:
            throw OpenAIConformanceHarnessCLIError.invalidMode(mode)
        }
    }

    public func run(
        transport: (any RemoteProviderHTTPTransport)? = nil
    ) async throws -> OpenAIConformanceReport {
        let report: OpenAIConformanceReport
        if let proxyParityTarget {
            report = try await OpenAIProxyParityHarness(
                target: proxyParityTarget,
                localTransport: transport,
                remoteTransport: transport
            ).run()
        } else if let target {
            report = try await OpenAIConformanceHarness(target: target, transport: transport).run()
        } else {
            throw OpenAIConformanceHarnessError.transportFailed("missing conformance target")
        }
        let outputDirectory = outputURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        try report.jsonData().write(to: outputURL, options: [.atomic])
        return report
    }

    private static func parseTimeoutSeconds(_ value: String?) throws -> UInt32 {
        guard let value else {
            return 30
        }
        guard let parsed = UInt32(value), parsed > 0 else {
            throw OpenAIConformanceHarnessCLIError.invalidTimeout(value)
        }
        return parsed
    }

    private static func validateModeSpecificOptions(
        mode: String,
        values: [String: String]
    ) throws {
        let commonOptions: Set<String> = ["--mode", "--output", "--timeout-seconds"]
        let allowedOptions: Set<String>
        switch mode {
        case "mock-backend-ci":
            allowedOptions = commonOptions.union(["--model"])
        case "real-backend-smoke":
            allowedOptions = commonOptions.union(["--api-key", "--base-url", "--model"])
        case "proxy-parity":
            allowedOptions = commonOptions.union([
                "--local-api-key",
                "--local-base-url",
                "--local-model",
                "--remote-api-key",
                "--remote-base-url",
                "--remote-model",
            ])
        default:
            return
        }
        for option in values.keys.sorted() where allowedOptions.contains(option) == false {
            throw OpenAIConformanceHarnessCLIError.unknownOption(option)
        }
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

private struct ProxyParityExecution: Sendable {
    let requestReceipt: OpenAIProxyParityRequestReceipt
    let responseEvaluation: (status: OpenAIConformanceObservedStatus, reason: String)
}

private struct OpenAIProxyParityRequestReceipt: Equatable, Sendable {
    let method: String
    let path: String
    let accept: String
    let contentType: String
    let requestKind: String
    let bodyFields: [String]
    let stream: Bool
    let toolNames: [String]
    let toolChoiceName: String
    let unsupportedField: String
    let modelPresent: Bool

    init(row: HarnessRow, request: URLRequest) throws {
        self.method = request.httpMethod ?? ""
        self.path = row.requestKind.endpointPath
        self.accept = request.value(forHTTPHeaderField: "Accept") ?? ""
        self.contentType = request.value(forHTTPHeaderField: "Content-Type") ?? ""
        self.requestKind = row.requestKind.receiptName
        let body = try Self.bodyObject(from: request)
        self.bodyFields = body.keys.sorted()
        self.stream = body["stream"] as? Bool ?? false
        self.toolNames = Self.toolNames(from: body)
        self.toolChoiceName = Self.toolChoiceName(from: body)
        self.unsupportedField = body["best_of"] == nil ? "" : "best_of"
        self.modelPresent = (body["model"] as? String)?.isEmpty == false
    }

    func firstMismatch(against other: OpenAIProxyParityRequestReceipt) -> String? {
        let checks: [(String, String, String)] = [
            ("method", method, other.method),
            ("path", path, other.path),
            ("accept", accept, other.accept),
            ("content_type", contentType, other.contentType),
            ("request_kind", requestKind, other.requestKind),
            ("body_fields", bodyFields.description, other.bodyFields.description),
            ("stream", String(stream), String(other.stream)),
            ("tool_names", toolNames.description, other.toolNames.description),
            ("tool_choice_name", toolChoiceName, other.toolChoiceName),
            ("unsupported_field", unsupportedField, other.unsupportedField),
            ("model_present", String(modelPresent), String(other.modelPresent)),
        ]
        for (key, local, remote) in checks where local != remote {
            return "request_receipt.\(key) local=\(local) remote=\(remote)"
        }
        return nil
    }

    private static func bodyObject(from request: URLRequest) throws -> [String: Any] {
        guard let body = request.httpBody,
              let object = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        else {
            throw OpenAIConformanceHarnessError.transportFailed("proxy parity request body was not JSON")
        }
        return object
    }

    private static func toolNames(from body: [String: Any]) -> [String] {
        guard let tools = body["tools"] as? [[String: Any]] else {
            return []
        }
        return tools.compactMap { tool in
            (tool["function"] as? [String: Any])?["name"] as? String
        }.sorted()
    }

    private static func toolChoiceName(from body: [String: Any]) -> String {
        guard let toolChoice = body["tool_choice"] as? [String: Any],
              let function = toolChoice["function"] as? [String: Any],
              let name = function["name"] as? String
        else {
            return ""
        }
        return name
    }
}

private extension HarnessRequestKind {
    var receiptName: String {
        switch self {
        case .nonStreamingChat:
            return "non_streaming_chat"
        case .streamingToolCall:
            return "streaming_tool_call"
        case .errorShape:
            return "error_shape"
        }
    }

    var endpointPath: String {
        switch self {
        case .nonStreamingChat, .streamingToolCall, .errorShape:
            return "/chat/completions"
        }
    }
}

private func makeNormalizedChatCompletionsURL(baseURL: String) throws -> URL {
    let trimmed = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
    let normalized = trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
    guard normalized.isEmpty == false,
          let url = URL(string: "\(normalized)/chat/completions")
    else {
        throw OpenAIConformanceHarnessError.invalidBaseURL(baseURL)
    }
    return url
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
