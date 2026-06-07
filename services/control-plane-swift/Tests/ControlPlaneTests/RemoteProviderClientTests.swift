import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Remote Provider Client")
struct RemoteProviderClientTests {
    @Test("endpoint probe normalizes provider model URLs and redacts secrets")
    func endpointProbeNormalizesProviderModelURLsAndRedactsSecrets() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(#"{ "data": [{ "id": "gpt-4.1", "object": "model" }] }"#.utf8)
        ))
        let clock = StepLatencyClock(values: [100, 112])
        let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { clock.next() })

        let receipt = try await probe.probe(
            ProviderEndpointProbeRequest(
                endpointID: "openai-main",
                providerKind: "openai-compatible",
                baseURL: " https://api.example.test/v1/chat/completions?api_key=sk-secret ",
                apiKey: "sk-secret"
            )
        )

        #expect(receipt.endpointID == "openai-main")
        #expect(receipt.providerKind == "openai-compatible")
        #expect(receipt.baseURLRedacted == "https://api.example.test/v1")
        #expect(receipt.modelCount == 1)
        #expect(receipt.capabilities.chat == true)
        #expect(receipt.capabilities.streaming == true)
        #expect(receipt.latencyMS == 12)
        #expect(receipt.failureReason == "")
        #expect(await transport.lastRequest?.url?.absoluteString == "https://api.example.test/v1/models")
        #expect(await transport.lastRequest?.value(forHTTPHeaderField: "Authorization") == "Bearer sk-secret")
        #expect(String(describing: receipt).contains("sk-secret") == false)
    }

    @Test("endpoint probe builds provider specific model list requests")
    func endpointProbeBuildsProviderSpecificModelListRequests() async throws {
        let cases: [
            (
                providerKind: String,
                baseURL: String,
                apiKey: String,
                responseBody: String,
                expectedURL: String,
                expectedAuthorization: String?,
                expectedXAPIKey: String?,
                expectedAnthropicVersion: String?
            )
        ] = [
            (
                providerKind: "anthropic",
                baseURL: "https://api.anthropic.example/v1/messages",
                apiKey: "anthropic-secret",
                responseBody: #"{ "data": [{ "id": "claude-sonnet-4.5", "type": "model" }] }"#,
                expectedURL: "https://api.anthropic.example/v1/models",
                expectedAuthorization: nil,
                expectedXAPIKey: "anthropic-secret",
                expectedAnthropicVersion: "2023-06-01"
            ),
            (
                providerKind: "ollama-native",
                baseURL: "http://127.0.0.1:11434/api/chat",
                apiKey: "",
                responseBody: #"{ "models": [{ "name": "llama3.2" }] }"#,
                expectedURL: "http://127.0.0.1:11434/api/tags",
                expectedAuthorization: nil,
                expectedXAPIKey: nil,
                expectedAnthropicVersion: nil
            ),
            (
                providerKind: "ollama-native",
                baseURL: "http://127.0.0.1:11434/api",
                apiKey: "",
                responseBody: #"{ "models": [{ "name": "llama3.2" }] }"#,
                expectedURL: "http://127.0.0.1:11434/api/tags",
                expectedAuthorization: nil,
                expectedXAPIKey: nil,
                expectedAnthropicVersion: nil
            ),
            (
                providerKind: "local-runtime",
                baseURL: "http://127.0.0.1:12436/v1/chat/completions",
                apiKey: "local-secret",
                responseBody: #"{ "data": [{ "id": "melix-dev-text", "object": "model" }] }"#,
                expectedURL: "http://127.0.0.1:12436/v1/models",
                expectedAuthorization: "Bearer local-secret",
                expectedXAPIKey: nil,
                expectedAnthropicVersion: nil
            ),
            (
                providerKind: "local-runtime",
                baseURL: "http://127.0.0.1:12436/v1",
                apiKey: "local-secret",
                responseBody: #"{ "data": [{ "id": "melix-dev-text", "object": "model" }] }"#,
                expectedURL: "http://127.0.0.1:12436/v1/models",
                expectedAuthorization: "Bearer local-secret",
                expectedXAPIKey: nil,
                expectedAnthropicVersion: nil
            ),
        ]

        for testCase in cases {
            let transport = RecordingRemoteProviderTransport(response: .init(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: Data(testCase.responseBody.utf8)
            ))
            let clock = StepLatencyClock(values: [10, 13])
            let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { clock.next() })

            let receipt = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "\(testCase.providerKind)-endpoint",
                    providerKind: testCase.providerKind,
                    baseURL: testCase.baseURL,
                    apiKey: testCase.apiKey
                )
            )

            #expect(receipt.failureReason == "")
            #expect(await transport.lastRequest?.url?.absoluteString == testCase.expectedURL)
            #expect(await transport.lastRequest?.value(forHTTPHeaderField: "Authorization") == testCase.expectedAuthorization)
            #expect(await transport.lastRequest?.value(forHTTPHeaderField: "x-api-key") == testCase.expectedXAPIKey)
            #expect(await transport.lastRequest?.value(forHTTPHeaderField: "anthropic-version") == testCase.expectedAnthropicVersion)
        }
    }

    @Test("endpoint probe normalizes provider kind casing for routing and receipts")
    func endpointProbeNormalizesProviderKindCasingForRoutingAndReceipts() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(#"{ "data": [{ "id": "claude-sonnet-4.5", "type": "model" }] }"#.utf8)
        ))
        let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { 1 })

        let receipt = try await probe.probe(
            ProviderEndpointProbeRequest(
                endpointID: "anthropic-main",
                providerKind: " Anthropic ",
                baseURL: "https://api.anthropic.example/v1/messages",
                apiKey: "anthropic-secret"
            )
        )

        #expect(receipt.providerKind == "anthropic")
        #expect(receipt.failureReason == "")
        #expect(await transport.lastRequest?.url?.absoluteString == "https://api.anthropic.example/v1/models")
        #expect(await transport.lastRequest?.value(forHTTPHeaderField: "Authorization") == nil)
        #expect(await transport.lastRequest?.value(forHTTPHeaderField: "x-api-key") == "anthropic-secret")
    }

    @Test("endpoint probe rejects malformed endpoint requests before transport")
    func endpointProbeRejectsMalformedEndpointRequestsBeforeTransport() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data()
        ))
        let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { 1 })

        await #expect(throws: RemoteProviderError.invalidRequest("provider endpoint base_url is empty")) {
            _ = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "blank",
                    providerKind: "openai-compatible",
                    baseURL: " ",
                    apiKey: ""
                )
            )
        }

        await #expect(throws: RemoteProviderError.invalidRequest("provider endpoint base_url is invalid: not a url")) {
            _ = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "invalid",
                    providerKind: "openai-compatible",
                    baseURL: "not a url",
                    apiKey: ""
                )
            )
        }

        await #expect(throws: RemoteProviderError.invalidRequest("unsupported provider endpoint probe kind: unknown-provider")) {
            _ = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "unknown",
                    providerKind: "unknown-provider",
                    baseURL: "https://api.example.test/v1",
                    apiKey: ""
                )
            )
        }
    }

    @Test("endpoint probe filters hidden disabled and non chat models from automatic selection")
    func endpointProbeFiltersHiddenDisabledAndNonChatModelsFromAutomaticSelection() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(
                #"""
                {
                  "data": [
                    { "id": "chat-visible", "object": "model", "capabilities": ["chat", "streaming", "tools", "json_schema"] },
                    { "id": "embedding-visible", "object": "model", "kind": "embedding", "capabilities": ["embeddings"] },
                    { "id": "embedding-chat", "object": "model", "capabilities": ["embeddings", "chat"] },
                    { "id": "state-hidden-chat", "object": "model", "capabilities": ["chat"], "state": "hidden" },
                    { "id": "hidden-chat", "object": "model", "capabilities": ["chat"], "hidden": true },
                    { "id": "disabled-chat", "object": "model", "capabilities": ["chat"], "disabled": true },
                    { "id": "rerank-only", "object": "model", "kind": "rerank", "capabilities": ["rerank"] },
                    { "id": "audio-only", "object": "model", "kind": "audio", "capabilities": ["speech"] }
                  ]
                }
                """#
                    .utf8
            )
        ))
        let clock = StepLatencyClock(values: [20, 25])
        let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { clock.next() })

        let receipt = try await probe.probe(
            ProviderEndpointProbeRequest(
                endpointID: "mixed-openai",
                providerKind: "openai-compatible",
                baseURL: "https://api.example.test/v1",
                apiKey: "sk-secret"
            )
        )

        #expect(receipt.modelCount == 2)
        #expect(receipt.capabilities.chat == true)
        #expect(receipt.capabilities.streaming == true)
        #expect(receipt.capabilities.tools == true)
        #expect(receipt.capabilities.structuredOutput == true)
        #expect(receipt.capabilities.embeddings == true)
    }

    @Test("endpoint probe returns typed redacted failure receipts")
    func endpointProbeReturnsTypedRedactedFailureReceipts() async throws {
        let failureCases: [(statusCode: Int, body: String, expectedReason: String)] = [
            (statusCode: 401, body: "bad key sk-secret", expectedReason: "auth_failed"),
            (statusCode: 500, body: "server exploded sk-secret", expectedReason: "model_list_failed"),
        ]

        for testCase in failureCases {
            let transport = RecordingRemoteProviderTransport(response: .init(
                statusCode: testCase.statusCode,
                headers: ["content-type": "text/plain"],
                body: Data(testCase.body.utf8)
            ))
            let clock = StepLatencyClock(values: [30, 39])
            let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { clock.next() })

            let receipt = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "failure-endpoint",
                    providerKind: "openai-compatible",
                    baseURL: "https://api.example.test/v1",
                    apiKey: "sk-secret"
                )
            )

            #expect(receipt.modelCount == 0)
            #expect(receipt.capabilities == ProviderEndpointCapabilities())
            #expect(receipt.latencyMS == 9)
            #expect(receipt.failureReason == testCase.expectedReason)
            #expect(String(describing: receipt).contains("sk-secret") == false)
            #expect(String(describing: receipt).contains(testCase.body) == false)
        }
    }

    @Test("endpoint probe classifies malformed and transport failures without leaking secrets")
    func endpointProbeClassifiesMalformedAndTransportFailuresWithoutLeakingSecrets() async throws {
        let malformedTransport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(#"{ "data": "not a model list", "secret": "sk-secret" }"#.utf8)
        ))
        let malformedClock = StepLatencyClock(values: [40, 46])
        let malformedProbe = ProviderEndpointHealthProbe(transport: malformedTransport, latencyClock: { malformedClock.next() })

        let malformedReceipt = try await malformedProbe.probe(
            ProviderEndpointProbeRequest(
                endpointID: "malformed-endpoint",
                providerKind: "openai-compatible",
                baseURL: "https://api.example.test/v1",
                apiKey: "sk-secret"
            )
        )

        #expect(malformedReceipt.modelCount == 0)
        #expect(malformedReceipt.failureReason == "model_list_malformed")
        #expect(String(describing: malformedReceipt).contains("sk-secret") == false)

        let transportFailure = RecordingRemoteProviderTransport(error: RemoteProviderError.invalidResponse("network lost sk-secret"))
        let transportClock = StepLatencyClock(values: [50, 57])
        let transportProbe = ProviderEndpointHealthProbe(transport: transportFailure, latencyClock: { transportClock.next() })

        let transportReceipt = try await transportProbe.probe(
            ProviderEndpointProbeRequest(
                endpointID: "transport-endpoint",
                providerKind: "openai-compatible",
                baseURL: "https://api.example.test/v1",
                apiKey: "sk-secret"
            )
        )

        #expect(transportReceipt.modelCount == 0)
        #expect(transportReceipt.failureReason == "transport_failed")
        #expect(String(describing: transportReceipt).contains("sk-secret") == false)
        #expect(String(describing: transportReceipt).contains("network lost") == false)
    }

    @Test("endpoint probe propagates cancellation instead of recording transport failure")
    func endpointProbePropagatesCancellationInsteadOfRecordingTransportFailure() async throws {
        let transport = RecordingRemoteProviderTransport(error: CancellationError())
        let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { 1 })

        await #expect(throws: CancellationError.self) {
            _ = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "cancelled-endpoint",
                    providerKind: "openai-compatible",
                    baseURL: "https://api.example.test/v1",
                    apiKey: ""
                )
            )
        }
    }

    @Test("endpoint probe receipt encodes stable snake case JSON")
    func endpointProbeReceiptEncodesStableSnakeCaseJSON() throws {
        let receipt = ProviderEndpointHealthReceipt(
            endpointID: "openai-main",
            providerKind: "openai-compatible",
            baseURLRedacted: "https://api.example.test/v1",
            modelCount: 2,
            capabilities: ProviderEndpointCapabilities(
                chat: true,
                streaming: true,
                tools: true,
                structuredOutput: true,
                embeddings: false
            ),
            latencyMS: 42,
            failureReason: ""
        )

        let object = try receipt.jsonObject(encoder: JSONEncoder())
        let capabilities = try #require(object["capabilities"] as? [String: Any])

        #expect(object["schema_version"] as? String == "melix.provider_endpoint_health.v1")
        #expect(object["endpoint_id"] as? String == "openai-main")
        #expect(object["provider_kind"] as? String == "openai-compatible")
        #expect(object["base_url_redacted"] as? String == "https://api.example.test/v1")
        #expect(object["model_count"] as? Int == 2)
        #expect(object["latency_ms"] as? Int == 42)
        #expect(object["failure_reason"] as? String == "")
        #expect(capabilities["chat"] as? Bool == true)
        #expect(capabilities["streaming"] as? Bool == true)
        #expect(capabilities["tools"] as? Bool == true)
        #expect(capabilities["structured_output"] as? Bool == true)
        #expect(capabilities["embeddings"] as? Bool == false)
    }

    @Test("endpoint probe default clock records elapsed latency")
    func endpointProbeDefaultClockRecordsElapsedLatency() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(#"{ "data": [{ "id": "gpt-4.1", "object": "model" }] }"#.utf8)
        ))
        let probe = ProviderEndpointHealthProbe(transport: transport)

        let receipt = try await probe.probe(
            ProviderEndpointProbeRequest(
                endpointID: "openai-main",
                providerKind: "openai-compatible",
                baseURL: "https://api.example.test/v1/",
                apiKey: "",
                timeoutSeconds: 0
            )
        )

        #expect(receipt.latencyMS >= 0)
        #expect(await transport.lastRequest?.timeoutInterval == 30)
    }

    @Test("parses OpenAI compatible non streaming chat completion")
    func parsesOpenAICompatibleNonStreamingChatCompletion() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(
                #"{ "choices": [{ "message": { "content": "remote answer" }, "finish_reason": "stop" }], "usage": { "prompt_tokens": 5, "completion_tokens": 2 } }"#
                    .utf8
            )
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        let result = try await client.complete(
            RemoteProviderChatRequest(
                serverID: "sub2api",
                providerKind: "openai-compatible",
                baseURL: "https://sub2api.example/v1",
                apiKey: "sk-secret",
                modelID: "gemini-2.5-flash",
                messages: [.init(role: "user", content: "hello")],
                stream: false,
                timeoutSeconds: 30
            )
        )

        #expect(result.assistantText == "remote answer")
        #expect(result.finishReason == "stop")
        #expect(result.promptTokens == 5)
        #expect(result.completionTokens == 2)
        #expect(await transport.lastRequest?.url?.absoluteString == "https://sub2api.example/v1/chat/completions")
        #expect(await transport.lastRequest?.value(forHTTPHeaderField: "Authorization") == "Bearer sk-secret")
        #expect(await transport.lastRequest?.value(forHTTPHeaderField: "User-Agent")?.contains("Melix") == true)
        #expect(await transport.lastRequest?.value(forHTTPHeaderField: "Accept") == "application/json")
        #expect(await transport.lastBodyString?.contains(#""model":"gemini-2.5-flash""#) == true)
        #expect(await transport.lastBodyString?.contains(#""stream":false"#) == true)
    }

    @Test("parses OpenAI compatible SSE chat completion")
    func parsesOpenAICompatibleSSEChatCompletion() async throws {
        let body = """
        data: {"choices":[{"delta":{"content":"hello "},"finish_reason":null}]}

        data: {"choices":[{"delta":{"content":"world"},"finish_reason":"stop"}],"usage":{"prompt_tokens":4,"completion_tokens":2}}

        data: [DONE]

        """
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "text/event-stream"],
            body: Data(body.utf8)
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "sub2api",
                providerKind: "openai-compatible",
                baseURL: "https://sub2api.example/v1/",
                apiKey: "sk-secret",
                modelID: "kimi-2.6",
                messages: [.init(role: "user", content: "hello")],
                stream: true,
                timeoutSeconds: 30
            )
        )
        var events: [RemoteProviderChatStreamEvent] = []
        for try await event in stream {
            events.append(event)
        }

        #expect(events == [
            .tokenDelta("hello "),
            .tokenDelta("world"),
            .usage(promptTokens: 4, completionTokens: 2),
            .completed(finishReason: "stop", assistantText: "hello world"),
        ])
        #expect(await transport.lastBodyString?.contains(#""stream":true"#) == true)
    }

    @Test("parses Gemini generateContent chat completion")
    func parsesGeminiGenerateContentChatCompletion() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(
                #"{ "candidates": [{ "content": { "parts": [{ "text": "gemini answer" }] }, "finishReason": "STOP" }], "usageMetadata": { "promptTokenCount": 7, "candidatesTokenCount": 3 } }"#
                    .utf8
            )
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        let result = try await client.complete(
            RemoteProviderChatRequest(
                serverID: "gemini",
                providerKind: "gemini-generative-language",
                baseURL: "https://generativelanguage.googleapis.com/v1beta/",
                apiKey: "AIza-secret",
                modelID: "gemini-2.5-flash",
                messages: [
                    .init(role: "system", content: "Be terse."),
                    .init(role: "user", content: "hello"),
                    .init(role: "assistant", content: "hi"),
                    .init(role: "user", content: "continue"),
                ],
                stream: false,
                timeoutSeconds: 30
            )
        )

        #expect(result.assistantText == "gemini answer")
        #expect(result.finishReason == "stop")
        #expect(result.promptTokens == 7)
        #expect(result.completionTokens == 3)
        #expect(await transport.lastRequest?.url?.absoluteString == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIza-secret")
        #expect(await transport.lastRequest?.value(forHTTPHeaderField: "Authorization") == nil)
        let bodyString = try #require(await transport.lastBodyString)
        let bodyData = try #require(bodyString.data(using: .utf8))
        let body = try #require(JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
        let systemInstruction = try #require(body["systemInstruction"] as? [String: Any])
        let systemParts = try #require(systemInstruction["parts"] as? [[String: Any]])
        let contents = try #require(body["contents"] as? [[String: Any]])
        #expect(systemParts.first?["text"] as? String == "Be terse.")
        #expect(contents.map { $0["role"] as? String } == ["user", "model", "user"])
    }

    @Test("Gemini stream falls back to generateContent and maps usage")
    func geminiStreamFallsBackToGenerateContentAndMapsUsage() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(
                #"{ "candidates": [{ "content": { "parts": [{ "text": "gemini streamed" }] }, "finishReason": "MAX_TOKENS" }], "usageMetadata": { "promptTokenCount": "8", "candidatesTokenCount": 2.0 } }"#
                    .utf8
            )
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "gemini",
                providerKind: "gemini-generative-language",
                baseURL: "https://generativelanguage.googleapis.com/v1beta",
                apiKey: "AIza-secret",
                modelID: "models/gemini-2.5-flash",
                messages: [
                    .init(role: "system", content: " "),
                    .init(role: "user", content: "hello"),
                ],
                stream: true
            )
        )
        var events: [RemoteProviderChatStreamEvent] = []
        for try await event in stream {
            events.append(event)
        }

        #expect(events == [
            .tokenDelta("gemini streamed"),
            .usage(promptTokens: 8, completionTokens: 2),
            .completed(finishReason: "length", assistantText: "gemini streamed"),
        ])
        #expect(await transport.lastRequest?.url?.absoluteString == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIza-secret")
        #expect(await transport.lastBodyString?.contains("systemInstruction") == false)
    }

    @Test("Gemini completion preserves provider specific finish reasons")
    func geminiCompletionPreservesProviderSpecificFinishReasons() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(
                #"{ "candidates": [{ "content": { "parts": [{ "text": "blocked" }] }, "finishReason": "SAFETY" }] }"#
                    .utf8
            )
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        let result = try await client.complete(
            RemoteProviderChatRequest(
                serverID: "gemini",
                providerKind: "gemini-generative-language",
                baseURL: "https://generativelanguage.googleapis.com/v1beta",
                apiKey: "AIza-secret",
                modelID: "gemini-2.5-flash",
                messages: [.init(role: "user", content: "hello")],
                stream: false
            )
        )

        #expect(result.assistantText == "blocked")
        #expect(result.finishReason == "safety")
        #expect(result.promptTokens == 0)
        #expect(result.completionTokens == 0)
    }

    @Test("provider and malformed response errors are readable")
    func providerAndMalformedResponseErrorsAreReadable() async throws {
        let providerErrorTransport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 429,
            headers: [:],
            body: Data("rate limited".utf8)
        ))
        let providerErrorClient = OpenAICompatibleRemoteProviderClient(transport: providerErrorTransport)

        await #expect(throws: RemoteProviderError.provider(statusCode: 429, message: "rate limited")) {
            try await providerErrorClient.complete(
                RemoteProviderChatRequest(
                    serverID: "sub2api",
                    providerKind: "openai-compatible",
                    baseURL: "https://sub2api.example/v1",
                    apiKey: "sk-secret",
                    modelID: "model",
                    messages: [.init(role: "user", content: "hello")],
                    stream: false
                )
            )
        }

        let malformedClient = OpenAICompatibleRemoteProviderClient(transport: RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: [:],
            body: Data("[]".utf8)
        )))
        await #expect(throws: RemoteProviderError.invalidResponse("remote provider response was not a JSON object")) {
            try await malformedClient.complete(
                RemoteProviderChatRequest(
                    serverID: "sub2api",
                    providerKind: "openai-compatible",
                    baseURL: "https://sub2api.example/v1",
                    apiKey: "sk-secret",
                    modelID: "model",
                    messages: [.init(role: "user", content: "hello")],
                    stream: false
                )
            )
        }

        let missingChoicesClient = OpenAICompatibleRemoteProviderClient(transport: RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: [:],
            body: Data(#"{ "choices": [] }"#.utf8)
        )))
        await #expect(throws: RemoteProviderError.invalidResponse("remote provider response did not include choices")) {
            try await missingChoicesClient.complete(
                RemoteProviderChatRequest(
                    serverID: "sub2api",
                    providerKind: "openai-compatible",
                    baseURL: "https://sub2api.example/v1",
                    apiKey: "sk-secret",
                    modelID: "model",
                    messages: [.init(role: "user", content: "hello")],
                    stream: false
                )
            )
        }

        let missingCandidatesClient = OpenAICompatibleRemoteProviderClient(transport: RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: [:],
            body: Data(#"{ "candidates": [] }"#.utf8)
        )))
        await #expect(throws: RemoteProviderError.invalidResponse("remote provider response did not include candidates")) {
            try await missingCandidatesClient.complete(
                RemoteProviderChatRequest(
                    serverID: "gemini",
                    providerKind: "gemini-generative-language",
                    baseURL: "https://generativelanguage.googleapis.com/v1beta",
                    apiKey: "AIza-secret",
                    modelID: "gemini-2.5-flash",
                    messages: [.init(role: "user", content: "hello")],
                    stream: false
                )
            )
        }

        let emptyBaseURLClient = OpenAICompatibleRemoteProviderClient(transport: RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: [:],
            body: Data()
        )))
        await #expect(throws: RemoteProviderError.invalidRequest("remote provider base_url is empty")) {
            try await emptyBaseURLClient.complete(
                RemoteProviderChatRequest(
                    serverID: "sub2api",
                    providerKind: "openai-compatible",
                    baseURL: " ",
                    apiKey: "sk-secret",
                    modelID: "model",
                    messages: [.init(role: "user", content: "hello")],
                    stream: false
                )
            )
        }
    }

    @Test("unsupported provider kind returns readable error")
    func unsupportedProviderKindReturnsReadableError() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: [:],
            body: Data()
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        do {
            _ = try await client.complete(
                RemoteProviderChatRequest(
                    serverID: "unsupported",
                    providerKind: "not-supported",
                    baseURL: "https://provider.example/v1",
                    apiKey: "sk-secret",
                    modelID: "model",
                    messages: [.init(role: "user", content: "hello")],
                    stream: false
                )
            )
            Issue.record("Expected unsupported provider error")
        } catch let error as RemoteProviderError {
            #expect(error.description.contains("unsupported remote provider kind: not-supported"))
        }
    }
}

private actor RecordingRemoteProviderTransport: RemoteProviderHTTPTransport {
    struct Response {
        let statusCode: Int
        let headers: [String: String]
        let body: Data
    }

    private let response: Response?
    private let error: Error?
    private(set) var lastRequest: URLRequest?
    private(set) var lastBodyString: String?

    init(response: Response) {
        self.response = response
        self.error = nil
    }

    init(error: Error) {
        self.response = nil
        self.error = error
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        lastRequest = request
        lastBodyString = request.httpBody.map { String(decoding: $0, as: UTF8.self) }
        if let error {
            throw error
        }
        let response = try #require(response)
        let httpResponse = HTTPURLResponse(
            url: request.url ?? URL(string: "https://sub2api.example/v1/chat/completions")!,
            statusCode: response.statusCode,
            httpVersion: "HTTP/1.1",
            headerFields: response.headers
        )!
        return (response.body, httpResponse)
    }
}

private final class StepLatencyClock: @unchecked Sendable {
    private let lock = NSLock()
    private let values: [UInt64]
    private var index = 0

    init(values: [UInt64]) {
        self.values = values
    }

    func next() -> UInt64 {
        lock.lock()
        defer { lock.unlock() }
        guard values.isEmpty == false else {
            return 0
        }
        let value = values[min(index, values.count - 1)]
        index += 1
        return value
    }
}
