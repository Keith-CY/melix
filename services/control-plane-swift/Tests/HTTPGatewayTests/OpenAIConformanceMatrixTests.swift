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
        let events: [Melix_Worker_V1_ExecuteEvent]?
        let assertion: @Sendable (HTTPResponse, Melix_Worker_V1_GenerateRequest?) async throws -> OpenAIConformanceObservedStatus

        init(
            field: String,
            route: String,
            expectedBehavior: String,
            requestBody: String,
            workerCanDispatch: Bool = true,
            model: Melix_Controlplane_V1_ModelSummary? = nil,
            events: [Melix_Worker_V1_ExecuteEvent]? = nil,
            assertion: @escaping @Sendable (HTTPResponse, Melix_Worker_V1_GenerateRequest?) async throws -> OpenAIConformanceObservedStatus
        ) {
            self.field = field
            self.route = route
            self.expectedBehavior = expectedBehavior
            self.requestBody = requestBody
            self.workerCanDispatch = workerCanDispatch
            self.model = model
            self.events = events
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
                field: "response_format.json_schema=null",
                route: "/v1/chat/completions -> typed structured-output rejection",
                expectedBehavior: "explicit null json_schema is rejected as a missing schema before worker dispatch.",
                requestBody: """
                {
                  "model": "melix-dev-text",
                  "response_format": {
                    "type": "json_schema",
                    "json_schema": null
                  },
                  "messages": [
                    { "role": "user", "content": "Return JSON." }
                  ]
                }
                """
            ) { response, request in
                let error = try await conformanceErrorPayload(from: response.body)
                #expect(response.statusCode == 400)
                #expect(error["code"] as? String == "invalid_argument")
                #expect(error["field"] as? String == "response_format")
                #expect(error["phase"] as? String == "structured_output")
                #expect(error["structured_output_error"] as? String == "missing_json_schema_definition")
                #expect(request == nil)
                return .pass
            },
            MatrixRow(
                field: "response_format.json_schema=sampler_enforced",
                route: "/v1/chat/completions -> worker structured-output sampler contract",
                expectedBehavior: "Supported JSON Schema is forwarded as an enforceable worker grammar and schema-valid output crosses the response boundary.",
                requestBody: """
                {
                  "model": "melix-dev-text",
                  "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                      "name": "answer",
                      "strict": true,
                      "schema": {
                        "type": "object",
                        "required": ["answer"],
                        "additionalProperties": false,
                        "properties": {
                          "answer": { "type": "string", "enum": ["yes", "no"] }
                        }
                      }
                    }
                  },
                  "messages": [
                    { "role": "user", "content": "Return JSON." }
                  ]
                }
                """,
                events: [
                    makeCompletedEvent(
                        requestID: "req-response_format.json_schema=sampler_enforced",
                        seq: 1,
                        finishReason: "stop",
                        assistantText: #"{"answer":"yes"}"#
                    ),
                ]
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.execution.ext["melix.structured_output.mode"] == "json_schema")
                #expect(generated.execution.ext["melix.structured_output.strict"] == "true")
                #expect(generated.execution.ext["melix.structured_output.schema_json"]?.contains(#""required":["answer"]"#) == true)
                return .pass
            },
            MatrixRow(
                field: "response_format.json_schema=worker_typed_refusal",
                route: "/v1/chat/completions -> typed worker sampler refusal",
                expectedBehavior: "A worker that cannot enforce the schema returns a typed structured-output error with sampler details.",
                requestBody: """
                {
                  "model": "melix-dev-text",
                  "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                      "name": "answer",
                      "strict": true,
                      "schema": {
                        "type": "object",
                        "required": ["answer"],
                        "additionalProperties": false,
                        "properties": {
                          "answer": { "type": "string", "enum": ["yes", "no"] }
                        }
                      }
                    }
                  },
                  "messages": [
                    { "role": "user", "content": "Return JSON." }
                  ]
                }
                """,
                events: [
                    makeConformanceErrorEvent(
                        requestID: "req-response_format.json_schema=worker_typed_refusal",
                        code: "unsupported_structured_output",
                        message: "The runtime cannot enforce this JSON schema.",
                        details: [
                            "mode": "json_schema",
                            "enforcement": "sampler",
                            "reason": "json_schema_unsupported_keyword",
                        ]
                    ),
                ]
            ) { response, request in
                let error = try await conformanceErrorPayload(from: response.body)
                let details = try #require(error["details"] as? [String: Any])
                let generated = try #require(request)
                #expect(response.statusCode == 500)
                #expect(error["code"] as? String == "unsupported_structured_output")
                #expect(details["mode"] as? String == "json_schema")
                #expect(details["enforcement"] as? String == "sampler")
                #expect(details["reason"] as? String == "json_schema_unsupported_keyword")
                #expect(generated.execution.ext["melix.structured_output.mode"] == "json_schema")
                #expect(generated.execution.ext["melix.structured_output.schema_json"]?.isEmpty == false)
                return .pass
            },
            MatrixRow(
                field: "tool_choice.required=sampler_wire",
                route: "/v1/chat/completions -> required tool sampler grammar",
                expectedBehavior: "Required tool selection forwards a token-zero wire descriptor and declared argument schema to the worker.",
                requestBody: Self.body(
                    extra: #""tools": [\#(weatherToolJSON)], "tool_choice": "required""#
                ),
                events: [
                    makeToolCallEvent(
                        requestID: "req-tool_choice.required=sampler_wire",
                        seq: 1,
                        callID: "tool-required",
                        toolName: "get_weather",
                        argumentsJSONFragment: #"{"city":"Tokyo"}"#
                    ),
                    makeCompletedEvent(
                        requestID: "req-tool_choice.required=sampler_wire",
                        seq: 2,
                        finishReason: "tool_calls",
                        assistantText: ""
                    ),
                ]
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.execution.toolConfig.toolChoice == "required")
                #expect(generated.execution.ext["melix.compat.tool_choice_resolved"] == "required")
                #expect(generated.execution.ext["melix.tool_wire.trigger"] == "<tool_call>")
                #expect(generated.execution.ext["melix.tool_wire.argument_style"] == "xml_parameters")
                return .pass
            },
            MatrixRow(
                field: "tool_choice.named=sampler_wire",
                route: "/v1/chat/completions -> named tool sampler grammar",
                expectedBehavior: "Named tool selection forwards a grammar contract that can admit only the selected declared tool.",
                requestBody: Self.body(
                    extra: #""tools": [\#(weatherToolJSON)], "tool_choice": { "type": "function", "function": { "name": "get_weather" } }"#
                ),
                events: [
                    makeToolCallEvent(
                        requestID: "req-tool_choice.named=sampler_wire",
                        seq: 1,
                        callID: "tool-named",
                        toolName: "get_weather",
                        argumentsJSONFragment: #"{"city":"Tokyo"}"#
                    ),
                    makeCompletedEvent(
                        requestID: "req-tool_choice.named=sampler_wire",
                        seq: 2,
                        finishReason: "tool_calls",
                        assistantText: ""
                    ),
                ]
            ) { response, request in
                #expect(response.statusCode == 200)
                let generated = try #require(request)
                #expect(generated.execution.toolConfig.toolChoice.contains("get_weather"))
                #expect(generated.execution.ext["melix.compat.tool_choice_resolved"]?.contains("get_weather") == true)
                #expect(generated.execution.ext["melix.tool_wire.trigger"] == "<tool_call>")
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
                requestBody: Self.body(extra: #""functions": [\#(weatherFunctionJSON)], "function_call": { "name": "get_weather" }"#),
                events: [
                    makeToolCallEvent(
                        requestID: "req-function_call",
                        seq: 1,
                        callID: "tool-1",
                        toolName: "get_weather",
                        argumentsJSONFragment: #"{"city":"Tokyo"}"#
                    ),
                    makeCompletedEvent(
                        requestID: "req-function_call",
                        seq: 2,
                        finishReason: "tool_calls",
                        assistantText: ""
                    ),
                ]
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
                events: row.events,
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
        #expect(reportJSON.contains("\"field\":\"response_format.json_schema=null\""))
        #expect(reportJSON.contains("\"field\":\"response_format.json_schema=sampler_enforced\""))
        #expect(reportJSON.contains("\"field\":\"response_format.json_schema=worker_typed_refusal\""))
        #expect(reportJSON.contains("\"field\":\"tool_choice.required=sampler_wire\""))
        #expect(reportJSON.contains("\"field\":\"tool_choice.named=sampler_wire\""))
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

    @Test("conformance report rows can carry parser policy fixture metadata")
    func conformanceReportRowsCanCarryParserPolicyFixtureMetadata() throws {
        let row = OpenAIConformanceRow(
            field: "tool_call_parser_policy:qwen3moe:qwen:qwen_xml_tool_call",
            route: "/v1/chat/completions -> parser policy evidence",
            expectedBehavior: "parser policy fixtures expose model family, parser mode, tag dialect, and resolved parser receipt evidence.",
            observedStatus: .pass,
            observedReason: "parser_policy=resolved",
            modelFamily: "qwen3moe",
            parserMode: "qwen",
            tagDialect: "qwen_xml_tool_call",
            requestedParser: "qwen",
            resolvedParser: "qwen",
            parserFallbackMode: "xml",
            parserRefusalReason: ""
        )
        let reportJSON = try OpenAIConformanceReport(rows: [row]).jsonString()

        #expect(reportJSON.contains(#""model_family":"qwen3moe""#))
        #expect(reportJSON.contains(#""parser_mode":"qwen""#))
        #expect(reportJSON.contains(#""tag_dialect":"qwen_xml_tool_call""#))
        #expect(reportJSON.contains(#""requested_parser":"qwen""#))
        #expect(reportJSON.contains(#""resolved_parser":"qwen""#))
        #expect(reportJSON.contains(#""parser_fallback_mode":"xml""#))
        #expect(reportJSON.contains(#""parser_refusal_reason":"""#))
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

    @Test("partially missing backend token logprobs do not emit partial OpenAI chat logprobs")
    func partiallyMissingBackendTokenLogprobsDoNotEmitPartialOpenAIChatLogprobs() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-output-logprobs-partial",
            events: [
                makeTokenEvent(
                    requestID: "req-output-logprobs-partial",
                    seq: 1,
                    text: "Alpha",
                    tokenIDs: [301],
                    tokenLogprobs: [-0.11]
                ),
                makeTokenEvent(requestID: "req-output-logprobs-partial", seq: 2, text: " Beta"),
                makeCompletedEvent(
                    requestID: "req-output-logprobs-partial",
                    seq: 3,
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

    @Test("empty backend token evidence does not emit partial OpenAI chat logprobs")
    func emptyBackendTokenEvidenceDoesNotEmitPartialOpenAIChatLogprobs() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-output-logprobs-empty-evidence",
            events: [
                makeTokenEvent(
                    requestID: "req-output-logprobs-empty-evidence",
                    seq: 1,
                    text: "",
                    tokenIDs: [300],
                    tokenLogprobs: [-0.01]
                ),
                makeTokenEvent(
                    requestID: "req-output-logprobs-empty-evidence",
                    seq: 2,
                    text: "Alpha",
                    tokenIDs: [301],
                    tokenLogprobs: [-0.11]
                ),
                makeCompletedEvent(
                    requestID: "req-output-logprobs-empty-evidence",
                    seq: 3,
                    finishReason: "stop",
                    assistantText: "Alpha"
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
        #expect(payload.contains("event: message") == false)
        #expect(payload.contains("\"tool_calls\""))
        #expect(payload.contains("\"name\":\"get_weather\""))
        #expect(payload.contains("\"arguments\":\"{\\\"city\\\":\\\"Tokyo\\\"}\""))
        #expect(payload.contains("\"finish_reason\":\"tool_calls\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("named tool_choice streams once matching tool call satisfies contract")
    func namedToolChoiceStreamsOnceMatchingToolCallSatisfiesContract() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-named-tool-choice-early-flush",
            events: [
                makeTokenEvent(
                    requestID: "req-named-tool-choice-early-flush",
                    seq: 1,
                    text: "buffered before tool"
                ),
                makeToolCallEvent(
                    requestID: "req-named-tool-choice-early-flush",
                    seq: 2,
                    callID: "tool-1",
                    toolName: "get_weather",
                    argumentsJSONFragment: #"{"city":"Tokyo"}"#,
                    fragmentIndex: 0
                ),
            ],
            heldCompletionEvent: makeCompletedEvent(
                requestID: "req-named-tool-choice-early-flush",
                seq: 3,
                finishReason: "tool_calls",
                assistantText: ""
            )
        )
        let response = try await Self.handler(
            worker: worker,
            requestID: "req-named-tool-choice-early-flush"
        ).handle(
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

        #expect(response.statusCode == 200)
        let capture = StreamPayloadCapture()
        let collectTask = Task {
            try await collectConformanceBody(response.body, capture: capture)
        }

        try await waitForConformancePayload(capture) { payload in
            payload.contains("\"name\":\"get_weather\"")
        }
        let payloadBeforeCompletion = await capture.payload()
        #expect(payloadBeforeCompletion.contains("\"name\":\"get_weather\""))
        #expect(payloadBeforeCompletion.contains("\"finish_reason\":\"tool_calls\"") == false)
        #expect(payloadBeforeCompletion.contains("data: [DONE]") == false)

        await worker.completeHeldStream()
        let finalPayload = try await collectTask.value
        #expect(finalPayload.contains("\"finish_reason\":\"tool_calls\""))
        #expect(finalPayload.contains("data: [DONE]"))
    }

    @Test("required tool_choice failures return typed errors without wire leaks")
    func requiredToolChoiceFailuresReturnTypedErrorsWithoutWireLeaks() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-required-tool-choice-failure",
            events: [
                makeTokenEvent(
                    requestID: "req-required-tool-choice-failure",
                    seq: 1,
                    text: "Plain answer with melix.compat.tool_choice_resolved and parser_mode"
                ),
                makeCompletedEvent(
                    requestID: "req-required-tool-choice-failure",
                    seq: 2,
                    finishReason: "stop",
                    assistantText: #"Plain answer <tool_call>{"name":"ghost","arguments":{}}</tool_call>"#
                ),
            ]
        )
        let response = try await Self.handler(worker: worker).handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(
                    Self.body(
                        extra: #""tools": [\#(weatherToolJSON)], "tool_choice": "required""#
                    ).utf8
                )
            )
        )
        let payload = try await collectConformanceBody(response.body)
        let object = try #require(try JSONSerialization.jsonObject(with: Data(payload.utf8)) as? [String: Any])
        let error = try #require(object["error"] as? [String: Any])
        let request = try #require(await worker.lastGenerateRequest)

        #expect(response.statusCode == 502)
        #expect(request.execution.toolConfig.toolChoice == "required")
        #expect(error["code"] as? String == "tool_choice_not_satisfied")
        #expect(error["field"] as? String == "tool_choice")
        #expect(error["phase"] as? String == "response_finalization")
        #expect(error["requested_tool_choice"] as? String == "required")
        #expect(error["observed_tool_calls"] as? [String] == [])
        #expect(payload.contains("Plain answer") == false)
        expectNoOpenAIWireLeaks(payload)
    }

    @Test("named tool_choice mismatches stream typed errors without wire leaks")
    func namedToolChoiceMismatchesStreamTypedErrorsWithoutWireLeaks() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-named-tool-choice-mismatch",
            events: [
                makeToolCallEvent(
                    requestID: "req-named-tool-choice-mismatch",
                    seq: 1,
                    callID: "tool-1",
                    toolName: "search_web",
                    argumentsJSONFragment: #"{"q":"Tokyo weather"}"#,
                    fragmentIndex: 1
                ),
                makeCompletedEvent(
                    requestID: "req-named-tool-choice-mismatch",
                    seq: 2,
                    finishReason: "tool_calls",
                    assistantText: ""
                ),
            ]
        )
        let response = try await Self.handler(worker: worker).handle(
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
        let records = parseSSERecords(payload)
        let errorRecord = try #require(records.first { $0.event == "error" })
        let error = try #require(try JSONSerialization.jsonObject(with: Data(errorRecord.data.utf8)) as? [String: Any])
        let details = try #require(error["details"] as? [String: Any])
        let request = try #require(await worker.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.execution.toolConfig.toolChoice.contains("get_weather"))
        #expect(error["code"] as? String == "tool_choice_not_satisfied")
        #expect(details["field"] as? String == "tool_choice")
        #expect(details["phase"] as? String == "response_finalization")
        #expect(details["requested_tool_choice"] as? String == "get_weather")
        #expect(details["observed_tool_calls"] as? String == "search_web")
        #expect(records.filter { $0.event == nil && $0.data != "[DONE]" }.isEmpty)
        #expect(payload.contains("\"name\":\"search_web\"") == false)
        #expect(payload.contains("data: [DONE]"))
        expectNoOpenAIWireLeaks(payload)
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
            "\"finish_reason\":\"stop\"",
            "\"usage\"",
            "data: [DONE]",
        ]))
    }

    @Test("streaming chat heartbeat emits parseable liveness envelope")
    func streamingChatHeartbeatEmitsParseableLivenessEnvelope() async throws {
        let worker = RecordingConformanceWorker(
            requestID: "req-stream-heartbeat",
            events: [
                makeTokenEvent(requestID: "req-stream-heartbeat", seq: 1, text: "working"),
                makeHeartbeatEvent(requestID: "req-stream-heartbeat", seq: 2, unixMs: 12_345),
                makeUsageEvent(requestID: "req-stream-heartbeat", seq: 3, promptTokens: 4, completionTokens: 1),
                makeCompletedEvent(
                    requestID: "req-stream-heartbeat",
                    seq: 4,
                    finishReason: "stop",
                    assistantText: "working"
                ),
            ]
        )
        let response = try await Self.handler(worker: worker).handle(
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
        let records = parseSSERecords(payload)
        let eventOrder = records.map { $0.event ?? "data" }.joined(separator: ",")
        let heartbeatRecord = try #require(records.first { $0.event == "heartbeat" })
        let heartbeatPayload = try #require(
            try JSONSerialization.jsonObject(with: Data(heartbeatRecord.data.utf8)) as? [String: Any]
        )

        #expect(response.statusCode == 200)
        #expect(heartbeatPayload["request_id"] as? String == "req-stream-heartbeat")
        #expect(heartbeatPayload["unix_ms"] as? Int == 12_345)
        #expect(records.filter { $0.event == "heartbeat" }.count == 1)
        #expect(records.filter { $0.event == nil && $0.data.contains(#""unix_ms""#) }.isEmpty)
        #expect(eventOrder == "data,heartbeat,data,data,data")
        #expect(orderedConformanceRanges(in: payload, needles: [
            "\"content\":\"working\"",
            "event: heartbeat",
            "\"finish_reason\":\"stop\"",
            "\"usage\"",
            "data: [DONE]",
        ]))

        let report = OpenAIConformanceReport(rows: [
            OpenAIConformanceRow(
                field: "worker heartbeat event",
                route: "/v1/chat/completions -> SSE liveness",
                expectedBehavior: "worker heartbeat events emit a named, JSON-parseable SSE heartbeat envelope before terminal chunks.",
                observedStatus: eventOrder == "data,heartbeat,data,data,data" ? .pass : .fail,
                observedReason: "chunk_order=\(eventOrder)"
            ),
        ])
        #expect(report.summary.passed == 1)
        #expect(report.summary.failed == 0)
        #expect(try report.jsonString().contains("\"worker heartbeat event\""))
    }

    @Test("streaming prefill progress stays invisible unless opted in")
    func streamingPrefillProgressStaysInvisibleUnlessOptedIn() async throws {
        func prefillEvents(requestID: String) -> [Melix_Worker_V1_ExecuteEvent] {
            [
                makePrefillStartedEvent(requestID: requestID, seq: 1, inputTokens: 6),
                makePrefillProgressEvent(requestID: requestID, seq: 2, processedTokens: 3, totalTokens: 6),
                makeTokenEvent(requestID: requestID, seq: 3, text: "hi"),
                makeUsageEvent(requestID: requestID, seq: 4, promptTokens: 6, completionTokens: 1),
                makeCompletedEvent(requestID: requestID, seq: 5, finishReason: "stop", assistantText: "hi"),
            ]
        }
        func chunkOrder(_ payload: String) -> String {
            parseSSERecords(payload).map { $0.event ?? "data" }.joined(separator: ",")
        }
        func expectStrictDataPurity(_ payload: String) throws {
            for record in parseSSERecords(payload) where record.event == nil {
                if record.data == "[DONE]" {
                    continue
                }
                let object = try JSONSerialization.jsonObject(with: Data(record.data.utf8))
                let json = try #require(object as? [String: Any])
                #expect(json["object"] as? String == "chat.completion.chunk")
            }
        }

        let defaultWorker = RecordingConformanceWorker(
            requestID: "req-stream-pf-default",
            events: prefillEvents(requestID: "req-stream-pf-default")
        )
        let defaultResponse = try await Self.handler(worker: defaultWorker).handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(
                    Self.body(extra: #""stream": true, "stream_options": { "include_usage": true }"#).utf8
                )
            )
        )
        let defaultPayload = try await collectConformanceBody(defaultResponse.body)

        #expect(defaultResponse.statusCode == 200)
        #expect(defaultPayload.contains("prefill_progress") == false)
        #expect(defaultPayload.contains("\"processed_tokens\"") == false)
        try expectStrictDataPurity(defaultPayload)
        let defaultOrder = chunkOrder(defaultPayload)
        #expect(defaultOrder == "data,data,data,data")

        let optInWorker = RecordingConformanceWorker(
            requestID: "req-stream-pf-opt-in",
            events: prefillEvents(requestID: "req-stream-pf-opt-in")
        )
        let optInResponse = try await Self.handler(worker: optInWorker).handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: Data(
                    Self.body(
                        extra: #""stream": true, "stream_options": { "include_usage": true, "include_prefill_progress": true }"#
                    ).utf8
                )
            )
        )
        let optInPayload = try await collectConformanceBody(optInResponse.body)
        let optInRequest = try #require(await optInWorker.lastGenerateRequest)

        #expect(optInResponse.statusCode == 200)
        #expect(optInRequest.execution.ext["melix.stream.include_prefill_progress"] == "true")
        #expect(optInPayload.contains("event: prefill_progress"))
        #expect(optInPayload.contains("\"phase\":\"started\""))
        #expect(optInPayload.contains("\"input_tokens\":6"))
        #expect(optInPayload.contains("\"phase\":\"progress\""))
        #expect(optInPayload.contains("\"processed_tokens\":3"))
        try expectStrictDataPurity(optInPayload)
        let optInOrder = chunkOrder(optInPayload)
        #expect(optInOrder == "prefill_progress,prefill_progress,data,data,data,data")

        let report = OpenAIConformanceReport(rows: [
            OpenAIConformanceRow(
                field: "stream_options.include_prefill_progress=absent",
                route: "/v1/chat/completions -> SSE chunk order",
                expectedBehavior: "prefill telemetry is dropped; only OpenAI data chunks reach the stream.",
                observedStatus: defaultOrder == "data,data,data,data" ? .pass : .fail,
                observedReason: "chunk_order=\(defaultOrder)"
            ),
            OpenAIConformanceRow(
                field: "stream_options.include_prefill_progress=true",
                route: "/v1/chat/completions -> SSE chunk order",
                expectedBehavior: "prefill telemetry uses the named prefill_progress event and stays out of unnamed data chunks.",
                observedStatus: optInOrder == "prefill_progress,prefill_progress,data,data,data,data" ? .pass : .fail,
                observedReason: "chunk_order=\(optInOrder)"
            ),
        ])
        #expect(report.summary.passed == 2)
        #expect(report.summary.failed == 0)
        let reportJSON = try report.jsonString()
        #expect(reportJSON.contains("\"chunk_order=data,data,data,data\""))
        #expect(reportJSON.contains("\"chunk_order=prefill_progress,prefill_progress,data,data,data,data\""))
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

    @Test("tool-call parser policy fixtures carry parser and dialect evidence")
    func toolCallParserPolicyFixturesCarryParserAndDialectEvidence() async throws {
        struct Fixture: Sendable {
            let scenario: String
            let modelFamily: String
            let parserMode: String
            let tagDialect: String
            let stream: Bool
        }

        let fixtures = [
            Fixture(
                scenario: "non_stream_unclosed_tool_call",
                modelFamily: "qwen3moe",
                parserMode: "qwen",
                tagDialect: "qwen_xml_tool_call",
                stream: false
            ),
            Fixture(
                scenario: "stream_split_tool_call_marker",
                modelFamily: "qwen3moe",
                parserMode: "qwen",
                tagDialect: "qwen_pipe_tool_call",
                stream: true
            ),
        ]
        var reportRows: [OpenAIConformanceRow] = []

        for fixture in fixtures {
            let requestID = "req-parser-policy-\(fixture.scenario)"
            let worker = RecordingConformanceWorker(
                requestID: requestID,
                events: parserPolicyEvents(requestID: requestID, stream: fixture.stream)
            )
            var model = warmConformanceModel(id: "melix-dev-text")
            model.settings.ext["text_family_id"] = fixture.modelFamily

            let response = try await Self.handler(worker: worker, model: model).handle(
                HTTPRequest(
                    method: .post,
                    path: "/v1/chat/completions",
                    headers: ["content-type": "application/json"],
                    body: Data(Self.body(extra: parserPolicyExtra(stream: fixture.stream, parserMode: fixture.parserMode)).utf8)
                )
            )
            let payload = try await collectConformanceBody(response.body)
            let request = try #require(await worker.lastGenerateRequest)
            let ext = request.execution.ext

            #expect(response.statusCode == 200)
            #expect(ext["melix.tool_parser.mode"] == fixture.parserMode)
            #expect(ext["melix.tool_parser.source"] == "request")
            #expect(ext["melix.tool_parser.namespaces"] == "tools.search")
            #expect(ext["melix.tool_parser.fallback_mode"] == "xml")
            #expect(ext["melix.compat.requested_parser"] == fixture.parserMode)
            #expect(ext["melix.compat.resolved_parser"] == fixture.parserMode)
            #expect(ext["melix.compat.parser_fallback_mode"] == "xml")
            #expect(ext["melix.compat.parser_refusal_reason"] == "")
            #expect(payload.contains(#""tool_calls""#) == false)
            #expect(payload.contains("ghost") == false)
            expectNoOpenAIWireLeaks(payload)

            let rowPassed = response.statusCode == 200
                && ext["melix.compat.requested_parser"] == fixture.parserMode
                && ext["melix.compat.resolved_parser"] == fixture.parserMode
                && ext["melix.compat.parser_fallback_mode"] == "xml"
                && !payload.contains(#""tool_calls""#)
                && !payload.contains("ghost")
            reportRows.append(
                OpenAIConformanceRow(
                    field: "tool_call_parser_policy:\(fixture.modelFamily):\(fixture.parserMode):\(fixture.tagDialect):\(fixture.scenario)",
                    route: "/v1/chat/completions -> parser policy evidence",
                    expectedBehavior: "Malformed backend tool-call text is suppressed while parser policy receipts identify the requested and resolved parser.",
                    observedStatus: rowPassed ? .pass : .fail,
                    observedReason: "scenario=\(fixture.scenario);status=\(response.statusCode)",
                    modelFamily: model.settings.ext["text_family_id"],
                    parserMode: ext["melix.tool_parser.mode"],
                    tagDialect: fixture.tagDialect,
                    requestedParser: ext["melix.compat.requested_parser"],
                    resolvedParser: ext["melix.compat.resolved_parser"],
                    parserFallbackMode: ext["melix.compat.parser_fallback_mode"],
                    parserRefusalReason: ext["melix.compat.parser_refusal_reason"]
                )
            )
        }

        let report = OpenAIConformanceReport(rows: reportRows)
        #expect(report.summary.passed == fixtures.count)
        #expect(report.summary.failed == 0)
        let reportJSON = try report.jsonString()
        #expect(reportJSON.contains(#""model_family":"qwen3moe""#))
        #expect(reportJSON.contains(#""parser_mode":"qwen""#))
        #expect(reportJSON.contains(#""tag_dialect":"qwen_xml_tool_call""#))
        #expect(reportJSON.contains(#""tag_dialect":"qwen_pipe_tool_call""#))
        #expect(reportJSON.contains(#""requested_parser":"qwen""#))
        #expect(reportJSON.contains(#""resolved_parser":"qwen""#))
        #expect(reportJSON.contains(#""parser_fallback_mode":"xml""#))
        #expect(reportJSON.contains(#""parser_refusal_reason":"""#))
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
        handler(worker: worker, requestID: worker.requestID, model: model)
    }

    private static func handler(
        worker: any WorkerRoutingClient & PhaseAwareWorkerClientProtocol & RuntimeIntrospectingWorkerClientProtocol,
        requestID: String? = nil,
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
            translator: ChatRequestTranslator(requestIDGenerator: { requestID ?? "req-conformance" }),
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
    try await collectConformanceBody(body, capture: nil)
}

private func collectConformanceBody(_ body: HTTPBody, capture: StreamPayloadCapture?) async throws -> String {
    switch body {
    case .data(let data):
        return try #require(String(data: data, encoding: .utf8))
    case .stream(let stream):
        var data = Data()
        for try await chunk in stream {
            if let text = String(data: chunk, encoding: .utf8) {
                await capture?.append(text)
            }
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

private func makeConformanceErrorEvent(
    requestID: String,
    code: String,
    message: String,
    details: [String: String]
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.seq = 1
    event.executionKind = "generate"
    event.phase = .executionFailed
    event.error.error.code = code
    event.error.error.message = message
    event.error.error.details = details
    return event
}

private actor StreamPayloadCapture {
    private var text = ""

    func append(_ chunk: String) {
        text += chunk
    }

    func payload() -> String {
        text
    }
}

private func waitForConformancePayload(
    _ capture: StreamPayloadCapture,
    timeout: Duration = .milliseconds(500),
    predicate: @escaping @Sendable (String) -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await predicate(capture.payload()) {
            return
        }
        try await Task.sleep(for: .milliseconds(10))
    }
    Issue.record("timed out waiting for streaming payload")
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

private func parserPolicyExtra(stream: Bool, parserMode: String) -> String {
    """
    "stream": \(stream ? "true" : "false"),
    "tool_parser": {
      "mode": "\(parserMode)",
      "namespaces": ["tools.search"],
      "xml_fallback": true
    },
    "tools": [\(weatherToolJSON)],
    "tool_choice": "auto"
    """
}

private func parserPolicyEvents(requestID: String, stream: Bool) -> [Melix_Worker_V1_ExecuteEvent] {
    if stream {
        return [
            makeTokenEvent(requestID: requestID, seq: 1, text: "Visible before "),
            makeTokenEvent(requestID: requestID, seq: 2, text: "<|tool_"),
            makeTokenEvent(
                requestID: requestID,
                seq: 3,
                text: #"call>{"name":"ghost","arguments":{"q":"leak"}}"#
            ),
            makeCompletedEvent(
                requestID: requestID,
                seq: 4,
                finishReason: "stop",
                assistantText: #"Visible before <|tool_call>{"name":"ghost","arguments":{"q":"leak"}}"#
            ),
        ]
    }

    return [
        makeCompletedEvent(
            requestID: requestID,
            seq: 1,
            finishReason: "stop",
            assistantText: #"Visible before <tool_call>{"name":"ghost","arguments":{"q":"leak"}}"#
        ),
    ]
}

private func expectNoOpenAIWireLeaks(_ payload: String) {
    for needle in [
        "melix.compat",
        "melix.tool_parser",
        "melix.openai",
        "\"melix\"",
        "\"assistant_text\"",
        "parser_mode",
        "parser_namespaces",
        "parser_fallback_mode",
        "mcp_source_ids",
        "internal_routing",
        "<tool_call>",
        "<|tool_call>",
    ] {
        #expect(payload.contains(needle) == false, "wire leak: \(needle)")
    }
}

private actor RecordingConformanceWorker:
    WorkerRoutingClient,
    PhaseAwareWorkerClientProtocol,
    RuntimeIntrospectingWorkerClientProtocol
{
    let requestID: String
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private let heldCompletionEvent: Melix_Worker_V1_ExecuteEvent?
    private let loadModelHandle: String
    private let dispatchAvailable: Bool
    private var heldContinuation: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation?
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?

    init(
        requestID: String,
        events: [Melix_Worker_V1_ExecuteEvent]? = nil,
        heldCompletionEvent: Melix_Worker_V1_ExecuteEvent? = nil,
        loadModelHandle: String = "melix-dev-text::swift",
        canDispatchRequests: Bool = true
    ) {
        self.requestID = requestID
        self.events = events ?? [
            makeCompletedEvent(requestID: requestID, seq: 1, finishReason: "stop", assistantText: "ok"),
        ]
        self.heldCompletionEvent = heldCompletionEvent
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
        if heldCompletionEvent != nil {
            let pair = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.makeStream()
            heldContinuation = pair.continuation
            for event in events {
                pair.continuation.yield(event)
            }
            return pair.stream
        }

        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func completeHeldStream() {
        guard let continuation = heldContinuation else {
            return
        }
        heldContinuation = nil
        if let heldCompletionEvent {
            continuation.yield(heldCompletionEvent)
        }
        continuation.finish()
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
