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

    @Test("POST /v1/embeddings routes to the embedding worker and returns JSON")
    func postEmbeddingsRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setEmbedResponse({
            var response = Melix_Worker_V1_EmbedResponse()
            response.embeddings = [
                {
                    var embedding = Melix_Worker_V1_Embedding()
                    embedding.values = [0.1, 0.2]
                    return embedding
                }(),
                {
                    var embedding = Melix_Worker_V1_Embedding()
                    embedding.values = [0.3, 0.4]
                    return embedding
                }(),
            ]
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                embeddingClient: embeddingClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha", "beta"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await embeddingClient.lastEmbedRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(request.modelHandle == "melix-dev-embed::python")
        #expect(request.inputs == ["alpha", "beta"])
        #expect(payload.contains("\"object\":\"list\""))
        #expect(payload.contains("\"embedding\":[0.1,0.2]"))
        #expect(payload.contains("\"model\":\"melix-dev-embed\""))
        #expect(metrics.values["embeddings.request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["embeddings.items_per_second", default: 0] > 0)
    }

    @Test("POST /v1/rerank routes to the rerank worker and returns JSON")
    func postRerankRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let rerankClient = ScriptedPhaseFiveWorkerClient()
        await rerankClient.setRerankResponse({
            var response = Melix_Worker_V1_RerankResponse()
            response.items = [
                {
                    var item = Melix_Worker_V1_RerankItem()
                    item.index = 1
                    item.score = 0.91
                    return item
                }(),
                {
                    var item = Melix_Worker_V1_RerankItem()
                    item.index = 0
                    item.score = 0.73
                    return item
                }(),
            ]
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devRerankModel()])
        _ = await catalog.loadModel(id: "melix-dev-rerank", dispatchHandle: "melix-dev-rerank::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                rerankClient: rerankClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-rerank",
              "query": "swift worker",
              "documents": ["python bridge", "swift worker"],
              "top_k": 2
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await rerankClient.lastRerankRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(request.modelHandle == "melix-dev-rerank::python")
        #expect(request.query == "swift worker")
        #expect(request.documents == ["python bridge", "swift worker"])
        #expect(payload.contains("\"model\":\"melix-dev-rerank\""))
        #expect(payload.contains("\"index\":1"))
        #expect(payload.contains("\"score\":0.91"))
        #expect(metrics.values["rerank.request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["rerank.documents_per_second", default: 0] > 0)
    }

    @Test("POST /v1/audio/transcriptions routes to the transcription worker and returns JSON")
    func postAudioTranscriptionsRoutesAndReturnsJSON() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setTranscribeResponse({
            var response = Melix_Worker_V1_TranscribeResponse()
            response.text = "hello audio"
            response.language = "en"
            response.durationSeconds = 0.25
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_base64": "aGVsbG8gYXVkaW8=",
              "format": "wav",
              "language": "en"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await audioClient.lastTranscribeRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "application/json")
        #expect(request.modelHandle == "melix-dev-transcribe::python")
        #expect(request.audioBytes == Data("hello audio".utf8))
        #expect(request.format == "wav")
        #expect(request.language == "en")
        #expect(payload.contains("\"model\":\"melix-dev-transcribe\""))
        #expect(payload.contains("\"text\":\"hello audio\""))
        #expect(payload.contains("\"language\":\"en\""))
        #expect(payload.contains("\"duration_seconds\":0.25"))
        #expect(metrics.values["audio.transcription_request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["audio.seconds_processed_per_second", default: 0] > 0)
    }

    @Test("POST /v1/audio/transcriptions records background-lane and runtime probe metrics")
    func postAudioTranscriptionsRecordsIsolationAndProbeMetrics() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setTranscribeResponse({
            var response = Melix_Worker_V1_TranscribeResponse()
            response.text = "hello audio"
            response.language = "en"
            response.durationSeconds = 0.5
            return response
        }())
        await audioClient.setRuntimeStatsResponse({
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.activeMultimodalRequests = 1
            response.stats.lastProbeKind = "transcription"
            response.stats.lastPreprocessLatencyMs = 14
            response.stats.lastPreprocessPeakMemoryBytes = 4096
            response.stats.lastTranscriptionLatencyMs = 22
            response.stats.lastAudioDurationSeconds = 0.5
            response.stats.lastAudioChunkCount = 3
            return response
        }())

        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel(metricsStore: metricsStore)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_base64": "aGVsbG8gYXVkaW8="
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let metrics = await metricsStore.snapshot()
        let queueSummary = await schedulerReadModel.snapshot()
        let lane = try #require(
            queueSummary.lanes.first(where: { $0.laneID == "multimodal.audio.transcription.background" })
        )

        #expect(response.statusCode == 200)
        #expect(lane.activeRequests == 0)
        #expect(lane.admissionRate == 1)
        #expect(metrics.values["scheduler.multimodal_queue_delay_ms", default: -1] >= 0)
        #expect(metrics.values["scheduler.multimodal_active_requests", default: -1] == 0)
        #expect(metrics.values["scheduler.text_protection_active", default: -1] == 0)
        #expect(metrics.values["audio.preprocess_latency_ms", default: -1] == 14)
        #expect(metrics.values["audio.preprocess_peak_memory_bytes", default: -1] == 4096)
        #expect(metrics.values["audio.transcription_latency_ms", default: -1] == 22)
        #expect(metrics.values["audio.audio_duration_seconds", default: -1] == 0.5)
        #expect(metrics.values["audio.audio_chunk_count", default: -1] == 3)
    }

    @Test("POST /v1/audio/transcriptions supports input_audio URIs and defaults the task")
    func postAudioTranscriptionsSupportsInputAudioURIsAndDefaultsTheTask() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setTranscribeResponse({
            var response = Melix_Worker_V1_TranscribeResponse()
            response.error.code = "invalid_argument"
            response.error.message = "bad audio uri"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "input_audio": {
                "url": "file:///tmp/audio.mp3",
                "format": "mp3",
                "mime_type": "audio/mpeg",
                "filename": "audio.mp3"
              }
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await audioClient.lastTranscribeRequest)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(request.audioUri == "file:///tmp/audio.mp3")
        #expect(request.audio.sourceKind == .mediaSourceUri)
        #expect(request.audio.format == "mp3")
        #expect(request.audio.mimeType == "audio/mpeg")
        #expect(request.audio.filename == "audio.mp3")
        #expect(request.task == "transcribe")
        #expect(request.language.isEmpty)
    }

    @Test("POST /v1/audio/transcriptions validates input payloads and thrown failures")
    func postAudioTranscriptionsValidatesInputPayloadsAndThrownFailures() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let invalidBase64 = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_base64": "%%%INVALID%%%"
            }
            """.data(using: .utf8)
        )
        let invalidBase64Response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: invalidBase64)
        )
        let invalidBase64Payload = try await collectBody(invalidBase64Response.body)

        #expect(invalidBase64Response.statusCode == 400)
        #expect(invalidBase64Payload.contains("\"code\":\"invalid_argument\""))
        #expect(invalidBase64Payload.contains("audio_base64 must be valid base64"))

        let missingAudio = try #require(
            """
            {
              "model": "melix-dev-transcribe"
            }
            """.data(using: .utf8)
        )
        let missingAudioResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: missingAudio)
        )
        let missingAudioPayload = try await collectBody(missingAudioResponse.body)

        #expect(missingAudioResponse.statusCode == 400)
        #expect(missingAudioPayload.contains("\"code\":\"invalid_argument\""))
        #expect(missingAudioPayload.contains("input_audio or audio_base64\\/audio_url is required"))

        await audioClient.setThrownFailure(WorkerClientError.unavailable)
        let thrownFailure = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_url": "file:///tmp/audio.wav"
            }
            """.data(using: .utf8)
        )
        let thrownFailureResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: thrownFailure)
        )
        let thrownFailurePayload = try await collectBody(thrownFailureResponse.body)

        #expect(thrownFailureResponse.statusCode == 503)
        #expect(thrownFailurePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/audio/transcriptions returns 409 and 503 for unavailable routes")
    func postAudioTranscriptionsReturns409And503ForUnavailableRoutes() async throws {
        let unloadedHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devTranscriptionModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-transcribe",
              "audio_url": "file:///tmp/audio.wav"
            }
            """.data(using: .utf8)
        )

        let unloadedResponse = try await unloadedHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let unloadedPayload = try await collectBody(unloadedResponse.body)

        #expect(unloadedResponse.statusCode == 409)
        #expect(unloadedPayload.contains("\"code\":\"model_not_ready\""))

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTranscriptionModel()])
        _ = await catalog.loadModel(id: "melix-dev-transcribe", dispatchHandle: "melix-dev-transcribe::python")
        let unavailableHandler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )

        let unavailableResponse = try await unavailableHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/transcriptions", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/audio/speech routes to the speech worker and returns audio bytes")
    func postAudioSpeechRoutesAndReturnsAudioBytes() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("VOICE=alloy\nFORMAT=wav\nTEXT=hello speech".utf8)
            response.format = "wav"
            return response
        }())

        let metricsStore = MetricsStore()
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            ),
            metricsStore: metricsStore
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech",
              "voice": "alloy",
              "format": "wav",
              "instructions": "Use a calm voice."
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)
        let request = try #require(await audioClient.lastSpeakRequest)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "audio/wav")
        #expect(request.modelHandle == "melix-dev-speech::python")
        #expect(request.input == "hello speech")
        #expect(request.voice == "alloy")
        #expect(request.format == "wav")
        #expect(request.instructions == "Use a calm voice.")
        #expect(payload == Data("VOICE=alloy\nFORMAT=wav\nTEXT=hello speech".utf8))
        #expect(metrics.values["audio.speech_request_latency_ms", default: -1] >= 0)
        #expect(metrics.values["audio.speech_output_bytes", default: 0] == 40)
    }

    @Test("POST /v1/audio/speech records background-lane and runtime probe metrics")
    func postAudioSpeechRecordsIsolationAndProbeMetrics() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("runtime-bytes".utf8)
            response.format = "wav"
            return response
        }())
        await audioClient.setRuntimeStatsResponse({
            var response = Melix_Worker_V1_GetRuntimeStatsResponse()
            response.stats.activeMultimodalRequests = 1
            response.stats.lastProbeKind = "speech"
            response.stats.lastSpeechLatencyMs = 31
            response.stats.lastAudioOutputBytes = 13
            return response
        }())

        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel(metricsStore: metricsStore)
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient,
                modelCatalog: catalog
            ),
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let metrics = await metricsStore.snapshot()
        let queueSummary = await schedulerReadModel.snapshot()
        let lane = try #require(
            queueSummary.lanes.first(where: { $0.laneID == "multimodal.audio.speech.background" })
        )

        #expect(response.statusCode == 200)
        #expect(lane.activeRequests == 0)
        #expect(lane.admissionRate == 1)
        #expect(metrics.values["audio.speech_latency_ms", default: -1] == 31)
        #expect(metrics.values["audio.speech_output_bytes", default: -1] == 13)
        #expect(metrics.values["scheduler.multimodal_queue_delay_ms", default: -1] >= 0)
        #expect(metrics.values["scheduler.text_protection_active", default: -1] == 0)
    }

    @Test("POST /v1/audio/speech defaults optional fields and resolves mp3 content types")
    func postAudioSpeechDefaultsOptionalFieldsAndResolvesMp3ContentTypes() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.audioBytes = Data("mp3-bytes".utf8)
            response.format = ""
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech",
              "format": "mp3"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let payload = try await collectBodyData(response.body)
        let request = try #require(await audioClient.lastSpeakRequest)

        #expect(response.statusCode == 200)
        #expect(response.headers["content-type"] == "audio/mpeg")
        #expect(request.voice.isEmpty)
        #expect(request.format == "mp3")
        #expect(request.instructions.isEmpty)
        #expect(payload == Data("mp3-bytes".utf8))
    }

    @Test("POST /v1/audio/speech maps worker errors and thrown failures to HTTP responses")
    func postAudioSpeechMapsWorkerErrorsAndThrownFailuresToHTTPResponses() async throws {
        let textClient = ScriptedWorkerClient(events: [])
        let audioClient = ScriptedPhaseFiveWorkerClient()
        await audioClient.setSpeakResponse({
            var response = Melix_Worker_V1_SpeakResponse()
            response.error.code = "internal"
            response.error.message = "speech synthesis failed"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: textClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: textClient,
                pythonCompatibilityClient: audioClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let errorResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let errorPayload = try await collectBody(errorResponse.body)

        #expect(errorResponse.statusCode == 500)
        #expect(errorPayload.contains("\"code\":\"internal\""))
        #expect(errorPayload.contains("\"message\":\"speech synthesis failed\""))

        await audioClient.setThrownFailure(WorkerClientError.unavailable)
        let unavailableResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/audio/speech returns 409 and 503 for unavailable routes")
    func postAudioSpeechReturns409And503ForUnavailableRoutes() async throws {
        let unloadedHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devSpeechModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-speech",
              "input": "hello speech"
            }
            """.data(using: .utf8)
        )

        let unloadedResponse = try await unloadedHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let unloadedPayload = try await collectBody(unloadedResponse.body)

        #expect(unloadedResponse.statusCode == 409)
        #expect(unloadedPayload.contains("\"code\":\"model_not_ready\""))

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devSpeechModel()])
        _ = await catalog.loadModel(id: "melix-dev-speech", dispatchHandle: "melix-dev-speech::python")
        let unavailableHandler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                pythonCompatibilityClient: ScriptedWorkerClient(events: [])
            )
        )

        let unavailableResponse = try await unavailableHandler.handle(
            HTTPRequest(method: .post, path: "/v1/audio/speech", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("GET /health reports route readiness and model counts")
    func getHealthReportsRouteReadinessAndModelCounts() async throws {
        let healthyClient = ScriptedWorkerClient(events: [])
        let unhealthyClient = UnavailableWorkerClient()
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel(), warmEmbeddingModel(), warmRerankModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: healthyClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: healthyClient,
                pythonCompatibilityClient: healthyClient,
                embeddingClient: healthyClient,
                rerankClient: unhealthyClient,
                modelOperationsClient: healthyClient
            ),
            metricsStore: metricsStore
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"status\":\"degraded\""))
        #expect(payload.contains("\"swift_text\":true"))
        #expect(payload.contains("\"python_embedding\":true"))
        #expect(payload.contains("\"python_rerank\":false"))
        #expect(payload.contains("\"python_transcription\":true"))
        #expect(payload.contains("\"python_speech\":true"))
        #expect(payload.contains("\"models_ready\":3"))
        #expect(payload.contains("\"models_total\":3"))
        #expect(metrics.values["operator.health_latency_ms", default: -1] >= 0)
    }

    @Test("GET /health reports ok when all routes are ready and pinned models count as ready")
    func getHealthReportsOkWhenAllRoutesAreReadyAndPinnedModelsCountAsReady() async throws {
        let healthyTextClient = ScriptedWorkerClient(events: [])
        let healthyPythonClient = ScriptedPhaseFiveWorkerClient()

        var pinned = warmModel()
        pinned.modelID = "melix-pinned-text"
        pinned.state = .modelPinned

        var discovered = warmEmbeddingModel()
        discovered.modelID = "melix-discovered-embed"
        discovered.state = .modelDiscovered

        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel(), pinned, discovered]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: healthyTextClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: healthyTextClient,
                pythonCompatibilityClient: healthyPythonClient,
                embeddingClient: healthyPythonClient,
                rerankClient: healthyPythonClient,
                modelOperationsClient: healthyPythonClient
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"status\":\"ok\""))
        #expect(payload.contains("\"models_ready\":2"))
        #expect(payload.contains("\"models_total\":3"))
    }

    @Test("GET /health reports missing route clients as false when a registry is present")
    func getHealthReportsMissingRouteClientsAsFalseWhenARegistryIsPresent() async throws {
        let healthyTextClient = ScriptedWorkerClient(events: [])
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: healthyTextClient),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(defaultTextClient: healthyTextClient)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"swift_text\":true"))
        #expect(payload.contains("\"python_embedding\":false"))
        #expect(payload.contains("\"python_model_operations\":false"))
    }

    @Test("GET /health degrades cleanly when no worker registry is wired")
    func getHealthDegradesCleanlyWithoutAWorkerRegistry() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            )
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/health", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"status\":\"degraded\""))
        #expect(payload.contains("\"swift_text\":false"))
        #expect(payload.contains("\"python_embedding\":false"))
        #expect(payload.contains("\"python_rerank\":false"))
        #expect(payload.contains("\"python_model_operations\":false"))
        #expect(payload.contains("\"python_transcription\":false"))
        #expect(payload.contains("\"python_speech\":false"))
    }

    @Test("POST /v1/embeddings returns 503 when the embedding worker throws")
    func postEmbeddingsReturns503WhenTheEmbeddingWorkerThrows() async throws {
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setThrownFailure(WorkerClientError.unavailable)

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: embeddingClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/rerank returns 409 and 503 when routing prerequisites are missing")
    func postRerankReturns409And503WhenRoutingPrerequisitesAreMissing() async throws {
        let unloadedHandler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devRerankModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                rerankClient: ScriptedPhaseFiveWorkerClient()
            )
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-rerank",
              "query": "swift worker",
              "documents": ["swift worker"],
              "top_k": 1
            }
            """.data(using: .utf8)
        )

        let unloadedResponse = try await unloadedHandler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let unloadedPayload = try await collectBody(unloadedResponse.body)

        #expect(unloadedResponse.statusCode == 409)
        #expect(unloadedPayload.contains("\"code\":\"model_not_ready\""))

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devRerankModel()])
        _ = await catalog.loadModel(id: "melix-dev-rerank", dispatchHandle: "melix-dev-rerank::python")
        let unavailableHandler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                rerankClient: ScriptedWorkerClient(events: [])
            )
        )

        let unavailableResponse = try await unavailableHandler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("GET /v1/cache/stats renders the control-plane cache summary")
    func getCacheStatsRendersControlPlaneCacheSummary() async throws {
        var snapshot = CacheMetadataStore.emptySnapshot()
        snapshot.summary.l1Bytes = 2048
        snapshot.summary.l2Bytes = 4096
        snapshot.summary.l1HitRate = 0.5
        snapshot.summary.l2RestoreHitRate = 0.75
        snapshot.summary.compressionRatio = 0.25
        snapshot.summary.quantizedBytes = 1024

        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            cacheMetadataStore: CacheMetadataStore(snapshot: snapshot)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/cache/stats", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"l1_bytes\":2048"))
        #expect(payload.contains("\"l2_bytes\":4096"))
        #expect(payload.contains("\"l1_hit_rate\":0.5"))
        #expect(payload.contains("\"l2_restore_hit_rate\":0.75"))
        #expect(payload.contains("\"compression_ratio\":0.25"))
        #expect(payload.contains("\"quantized_bytes\":1024"))
    }

    @Test("GET /v1/cache/stats returns empty zeros and metrics without a cache store")
    func getCacheStatsReturnsEmptyZerosAndMetricsWithoutACacheStore() async throws {
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            metricsStore: metricsStore
        )

        let response = try await handler.handle(
            HTTPRequest(method: .get, path: "/v1/cache/stats", headers: [:], body: Data())
        )
        let payload = try await collectBody(response.body)
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(payload.contains("\"l1_bytes\":0"))
        #expect(payload.contains("\"l2_bytes\":0"))
        #expect(payload.contains("\"compression_ratio\":0"))
        #expect(metrics.values["operator.cache_stats_latency_ms", default: -1] >= 0)
    }

    @Test("POST /v1/embeddings accepts a single string input and estimates usage")
    func postEmbeddingsAcceptsASingleStringInputAndEstimatesUsage() async throws {
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setEmbedResponse({
            var response = Melix_Worker_V1_EmbedResponse()
            response.embeddings = [
                {
                    var embedding = Melix_Worker_V1_Embedding()
                    embedding.values = [0.9, 0.1]
                    return embedding
                }(),
            ]
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel(), ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: embeddingClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": "alpha beta"
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let request = try #require(await embeddingClient.lastEmbedRequest)

        #expect(response.statusCode == 200)
        #expect(request.inputs == ["alpha beta"])
        #expect(payload.contains("\"prompt_tokens\":2"))
        #expect(payload.contains("\"total_tokens\":2"))
    }

    @Test("POST /v1/embeddings returns 409 when the embedding model is not loaded")
    func postEmbeddingsReturns409WhenTheEmbeddingModelIsNotLoaded() async throws {
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: ScriptedPhaseFiveWorkerClient()
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 409)
        #expect(payload.contains("\"code\":\"model_not_ready\""))
    }

    @Test("POST /v1/embeddings returns 503 when no compatible embedding worker is available")
    func postEmbeddingsReturns503WhenNoCompatibleEmbeddingWorkerIsAvailable() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: ScriptedWorkerClient(events: [])
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 503)
        #expect(payload.contains("\"code\":\"worker_unavailable\""))
    }

    @Test("POST /v1/embeddings maps worker error payloads to HTTP responses")
    func postEmbeddingsMapsWorkerErrorPayloadsToHTTPResponses() async throws {
        let embeddingClient = ScriptedPhaseFiveWorkerClient()
        await embeddingClient.setEmbedResponse({
            var response = Melix_Worker_V1_EmbedResponse()
            response.error.code = "invalid_argument"
            response.error.message = "bad embedding input"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.loadModel(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                embeddingClient: embeddingClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-embed",
              "input": ["alpha"]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/embeddings", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)

        #expect(response.statusCode == 400)
        #expect(payload.contains("\"code\":\"invalid_argument\""))
        #expect(payload.contains("\"message\":\"bad embedding input\""))
    }

    @Test("POST /v1/rerank maps worker errors and thrown failures to HTTP responses")
    func postRerankMapsWorkerErrorsAndThrownFailuresToHTTPResponses() async throws {
        let rerankClient = ScriptedPhaseFiveWorkerClient()
        await rerankClient.setRerankResponse({
            var response = Melix_Worker_V1_RerankResponse()
            response.error.code = "not_found"
            response.error.message = "rerank model missing"
            return response
        }())

        let catalog = ModelCatalog(seedModels: [ModelCatalog.devRerankModel()])
        _ = await catalog.loadModel(id: "melix-dev-rerank", dispatchHandle: "melix-dev-rerank::python")
        let handler = OpenAIHandler(
            modelCatalog: catalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: ScriptedWorkerClient(events: [])),
                abortRegistry: AbortRegistry()
            ),
            workerRegistry: WorkerRegistry(
                defaultTextClient: ScriptedWorkerClient(events: []),
                rerankClient: rerankClient
            )
        )

        let body = try #require(
            """
            {
              "model": "melix-dev-rerank",
              "query": "swift worker",
              "documents": ["swift worker"],
              "top_k": 1
            }
            """.data(using: .utf8)
        )

        let errorResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let errorPayload = try await collectBody(errorResponse.body)

        #expect(errorResponse.statusCode == 404)
        #expect(errorPayload.contains("\"code\":\"not_found\""))

        await rerankClient.setThrownFailure(WorkerClientError.unavailable)
        let unavailableResponse = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/rerank", headers: [:], body: body)
        )
        let unavailablePayload = try await collectBody(unavailableResponse.body)

        #expect(unavailableResponse.statusCode == 503)
        #expect(unavailablePayload.contains("\"code\":\"worker_unavailable\""))
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

    @Test("handler applies workflow-aware shaping and records shaping metrics")
    func handlerAppliesWorkflowAwareShapingAndRecordsMetrics() async throws {
        let workerClient = ScriptedWorkerClient(events: [
            makeCompletedEvent(requestID: "msg-workflow", seq: 1, finishReason: "stop", assistantText: "done"),
        ])
        let metricsStore = MetricsStore()
        let handler = OpenAIHandler(
            modelCatalog: ModelCatalog(seedModels: [warmModel()]),
            requestCoordinator: RequestCoordinator(
                workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
                abortRegistry: AbortRegistry(),
                metricsStore: metricsStore
            ),
            metricsStore: metricsStore,
            translator: ChatRequestTranslator(requestIDGenerator: { "msg-workflow" })
        )
        let body = try #require(
            """
            {
              "model": "melix-dev-text",
              "stream": true,
              "preset_id": "deep_reasoning",
              "workflow": "tool_followup",
              "workflow_run_id": "wf-handler",
              "workflow_node_id": "node-handler",
              "session_id": "session-handler",
              "messages": [
                { "role": "user", "content": "Continue the tool result." }
              ]
            }
            """.data(using: .utf8)
        )

        let response = try await handler.handle(
            HTTPRequest(method: .post, path: "/v1/messages", headers: [:], body: body)
        )
        let payload = try await collectBody(response.body)
        let generated = await workerClient.lastGenerateRequest
        let metrics = await metricsStore.snapshot()

        #expect(response.statusCode == 200)
        #expect(payload.contains("event: message.completed"))
        #expect(generated?.execution.id.workflowRunID == "wf-handler")
        #expect(generated?.execution.id.workflowNodeID == "node-handler")
        #expect(generated?.execution.scheduling.lane == "text.prefill.hot")
        #expect(generated?.execution.scheduling.admissionPolicy == "workflow.tool_followup")
        #expect(generated?.execution.cacheHints.cachePolicy == "session-hot")
        #expect(generated?.execution.ext["melix.preset_id"] == "deep_reasoning")
        #expect(generated?.execution.ext["melix.workflow"] == "tool_followup")
        #expect(metrics.values["http.preset_shaped_count", default: 0] == 1)
        #expect(metrics.values["http.workflow_shaped_count", default: 0] == 1)
        #expect(metrics.values["http.shaping_ms", default: -1] >= 0)
    }

    private func warmModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devTextModel()
        model.state = .modelWarm
        return model
    }

    private func warmEmbeddingModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devEmbeddingModel()
        model.state = .modelWarm
        return model
    }

    private func warmRerankModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devRerankModel()
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

private actor ScriptedPhaseFiveWorkerClient:
    WorkerRoutingClient,
    NonTextInferenceWorkerClientProtocol,
    RuntimeIntrospectingWorkerClientProtocol
{
    private(set) var lastEmbedRequest: Melix_Worker_V1_EmbedRequest?
    private(set) var lastRerankRequest: Melix_Worker_V1_RerankRequest?
    private(set) var lastTranscribeRequest: Melix_Worker_V1_TranscribeRequest?
    private(set) var lastSpeakRequest: Melix_Worker_V1_SpeakRequest?
    private var embedResponse = Melix_Worker_V1_EmbedResponse()
    private var rerankResponse = Melix_Worker_V1_RerankResponse()
    private var transcribeResponse = Melix_Worker_V1_TranscribeResponse()
    private var speakResponse = Melix_Worker_V1_SpeakResponse()
    private var runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
    private var thrownFailure: Error?

    func setEmbedResponse(_ response: Melix_Worker_V1_EmbedResponse) {
        embedResponse = response
    }

    func setRerankResponse(_ response: Melix_Worker_V1_RerankResponse) {
        rerankResponse = response
    }

    func setTranscribeResponse(_ response: Melix_Worker_V1_TranscribeResponse) {
        transcribeResponse = response
    }

    func setSpeakResponse(_ response: Melix_Worker_V1_SpeakResponse) {
        speakResponse = response
    }

    func setRuntimeStatsResponse(_ response: Melix_Worker_V1_GetRuntimeStatsResponse) {
        runtimeStatsResponse = response
    }

    func setThrownFailure(_ failure: Error?) {
        thrownFailure = failure
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
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
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastEmbedRequest = request
        return embedResponse
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastRerankRequest = request
        return rerankResponse
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastTranscribeRequest = request
        return transcribeResponse
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        lastSpeakRequest = request
        return speakResponse
    }

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        if let thrownFailure {
            throw thrownFailure
        }
        return runtimeStatsResponse
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

private func collectBodyData(_ body: HTTPBody) async throws -> Data {
    switch body {
    case .data(let data):
        return data
    case .stream(let stream):
        var data = Data()
        for try await chunk in stream {
            data.append(chunk)
        }
        return data
    }
}
