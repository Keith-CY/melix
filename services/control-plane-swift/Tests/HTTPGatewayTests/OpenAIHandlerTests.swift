import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("OpenAI Handler")
struct OpenAIHandlerTests {
    @Test("POST /v1/chat/completions translates into a worker generate request")
    func postChatCompletionsTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "req-fixed", seq: 1, text: "Hel"),
            makeTokenEvent(requestID: "req-fixed", seq: 2, text: "lo"),
            makeUsageEvent(requestID: "req-fixed", seq: 3, promptTokens: 1, completionTokens: 2),
            makeCompletedEvent(requestID: "req-fixed", seq: 4, finishReason: "stop", assistantText: "Hello"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-fixed" })
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            translator: translator,
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 123) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ],
              "temperature": 0.2,
              "max_tokens": 16
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.execution.id.requestID == "req-fixed")
        #expect(request.execution.modelHandle == "melix-dev-text::local")
        #expect(request.execution.scheduling.lane == "text.decode.interactive")
        #expect(request.execution.scheduling.priority == 100)
        #expect(request.execution.scheduling.latencySensitive)
        #expect(request.messages.count == 1)
        #expect(request.messages[0].role == "user")
        #expect(request.messages[0].parts.count == 1)
        #expect(request.messages[0].parts[0].text == "Hello")
        #expect(request.sampling.temperature == 0.2)
        #expect(request.sampling.maxOutputTokens == 16)
        #expect(payload.contains("\"content\":\"Hel\""))
        #expect(payload.contains("\"content\":\"lo\""))
        #expect(payload.contains("\"finish_reason\":\"stop\""))
        #expect(payload.contains("\"prompt_tokens\":1"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("chat completions translator preserves recovery metadata on worker requests")
    func postChatCompletionsPreservesRecoveryMetadata() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "req-recovery", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-recovery" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "session_id": "session-recovery",
              "branch_id": "branch-main",
              "parent_request_id": "req-parent",
              "restore_snapshot_id": "snap-parent",
              "save_boundary_snapshot": true,
              "messages": [
                { "role": "user", "content": "Resume" }
              ]
            }
            """.data(using: .utf8)
        )

        _ = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/chat/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )

        let request = try #require(await workerClient.lastGenerateRequest)
        #expect(request.execution.id.sessionID == "session-recovery")
        #expect(request.execution.id.branchID == "branch-main")
        #expect(request.execution.id.parentRequestID == "req-parent")
        #expect(request.execution.cacheHints.restoreSnapshotID == "snap-parent")
        #expect(request.execution.cacheHints.saveBoundarySnapshot)
        #expect(request.execution.cacheHints.persistL2)
        #expect(request.execution.cacheHints.preferHotPrefix)
    }

    @Test("POST /v1/responses translates into the shared text request model")
    func postResponsesTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "resp-fixed", seq: 1, text: "Hello"),
            makeUsageEvent(requestID: "resp-fixed", seq: 2, promptTokens: 2, completionTokens: 1),
            makeCompletedEvent(requestID: "resp-fixed", seq: 3, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-fixed" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "instructions": "Be terse.",
              "input": "hello responses"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.messages.count == 2)
        #expect(request.messages[0].role == "system")
        #expect(request.messages[0].parts.first?.text == "Be terse.")
        #expect(request.messages[1].role == "user")
        #expect(request.messages[1].parts.first?.text == "hello responses")
        #expect(payload.contains("event: response.output_text.delta"))
        #expect(payload.contains("\"type\":\"response.output_text.delta\""))
        #expect(payload.contains("\"response_id\":\"resp-fixed\""))
        #expect(payload.contains("event: response.completed"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/completions translates prompt input into the shared text request model")
    func postCompletionsTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "cmp-fixed", seq: 1, text: "Hello"),
            makeUsageEvent(requestID: "cmp-fixed", seq: 2, promptTokens: 2, completionTokens: 1),
            makeCompletedEvent(requestID: "cmp-fixed", seq: 3, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "cmp-fixed" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "prompt": "hello completions"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/completions",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.messages.count == 1)
        #expect(request.messages[0].role == "user")
        #expect(request.messages[0].parts.first?.text == "hello completions")
        #expect(payload.contains("\"object\":\"text_completion\""))
        #expect(payload.contains("\"text\":\"Hello\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/messages translates into the shared text request model")
    func postMessagesTranslatesAndStreams() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeTokenEvent(requestID: "msg-fixed", seq: 1, text: "Hello"),
            makeCompletedEvent(requestID: "msg-fixed", seq: 2, finishReason: "stop", assistantText: "Hello"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "msg-fixed" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "system": "Be terse.",
              "messages": [
                { "role": "user", "content": "hello messages" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/messages",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "text/event-stream; charset=utf-8")
        #expect(request.messages.count == 2)
        #expect(request.messages[0].role == "system")
        #expect(request.messages[0].parts.first?.text == "Be terse.")
        #expect(request.messages[1].role == "user")
        #expect(request.messages[1].parts.first?.text == "hello messages")
        #expect(payload.contains("event: message.delta"))
        #expect(payload.contains("\"type\":\"message.delta\""))
        #expect(payload.contains("\"message_id\":\"msg-fixed\""))
        #expect(payload.contains("event: message.completed"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("POST /v1/responses forwards reasoning and tool delta events")
    func postResponsesForwardsReasoningAndToolDeltas() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeReasoningEvent(requestID: "resp-deltas", seq: 1, text: "think"),
            makeToolCallEvent(
                requestID: "resp-deltas",
                seq: 2,
                callID: "tool-1",
                toolName: "search",
                argumentsJSONFragment: "{\"q\":\"melix\"}"
            ),
            makeCompletedEvent(requestID: "resp-deltas", seq: 3, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-deltas" }),
            sseWriter: SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "hello responses"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(
                method: .post,
                path: "/v1/responses",
                headers: ["content-type": "application/json"],
                body: body
            )
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("event: response.reasoning.delta"))
        #expect(payload.contains("\"type\":\"response.reasoning.delta\""))
        #expect(payload.contains("\"delta\":\"think\""))
        #expect(payload.contains("event: response.tool_call.delta"))
        #expect(payload.contains("\"type\":\"response.tool_call.delta\""))
        #expect(payload.contains("\"tool_name\":\"search\""))
        #expect(payload.contains("event: response.completed"))
    }

    @Test("responses requests default stream to true when omitted")
    func responsesRequestsDefaultStreamToTrue() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "resp-default", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry()
            ),
            translator: ChatRequestTranslator(requestIDGenerator: { "resp-default" })
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "input": "hello default stream"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let request = try #require(await workerClient.lastGenerateRequest)

        #expect(response.statusCode == 200)
        #expect(request.execution.id.requestID == "resp-default")
        #expect(request.messages.count == 1)
        #expect(request.messages[0].parts.first?.text == "hello default stream")
    }

    @Test("non-stream responses requests return 400")
    func nonStreamResponsesRequestsReturn400() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "input": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
    }

    @Test("non-stream completions requests return 400")
    func nonStreamCompletionsRequestsReturn400() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "prompt": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
    }

    @Test("non-stream messages requests return 400")
    func nonStreamMessagesRequestsReturn400() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/messages", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
    }

    @Test("responses requests return 409 when the model is not ready")
    func responsesModelNotReadyReturns409() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "input": "Hello"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/responses", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("GET /v1/models returns model state from the catalog")
    func getModelsReturnsCatalogState() async throws {
        let catalog = ModelCatalog(seedModels: [warmModel()])
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/models", headers: [:], body: Data())
        )

        let body = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(body.contains("\"object\":\"list\""))
        #expect(body.contains("\"id\":\"melix-dev-text\""))
        #expect(body.contains("\"melix_state\":\"warm\""))
        #expect(body.contains("\"owned_by\":\"melix\""))
    }

    @Test("GET /v1/models renders all public Melix model states")
    func getModelsRendersAllStates() async throws {
        var pinned = ModelCatalog.devTextModel()
        pinned.modelID = "melix-pinned"
        pinned.state = .modelPinned

        var unloaded = ModelCatalog.devTextModel()
        unloaded.modelID = "melix-unloaded"
        unloaded.state = .modelUnloaded

        var loading = ModelCatalog.devTextModel()
        loading.modelID = "melix-loading"
        loading.state = .modelLoading

        var discovered = ModelCatalog.devTextModel()
        discovered.modelID = "melix-discovered"
        discovered.state = .modelDiscovered

        var failed = ModelCatalog.devTextModel()
        failed.modelID = "melix-failed"
        failed.state = .modelFailed

        var evicting = ModelCatalog.devTextModel()
        evicting.modelID = "melix-evicting"
        evicting.state = .modelEvicting

        var unknown = ModelCatalog.devTextModel()
        unknown.modelID = "melix-unknown"
        unknown.state = .UNRECOGNIZED(99)

        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [pinned, unloaded, loading, discovered, failed, evicting, unknown]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/models", headers: [:], body: Data())
        )
        let body = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(body.contains("\"id\":\"melix-pinned\""))
        #expect(body.contains("\"melix_state\":\"pinned\""))
        #expect(body.contains("\"id\":\"melix-unloaded\""))
        #expect(body.contains("\"melix_state\":\"unloaded\""))
        #expect(body.contains("\"id\":\"melix-loading\""))
        #expect(body.contains("\"melix_state\":\"loading\""))
        #expect(body.contains("\"id\":\"melix-discovered\""))
        #expect(body.contains("\"melix_state\":\"discovered\""))
        #expect(body.contains("\"id\":\"melix-failed\""))
        #expect(body.contains("\"melix_state\":\"failed\""))
        #expect(body.contains("\"id\":\"melix-evicting\""))
        #expect(body.contains("\"melix_state\":\"evicting\""))
        #expect(body.contains("\"id\":\"melix-unknown\""))
        #expect(body.contains("\"melix_state\":\"unknown\""))
    }

    @Test("unknown routes return 404 json")
    func unknownRoutesReturn404() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/unknown", headers: [:], body: Data())
        )
        let body = try await collectBody(response.body)

        #expect(response.statusCode == 404)
        #expect(body.contains("\"code\":\"not_found\""))
    }

    @Test("non-stream chat requests return 400")
    func nonStreamRequestsReturn400() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": false,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"stream_required\""))
    }

    @Test("chat requests return 409 when the model is not ready")
    func modelNotReadyReturns409() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("chat requests return 503 when the worker is unavailable")
    func workerUnavailableReturns503() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: UnavailableWorkerClient()),
                abortRegistry: AbortRegistry()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("second chat request waits in queue until the active request is cancelled")
    func secondRequestQueuesUntilTheActiveRequestIsCancelled() async throws {
        let workerClient = BlockingOpenAIWorkerClient()
        let requestIDs = RequestIDSequence(["req-1", "req-2"])
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: {
                requestIDs.next()
            })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let first = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let secondTask = Task {
            try await handler.handle(
                HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
            )
        }

        try await Task.sleep(for: .milliseconds(50))
        #expect(await workerClient.generatedRequestIDs == ["req-1"])

        #expect(try await coordinator.cancel(requestID: "req-1"))

        let second = try await secondTask.value
        #expect(await workerClient.generatedRequestIDs == ["req-1", "req-2"])
        #expect(try await coordinator.cancel(requestID: "req-2"))

        #expect(first.statusCode == 200)
        #expect(second.statusCode == 200)
    }

    @Test("duplicate request identifiers return 409 conflict")
    func duplicateRequestIdentifiersReturn409() async throws {
        let workerClient = BlockingOpenAIWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: coordinator,
            translator: ChatRequestTranslator(requestIDGenerator: { "req-duplicate" })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "messages": [
                { "role": "user", "content": "Hello" }
              ]
            }
            """.data(using: .utf8)
        )

        let first = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let second = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/chat/completions", headers: [:], body: body)
        )
        let secondPayload = try await collectBody(second.body)

        #expect(first.statusCode == 200)
        #expect(second.statusCode == 409)
        #expect(secondPayload.contains("\"code\":\"request_already_active\""))
        #expect(secondPayload.contains("A text generation request is already active."))
        #expect(try await coordinator.cancel(requestID: "req-duplicate"))
    }

    private func warmModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devTextModel()
        model.state = .modelWarm
        return model
    }
}

private actor ScriptedWorkerClient: WorkerRoutingClient {
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?

    init(events: [Melix_Worker_V1_ExecuteEvent]) {
        self.events = events
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

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor UnavailableWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool {
        false
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        throw WorkerClientError.unavailable
    }
}

private actor BlockingOpenAIWorkerClient: WorkerRoutingClient {
    private(set) var generatedRequestIDs: [String] = []

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        generatedRequestIDs.append(request.execution.id.requestID)
        return AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { _ in }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private final class RequestIDSequence: @unchecked Sendable {
    private var remaining: [String]
    private let lock = NSLock()

    init(_ remaining: [String]) {
        self.remaining = remaining
    }

    func next() -> String {
        lock.lock()
        defer { lock.unlock() }
        return remaining.removeFirst()
    }
}

private func collectBody(_ body: HTTPBody) async throws -> String {
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
