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
