import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixWorkerProtocol

@Suite("Protocol Compatibility Matrix")
struct ProtocolCompatibilityMatrixTests {
    private struct StreamCase {
        let name: String
        let shape: SSEStreamWriter.StreamShape
        let markers: [String]
    }

    @Test("stream-family discriminators stay stable across protocol shapes")
    func streamFamilyDiscriminatorsStayStableAcrossProtocolShapes() async throws {
        let writer = SSEStreamWriter(now: { Date(timeIntervalSince1970: 456) })
        let cases = [
            StreamCase(
                name: "chat.completions",
                shape: .chatCompletions,
                markers: [
                    "\"object\":\"chat.completion.chunk\"",
                    "\"content\":\"A\"",
                    "\"finish_reason\":\"stop\"",
                    "data: [DONE]",
                ]
            ),
            StreamCase(
                name: "completions",
                shape: .completions,
                markers: [
                    "\"object\":\"text_completion\"",
                    "\"text\":\"A\"",
                    "\"finish_reason\":\"stop\"",
                    "data: [DONE]",
                ]
            ),
            StreamCase(
                name: "responses",
                shape: .responses,
                markers: [
                    "event: response.output_text.delta",
                    "\"type\":\"response.output_text.delta\"",
                    "event: response.completed",
                    "\"type\":\"response.completed\"",
                    "data: [DONE]",
                ]
            ),
            StreamCase(
                name: "messages",
                shape: .messages,
                markers: [
                    "event: message.delta",
                    "\"type\":\"message.delta\"",
                    "event: message.completed",
                    "\"type\":\"message.completed\"",
                    "data: [DONE]",
                ]
            ),
        ]

        for streamCase in cases {
            let stream = AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> { continuation in
                continuation.yield(makeTokenEvent(requestID: streamCase.name, seq: 1, text: "A"))
                continuation.yield(makeCompletedEvent(requestID: streamCase.name, seq: 2, finishReason: "stop", assistantText: "A"))
                continuation.finish()
            }

            let payload = try await collectChunks(
                writer.encode(
                    stream: stream,
                    requestID: streamCase.name,
                    modelID: "melix-dev-text",
                    shape: streamCase.shape
                )
            )

            for marker in streamCase.markers {
                #expect(payload.contains(marker), "\(streamCase.name) missing marker \(marker)")
            }
        }
    }
}
