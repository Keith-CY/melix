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

    @Test("endpoint probe records redacted model list URL classification receipts")
    func endpointProbeRecordsRedactedModelListURLClassificationReceipts() async throws {
        let cases: [
            (
                providerKind: String,
                baseURL: String,
                apiKey: String,
                responseBody: String,
                expectedRequestURL: String,
                expectedBaseURLRedacted: String,
                expectedNormalizedBaseKind: String,
                expectedModelsEndpointKind: String,
                expectedAuthRedacted: Bool,
                expectedFallbackAttempted: Bool
            )
        ] = [
            (
                providerKind: "openai-compatible",
                baseURL: "https://api.example.test",
                apiKey: "",
                responseBody: #"{ "data": [{ "id": "gpt-4.1", "object": "model" }] }"#,
                expectedRequestURL: "https://api.example.test/models",
                expectedBaseURLRedacted: "https://api.example.test",
                expectedNormalizedBaseKind: "base_url",
                expectedModelsEndpointKind: "openai_models",
                expectedAuthRedacted: false,
                expectedFallbackAttempted: true
            ),
            (
                providerKind: "openai-compatible",
                baseURL: "https://api.example.test/v1?api_key=sk-secret",
                apiKey: "sk-secret",
                responseBody: #"{ "data": [{ "id": "gpt-4.1", "object": "model" }] }"#,
                expectedRequestURL: "https://api.example.test/v1/models",
                expectedBaseURLRedacted: "https://api.example.test/v1",
                expectedNormalizedBaseKind: "versioned_base",
                expectedModelsEndpointKind: "openai_models",
                expectedAuthRedacted: true,
                expectedFallbackAttempted: true
            ),
            (
                providerKind: "openai-compatible",
                baseURL: "https://api.example.test/v1/chat/completions#secret",
                apiKey: "",
                responseBody: #"{ "data": [{ "id": "gpt-4.1", "object": "model" }] }"#,
                expectedRequestURL: "https://api.example.test/v1/models",
                expectedBaseURLRedacted: "https://api.example.test/v1",
                expectedNormalizedBaseKind: "chat_completions_endpoint",
                expectedModelsEndpointKind: "openai_models",
                expectedAuthRedacted: true,
                expectedFallbackAttempted: true
            ),
            (
                providerKind: "ollama-native",
                baseURL: "http://127.0.0.1:11434/api/chat",
                apiKey: "",
                responseBody: #"{ "models": [{ "name": "llama3.2" }] }"#,
                expectedRequestURL: "http://127.0.0.1:11434/api/tags",
                expectedBaseURLRedacted: "http://127.0.0.1:11434/api",
                expectedNormalizedBaseKind: "ollama_chat_endpoint",
                expectedModelsEndpointKind: "ollama_tags",
                expectedAuthRedacted: false,
                expectedFallbackAttempted: true
            ),
            (
                providerKind: "ollama-native",
                baseURL: "http://127.0.0.1:11434/api/generate",
                apiKey: "",
                responseBody: #"{ "models": [{ "name": "llama3.2" }] }"#,
                expectedRequestURL: "http://127.0.0.1:11434/api/tags",
                expectedBaseURLRedacted: "http://127.0.0.1:11434/api",
                expectedNormalizedBaseKind: "ollama_generate_endpoint",
                expectedModelsEndpointKind: "ollama_tags",
                expectedAuthRedacted: false,
                expectedFallbackAttempted: true
            ),
            (
                providerKind: "ollama-native",
                baseURL: "http://127.0.0.1:11434/api/tags",
                apiKey: "",
                responseBody: #"{ "models": [{ "name": "llama3.2" }] }"#,
                expectedRequestURL: "http://127.0.0.1:11434/api/tags",
                expectedBaseURLRedacted: "http://127.0.0.1:11434/api",
                expectedNormalizedBaseKind: "ollama_tags_endpoint",
                expectedModelsEndpointKind: "ollama_tags",
                expectedAuthRedacted: false,
                expectedFallbackAttempted: false
            ),
            (
                providerKind: "local-runtime",
                baseURL: "http://127.0.0.1:12436/v1/models",
                apiKey: "",
                responseBody: #"{ "data": [{ "id": "melix-dev-text", "object": "model" }] }"#,
                expectedRequestURL: "http://127.0.0.1:12436/v1/models",
                expectedBaseURLRedacted: "http://127.0.0.1:12436/v1",
                expectedNormalizedBaseKind: "models_endpoint",
                expectedModelsEndpointKind: "local_runtime_models",
                expectedAuthRedacted: false,
                expectedFallbackAttempted: false
            ),
        ]

        for testCase in cases {
            let transport = RecordingRemoteProviderTransport(response: .init(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: Data(testCase.responseBody.utf8)
            ))
            let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { 1 })

            let receipt = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "\(testCase.providerKind)-url-classification",
                    providerKind: testCase.providerKind,
                    baseURL: testCase.baseURL,
                    apiKey: testCase.apiKey
                )
            )

            #expect(await transport.lastRequest?.url?.absoluteString == testCase.expectedRequestURL)
            #expect(receipt.baseURLRedacted == testCase.expectedBaseURLRedacted)
            #expect(receipt.normalizedBaseKind == testCase.expectedNormalizedBaseKind)
            #expect(receipt.modelsEndpointKind == testCase.expectedModelsEndpointKind)
            #expect(receipt.probeStatus == "ok")
            #expect(receipt.authRedacted == testCase.expectedAuthRedacted)
            #expect(receipt.fallbackAttempted == testCase.expectedFallbackAttempted)
            #expect(String(describing: receipt).contains("sk-secret") == false)
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

    @Test("endpoint probe applies explicit tool support mode while preserving detection")
    func endpointProbeAppliesExplicitToolSupportModeWhilePreservingDetection() async throws {
        let responseBody = #"{ "data": [{ "id": "local-model", "object": "model", "capabilities": ["chat"] }] }"#
        let cases: [
            (
                mode: ProviderEndpointToolSupportMode,
                expectedEffectiveToolSupport: Bool,
                expectedDetectedToolSupport: Bool,
                expectedOverrideSource: String
            )
        ] = [
            (.auto, false, false, "probe_detection"),
            (.forceOn, true, false, "endpoint_config"),
            (.forceOff, false, false, "endpoint_config"),
        ]

        for testCase in cases {
            let transport = RecordingRemoteProviderTransport(response: .init(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: Data(responseBody.utf8)
            ))
            let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { 1 })

            let receipt = try await probe.probe(
                ProviderEndpointProbeRequest(
                    endpointID: "local-tools",
                    providerKind: "openai-compatible",
                    baseURL: "http://127.0.0.1:12436/v1",
                    apiKey: "",
                    toolSupportMode: testCase.mode
                )
            )

            #expect(receipt.toolSupportMode == testCase.mode)
            #expect(receipt.detectedToolSupport == testCase.expectedDetectedToolSupport)
            #expect(receipt.overrideSource == testCase.expectedOverrideSource)
            #expect(receipt.lastProbeStatus == "ok")
            #expect(receipt.capabilities.tools == testCase.expectedEffectiveToolSupport)
        }
    }

    @Test("endpoint probe force off suppresses detected tool support")
    func endpointProbeForceOffSuppressesDetectedToolSupport() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(#"{ "data": [{ "id": "tool-model", "object": "model", "capabilities": ["chat", "tools"] }] }"#.utf8)
        ))
        let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { 1 })

        let receipt = try await probe.probe(
            ProviderEndpointProbeRequest(
                endpointID: "local-tools",
                providerKind: "openai-compatible",
                baseURL: "http://127.0.0.1:12436/v1",
                apiKey: "",
                toolSupportMode: .forceOff
            )
        )

        #expect(receipt.toolSupportMode == .forceOff)
        #expect(receipt.detectedToolSupport == true)
        #expect(receipt.capabilities.tools == false)
        #expect(receipt.overrideSource == "endpoint_config")
        #expect(receipt.lastProbeStatus == "ok")
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
            #expect(receipt.toolSupportMode == .auto)
            #expect(receipt.detectedToolSupport == false)
            #expect(receipt.overrideSource == "probe_detection")
            #expect(receipt.lastProbeStatus == testCase.expectedReason)
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
            normalizedBaseKind: "versioned_base",
            modelsEndpointKind: "openai_models",
            probeStatus: "ok",
            authRedacted: true,
            fallbackAttempted: true,
            modelCount: 2,
            capabilities: ProviderEndpointCapabilities(
                chat: true,
                streaming: true,
                tools: true,
                structuredOutput: true,
                embeddings: false
            ),
            toolSupportMode: .forceOn,
            detectedToolSupport: false,
            overrideSource: "endpoint_config",
            lastProbeStatus: "ok",
            latencyMS: 42,
            failureReason: ""
        )

        let object = try receipt.jsonObject(encoder: JSONEncoder())
        let capabilities = try #require(object["capabilities"] as? [String: Any])

        #expect(object["schema_version"] as? String == "melix.provider_endpoint_health.v1")
        #expect(object["endpoint_id"] as? String == "openai-main")
        #expect(object["provider_kind"] as? String == "openai-compatible")
        #expect(object["base_url_redacted"] as? String == "https://api.example.test/v1")
        #expect(object["normalized_base_kind"] as? String == "versioned_base")
        #expect(object["models_endpoint_kind"] as? String == "openai_models")
        #expect(object["probe_status"] as? String == "ok")
        #expect(object["auth_redacted"] as? Bool == true)
        #expect(object["fallback_attempted"] as? Bool == true)
        #expect(object["model_count"] as? Int == 2)
        #expect(object["tool_support_mode"] as? String == "force_on")
        #expect(object["detected_tool_support"] as? Bool == false)
        #expect(object["override_source"] as? String == "endpoint_config")
        #expect(object["last_probe_status"] as? String == "ok")
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

    @Test("parses OpenAI compatible usage-only terminal SSE chunk")
    func parsesOpenAICompatibleUsageOnlyTerminalSSEChunk() async throws {
        let body = """
        data: {"choices":[{"delta":{"content":"remote answer"},"finish_reason":null}]}

        data: {"choices":[{"delta":{},"finish_reason":"stop"}]}

        data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}

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
                serverID: "usage-only-terminal",
                providerKind: "openai-compatible",
                baseURL: "https://usage-only.example/v1",
                apiKey: "sk-secret",
                modelID: "reasoning-model",
                messages: [.init(role: "user", content: "hello")],
                stream: true
            )
        )
        var events: [RemoteProviderChatStreamEvent] = []
        for try await event in stream {
            events.append(event)
        }

        #expect(events == [
            .tokenDelta("remote answer"),
            .usage(promptTokens: 7, completionTokens: 3),
            .completed(finishReason: "stop", assistantText: "remote answer"),
        ])
    }

    @Test("rejects OpenAI compatible SSE chunk without choices or usage")
    func rejectsOpenAICompatibleSSEChunkWithoutChoicesOrUsage() async throws {
        for malformedEvent in [#"{}"#, #"{"choices":[]}"#] {
            let body = """
            data: {"choices":[{"delta":{"content":"partial"},"finish_reason":null}]}

            data: \(malformedEvent)

            data: [DONE]

            """
            let client = OpenAICompatibleRemoteProviderClient(transport: RecordingRemoteProviderTransport(response: .init(
                statusCode: 200,
                headers: ["content-type": "text/event-stream"],
                body: Data(body.utf8)
            )))

            await #expect(throws: RemoteProviderError.invalidResponse("remote provider response did not include choices")) {
                let stream = try await client.stream(
                    RemoteProviderChatRequest(
                        serverID: "malformed-stream",
                        providerKind: "openai-compatible",
                        baseURL: "https://malformed.example/v1",
                        apiKey: "sk-secret",
                        modelID: "model",
                        messages: [.init(role: "user", content: "hello")],
                        stream: true
                    )
                )
                for try await _ in stream {}
            }
        }
    }

    @Test("streams reasoning and fragmented tool identity without mixing assistant text")
    func streamsReasoningAndFragmentedToolIdentityWithoutMixingAssistantText() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "text/event-stream"],
            body: Data(
                (#"""
                data: {"choices":[{"delta":{"reasoning_content":"check "},"finish_reason":null}]}

                data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_","type":"func","function":{"name":"look","arguments":"{\"q\":"}}]},"finish_reason":null}]}

                data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"up","type":"tion","function":{"name":"up","arguments":"\"Kyoto\"}"}}]},"finish_reason":"tool_calls"}]}

                data: [DONE]

                """#).utf8
            )
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "reasoning-tools",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "tool-model",
                messages: [.init(role: "user", content: "Look up Kyoto")],
                tools: [
                    RemoteProviderToolDefinition(
                        name: "lookup",
                        parametersJSON: #"{"type":"object"}"#
                    ),
                ],
                toolChoice: "auto",
                parallelToolCalls: false,
                stream: true,
                enableThinking: true,
                reasoningEffort: "medium"
            )
        )
        var events: [RemoteProviderChatStreamEvent] = []
        for try await event in stream {
            events.append(event)
        }

        #expect(events == [
            .reasoningDelta("check "),
            .toolCallsCompleted([
                RemoteProviderToolCall(
                    callID: "call_up",
                    toolName: "lookup",
                    argumentsJSON: #"{"q":"Kyoto"}"#
                ),
            ]),
            .completed(finishReason: "tool_calls", assistantText: ""),
        ])
        let bodyData = try #require(await transport.lastRequest?.httpBody)
        let body = try #require(JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
        #expect(body["reasoning_effort"] as? String == "medium")
        #expect(body["enable_thinking"] == nil)
        #expect((body["tools"] as? [[String: Any]])?.count == 1)
        #expect((body["stream_options"] as? [String: Bool])?["include_usage"] == true)
    }

    @Test("serializes structured tools, history, and generation controls together")
    func serializesStructuredToolsHistoryAndGenerationControlsTogether() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(
                #"{"choices":[{"message":{"content":"","tool_calls":[{"id":"call_next","type":"function","function":{"name":"lookup","arguments":"{\"query\":\"Kyoto\"}"}}]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":12,"completion_tokens":4}}"#.utf8
            )
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)
        let priorCall = RemoteProviderToolCall(
            callID: "call_prior",
            toolName: "lookup",
            argumentsJSON: #"{"query":"Tokyo"}"#
        )

        let result = try await client.complete(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "tool-model",
                messages: [
                    .init(role: "user", content: "Look it up"),
                    .init(role: "assistant", content: "", toolCalls: [priorCall]),
                    .init(
                        role: "tool",
                        content: #"{"temperature":22}"#,
                        name: "lookup",
                        toolCallID: "call_prior"
                    ),
                ],
                tools: [
                    RemoteProviderToolDefinition(
                        name: "lookup",
                        description: "Look up a city",
                        parametersJSON: #"{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}"#
                    ),
                ],
                toolChoice: "auto",
                parallelToolCalls: false,
                stream: false,
                enableThinking: false,
                reasoningEffort: "none",
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )

        #expect(result.finishReason == "tool_calls")
        #expect(result.toolCalls == [
            RemoteProviderToolCall(
                callID: "call_next",
                toolName: "lookup",
                argumentsJSON: #"{"query":"Kyoto"}"#
            ),
        ])

        let bodyData = try #require(await transport.lastRequest?.httpBody)
        let body = try #require(JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
        let messages = try #require(body["messages"] as? [[String: Any]])
        let assistantToolCalls = try #require(messages[1]["tool_calls"] as? [[String: Any]])
        let assistantFunction = try #require(assistantToolCalls[0]["function"] as? [String: Any])
        let tools = try #require(body["tools"] as? [[String: Any]])
        let toolFunction = try #require(tools[0]["function"] as? [String: Any])
        let parameters = try #require(toolFunction["parameters"] as? [String: Any])

        #expect(assistantToolCalls[0]["id"] as? String == "call_prior")
        #expect(assistantFunction["arguments"] as? String == #"{"query":"Tokyo"}"#)
        #expect(messages[2]["tool_call_id"] as? String == "call_prior")
        #expect(messages[2]["name"] as? String == "lookup")
        #expect(toolFunction["name"] as? String == "lookup")
        #expect(parameters["type"] as? String == "object")
        #expect(body["tool_choice"] as? String == "auto")
        #expect(body["parallel_tool_calls"] as? Bool == false)
        #expect(body["enable_thinking"] as? Bool == false)
        #expect(body["reasoning_effort"] as? String == "none")
        #expect(body["temperature"] as? Double == 0.2)
        #expect(body["top_p"] as? Double == 0.9)
        #expect(body["max_tokens"] as? Int == 128)
    }

    @Test("omits enable_thinking unless thinking is explicitly disabled")
    func omitsEnableThinkingUnlessThinkingIsExplicitlyDisabled() async throws {
        for enableThinking in [nil, true] as [Bool?] {
            let transport = RecordingRemoteProviderTransport(response: .init(
                statusCode: 200,
                headers: ["content-type": "application/json"],
                body: Data(
                    #"{ "choices": [{ "message": { "content": "OK." }, "finish_reason": "stop" }] }"#
                        .utf8
                )
            ))
            let client = OpenAICompatibleRemoteProviderClient(transport: transport)

            _ = try await client.complete(
                RemoteProviderChatRequest(
                    serverID: "strict-endpoint",
                    providerKind: "openai-compatible",
                    baseURL: "https://strict.example/v1",
                    apiKey: "sk-secret",
                    modelID: "gpt-5",
                    messages: [.init(role: "user", content: "Reply with exactly OK.")],
                    stream: false,
                    enableThinking: enableThinking
                )
            )

            let bodyData = try #require(await transport.lastRequest?.httpBody)
            let body = try #require(JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
            #expect(body["enable_thinking"] == nil)
            #expect(body["reasoning_effort"] == nil)
            #expect(body["temperature"] == nil)
            #expect(body["top_p"] == nil)
            #expect(body["max_tokens"] == nil)
        }
    }

    @Test("streams incrementally and accumulates fragmented tool calls")
    func streamsIncrementallyAndAccumulatesFragmentedToolCalls() async throws {
        let transport = ControlledRemoteProviderStreamingTransport()
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)
        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "tool-model",
                messages: [.init(role: "user", content: "weather")],
                tools: [
                    RemoteProviderToolDefinition(
                        name: "weather",
                        parametersJSON: #"{"type":"object"}"#
                    ),
                ],
                stream: true
            )
        )
        var iterator = stream.makeAsyncIterator()

        await transport.yield(
            #"data: {"choices":[{"delta":{"content":"checking "},"finish_reason":null}]}"# + "\n\n"
        )
        #expect(try await iterator.next() == .tokenDelta("checking "))

        await transport.yield(
            #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_weather","type":"function","function":{"name":"weather","arguments":"{\"city\":"}}]},"finish_reason":null}]}"# + "\n\n"
        )
        await transport.yield(
            #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\"Tokyo\"}"}}]},"finish_reason":"tool_calls"}]}"# + "\n\n"
        )
        #expect(
            try await iterator.next() == .toolCallDelta(
                RemoteProviderToolCallDelta(
                    index: 0,
                    callID: "call_weather",
                    toolName: "weather",
                    argumentsFragment: #"{"city":"Tokyo"}"#
                )
            )
        )

        await transport.yield(
            #"data: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":3}}"# + "\n\n"
        )
        #expect(try await iterator.next() == .usage(promptTokens: 9, completionTokens: 3))

        await transport.yield("data: [DONE]\n\n")
        #expect(
            try await iterator.next() == .toolCallsCompleted([
                RemoteProviderToolCall(
                    callID: "call_weather",
                    toolName: "weather",
                    argumentsJSON: #"{"city":"Tokyo"}"#
                ),
            ])
        )
        #expect(
            try await iterator.next() == .completed(
                finishReason: "tool_calls",
                assistantText: "checking "
            )
        )
        #expect(try await iterator.next() == nil)

        let requestBody = try #require(await transport.lastRequest?.httpBody)
        let requestObject = try #require(JSONSerialization.jsonObject(with: requestBody) as? [String: Any])
        let streamOptions = try #require(requestObject["stream_options"] as? [String: Any])
        #expect(streamOptions["include_usage"] as? Bool == true)
    }

    @Test("buffers tool arguments until fragmented identity is complete")
    func buffersToolArgumentsUntilFragmentedIdentityIsComplete() async throws {
        let transport = ControlledRemoteProviderStreamingTransport()
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)
        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "tool-model",
                messages: [.init(role: "user", content: "weather")],
                tools: [
                    RemoteProviderToolDefinition(
                        name: "weather",
                        parametersJSON: #"{"type":"object"}"#
                    ),
                ],
                stream: true
            )
        )
        let collector = Task {
            var events: [RemoteProviderChatStreamEvent] = []
            for try await event in stream {
                events.append(event)
            }
            return events
        }

        await transport.yield(
            #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_","function":{"arguments":"{\"city\":"}}]},"finish_reason":null}]}"#
                + "\n\n"
        )
        await transport.yield(
            #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"weather","function":{"name":"wea","arguments":"\"Tokyo\""}}]},"finish_reason":null}]}"#
                + "\n\n"
        )
        await transport.yield(
            #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"ther"}}]},"finish_reason":null}]}"#
                + "\n\n"
        )
        await transport.yield(
            #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"}"}}]},"finish_reason":"tool_calls"}]}"#
                + "\n\n"
        )
        await transport.yield("data: [DONE]\n\n")

        let events = try await collector.value
        #expect(events.first == .toolCallDelta(
            RemoteProviderToolCallDelta(
                index: 0,
                callID: "call_weather",
                toolName: "weather",
                argumentsFragment: #"{"city":"Tokyo"}"#
            )
        ))
        #expect(events.contains(.toolCallsCompleted([
            RemoteProviderToolCall(
                callID: "call_weather",
                toolName: "weather",
                argumentsJSON: #"{"city":"Tokyo"}"#
            ),
        ])))
    }

    @Test("stream termination cancels the underlying transport")
    func streamTerminationCancelsUnderlyingTransport() async throws {
        let transport = ControlledRemoteProviderStreamingTransport()
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)
        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "model",
                messages: [.init(role: "user", content: "hello")],
                stream: true
            )
        )
        let consumer = Task {
            for try await _ in stream {}
        }
        await Task.yield()
        consumer.cancel()
        _ = await consumer.result

        for _ in 0..<1_000 where transport.cancellationProbe.wasMarked == false {
            await Task.yield()
        }
        #expect(transport.cancellationProbe.wasMarked)
    }

    @Test("URLSession streaming cancellation cancels its data task")
    func urlSessionStreamingCancellationCancelsItsDataTask() async throws {
        RemoteProviderHoldingURLProtocol.state.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RemoteProviderHoldingURLProtocol.self]
        let transport = URLSessionRemoteProviderHTTPTransport(
            streamingConfiguration: configuration
        )
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)
        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://streaming.example.test/v1",
                apiKey: "secret",
                modelID: "model",
                messages: [.init(role: "user", content: "hello")],
                stream: true
            )
        )
        var iterator = stream.makeAsyncIterator()
        #expect(try await iterator.next() == .tokenDelta("first"))

        let consumer = Task {
            while try await iterator.next() != nil {}
        }
        await Task.yield()
        consumer.cancel()
        _ = await consumer.result

        for _ in 0..<100 where RemoteProviderHoldingURLProtocol.state.wasStopped == false {
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(RemoteProviderHoldingURLProtocol.state.wasStopped)
    }

    @Test("URLSession transport supports buffered data and normally completed streams")
    func urlSessionTransportSupportsBufferedDataAndNormallyCompletedStreams() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RemoteProviderCompletingURLProtocol.self]
        let bufferedSession = URLSession(configuration: configuration)
        let transport = URLSessionRemoteProviderHTTPTransport(
            bufferedSession: bufferedSession,
            streamingConfiguration: configuration
        )
        let url = try #require(URL(string: "https://completing.example.test/v1/chat/completions"))
        let (data, response) = try await transport.data(for: URLRequest(url: url))
        #expect(response.statusCode == 200)
        #expect(data.isEmpty == false)

        let client = OpenAICompatibleRemoteProviderClient(transport: transport)
        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://completing.example.test/v1",
                apiKey: "secret",
                modelID: "model",
                messages: [.init(role: "user", content: "hello")],
                stream: true
            )
        )
        var events: [RemoteProviderChatStreamEvent] = []
        for try await event in stream {
            events.append(event)
        }
        #expect(events == [
            .tokenDelta("complete"),
            .completed(finishReason: "stop", assistantText: "complete"),
        ])
    }

    @Test("cancelling before URLSession response headers aborts the data task")
    func cancellingBeforeURLSessionResponseHeadersAbortsTheDataTask() async throws {
        RemoteProviderNoResponseURLProtocol.state.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RemoteProviderNoResponseURLProtocol.self]
        let transport = URLSessionRemoteProviderHTTPTransport(
            streamingConfiguration: configuration
        )
        let request = URLRequest(
            url: try #require(URL(string: "https://no-response.example.test/chat/completions"))
        )
        let task = Task {
            try await transport.stream(for: request)
        }
        await Task.yield()
        task.cancel()
        let result = await task.result
        if case .success = result {
            Issue.record("Expected response-header wait to be cancelled")
        }

        for _ in 0..<100 where RemoteProviderNoResponseURLProtocol.state.wasStopped == false {
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(RemoteProviderNoResponseURLProtocol.state.wasStopped)
    }

    @Test("streaming provider failures and malformed tool shapes fail closed")
    func streamingProviderFailuresAndMalformedToolShapesFailClosed() async throws {
        let providerErrorClient = OpenAICompatibleRemoteProviderClient(
            transport: RecordingRemoteProviderTransport(response: .init(
                statusCode: 429,
                headers: ["content-type": "application/json"],
                body: Data("rate limited".utf8)
            ))
        )
        await #expect(throws: RemoteProviderError.provider(statusCode: 429, message: "rate limited")) {
            _ = try await providerErrorClient.stream(
                RemoteProviderChatRequest(
                    serverID: "remote",
                    providerKind: "openai-compatible",
                    baseURL: "https://provider.example/v1",
                    apiKey: "secret",
                    modelID: "model",
                    messages: [.init(role: "user", content: "hello")],
                    stream: true
                )
            )
        }

        for body in [
            #"{"choices":[{"message":{"tool_calls":{}},"finish_reason":"tool_calls"}]}"#,
            #"{"choices":[{"message":{"tool_calls":[{"id":"","function":{"name":"lookup","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}"#,
            #"{"choices":[{"message":{"tool_calls":[{"id":"duplicate","function":{"name":"lookup","arguments":"{}"}},{"id":"duplicate","function":{"name":"lookup","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}"#,
        ] {
            let client = OpenAICompatibleRemoteProviderClient(
                transport: RecordingRemoteProviderTransport(response: .init(
                    statusCode: 200,
                    headers: ["content-type": "application/json"],
                    body: Data(body.utf8)
                ))
            )
            await #expect(throws: RemoteProviderError.self) {
                _ = try await client.complete(
                    RemoteProviderChatRequest(
                        serverID: "remote",
                        providerKind: "openai-compatible",
                        baseURL: "https://provider.example/v1",
                        apiKey: "secret",
                        modelID: "model",
                        messages: [.init(role: "user", content: "hello")],
                        stream: false
                    )
                )
            }
        }
    }

    @Test("tool request validation rejects invalid schemas and unsupported Gemini history")
    func toolRequestValidationRejectsInvalidSchemasAndUnsupportedGeminiHistory() async throws {
        let transport = RecordingRemoteProviderTransport(response: .init(
            statusCode: 200,
            headers: ["content-type": "application/json"],
            body: Data(#"{"choices":[{"message":{},"finish_reason":null}]}"#.utf8)
        ))
        let client = OpenAICompatibleRemoteProviderClient(transport: transport)

        for tool in [
            RemoteProviderToolDefinition(name: " ", parametersJSON: #"{"type":"object"}"#),
            RemoteProviderToolDefinition(name: "lookup", parametersJSON: "[]"),
        ] {
            await #expect(throws: RemoteProviderError.self) {
                _ = try await client.complete(
                    RemoteProviderChatRequest(
                        serverID: "remote",
                        providerKind: "openai-compatible",
                        baseURL: "https://provider.example/v1",
                        apiKey: "secret",
                        modelID: "model",
                        messages: [.init(role: "user", content: "hello")],
                        tools: [tool],
                        stream: false,
                        timeoutSeconds: 0
                    )
                )
            }
        }

        await #expect(throws: RemoteProviderError.invalidRequest(
            "structured tools are currently supported only by openai-compatible remote providers"
        )) {
            _ = try await client.complete(
                RemoteProviderChatRequest(
                    serverID: "gemini",
                    providerKind: "gemini-generative-language",
                    baseURL: "https://generativelanguage.googleapis.com/v1beta",
                    apiKey: "secret",
                    modelID: "gemini",
                    messages: [
                        .init(
                            role: "tool",
                            content: "{}",
                            toolCallID: "call-1"
                        ),
                    ],
                    stream: false
                )
            )
        }

        await #expect(throws: RemoteProviderError.invalidRequest("remote provider base_url is empty")) {
            _ = try await client.complete(
                RemoteProviderChatRequest(
                    serverID: "gemini",
                    providerKind: "gemini-generative-language",
                    baseURL: " ",
                    apiKey: "secret",
                    modelID: "gemini",
                    messages: [.init(role: "user", content: "hello")],
                    stream: false,
                    timeoutSeconds: 0
                )
            )
        }

        let completion = try await client.complete(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "model",
                messages: [.init(role: "user", content: "hello")],
                stream: false,
                timeoutSeconds: 0
            )
        )
        #expect(completion.assistantText == "")
        #expect(completion.finishReason == "stop")
        #expect(completion.promptTokens == 0)
        #expect(completion.completionTokens == 0)
        #expect(await transport.lastRequest?.timeoutInterval == 60)
    }

    @Test("SSE accepts CRLF comments and terminal finish without done marker")
    func sseAcceptsCRLFCommentsAndTerminalFinishWithoutDoneMarker() async throws {
        let body = ": keepalive\r\nid: ignored\r\n" +
            #"data: {"choices":[{"delta":{"content":"done"},"finish_reason":"stop"}]}"#
        let client = OpenAICompatibleRemoteProviderClient(
            transport: RecordingRemoteProviderTransport(response: .init(
                statusCode: 200,
                headers: ["content-type": "text/event-stream"],
                body: Data(body.utf8)
            ))
        )
        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "model",
                messages: [.init(role: "user", content: "hello")],
                stream: true
            )
        )
        var events: [RemoteProviderChatStreamEvent] = []
        for try await event in stream {
            events.append(event)
        }
        #expect(events == [
            .tokenDelta("done"),
            .completed(finishReason: "stop", assistantText: "done"),
        ])
    }

    @Test("malformed SSE variants fail without emitting a terminal event")
    func malformedSSEVariantsFailWithoutEmittingATerminalEvent() async throws {
        let bodies = [
            "data: []\n\n",
            #"data: {"usage":{}}"# + "\n\n",
            #"data: {"choices":[{"delta":{"tool_calls":{}},"finish_reason":null}]}"# + "\n\n",
            #"data: {"choices":[{"delta":{"tool_calls":[{"index":-1,"function":{"name":"x","arguments":"{}"}}]},"finish_reason":null}]}"# + "\n\n",
            (
                #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_","function":{"name":"look","arguments":"{\"q\":"}}]},"finish_reason":null}]}"# + "\n\n"
                    + #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\"Kyoto\""}}]},"finish_reason":null}]}"# + "\n\n"
                    + #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"up","function":{"name":"up","arguments":"}"}}]},"finish_reason":"tool_calls"}]}"# + "\n\n"
            ),
            (
                #"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"duplicate","function":{"name":"first","arguments":"{}"}},{"index":1,"id":"duplicate","function":{"name":"second","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}"#
                    + "\n\ndata: [DONE]\n\n"
            ),
            #"data: {"choices":[{"delta":{"content":"unterminated"},"finish_reason":null}]}"# + "\n\n",
        ]

        for body in bodies {
            let client = OpenAICompatibleRemoteProviderClient(
                transport: RecordingRemoteProviderTransport(response: .init(
                    statusCode: 200,
                    headers: ["content-type": "text/event-stream"],
                    body: Data(body.utf8)
                ))
            )
            let stream = try await client.stream(
                RemoteProviderChatRequest(
                    serverID: "remote",
                    providerKind: "openai-compatible",
                    baseURL: "https://provider.example/v1",
                    apiKey: "secret",
                    modelID: "model",
                    messages: [.init(role: "user", content: "hello")],
                    stream: true
                )
            )
            do {
                for try await _ in stream {}
                Issue.record("Expected malformed SSE to fail")
            } catch {
                #expect(error is RemoteProviderError)
            }
        }
    }

    @Test("SSE rejects an oversized transport chunk before buffering it")
    func sseRejectsOversizedTransportChunkBeforeBuffering() async throws {
        let oversized = Data(repeating: 0x61, count: 1_048_577)
        let client = OpenAICompatibleRemoteProviderClient(
            transport: RecordingRemoteProviderTransport(response: .init(
                statusCode: 200,
                headers: ["content-type": "text/event-stream"],
                body: oversized
            ))
        )
        let stream = try await client.stream(
            RemoteProviderChatRequest(
                serverID: "remote",
                providerKind: "openai-compatible",
                baseURL: "https://provider.example/v1",
                apiKey: "secret",
                modelID: "model",
                messages: [.init(role: "user", content: "hello")],
                stream: true
            )
        )
        do {
            for try await _ in stream {}
            Issue.record("Expected oversized SSE transport to fail")
        } catch let error as RemoteProviderError {
            #expect(
                error.description.contains("bounded transport budget")
            )
        }
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

private actor ControlledRemoteProviderStreamingTransport: RemoteProviderHTTPTransport {
    nonisolated let cancellationProbe = RemoteProviderCancellationProbe()

    private let body: AsyncThrowingStream<Data, Error>
    private let continuation: AsyncThrowingStream<Data, Error>.Continuation
    private(set) var lastRequest: URLRequest?

    init() {
        let pair = AsyncThrowingStream<Data, Error>.makeStream()
        body = pair.stream
        continuation = pair.continuation
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        throw RemoteProviderError.invalidRequest("buffered transport was not expected")
    }

    func stream(for request: URLRequest) async throws -> RemoteProviderHTTPResponseStream {
        lastRequest = request
        let continuation = self.continuation
        let cancellationProbe = self.cancellationProbe
        return RemoteProviderHTTPResponseStream(
            response: HTTPURLResponse(
                url: request.url ?? URL(string: "https://provider.example/v1/chat/completions")!,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: ["content-type": "text/event-stream"]
            )!,
            body: body,
            cancel: {
                cancellationProbe.mark()
                continuation.finish(throwing: CancellationError())
            }
        )
    }

    func yield(_ text: String) {
        continuation.yield(Data(text.utf8))
    }
}

private final class RemoteProviderCancellationProbe: @unchecked Sendable {
    private let lock = NSLock()
    private var marked = false

    var wasMarked: Bool {
        lock.lock()
        defer { lock.unlock() }
        return marked
    }

    func mark() {
        lock.lock()
        marked = true
        lock.unlock()
    }
}

private final class RemoteProviderHoldingURLProtocolState: @unchecked Sendable {
    private let lock = NSLock()
    private var stopped = false

    var wasStopped: Bool {
        lock.lock()
        defer { lock.unlock() }
        return stopped
    }

    func reset() {
        lock.lock()
        stopped = false
        lock.unlock()
    }

    func markStopped() {
        lock.lock()
        stopped = true
        lock.unlock()
    }
}

private final class RemoteProviderHoldingURLProtocol: URLProtocol, @unchecked Sendable {
    static let state = RemoteProviderHoldingURLProtocolState()

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "streaming.example.test"
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        guard let url = request.url,
              let response = HTTPURLResponse(
                  url: url,
                  statusCode: 200,
                  httpVersion: "HTTP/1.1",
                  headerFields: ["content-type": "text/event-stream"]
              )
        else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(
            self,
            didLoad: Data(
                (#"data: {"choices":[{"delta":{"content":"first"},"finish_reason":null}]}"# + "\n\n").utf8
            )
        )
    }

    override func stopLoading() {
        Self.state.markStopped()
    }
}

private final class RemoteProviderCompletingURLProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "completing.example.test"
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        guard let url = request.url,
              let response = HTTPURLResponse(
                  url: url,
                  statusCode: 200,
                  httpVersion: "HTTP/1.1",
                  headerFields: ["content-type": "text/event-stream"]
              )
        else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(
            self,
            didLoad: Data(
                (#"data: {"choices":[{"delta":{"content":"complete"},"finish_reason":"stop"}]}"# + "\n\n").utf8
            )
        )
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private final class RemoteProviderNoResponseURLProtocol: URLProtocol, @unchecked Sendable {
    static let state = RemoteProviderHoldingURLProtocolState()

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "no-response.example.test"
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {}

    override func stopLoading() {
        Self.state.markStopped()
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
