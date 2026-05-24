import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("OpenAI Compatibility Conformance Matrix")
struct OpenAIConformanceMatrixTests {
    private struct MatrixRow: Sendable {
        let field: String
        let route: String
        let expectedBehavior: String
        let requestBody: String
        let assertion: @Sendable (HTTPResponse, Melix_Worker_V1_GenerateRequest?) async throws -> OpenAIConformanceObservedStatus
    }

    @Test("chat compatibility rows normalize or reject at the OpenAI boundary")
    func chatCompatibilityRowsNormalizeOrRejectAtBoundary() async throws {
        let rows: [MatrixRow] = [
            MatrixRow(
                field: "max_completion_tokens",
                route: "/v1/chat/completions -> sampling.max_output_tokens",
                expectedBehavior: "max_completion_tokens maps to worker sampling and records the OpenAI alias.",
                requestBody: Self.body(extra: #""max_completion_tokens": 37"#)
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.sampling.maxOutputTokens == 37)
                #expect(generated.execution.ext["melix.openai.request.max_tokens_field"] == "max_completion_tokens")
                return .pass
            },
            MatrixRow(
                field: "max_tokens,max_completion_tokens",
                route: "/v1/chat/completions -> typed rejection",
                expectedBehavior: "conflicting max token fields return HTTP 400 and do not dispatch to the worker.",
                requestBody: Self.body(extra: #""max_tokens": 16, "max_completion_tokens": 37"#)
            ) { response, request in
                let payload = try await collectConformanceBody(response.body)
                #expect(response.statusCode == 400)
                #expect(payload.contains("\"code\":\"invalid_generation_bounds\""))
                #expect(payload.contains("max_tokens"))
                #expect(payload.contains("max_completion_tokens"))
                #expect(request == nil)
                return .pass
            },
            MatrixRow(
                field: "parallel_tool_calls=false",
                route: "/v1/chat/completions -> execution.ext tool policy receipt",
                expectedBehavior: "parallel_tool_calls=false is preserved as an effective non-parallel tool policy.",
                requestBody: Self.body(
                    extra: #""parallel_tool_calls": false, "tools": [\#(weatherToolJSON)], "tool_choice": "auto""#
                )
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.execution.hasToolConfig)
                #expect(generated.execution.ext["melix.openai.parallel_tool_calls.requested"] == "false")
                #expect(generated.execution.ext["melix.tool_config.parallel_policy"] == "disabled")
                return .pass
            },
            MatrixRow(
                field: "functions",
                route: "/v1/chat/completions -> tool_config.tools",
                expectedBehavior: "legacy functions normalize into the same worker tool boundary as tools[].",
                requestBody: Self.body(extra: #""functions": [\#(weatherFunctionJSON)]"#)
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.execution.hasToolConfig)
                #expect(generated.execution.toolConfig.tools.map(\.name) == ["get_weather"])
                #expect(generated.execution.ext["melix.tool_config.source"] == "openai_chat_tools")
                #expect(generated.execution.ext["melix.openai.legacy_functions"] == "true")
                return .pass
            },
            MatrixRow(
                field: "function_call",
                route: "/v1/chat/completions -> tool_config.tool_choice",
                expectedBehavior: "legacy function_call normalizes into forced worker tool-choice metadata.",
                requestBody: Self.body(extra: #""functions": [\#(weatherFunctionJSON)], "function_call": { "name": "get_weather" }"#)
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.execution.toolConfig.toolChoice.contains("get_weather"))
                #expect(generated.execution.ext["melix.openai.legacy_function_call"] == "true")
                return .pass
            },
            MatrixRow(
                field: "stop",
                route: "/v1/chat/completions -> sampling.stop",
                expectedBehavior: "scalar stop forwards as a single worker stop sequence.",
                requestBody: Self.body(extra: #""stop": "END""#)
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.sampling.stop == ["END"])
                #expect(generated.execution.ext["melix.generation.stop_effective"] == "END")
                return .pass
            },
            MatrixRow(
                field: "stop[]",
                route: "/v1/chat/completions -> sampling.stop",
                expectedBehavior: "array stop forwards ordered worker stop sequences.",
                requestBody: Self.body(extra: #""stop": ["END", "DONE"]"#)
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.sampling.stop == ["END", "DONE"])
                #expect(generated.execution.ext["melix.generation.stop_effective"] == #"["END","DONE"]"#)
                return .pass
            },
            MatrixRow(
                field: "logprobs,top_logprobs",
                route: "/v1/chat/completions -> execution.ext effective receipt",
                expectedBehavior: "logprobs requests are visible as unsupported-effective receipts until workers emit token distributions.",
                requestBody: Self.body(extra: #""logprobs": true, "top_logprobs": 3"#)
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.execution.ext["melix.openai.logprobs.requested"] == "true")
                #expect(generated.execution.ext["melix.openai.top_logprobs.requested"] == "3")
                #expect(generated.execution.ext["melix.openai.logprobs.effective"] == "unsupported")
                return .pass
            },
        ]

        var reportRows: [OpenAIConformanceRow] = []
        for row in rows {
            let worker = RecordingConformanceWorker(requestID: "req-\(row.field)")
            let handler = Self.handler(worker: worker)
            let response = try await handler.handle(
                HTTPRequest(
                    method: .post,
                    path: "/v1/chat/completions",
                    headers: ["content-type": "application/json"],
                    body: Data(row.requestBody.utf8)
                )
            )
            let request = await worker.lastGenerateRequest
            let status = try await row.assertion(response, request)
            reportRows.append(
                OpenAIConformanceRow(
                    field: row.field,
                    route: row.route,
                    expectedBehavior: row.expectedBehavior,
                    observedStatus: status,
                    observedReason: "status=\(response.statusCode)"
                )
            )
        }

        let report = OpenAIConformanceReport(rows: reportRows)
        #expect(report.summary.passed == rows.count)
        #expect(report.summary.failed == 0)
        let reportJSON = try report.jsonString()
        #expect(reportJSON.contains("\"schema_version\":\"melix.openai_conformance_report.v1\""))
        #expect(reportJSON.contains("\"field\":\"logprobs,top_logprobs\""))
    }

