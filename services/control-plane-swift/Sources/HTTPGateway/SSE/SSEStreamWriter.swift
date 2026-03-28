import Foundation
import MelixWorkerProtocol

public struct SSEStreamWriter: Sendable {
    public enum StreamShape: Sendable {
        case chatCompletions
        case completions
        case responses
        case messages
    }

    private let now: @Sendable () -> Date

    public init(now: @escaping @Sendable () -> Date = Date.init) {
        self.now = now
    }

    public func encode(
        stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>,
        requestID: String,
        modelID: String,
        shape: StreamShape = .chatCompletions
    ) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await event in stream {
                        continuation.yield(
                            encode(
                                event: event,
                                requestID: requestID,
                                modelID: modelID,
                                shape: shape
                            )
                        )
                    }
                } catch {
                    continuation.yield(errorFrame(requestID: requestID, code: "transport_error", message: error.localizedDescription))
                }

                continuation.yield(doneFrame())
                continuation.finish()
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private func encode(
        event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        modelID: String,
        shape: StreamShape
    ) -> Data {
        switch shape {
        case .chatCompletions:
            return encodeChatCompletions(event: event, requestID: requestID, modelID: modelID)
        case .completions:
            return encodeCompletions(event: event, requestID: requestID, modelID: modelID)
        case .responses:
            return encodeResponses(event: event, requestID: requestID, modelID: modelID)
        case .messages:
            return encodeMessages(event: event, requestID: requestID, modelID: modelID)
        }
    }

    private func encodeCompletions(
        event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        modelID: String
    ) -> Data {
        switch event.payload {
        case .tokenDelta(let delta):
            return frame(
                event: "message",
                json: [
                    "id": requestID,
                    "object": "text_completion",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "choices": [
                        [
                            "index": 0,
                            "text": delta.text,
                            "finish_reason": NSNull(),
                        ],
                    ],
                ]
            )
        case .usageDelta(let usage):
            return frame(
                event: "usage",
                json: [
                    "request_id": requestID,
                    "usage": [
                        "prompt_tokens": Int(usage.promptTokens),
                        "completion_tokens": Int(usage.completionTokens),
                    ],
                ]
            )
        case .reasoningDelta(let reasoning):
            return frame(
                event: "reasoning",
                json: [
                    "id": requestID,
                    "type": "completion.reasoning.delta",
                    "object": "text_completion.reasoning.delta",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "delta": reasoning.text,
                ]
            )
        case .toolCallDelta(let toolCall):
            return frame(
                event: "tool_call",
                json: [
                    "id": requestID,
                    "type": "completion.tool_call.delta",
                    "object": "text_completion.tool_call.delta",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "tool_call": [
                        "call_id": toolCall.callID,
                        "tool_name": toolCall.toolName,
                        "arguments": toolCall.argumentsJsonFragment,
                    ],
                ]
            )
        case .heartbeat(let heartbeat):
            return frame(
                event: "heartbeat",
                json: [
                    "request_id": requestID,
                    "unix_ms": Int(heartbeat.unixMs),
                ]
            )
        case .completed(let completed):
            return frame(
                event: "message",
                json: [
                    "id": requestID,
                    "object": "text_completion",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "choices": [
                        [
                            "index": 0,
                            "text": completed.assistantText,
                            "finish_reason": completed.finishReason,
                        ],
                    ],
                ]
            )
        case .error(let error):
            return errorFrame(
                requestID: requestID,
                code: error.error.code,
                message: error.error.message
            )
        default:
            return frame(
                event: "message",
                json: [
                    "request_id": requestID,
                    "event_seq": Int(event.seq),
                ]
            )
        }
    }

    private func encodeChatCompletions(
        event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        modelID: String
    ) -> Data {
        switch event.payload {
        case .tokenDelta(let delta):
            return frame(
                event: "message",
                json: [
                    "id": requestID,
                    "object": "chat.completion.chunk",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "choices": [
                        [
                            "index": 0,
                            "delta": [
                                "content": delta.text,
                            ],
                            "finish_reason": NSNull(),
                        ],
                    ],
                ]
            )
        case .usageDelta(let usage):
            return frame(
                event: "usage",
                json: [
                    "request_id": requestID,
                    "usage": [
                        "prompt_tokens": Int(usage.promptTokens),
                        "completion_tokens": Int(usage.completionTokens),
                    ],
                ]
            )
        case .reasoningDelta(let reasoning):
            return frame(
                event: "reasoning",
                json: [
                    "id": requestID,
                    "object": "chat.completion.reasoning.delta",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "choices": [
                        [
                            "index": 0,
                            "delta": [
                                "reasoning": reasoning.text,
                            ],
                            "finish_reason": NSNull(),
                        ],
                    ],
                ]
            )
        case .toolCallDelta(let toolCall):
            return frame(
                event: "tool_call",
                json: [
                    "id": requestID,
                    "object": "chat.completion.tool_call.delta",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "choices": [
                        [
                            "index": 0,
                            "delta": [
                                "tool_calls": [
                                    [
                                        "id": toolCall.callID,
                                        "type": "function",
                                        "function": [
                                            "name": toolCall.toolName,
                                            "arguments": toolCall.argumentsJsonFragment,
                                        ],
                                    ],
                                ],
                            ],
                            "finish_reason": NSNull(),
                        ],
                    ],
                ]
            )
        case .heartbeat(let heartbeat):
            return frame(
                event: "heartbeat",
                json: [
                    "request_id": requestID,
                    "unix_ms": Int(heartbeat.unixMs),
                ]
            )
        case .completed(let completed):
            return frame(
                event: "message",
                json: [
                    "id": requestID,
                    "object": "chat.completion.chunk",
                    "created": Int(now().timeIntervalSince1970),
                    "model": modelID,
                    "choices": [
                        [
                            "index": 0,
                            "delta": [:],
                            "finish_reason": completed.finishReason,
                        ],
                    ],
                    "melix": [
                        "assistant_text": completed.assistantText,
                    ],
                ]
            )
        case .error(let error):
            return errorFrame(
                requestID: requestID,
                code: error.error.code,
                message: error.error.message
            )
        default:
            return frame(
                event: "message",
                json: [
                    "request_id": requestID,
                    "event_seq": Int(event.seq),
                ]
            )
        }
    }

    private func encodeResponses(
        event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        modelID: String
    ) -> Data {
        switch event.payload {
        case .tokenDelta(let delta):
            return frame(
                event: "response.output_text.delta",
                json: [
                    "type": "response.output_text.delta",
                    "response_id": requestID,
                    "model": modelID,
                    "output_index": 0,
                    "content_index": 0,
                    "delta": delta.text,
                ]
            )
        case .usageDelta(let usage):
            return frame(
                event: "response.usage",
                json: [
                    "type": "response.usage",
                    "response_id": requestID,
                    "usage": [
                        "input_tokens": Int(usage.promptTokens),
                        "output_tokens": Int(usage.completionTokens),
                    ],
                ]
            )
        case .reasoningDelta(let reasoning):
            return frame(
                event: "response.reasoning.delta",
                json: [
                    "type": "response.reasoning.delta",
                    "response_id": requestID,
                    "model": modelID,
                    "delta": reasoning.text,
                ]
            )
        case .toolCallDelta(let toolCall):
            return frame(
                event: "response.tool_call.delta",
                json: [
                    "type": "response.tool_call.delta",
                    "response_id": requestID,
                    "model": modelID,
                    "call_id": toolCall.callID,
                    "tool_name": toolCall.toolName,
                    "arguments": toolCall.argumentsJsonFragment,
                ]
            )
        case .heartbeat(let heartbeat):
            return frame(
                event: "response.heartbeat",
                json: [
                    "type": "response.heartbeat",
                    "response_id": requestID,
                    "unix_ms": Int(heartbeat.unixMs),
                ]
            )
        case .completed(let completed):
            return frame(
                event: "response.completed",
                json: [
                    "type": "response.completed",
                    "response_id": requestID,
                    "model": modelID,
                    "finish_reason": completed.finishReason,
                    "output": [
                        [
                            "type": "output_text",
                            "text": completed.assistantText,
                        ],
                    ],
                ]
            )
        case .error(let error):
            return errorFrame(
                requestID: requestID,
                code: error.error.code,
                message: error.error.message
            )
        default:
            return frame(
                event: "response.event",
                json: [
                    "type": "response.event",
                    "response_id": requestID,
                    "event_seq": Int(event.seq),
                ]
            )
        }
    }

    private func encodeMessages(
        event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        modelID: String
    ) -> Data {
        switch event.payload {
        case .tokenDelta(let delta):
            return frame(
                event: "message.delta",
                json: [
                    "type": "message.delta",
                    "message_id": requestID,
                    "model": modelID,
                    "delta": delta.text,
                ]
            )
        case .reasoningDelta(let reasoning):
            return frame(
                event: "message.reasoning.delta",
                json: [
                    "type": "message.reasoning.delta",
                    "message_id": requestID,
                    "model": modelID,
                    "delta": reasoning.text,
                ]
            )
        case .toolCallDelta(let toolCall):
            return frame(
                event: "message.tool_call.delta",
                json: [
                    "type": "message.tool_call.delta",
                    "message_id": requestID,
                    "model": modelID,
                    "call_id": toolCall.callID,
                    "tool_name": toolCall.toolName,
                    "arguments": toolCall.argumentsJsonFragment,
                ]
            )
        case .usageDelta(let usage):
            return frame(
                event: "message.usage",
                json: [
                    "type": "message.usage",
                    "message_id": requestID,
                    "usage": [
                        "input_tokens": Int(usage.promptTokens),
                        "output_tokens": Int(usage.completionTokens),
                    ],
                ]
            )
        case .heartbeat(let heartbeat):
            return frame(
                event: "message.heartbeat",
                json: [
                    "type": "message.heartbeat",
                    "message_id": requestID,
                    "unix_ms": Int(heartbeat.unixMs),
                ]
            )
        case .completed(let completed):
            return frame(
                event: "message.completed",
                json: [
                    "type": "message.completed",
                    "message_id": requestID,
                    "model": modelID,
                    "finish_reason": completed.finishReason,
                    "content": [
                        [
                            "type": "output_text",
                            "text": completed.assistantText,
                        ],
                    ],
                ]
            )
        case .error(let error):
            return errorFrame(
                requestID: requestID,
                code: error.error.code,
                message: error.error.message
            )
        default:
            return frame(
                event: "message.event",
                json: [
                    "type": "message.event",
                    "message_id": requestID,
                    "event_seq": Int(event.seq),
                ]
            )
        }
    }

    private func errorFrame(
        requestID: String,
        code: String,
        message: String
    ) -> Data {
        frame(
            event: "error",
            json: [
                "request_id": requestID,
                "code": code,
                "message": message,
            ]
        )
    }

    private func doneFrame() -> Data {
        Data("data: [DONE]\n\n".utf8)
    }

    private func frame(event: String, json: [String: Any]) -> Data {
        let payloadData = (try? JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])) ?? Data("{}".utf8)
        let payload = String(decoding: payloadData, as: UTF8.self)
        return Data("event: \(event)\ndata: \(payload)\n\n".utf8)
    }
}
