import Foundation
import MelixWorkerProtocol

public struct SSEStreamWriter: Sendable {
    public enum StreamShape: Sendable {
        case chatCompletions
        case completions
        case responses
        case messages
    }

    public struct StreamOptions: Sendable, Equatable {
        public let includeUsage: Bool

        public init(includeUsage: Bool = true) {
            self.includeUsage = includeUsage
        }
    }

    private let now: @Sendable () -> Date
    private let keepaliveInterval: TimeInterval?

    public init(
        now: @escaping @Sendable () -> Date = Date.init,
        keepaliveInterval: TimeInterval? = 15
    ) {
        self.now = now
        self.keepaliveInterval = keepaliveInterval
    }

    public func encode(
        stream: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>,
        requestID: String,
        modelID: String,
        shape: StreamShape = .chatCompletions,
        toolParser: ToolParserSelection? = nil,
        options: StreamOptions = StreamOptions(),
        onDisconnect: (@Sendable () async -> Void)? = nil
    ) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { continuation in
            let keepaliveTask = keepaliveTask(continuation: continuation)
            let task = Task {
                do {
                    for try await event in stream {
                        if !options.includeUsage, case .usageDelta = event.payload {
                            continue
                        }
                        continuation.yield(
                            encode(
                                event: event,
                                requestID: requestID,
                                modelID: modelID,
                                shape: shape,
                                toolParser: toolParser
                            )
                        )
                    }
                } catch {
                    continuation.yield(errorFrame(requestID: requestID, code: "transport_error", message: error.localizedDescription))
                }

                keepaliveTask?.cancel()
                continuation.yield(doneFrame())
                continuation.finish()
            }

            continuation.onTermination = { termination in
                keepaliveTask?.cancel()
                task.cancel()
                guard case .cancelled = termination else {
                    return
                }
                guard let onDisconnect else {
                    return
                }
                Task {
                    await onDisconnect()
                }
            }
        }
    }

    private func keepaliveTask(
        continuation: AsyncThrowingStream<Data, Error>.Continuation
    ) -> Task<Void, Never>? {
        guard let keepaliveInterval, keepaliveInterval > 0 else {
            return nil
        }

        let sleepNanoseconds = UInt64(keepaliveInterval * 1_000_000_000)
        return Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: sleepNanoseconds)
                guard !Task.isCancelled else {
                    break
                }
                continuation.yield(keepaliveFrame())
            }
        }
    }

    private func encode(
        event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        modelID: String,
        shape: StreamShape,
        toolParser: ToolParserSelection?
    ) -> Data {
        switch shape {
        case .chatCompletions:
            return encodeChatCompletions(event: event, requestID: requestID, modelID: modelID, toolParser: toolParser)
        case .completions:
            return encodeCompletions(event: event, requestID: requestID, modelID: modelID, toolParser: toolParser)
        case .responses:
            return encodeResponses(event: event, requestID: requestID, modelID: modelID, toolParser: toolParser)
        case .messages:
            return encodeMessages(event: event, requestID: requestID, modelID: modelID, toolParser: toolParser)
        }
    }

    private func encodeCompletions(
        event: Melix_Worker_V1_ExecuteEvent,
        requestID: String,
        modelID: String,
        toolParser: ToolParserSelection?
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
            let payload = mergeToolParserMetadata(
                into: [
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
                ],
                toolParser: toolParser
            )
            return frame(
                event: "tool_call",
                json: payload
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
        modelID: String,
        toolParser: ToolParserSelection?
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
            let payload = mergeToolParserMetadata(
                into: [
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
                ],
                toolParser: toolParser
            )
            return frame(
                event: "tool_call",
                json: payload
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
        modelID: String,
        toolParser: ToolParserSelection?
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
            let payload = mergeToolParserMetadata(
                into: [
                    "type": "response.tool_call.delta",
                    "response_id": requestID,
                    "model": modelID,
                    "call_id": toolCall.callID,
                    "tool_name": toolCall.toolName,
                    "arguments": toolCall.argumentsJsonFragment,
                ],
                toolParser: toolParser
            )
            return frame(
                event: "response.tool_call.delta",
                json: payload
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
        modelID: String,
        toolParser: ToolParserSelection?
    ) -> Data {
        switch event.payload {
        case .tokenDelta(let delta):
            return frame(
                event: "message.delta",
                json: [
                    "type": "message.delta",
                    "message_id": requestID,
                    "model": modelID,
                    "content_block": [
                        "type": "text",
                    ],
                    "delta": [
                        "type": "text_delta",
                        "text": delta.text,
                    ],
                ]
            )
        case .reasoningDelta(let reasoning):
            return frame(
                event: "message.reasoning.delta",
                json: [
                    "type": "message.reasoning.delta",
                    "message_id": requestID,
                    "model": modelID,
                    "content_block": [
                        "type": "thinking",
                    ],
                    "delta": [
                        "type": "thinking_delta",
                        "thinking": reasoning.text,
                    ],
                ]
            )
        case .toolCallDelta(let toolCall):
            let payload = mergeToolParserMetadata(
                into: [
                    "type": "message.tool_call.delta",
                    "message_id": requestID,
                    "model": modelID,
                    "call_id": toolCall.callID,
                    "tool_name": toolCall.toolName,
                    "arguments": toolCall.argumentsJsonFragment,
                ],
                toolParser: toolParser
            )
            return frame(
                event: "message.tool_call.delta",
                json: payload
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
            var content: [[String: Any]] = []
            if !completed.reasoningText.isEmpty {
                content.append([
                    "type": "thinking",
                    "thinking": completed.reasoningText,
                ])
            }
            if !completed.assistantText.isEmpty {
                content.append([
                    "type": "text",
                    "text": completed.assistantText,
                ])
            }
            return frame(
                event: "message.completed",
                json: [
                    "type": "message.completed",
                    "message_id": requestID,
                    "model": modelID,
                    "finish_reason": completed.finishReason,
                    "stop_reason": completed.finishReason,
                    "content": content,
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

    private func keepaliveFrame() -> Data {
        Data(": keepalive \(Int(now().timeIntervalSince1970 * 1000))\n\n".utf8)
    }

    private func mergeToolParserMetadata(
        into json: [String: Any],
        toolParser: ToolParserSelection?
    ) -> [String: Any] {
        guard let toolParser else {
            return json
        }

        var merged = json
        merged["parser_mode"] = toolParser.mode.rawValue
        if !toolParser.namespaces.isEmpty {
            merged["parser_namespaces"] = toolParser.namespaces
        }
        if let fallbackMode = toolParser.fallbackMode {
            merged["parser_fallback_mode"] = fallbackMode.rawValue
        }
        if !toolParser.mcpSourceIDs.isEmpty {
            merged["mcp_source_ids"] = toolParser.mcpSourceIDs
        }
        return merged
    }

    private func frame(event: String, json: [String: Any]) -> Data {
        let payloadData = (try? JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])) ?? Data("{}".utf8)
        let payload = String(decoding: payloadData, as: UTF8.self)
        return Data("event: \(event)\ndata: \(payload)\n\n".utf8)
    }
}
