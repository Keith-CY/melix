import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Remote Provider Client")
struct RemoteProviderClientTests {
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

    private let response: Response
    private(set) var lastRequest: URLRequest?
    private(set) var lastBodyString: String?

    init(response: Response) {
        self.response = response
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        lastRequest = request
        lastBodyString = request.httpBody.map { String(decoding: $0, as: UTF8.self) }
        let httpResponse = HTTPURLResponse(
            url: request.url ?? URL(string: "https://sub2api.example/v1/chat/completions")!,
            statusCode: response.statusCode,
            httpVersion: "HTTP/1.1",
            headerFields: response.headers
        )!
        return (response.body, httpResponse)
    }
}
