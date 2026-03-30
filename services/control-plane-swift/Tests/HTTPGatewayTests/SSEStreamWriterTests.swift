import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("SSE Stream Writer")
struct SSEStreamWriterTests {
    @Test("SSE emits ordered delta, heartbeat, usage, completion, and done frames")
    func emitsOrderedFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeTokenEvent(requestID: "req-1", seq: 1, text: "A"))
            continuation.yield(makeHeartbeatEvent(requestID: "req-1", seq: 2, unixMs: 99))
            continuation.yield(makeUsageEvent(requestID: "req-1", seq: 3, promptTokens: 3, completionTokens: 1))
            continuation.yield(makeCompletedEvent(requestID: "req-1", seq: 4, finishReason: "stop", assistantText: "A"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(stream: stream, requestID: "req-1", modelID: "melix-dev-text")
        )

        #expect(payload.contains("event: message"))
        #expect(payload.contains("\"content\":\"A\""))
        #expect(payload.contains("event: heartbeat"))
        #expect(payload.contains("\"unix_ms\":99"))
        #expect(payload.contains("\"prompt_tokens\":3"))
        #expect(payload.contains("\"finish_reason\":\"stop\""))
        #expect(payload.contains("data: [DONE]"))
        #expect(orderedRanges(in: payload, needles: [
            "\"content\":\"A\"",
            "\"unix_ms\":99",
            "\"prompt_tokens\":3",
            "\"finish_reason\":\"stop\"",
            "data: [DONE]",
        ]))
    }

    @Test("SSE emits error frames and terminates with done marker")
    func emitsErrorFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeErrorEvent(requestID: "req-err", seq: 1, code: "runtime_error", message: "boom"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(stream: stream, requestID: "req-err", modelID: "melix-dev-text")
        )

        #expect(payload.contains("event: error"))
        #expect(payload.contains("\"code\":\"runtime_error\""))
        #expect(payload.contains("\"message\":\"boom\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("SSE emits transport errors when the upstream stream throws")
    func emitsTransportErrors() async throws {
        enum TestError: LocalizedError {
            case boom

            var errorDescription: String? { "transport boom" }
        }

        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeTokenEvent(requestID: "req-transport", seq: 1, text: "A"))
            continuation.finish(throwing: TestError.boom)
        }

        let payload = try await collectChunks(
            writer.encode(stream: stream, requestID: "req-transport", modelID: "melix-dev-text")
        )

        #expect(payload.contains("\"content\":\"A\""))
        #expect(payload.contains("event: error"))
        #expect(payload.contains("\"code\":\"transport_error\""))
        #expect(payload.contains("\"message\":\"transport boom\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("chat completion streams emit fallback frames for untyped events")
    func emitsChatFallbackFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            var event = Melix_Worker_V1_ExecuteEvent()
            event.requestID = "req-fallback"
            event.executionKind = "generate"
            event.seq = 9
            continuation.yield(event)
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(stream: stream, requestID: "req-fallback", modelID: "melix-dev-text")
        )

        #expect(payload.contains("event: message"))
        #expect(payload.contains("\"request_id\":\"req-fallback\""))
        #expect(payload.contains("\"event_seq\":9"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("responses streams emit delta usage completion and done frames")
    func emitsResponsesFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeTokenEvent(requestID: "resp-1", seq: 1, text: "A"))
            continuation.yield(makeUsageEvent(requestID: "resp-1", seq: 2, promptTokens: 3, completionTokens: 1))
            continuation.yield(makeCompletedEvent(requestID: "resp-1", seq: 3, finishReason: "stop", assistantText: "A"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "resp-1",
                modelID: "melix-dev-text",
                shape: .responses
            )
        )

        #expect(payload.contains("event: response.output_text.delta"))
        #expect(payload.contains("\"type\":\"response.output_text.delta\""))
        #expect(payload.contains("\"response_id\":\"resp-1\""))
        #expect(payload.contains("\"delta\":\"A\""))
        #expect(payload.contains("event: response.usage"))
        #expect(payload.contains("\"input_tokens\":3"))
        #expect(payload.contains("event: response.completed"))
        #expect(payload.contains("\"finish_reason\":\"stop\""))
        #expect(payload.contains("data: [DONE]"))
        #expect(orderedRanges(in: payload, needles: [
            "\"type\":\"response.output_text.delta\"",
            "\"type\":\"response.usage\"",
            "\"type\":\"response.completed\"",
            "data: [DONE]",
        ]))
    }

    @Test("responses streams emit heartbeat error fallback and done frames")
    func emitsResponsesHeartbeatErrorAndFallbackFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeHeartbeatEvent(requestID: "resp-misc", seq: 1, unixMs: 321))
            continuation.yield(makeErrorEvent(requestID: "resp-misc", seq: 2, code: "runtime_error", message: "boom"))
            var fallback = Melix_Worker_V1_ExecuteEvent()
            fallback.requestID = "resp-misc"
            fallback.executionKind = "generate"
            fallback.seq = 3
            continuation.yield(fallback)
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "resp-misc",
                modelID: "melix-dev-text",
                shape: .responses
            )
        )

        #expect(payload.contains("event: response.heartbeat"))
        #expect(payload.contains("\"type\":\"response.heartbeat\""))
        #expect(payload.contains("\"unix_ms\":321"))
        #expect(payload.contains("event: error"))
        #expect(payload.contains("\"code\":\"runtime_error\""))
        #expect(payload.contains("event: response.event"))
        #expect(payload.contains("\"type\":\"response.event\""))
        #expect(payload.contains("\"event_seq\":3"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("completions streams emit chunk usage completion and done frames")
    func emitsCompletionsFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeTokenEvent(requestID: "cmp-1", seq: 1, text: "A"))
            continuation.yield(makeUsageEvent(requestID: "cmp-1", seq: 2, promptTokens: 4, completionTokens: 1))
            continuation.yield(makeCompletedEvent(requestID: "cmp-1", seq: 3, finishReason: "stop", assistantText: "A"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "cmp-1",
                modelID: "melix-dev-text",
                shape: .completions
            )
        )

        #expect(payload.contains("\"object\":\"text_completion\""))
        #expect(payload.contains("\"text\":\"A\""))
        #expect(payload.contains("event: usage"))
        #expect(payload.contains("\"prompt_tokens\":4"))
        #expect(payload.contains("\"finish_reason\":\"stop\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("messages streams emit delta heartbeat completion fallback and done frames")
    func emitsMessagesFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeTokenEvent(requestID: "msg-1", seq: 1, text: "A"))
            continuation.yield(makeHeartbeatEvent(requestID: "msg-1", seq: 2, unixMs: 456))
            var fallback = Melix_Worker_V1_ExecuteEvent()
            fallback.requestID = "msg-1"
            fallback.executionKind = "generate"
            fallback.seq = 3
            continuation.yield(fallback)
            continuation.yield(makeCompletedEvent(requestID: "msg-1", seq: 4, finishReason: "stop", assistantText: "A"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "msg-1",
                modelID: "melix-dev-text",
                shape: .messages
            )
        )

        #expect(payload.contains("event: message.delta"))
        #expect(payload.contains("\"type\":\"message.delta\""))
        #expect(payload.contains("\"message_id\":\"msg-1\""))
        #expect(payload.contains("\"content_block\":{\"type\":\"text\"}"))
        #expect(payload.contains("\"delta\":{\"text\":\"A\",\"type\":\"text_delta\"}"))
        #expect(payload.contains("event: message.heartbeat"))
        #expect(payload.contains("\"type\":\"message.heartbeat\""))
        #expect(payload.contains("event: message.event"))
        #expect(payload.contains("\"type\":\"message.event\""))
        #expect(payload.contains("\"event_seq\":3"))
        #expect(payload.contains("event: message.completed"))
        #expect(payload.contains("\"type\":\"message.completed\""))
        #expect(payload.contains("\"content\":[{\"text\":\"A\",\"type\":\"text\"}]"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("completions streams emit heartbeat error fallback and done frames")
    func emitsCompletionsHeartbeatErrorAndFallbackFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeHeartbeatEvent(requestID: "cmp-misc", seq: 1, unixMs: 654))
            continuation.yield(makeErrorEvent(requestID: "cmp-misc", seq: 2, code: "runtime_error", message: "boom"))
            var fallback = Melix_Worker_V1_ExecuteEvent()
            fallback.requestID = "cmp-misc"
            fallback.executionKind = "generate"
            fallback.seq = 3
            continuation.yield(fallback)
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "cmp-misc",
                modelID: "melix-dev-text",
                shape: .completions
            )
        )

        #expect(payload.contains("event: heartbeat"))
        #expect(payload.contains("\"request_id\":\"cmp-misc\""))
        #expect(payload.contains("\"unix_ms\":654"))
        #expect(payload.contains("event: error"))
        #expect(payload.contains("\"code\":\"runtime_error\""))
        #expect(payload.contains("event: message"))
        #expect(payload.contains("\"event_seq\":3"))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("messages streams emit usage error and done frames")
    func emitsMessagesUsageAndErrorFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeUsageEvent(requestID: "msg-usage", seq: 1, promptTokens: 8, completionTokens: 2))
            continuation.yield(makeErrorEvent(requestID: "msg-usage", seq: 2, code: "runtime_error", message: "boom"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "msg-usage",
                modelID: "melix-dev-text",
                shape: .messages
            )
        )

        #expect(payload.contains("event: message.usage"))
        #expect(payload.contains("\"type\":\"message.usage\""))
        #expect(payload.contains("\"input_tokens\":8"))
        #expect(payload.contains("\"output_tokens\":2"))
        #expect(payload.contains("event: error"))
        #expect(payload.contains("\"code\":\"runtime_error\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("default writer initializer emits valid completion frames")
    func defaultInitializerEmitsFrames() async throws {
        let writer = SSEStreamWriter()

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeTokenEvent(requestID: "default-init", seq: 1, text: "A"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "default-init",
                modelID: "melix-dev-text",
                shape: .completions
            )
        )

        #expect(payload.contains("\"object\":\"text_completion\""))
        #expect(payload.contains("\"text\":\"A\""))
        #expect(payload.contains("data: [DONE]"))
    }

    @Test("chat completions streams emit reasoning and tool deltas in order")
    func emitsChatReasoningAndToolFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        let parser = ToolParserSelection(
            mode: .qwen,
            namespaces: ["tools.search"],
            source: "request",
            fallbackMode: .xml
        )

        let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
            continuation.yield(makeReasoningEvent(requestID: "chat-deltas", seq: 1, text: "think"))
            continuation.yield(makeToolCallEvent(
                requestID: "chat-deltas",
                seq: 2,
                callID: "tool-1",
                toolName: "search",
                argumentsJSONFragment: "{\"q\":\"melix\"}"
            ))
            continuation.yield(makeCompletedEvent(requestID: "chat-deltas", seq: 3, finishReason: "stop", assistantText: "done"))
            continuation.finish()
        }

        let payload = try await collectChunks(
            writer.encode(
                stream: stream,
                requestID: "chat-deltas",
                modelID: "melix-dev-text",
                shape: .chatCompletions,
                toolParser: parser
            )
        )

        #expect(payload.contains("event: reasoning"))
        #expect(payload.contains("\"object\":\"chat.completion.reasoning.delta\""))
        #expect(payload.contains("\"reasoning\":\"think\""))
        #expect(payload.contains("event: tool_call"))
        #expect(payload.contains("\"object\":\"chat.completion.tool_call.delta\""))
        #expect(payload.contains("\"name\":\"search\""))
        #expect(payload.contains("\"arguments\":\"{\\\"q\\\":\\\"melix\\\"}\""))
        #expect(payload.contains("\"parser_mode\":\"qwen\""))
        #expect(payload.contains("\"parser_namespaces\":[\"tools.search\"]"))
        #expect(payload.contains("\"parser_fallback_mode\":\"xml\""))
        #expect(orderedRanges(in: payload, needles: [
            "event: reasoning",
            "event: tool_call",
            "event: message",
            "data: [DONE]",
        ]))
    }

    @Test("responses messages and completions streams emit endpoint-specific reasoning and tool deltas")
    func emitsEndpointSpecificReasoningAndToolFrames() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        let parser = ToolParserSelection(
            mode: .mistral,
            namespaces: ["tools.math"],
            source: "model"
        )

        func payload(for shape: SSEStreamWriter.StreamShape, requestID: String) async throws -> String {
            let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
                continuation.yield(makeReasoningEvent(requestID: requestID, seq: 1, text: "think"))
                continuation.yield(makeToolCallEvent(
                    requestID: requestID,
                    seq: 2,
                    callID: "tool-1",
                    toolName: "search",
                    argumentsJSONFragment: "{\"q\":\"melix\"}"
                ))
                continuation.finish()
            }

            return try await collectChunks(
                writer.encode(
                    stream: stream,
                    requestID: requestID,
                    modelID: "melix-dev-text",
                    shape: shape,
                    toolParser: parser
                )
            )
        }

        let completionsPayload = try await payload(for: .completions, requestID: "cmp-deltas")
        #expect(completionsPayload.contains("event: reasoning"))
        #expect(completionsPayload.contains("\"type\":\"completion.reasoning.delta\""))
        #expect(completionsPayload.contains("\"delta\":\"think\""))
        #expect(completionsPayload.contains("event: tool_call"))
        #expect(completionsPayload.contains("\"type\":\"completion.tool_call.delta\""))
        #expect(completionsPayload.contains("\"call_id\":\"tool-1\""))
        #expect(completionsPayload.contains("\"parser_mode\":\"mistral\""))
        #expect(completionsPayload.contains("\"parser_namespaces\":[\"tools.math\"]"))

        let responsesPayload = try await payload(for: .responses, requestID: "resp-deltas")
        #expect(responsesPayload.contains("event: response.reasoning.delta"))
        #expect(responsesPayload.contains("\"type\":\"response.reasoning.delta\""))
        #expect(responsesPayload.contains("event: response.tool_call.delta"))
        #expect(responsesPayload.contains("\"type\":\"response.tool_call.delta\""))
        #expect(responsesPayload.contains("\"parser_mode\":\"mistral\""))
        #expect(responsesPayload.contains("\"parser_namespaces\":[\"tools.math\"]"))

        let messagesPayload = try await payload(for: .messages, requestID: "msg-deltas")
        #expect(messagesPayload.contains("event: message.reasoning.delta"))
        #expect(messagesPayload.contains("\"type\":\"message.reasoning.delta\""))
        #expect(messagesPayload.contains("\"content_block\":{\"type\":\"thinking\"}"))
        #expect(messagesPayload.contains("\"delta\":{\"thinking\":\"think\",\"type\":\"thinking_delta\"}"))
        #expect(messagesPayload.contains("event: message.tool_call.delta"))
        #expect(messagesPayload.contains("\"type\":\"message.tool_call.delta\""))
        #expect(messagesPayload.contains("\"parser_mode\":\"mistral\""))
        #expect(messagesPayload.contains("\"parser_namespaces\":[\"tools.math\"]"))
    }
}

private func collectChunks(
    _ stream: AsyncThrowingStream<Data, Error>
) async throws -> String {
    var data = Data()
    for try await chunk in stream {
        data.append(chunk)
    }
    return try #require(String(data: data, encoding: .utf8))
}

private func orderedRanges(in payload: String, needles: [String]) -> Bool {
    var searchStart = payload.startIndex
    for needle in needles {
        guard let range = payload.range(of: needle, range: searchStart..<payload.endIndex) else {
            return false
        }
        searchStart = range.upperBound
    }
    return true
}