    @Test("payload model routes to selected served model in active roster")
    func payloadModelRoutesToSelectedServedModelInActiveRoster() async throws {
        var primary = warmConformanceModel(id: "melix-primary")
        primary.state = .modelWarm
        var secondary = warmConformanceModel(id: "melix-secondary")
        secondary.state = .modelWarm
        let catalog = ModelCatalog(seedModels: [primary, secondary])
        _ = await catalog.recordLoadSucceeded(id: "melix-secondary", dispatchHandle: "melix-secondary::swift")
        let worker = RecordingConformanceWorker(requestID: "req-routed-model")
        let registry = WorkerRegistry(defaultTextClient: worker, modelCatalog: catalog)
        let gatewayConfigStore = GatewayConfigStore(
            storeURL: FileManager.default.temporaryDirectory
                .appendingPathComponent("melix-openai-conformance-\(UUID().uuidString).json"),
            defaults: [:]
        )
        var command = Melix_Controlplane_V1_ApplyGatewayConfig()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.host = "127.0.0.1"
        command.port = 12_434
        command.defaultModelID = "melix-primary"
        command.servedModelIds = ["melix-primary", "melix-secondary"]
        command.rateLimitPerMinute = 120
        command.timeoutSeconds = 60
        try await gatewayConfigStore.apply(command: command)

        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: registry,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-routed-model" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) }),
            gatewayConfigStore: gatewayConfigStore
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(model: "melix-secondary", extra: #""max_completion_tokens": 11"#).utf8)
            )
        )
        _ = try await collectConformanceBody(response.body)
        let request = try #require(await worker.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.execution.modelHandle == "melix-secondary::swift")
        #expect(request.execution.scope.modelID == "melix-secondary")
        #expect(request.sampling.maxOutputTokens == 11)
    }

    @Test("reasoning usage and logprob-adjacent rows stay explicit at output boundary")
    func reasoningUsageAndLogprobAdjacentRowsStayExplicitAtOutputBoundary() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-output-boundary",
            events: [
                makeReasoningEvent(requestID: "req-output-boundary", seq: 1, text: "think"),
                makeUsageEvent(requestID: "req-output-boundary", seq: 2, promptTokens: 5, completionTokens: 7),
                makeCompletedEvent(
                    requestID: "req-output-boundary",
                    seq: 3,
                    finishReason: "stop",
                    assistantText: "done",
                    reasoningText: "think"
                ),
            ]
        )
        let handler = Self.handler(worker: worker)
        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(extra: #""stream": false, "logprobs": true, "max_completion_tokens": 7"#).utf8)
            )
        )
        let payload = try await collectConformanceBody(response.body)
        let request = try #require(await worker.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"completion_tokens\":7"))
        #expect(payload.contains("\"total_tokens\":12"))
        #expect(payload.contains("\"content\":\"done\""))
        #expect(request.execution.ext["melix.openai.logprobs.effective"] == "unsupported")
        #expect(request.execution.ext["melix.reasoning.mode"]?.isEmpty == false)
    }

    @Test("streaming and non-streaming fixtures agree on compatibility receipts")
    func streamingAndNonStreamingFixturesAgreeOnCompatibilityReceipts() async throws {
        let streamWorker = RecordingConformanceWorker(requestID: "req-stream")
        let nonStreamWorker = RecordingConformanceWorker(requestID: "req-non-stream")
        let streamHandler = Self.handler(worker: streamWorker)
        let nonStreamHandler = Self.handler(worker: nonStreamWorker)
        let extra = #""logprobs": true, "top_logprobs": 2, "parallel_tool_calls": false, "tools": [\#(weatherToolJSON)]"#

        _ = try await streamHandler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(extra: #""stream": true, \#(extra)"#).utf8)
            )
        )
        _ = try await collectConformanceBody(
            try await nonStreamHandler.handle(
                HTTPRequest(
                    method: .post,
                    path: "/v1/chat/completions",
                    headers: ["content-type": "application/json"],
                    body: Data(Self.body(extra: #""stream": false, \#(extra)"#).utf8)
                )
            ).body
        )

        let streamExt = try #require(await streamWorker.lastGenerateRequest?.execution.ext)
        let nonStreamExt = try #require(await nonStreamWorker.lastGenerateRequest?.execution.ext)

        for key in [
            "melix.openai.logprobs.requested",
            "melix.openai.top_logprobs.requested",
            "melix.openai.logprobs.effective",
            "melix.openai.parallel_tool_calls.requested",
            "melix.tool_config.parallel_policy",
        ] {
            #expect(streamExt[key] == nonStreamExt[key], "mismatch for \(key)")
        }
    }

    @Test("streaming fixture emits OpenAI-compatible tool-call deltas")
    func streamingFixtureEmitsOpenAICompatibleToolCallDeltas() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-stream-tool",
            events: [
                makeToolCallEvent(
                    requestID: "req-stream-tool",
                    seq: 1,
                    callID: "tool-1",
                    toolName: "get_weather",
                    argumentsJSONFragment: #"{"city":"Tokyo"}"#,
                    fragmentIndex: 0
                ),
                makeCompletedEvent(
                    requestID: "req-stream-tool",
                    seq: 2,
                    finishReason: "tool_calls",
                    assistantText: ""
                ),
            ]
        )
        let handler = Self.handler(worker: worker)
        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(
                    Self.body(
                        extra: #""stream": true, "tools": [\#(weatherToolJSON)], "tool_choice": { "type": "function", "function": { "name": "get_weather" } }"#
                    ).utf8
                )
            )
        )
        let payload = try await collectConformanceBody(response.body)
        let request = try #require(await worker.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.execution.toolConfig.toolChoice.contains("get_weather"))
        #expect(payload.contains("event: message"))
        #expect(payload.contains("\"tool_calls\""))
        #expect(payload.contains("\"name\":\"get_weather\""))
        #expect(payload.contains("\"arguments\":\"{\\\"city\\\":\\\"Tokyo\\\"}\""))
        #expect(payload.contains("\"finish_reason\":\"tool_calls\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("legacy function_call codable values normalize into stable tool choices")
    func legacyFunctionCallCodableValuesNormalizeIntoStableToolChoices() throws {
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]

        let mode = try decoder.decode(OpenAILegacyFunctionCall.self, from: Data(#""auto""#.utf8))
        let named = try decoder.decode(OpenAILegacyFunctionCall.self, from: Data(#"{"name":"get_weather"}"#.utf8))
        let structured = try decoder.decode(
            OpenAILegacyFunctionCall.self,
            from: Data(#"{"type":"function","function":{"name":"get_weather"}}"#.utf8)
        )

        #expect(mode.normalizedToolChoice == "auto")
        #expect(named.normalizedToolChoice?.contains("get_weather") == true)
        #expect(structured.normalizedToolChoice?.contains("\"function\"") == true)
        #expect(OpenAILegacyFunctionCall.named("   ").normalizedToolChoice == nil)
        #expect(String(decoding: try encoder.encode(mode), as: UTF8.self) == #""auto""#)
        #expect(String(decoding: try encoder.encode(named), as: UTF8.self).contains("get_weather"))
        #expect(String(decoding: try encoder.encode(structured), as: UTF8.self).contains("\"function\""))
    }

    @Test("programmatic OpenAI chat requests encode legacy compatibility fields")
    func programmaticOpenAIChatRequestsEncodeLegacyCompatibilityFields() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let request = OpenAIChatCompletionsRequest(
            model: "melix-dev-text",
            messages: [
                OpenAIChatCompletionsRequest.Message(role: "user", content: "encode")
            ],
            maxTokens: 9,
            legacyFunctions: [
                OpenAIChatTool.FunctionDefinition(
                    name: "get_weather",
                    parameters: .object([
                        "type": .string("object"),
                    ])
                ),
            ],
            legacyFunctionCall: .named("get_weather"),
            parallelToolCalls: false,
            logprobs: true,
            topLogprobs: 2
        )

        let encoded = String(decoding: try encoder.encode(request), as: UTF8.self)
        #expect(encoded.contains("\"functions\""))
        #expect(encoded.contains("\"function_call\""))
        #expect(encoded.contains("\"parallel_tool_calls\":false"))
        #expect(encoded.contains("\"logprobs\":true"))
        #expect(encoded.contains("\"top_logprobs\":2"))
        #expect(request.compatibilityReceipts["melix.openai.request.max_tokens_field"] == "max_tokens")
    }

    @Test("multimodal chat normalization carries compatibility receipts")
    func multimodalChatNormalizationCarriesCompatibilityReceipts() throws {
        let request = try JSONDecoder().decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "max_completion_tokens": 13,
                  "logprobs": true,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Look." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "url": "file:///tmp/fixture.png",
                            "mime_type": "image/png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try ChatRequestTranslator(requestIDGenerator: { "req-multimodal-receipt" })
            .normalizeMultimodalChat(request)

        #expect(normalized.messages.first?.parts.count == 2)
        #expect(normalized.openAICompatibilityReceipts["melix.openai.request.max_tokens_field"] == "max_completion_tokens")
        #expect(normalized.openAICompatibilityReceipts["melix.openai.logprobs.effective"] == "unsupported")
    }

    @Test("recording worker fixture covers phase-aware and model lifecycle methods")
    func recordingWorkerFixtureCoversPhaseAwareAndModelLifecycleMethods() async throws {
        let worker = RecordingConformanceWorker(requestID: "req-fixture")

        #expect(try await worker.abort(requestID: "req-fixture"))

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-fixture"
        let prefill = try await worker.prefill(request: prefillRequest)
        #expect(prefill.ok)
        #expect(prefill.decodeHandle == "decode-req-fixture")
        #expect(prefill.promptTokens == 1)
        #expect(prefill.appliedAcceleration.mode == .baseline)

        var decodeRequest = Melix_Worker_V1_DecodeRequest()
        decodeRequest.execution.id.requestID = "req-fixture"
        let decodeEvents = try await collectConformanceEvents(worker.decode(request: decodeRequest))
        #expect(decodeEvents.count == 1)

        var loadRequest = Melix_Worker_V1_LoadModelRequest()
        loadRequest.model.modelID = "melix-fixture"
        let load = try await worker.loadModel(request: loadRequest)
        #expect(load.ok)
        #expect(load.modelHandle == "melix-fixture::swift")

        let unload = try await worker.unloadModel(request: Melix_Worker_V1_UnloadModelRequest())
        #expect(unload.ok)
        let stats = try await worker.runtimeStats()
        #expect(!stats.hasStats)
    }

    private static func handler(worker: RecordingConformanceWorker) -> OpenAIHandler {
        let catalog = ModelCatalog(seedModels: [warmConformanceModel(id: "melix-dev-text")])
        let registry = WorkerRegistry(defaultTextClient: worker, modelCatalog: catalog)
        return OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: registry,
                abortRegistry: AbortRegistry(),
                modelCatalog: catalog
            ),
            workerRegistry: registry,
            translator: ChatRequestTranslator(requestIDGenerator: { worker.requestID }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )
    }

    private static func body(model: String = "melix-dev-text", extra: String) -> String {
        """
        {
          "model": "\(model)",
          "messages": [
            { "role": "user", "content": "Conformance check." }
          ],
          \(extra)
        }
        """
    }
}

private let weatherFunctionJSON = """
{
  "name": "get_weather",
  "description": "Get weather.",
  "parameters": {
    "type": "object",
    "properties": {
      "city": { "type": "string" }
    },
    "required": ["city"]
  }
}
"""

private let weatherToolJSON = """
{
  "type": "function",
  "function": \(weatherFunctionJSON)
}
"""

private func warmConformanceModel(id: String) -> Melix_Controlplane_V1_ModelSummary {
    var model = ModelCatalog.devTextModel()
    model.modelID = id
    model.state = .modelWarm
    return model
}

private func collectConformanceBody(_ body: HTTPBody) async throws -> String {
    switch body {
    case .data(let data):
        return try #require(String(data: data, encoding: .utf8))
    case .stream(let stream):
        var data = Data()
        for try await chunk in stream {
            data.append(chunk)
        }
        return try #require(String(data: data, encoding: .utf8))
    }
}

private func collectConformanceEvents(
    _ stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
) async throws -> [Melix_Worker_V1_ExecuteEvent] {
    var events: [Melix_Worker_V1_ExecuteEvent] = []
    for try await event in stream {
        events.append(event)
    }
    return events
}

private actor RecordingConformanceWorker:
    WorkerRoutingClient,
    PhaseAwareWorkerClientProtocol,
    RuntimeIntrospectingWorkerClientProtocol
{
    let requestID: String
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private let loadModelHandle: String
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?

    init(
        requestID: String,
        events: [Melix_Worker_V1_ExecuteEvent]? = nil,
        loadModelHandle: String = "melix-dev-text::swift"
    ) {
        self.requestID = requestID
        self.events = events ?? [
            makeCompletedEvent(requestID: requestID, seq: 1, finishReason: "stop", assistantText: "ok"),
        ]
        self.loadModelHandle = loadModelHandle
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        lastGenerateRequest = request
        let events = self.events
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func prefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        var response = Melix_Worker_V1_PrefillResponse()
        response.ok = true
        response.decodeHandle = "decode-\(request.execution.id.requestID)"
        response.promptTokens = 1
        response.appliedAcceleration.mode = .baseline
        return response
    }

    func decode(
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        let events = self.events
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = loadModelHandle == "melix-dev-text::swift" ? "\(request.model.modelID)::swift" : loadModelHandle
        return response
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        _ = request
        var response = Melix_Worker_V1_UnloadModelResponse()
        response.ok = true
        return response
    }

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        Melix_Worker_V1_GetRuntimeStatsResponse()
    }
}
