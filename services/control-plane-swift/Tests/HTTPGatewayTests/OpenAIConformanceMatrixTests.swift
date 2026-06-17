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
        let workerCanDispatch: Bool
        let model: Melix_Controlplane_V1_ModelSummary?
        let assertion: @Sendable (HTTPResponse, Melix_Worker_V1_GenerateRequest?) async throws -> OpenAIConformanceObservedStatus

        init(
            field: String,
            route: String,
            expectedBehavior: String,
            requestBody: String,
            workerCanDispatch: Bool = true,
            model: Melix_Controlplane_V1_ModelSummary? = nil,
            assertion: @escaping @Sendable (HTTPResponse, Melix_Worker_V1_GenerateRequest?) async throws -> OpenAIConformanceObservedStatus
        ) {
            self.field = field
            self.route = route
            self.expectedBehavior = expectedBehavior
            self.requestBody = requestBody
            self.workerCanDispatch = workerCanDispatch
            self.model = model
            self.assertion = assertion
        }
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
                let error = try await conformanceErrorPayload(from: response.body)
                #expect(response.statusCode == 400)
                #expect(error["code"] as? String == "invalid_generation_bounds")
                #expect(error["field"] as? String == "max_tokens,max_completion_tokens")
                #expect(error["phase"] as? String == "generation_bounds")
                #expect(error["bounds_rejection_reason"] as? String == "output_cap_conflict")
                #expect(request == nil)
                return .pass
            },
            MatrixRow(
                field: "best_of",
                route: "/v1/chat/completions -> typed unsupported-field rejection",
                expectedBehavior: "unsupported OpenAI fields return a typed payload naming the field and boundary phase.",
                requestBody: Self.body(extra: #""best_of": 2"#)
            ) { response, request in
                let error = try await conformanceErrorPayload(from: response.body)
                #expect(response.statusCode == 400)
                #expect(error["code"] as? String == "unsupported_request_field")
                #expect(error["field"] as? String == "best_of")
                #expect(error["phase"] as? String == "openai_request_validation")
                #expect(request == nil)
                return .pass
            },
            MatrixRow(
                field: "messages",
                route: "/v1/chat/completions -> typed schema rejection",
                expectedBehavior: "invalid schema payloads return a typed error naming the incompatible field and decode phase.",
                requestBody: """
                {
                  "model": "melix-dev-text",
                  "messages": "not-an-array"
                }
                """
            ) { response, request in
                let error = try await conformanceErrorPayload(from: response.body)
                #expect(response.statusCode == 400)
                #expect(error["code"] as? String == "invalid_request_schema")
                #expect(error["field"] as? String == "messages")
                #expect(error["phase"] as? String == "decode")
                #expect(request == nil)
                return .pass
            },
            MatrixRow(
                field: "backend_unavailable",
                route: "/v1/chat/completions -> typed backend-unavailable rejection",
                expectedBehavior: "worker unavailability returns a typed payload naming the dispatch phase before generation.",
                requestBody: Self.body(extra: #""max_completion_tokens": 8"#),
                workerCanDispatch: false
            ) { response, request in
                let error = try await conformanceErrorPayload(from: response.body)
                #expect(response.statusCode == 503)
                #expect(error["code"] as? String == "worker_unavailable")
                #expect(error["field"] as? String == "worker")
                #expect(error["phase"] as? String == "backend_dispatch")
                #expect(request == nil)
                return .pass
            },
            MatrixRow(
                field: "context_overflow",
                route: "/v1/chat/completions -> prompt-budget admission",
                expectedBehavior: "context overflow returns a typed prompt-budget payload with context metadata and no worker dispatch.",
                requestBody: """
                {
                  "model": "melix-dev-text",
                  "max_tokens": 4,
                  "messages": [
                    { "role": "user", "content": "one two three four five six seven eight nine ten eleven twelve" }
                  ]
                }
                """,
                model: {
                    var model = warmConformanceModel(id: "melix-dev-text")
                    model.maxContext = 8
                    return model
                }()
            ) { response, request in
                let error = try await conformanceErrorPayload(from: response.body)
                let metadata = try #require(error["prompt_token_metadata"] as? [String: Any])
                #expect(response.statusCode == 400)
                #expect(error["code"] as? String == "prompt_budget_exceeded")
                #expect(error["field"] as? String == "messages")
                #expect(error["phase"] as? String == "prompt_budget")
                #expect(metadata["context_window_tokens"] as? Int == 8)
                #expect(metadata["admission_phase"] as? String == "prompt_budget")
                #expect(metadata["prefill_started"] as? Bool == false)
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
                field: "seed,frequency_penalty",
                route: "/v1/chat/completions -> sampling passthrough",
                expectedBehavior: "seed and frequency_penalty forward into worker sampling and generation receipts.",
                requestBody: Self.body(extra: #""seed": 123, "frequency_penalty": 0.35"#)
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.sampling.seed == 123)
                #expect(generated.sampling.frequencyPenalty == Float(0.35))
                #expect(generated.execution.ext["melix.generation.seed"] == "123")
                #expect(generated.execution.ext["melix.generation.frequency_penalty"] == "0.35")
                return .pass
            },
            MatrixRow(
                field: "logprobs,top_logprobs",
                route: "/v1/chat/completions -> execution.ext effective receipt",
                expectedBehavior: "logprobs requests keep request-time receipts and surface backend token evidence at the output boundary.",
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
            let worker = RecordingConformanceWorker(
                requestID: "req-\(row.field)",
                canDispatchRequests: row.workerCanDispatch
            )
            let handler = Self.handler(worker: worker, model: row.model)
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

    @Test("conformance report summary counts every observed status in one pass")
    func conformanceReportSummaryCountsEveryObservedStatus() {
        let report = OpenAIConformanceReport(rows: [
            OpenAIConformanceRow(
                field: "pass",
                route: "/v1/chat/completions",
                expectedBehavior: "passes",
                observedStatus: .pass,
                observedReason: "ok"
            ),
            OpenAIConformanceRow(
                field: "fail",
                route: "/v1/chat/completions",
                expectedBehavior: "fails",
                observedStatus: .fail,
                observedReason: "mismatch"
            ),
            OpenAIConformanceRow(
                field: "skipped",
                route: "/v1/chat/completions",
                expectedBehavior: "skips",
                observedStatus: .skipped,
                observedReason: "deferred"
            ),
        ])

        #expect(report.summary.total == 3)
        #expect(report.summary.passed == 1)
        #expect(report.summary.failed == 1)
        #expect(report.summary.skipped == 1)
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

    @Test("backend token logprobs surface in non-streaming OpenAI chat response")
    func backendTokenLogprobsSurfaceInNonStreamingOpenAIChatResponse() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-output-logprobs",
            events: [
                makeTokenEvent(
                    requestID: "req-output-logprobs",
                    seq: 1,
                    text: "Alpha",
                    tokenIDs: [301],
                    tokenLogprobs: [-0.11]
                ),
                makeTokenEvent(
                    requestID: "req-output-logprobs",
                    seq: 2,
                    text: " Beta",
                    tokenIDs: [302],
                    tokenLogprobs: [-0.22]
                ),
                makeUsageEvent(requestID: "req-output-logprobs", seq: 3, promptTokens: 3, completionTokens: 2),
                makeCompletedEvent(
                    requestID: "req-output-logprobs",
                    seq: 4,
                    finishReason: "stop",
                    assistantText: "Alpha Beta"
                ),
            ]
        )
        let handler = Self.handler(worker: worker)
        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(extra: #""stream": false, "logprobs": true, "top_logprobs": 2"#).utf8)
            )
        )
        let body = try await collectConformanceBody(response.body)
        let data = try #require(body.data(using: .utf8))
        let payload = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let choice = try #require((payload["choices"] as? [[String: Any]])?.first)
        let logprobs = try #require(choice["logprobs"] as? [String: Any])
        let content = try #require(logprobs["content"] as? [[String: Any]])
        let firstTopLogprobs = try #require(content[0]["top_logprobs"] as? [[String: Any]])
        let secondTopLogprobs = try #require(content[1]["top_logprobs"] as? [[String: Any]])
        let request = try #require(await worker.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(choice["finish_reason"] as? String == "stop")
        #expect(content.count == 2)
        #expect(content[0]["token"] as? String == "Alpha")
        #expect(content[0]["logprob"] as? Double == -0.11)
        #expect(firstTopLogprobs.isEmpty)
        #expect(content[1]["token"] as? String == " Beta")
        #expect(content[1]["logprob"] as? Double == -0.22)
        #expect(secondTopLogprobs.isEmpty)
        #expect(logprobs["refusal"] is NSNull)
        #expect(request.execution.ext["melix.openai.logprobs.effective"] == "unsupported")
    }

    @Test("missing backend token logprobs do not synthesize OpenAI chat logprobs")
    func missingBackendTokenLogprobsDoNotSynthesizeOpenAIChatLogprobs() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-output-logprobs-missing",
            events: [
                makeTokenEvent(requestID: "req-output-logprobs-missing", seq: 1, text: "done"),
                makeCompletedEvent(
                    requestID: "req-output-logprobs-missing",
                    seq: 2,
                    finishReason: "stop",
                    assistantText: "done"
                ),
            ]
        )
        let handler = Self.handler(worker: worker)
        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(extra: #""stream": false, "logprobs": true"#).utf8)
            )
        )
        let body = try await collectConformanceBody(response.body)
        let data = try #require(body.data(using: .utf8))
        let payload = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let choice = try #require((payload["choices"] as? [[String: Any]])?.first)
        let request = try #require(await worker.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(choice["logprobs"] == nil)
        #expect(request.execution.ext["melix.openai.logprobs.effective"] == "unsupported")
    }

    @Test("unaligned backend token logprobs do not synthesize OpenAI chat logprobs")
    func unalignedBackendTokenLogprobsDoNotSynthesizeOpenAIChatLogprobs() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-output-logprobs-unaligned",
            events: [
                makeTokenEvent(
                    requestID: "req-output-logprobs-unaligned",
                    seq: 1,
                    text: "Alpha Beta",
                    tokenIDs: [301, 302],
                    tokenLogprobs: [-0.11, -0.22]
                ),
                makeCompletedEvent(
                    requestID: "req-output-logprobs-unaligned",
                    seq: 2,
                    finishReason: "stop",
                    assistantText: "Alpha Beta"
                ),
            ]
        )
        let handler = Self.handler(worker: worker)
        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(extra: #""stream": false, "logprobs": true"#).utf8)
            )
        )
        let body = try await collectConformanceBody(response.body)
        let data = try #require(body.data(using: .utf8))
        let payload = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let choice = try #require((payload["choices"] as? [[String: Any]])?.first)

        #expect(response.statusCode == 200)
        #expect(choice["logprobs"] == nil)
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

    @Test("streaming chat usage trailer uses OpenAI chunk shape")
    func streamingChatUsageTrailerUsesOpenAIChunkShape() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-stream-usage-trailer",
            events: [
                makeTokenEvent(requestID: "req-stream-usage-trailer", seq: 1, text: "done"),
                makeUsageEvent(requestID: "req-stream-usage-trailer", seq: 2, promptTokens: 5, completionTokens: 7),
                makeCompletedEvent(
                    requestID: "req-stream-usage-trailer",
                    seq: 3,
                    finishReason: "stop",
                    assistantText: "done"
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
                    Self.body(extra: #""stream": true, "stream_options": { "include_usage": true }"#).utf8
                )
            )
        )
        let payload = try await collectConformanceBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("event: usage") == false)
        #expect(payload.contains("\"object\":\"chat.completion.chunk\""))
        #expect(payload.contains("\"choices\":[]"))
        #expect(payload.contains("\"usage\""))
        #expect(payload.contains("\"prompt_tokens\":5"))
        #expect(payload.contains("\"completion_tokens\":7"))
        #expect(payload.contains("\"total_tokens\":12"))
        #expect(orderedConformanceRanges(in: payload, needles: [
            "\"content\":\"done\"",
            "\"usage\"",
            "\"finish_reason\":\"stop\"",
            "data: [DONE]",
        ]))
    }

    @Test("orphan tool-call markup is suppressed across streaming and non-streaming chat")
    func orphanToolCallMarkupIsSuppressedAcrossStreamingAndNonStreamingChat() async throws {
        let nonStreamWorker = RecordingConformanceWorker(
            requestID: "req-orphan-non-stream",
            events: [
                makeCompletedEvent(
                    requestID: "req-orphan-non-stream",
                    seq: 1,
                    finishReason: "stop",
                    assistantText: #"Visible before <tool_call>{"name":"ghost","arguments":{"q":"leak"}}"#
                ),
            ]
        )
        let nonStreamResponse = try await Self.handler(worker: nonStreamWorker).handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(extra: #""stream": false"#).utf8)
            )
        )
        let nonStreamPayload = try await collectConformanceBody(nonStreamResponse.body)

        #expect(nonStreamResponse.statusCode == 200)
        #expect(nonStreamPayload.contains(#""content":"Visible before ""#))
        #expect(nonStreamPayload.contains("<tool_call>") == false)
        #expect(nonStreamPayload.contains("\"ghost\"") == false)

        let streamWorker = RecordingConformanceWorker(
            requestID: "req-orphan-stream",
            events: [
                makeTokenEvent(requestID: "req-orphan-stream", seq: 1, text: "stream visible "),
                makeTokenEvent(requestID: "req-orphan-stream", seq: 2, text: "<|tool_"),
                makeTokenEvent(
                    requestID: "req-orphan-stream",
                    seq: 3,
                    text: #"call>call:terminal.execute{"command":"pwd"}"#
                ),
                makeCompletedEvent(
                    requestID: "req-orphan-stream",
                    seq: 4,
                    finishReason: "stop",
                    assistantText: #"stream visible <|tool_call>call:terminal.execute{"command":"pwd"}"#
                ),
            ]
        )
        let streamResponse = try await Self.handler(worker: streamWorker).handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(Self.body(extra: #""stream": true"#).utf8)
            )
        )
        let streamPayload = try await collectConformanceBody(streamResponse.body)

        #expect(streamResponse.statusCode == 200)
        #expect(streamPayload.contains(#""content":"stream visible ""#))
        #expect(streamPayload.contains("<|tool_") == false)
        #expect(streamPayload.contains("<|tool_call>") == false)
        #expect(streamPayload.contains("terminal.execute") == false)
        #expect(streamPayload.contains("data: [DONE]"))
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

    private static func handler(
        worker: RecordingConformanceWorker,
        model: Melix_Controlplane_V1_ModelSummary? = nil
    ) -> OpenAIHandler {
        let catalog = ModelCatalog(seedModels: [model ?? warmConformanceModel(id: "melix-dev-text")])
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

private func conformanceErrorPayload(from body: HTTPBody) async throws -> [String: Any] {
    let payload = try await collectConformanceBody(body)
    let data = try #require(payload.data(using: .utf8))
    let object = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
    return try #require(object["error"] as? [String: Any])
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

private func orderedConformanceRanges(in payload: String, needles: [String]) -> Bool {
    var cursor = payload.startIndex
    for needle in needles {
        guard let range = payload[cursor...].range(of: needle) else {
            return false
        }
        cursor = range.upperBound
    }
    return true
}

private actor RecordingConformanceWorker:
    WorkerRoutingClient,
    PhaseAwareWorkerClientProtocol,
    RuntimeIntrospectingWorkerClientProtocol
{
    let requestID: String
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private let loadModelHandle: String
    private let dispatchAvailable: Bool
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?

    init(
        requestID: String,
        events: [Melix_Worker_V1_ExecuteEvent]? = nil,
        loadModelHandle: String = "melix-dev-text::swift",
        canDispatchRequests: Bool = true
    ) {
        self.requestID = requestID
        self.events = events ?? [
            makeCompletedEvent(requestID: requestID, seq: 1, finishReason: "stop", assistantText: "ok"),
        ]
        self.loadModelHandle = loadModelHandle
        self.dispatchAvailable = canDispatchRequests
    }

    func canDispatchRequests() async -> Bool {
        dispatchAvailable
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
