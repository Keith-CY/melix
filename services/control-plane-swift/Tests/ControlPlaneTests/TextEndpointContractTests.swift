import Foundation
import Testing
@testable import MelixControlPlaneCore

struct TextEndpointContractTests {
    @Test("request contracts decode melix session metadata across endpoint variants")
    func requestContractsDecodeMelixSessionMetadata() throws {
        let decoder = JSONDecoder()

        let completions = try decoder.decode(
            OpenAICompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "prompt": "Explain the cache.",
                  "stream": true,
                  "temperature": 0.3,
                  "top_p": 0.85,
                  "max_tokens": 64,
                  "session_id": "session-1",
                  "branch_id": "branch-main",
                  "parent_request_id": "req-parent",
                  "restore_snapshot_id": "snap-1",
                  "save_boundary_snapshot": false
                }
                """.utf8
            )
        )
        let messages = try decoder.decode(
            MelixMessagesRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "system": "Be terse.",
                  "stream": true,
                  "temperature": 0.4,
                  "top_p": 0.9,
                  "max_tokens": 32,
                  "session_id": "session-2",
                  "messages": [
                    { "role": "user", "content": "Explain the queue." }
                  ]
                }
                """.utf8
            )
        )

        #expect(completions.sessionID == "session-1")
        #expect(completions.branchID == "branch-main")
        #expect(completions.parentRequestID == "req-parent")
        #expect(completions.restoreSnapshotID == "snap-1")
        #expect(completions.saveBoundarySnapshot == false)
        #expect(messages.system == "Be terse.")
        #expect(messages.sessionID == "session-2")
        #expect(messages.messages == [.init(role: "user", content: "Explain the queue.")])
    }

    @Test("responses input supports both text and message-array codable forms")
    func responsesInputSupportsTextAndMessageArrays() throws {
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]

        let textRequest = try decoder.decode(
            OpenAIResponsesRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "input": "Summarize the queue."
                }
                """.utf8
            )
        )
        let messageRequest = try decoder.decode(
            OpenAIResponsesRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "instructions": "Be terse.",
                  "input": [
                    { "role": "user", "content": "Summarize the queue." }
                  ]
                }
                """.utf8
            )
        )

        #expect(textRequest.input == .text("Summarize the queue."))
        #expect(
            messageRequest.input == .messages([
                .init(role: "user", content: "Summarize the queue."),
            ])
        )

        let encoded = try String(decoding: encoder.encode(messageRequest), as: UTF8.self)
        #expect(encoded.contains("\"instructions\":\"Be terse.\""))
        #expect(encoded.contains("\"input\":["))
    }

    @Test("equivalent single-turn requests normalize to the same internal text shape")
    func equivalentSingleTurnRequestsNormalizeToSameShape() {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-normalized" })

        let chat = translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain cache routing.")],
                stream: true,
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )
        let completions = translator.normalize(
            OpenAICompletionsRequest(
                model: "melix-dev-text",
                prompt: "Explain cache routing.",
                stream: true,
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )
        let responses = translator.normalize(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Explain cache routing."),
                stream: true,
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )
        let messages = translator.normalize(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain cache routing.")],
                stream: true,
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )

        let expectedMessages = [NormalizedTextMessage(role: "user", content: "Explain cache routing.")]
        #expect(chat.messages == expectedMessages)
        #expect(completions.messages == expectedMessages)
        #expect(responses.messages == expectedMessages)
        #expect(messages.messages == expectedMessages)
        #expect(chat.stream == completions.stream)
        #expect(completions.stream == responses.stream)
        #expect(responses.stream == messages.stream)
        #expect(chat.temperature == completions.temperature)
        #expect(completions.temperature == responses.temperature)
        #expect(responses.temperature == messages.temperature)
        #expect(chat.topP == completions.topP)
        #expect(completions.topP == responses.topP)
        #expect(responses.topP == messages.topP)
        #expect(chat.maxTokens == completions.maxTokens)
        #expect(completions.maxTokens == responses.maxTokens)
        #expect(responses.maxTokens == messages.maxTokens)
    }

    @Test("system and instructions fields align across chat, responses, and messages requests")
    func systemFieldsNormalizeConsistently() {
        let translator = ChatRequestTranslator()

        let chat = translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [
                    .init(role: "system", content: "Be terse."),
                    .init(role: "user", content: "Summarize the queue."),
                ]
            )
        )
        let responses = translator.normalize(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Summarize the queue."),
                instructions: "Be terse."
            )
        )
        let messages = translator.normalize(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Summarize the queue.")],
                system: "Be terse."
            )
        )

        let expectedMessages = [
            NormalizedTextMessage(role: "system", content: "Be terse."),
            NormalizedTextMessage(role: "user", content: "Summarize the queue."),
        ]
        #expect(chat.messages == expectedMessages)
        #expect(responses.messages == expectedMessages)
        #expect(messages.messages == expectedMessages)
    }

    @Test("responses message inputs normalize without losing role ordering")
    func responsesMessageInputsNormalizeWithoutLosingRoleOrdering() {
        let translator = ChatRequestTranslator()
        let normalized = translator.normalize(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .messages([
                    .init(role: "assistant", content: "Prior answer"),
                    .init(role: "user", content: "Continue"),
                ]),
                instructions: "Stay concise."
            )
        )

        #expect(
            normalized.messages == [
                .init(role: "system", content: "Stay concise."),
                .init(role: "assistant", content: "Prior answer"),
                .init(role: "user", content: "Continue"),
            ]
        )
    }

    @Test("normalized requests translate recovery and cache metadata consistently")
    func normalizedRequestsTranslateRecoveryMetadataConsistently() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-text-endpoints" })
        let normalized = NormalizedTextRequest(
            endpoint: .responses,
            model: "melix-dev-text",
            messages: [
                .init(role: "system", content: "Be terse."),
                .init(role: "user", content: "Resume here."),
            ],
            stream: true,
            temperature: 0.4,
            topP: 0.8,
            maxTokens: 64,
            sessionID: "session-1",
            branchID: "branch-main",
            parentRequestID: "req-parent",
            restoreSnapshotID: "snap-parent",
            saveBoundarySnapshot: true
        )

        let translated = try translator.translate(normalized, modelHandle: "melix-dev-text::swift")

        #expect(translated.requestID == "req-text-endpoints")
        #expect(translated.modelID == "melix-dev-text")
        #expect(translated.stream)
        #expect(translated.workerRequest.execution.id.sessionID == "session-1")
        #expect(translated.workerRequest.execution.id.branchID == "branch-main")
        #expect(translated.workerRequest.execution.id.parentRequestID == "req-parent")
        #expect(translated.workerRequest.execution.cacheHints.restoreSnapshotID == "snap-parent")
        #expect(translated.workerRequest.execution.cacheHints.saveBoundarySnapshot)
        #expect(translated.workerRequest.execution.cacheHints.allowL1)
        #expect(translated.workerRequest.execution.cacheHints.allowL2)
        #expect(translated.workerRequest.execution.cacheHints.persistL2)
        #expect(translated.workerRequest.execution.cacheHints.preferHotPrefix)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 64)
        #expect(translated.workerRequest.messages.count == 2)
        #expect(translated.workerRequest.messages[0].role == "system")
        #expect(translated.workerRequest.messages[1].role == "user")
    }

    @Test("chat translation wrapper applies request defaults and session-aware cache hints")
    func chatTranslationWrapperAppliesDefaultsAndSessionAwareHints() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-chat-wrapper" })
        let translated = try translator.translate(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Hello")],
                sessionID: "session-wrapper"
            ),
            modelHandle: "melix-dev-text::swift"
        )

        #expect(translated.requestID == "req-chat-wrapper")
        #expect(translated.workerRequest.stream)
        #expect(translated.workerRequest.sampling.temperature == 0.7)
        #expect(translated.workerRequest.sampling.topP == 1.0)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 256)
        #expect(translated.workerRequest.execution.id.branchID == "branch-main")
        #expect(translated.workerRequest.execution.cacheHints.saveBoundarySnapshot)
        #expect(translated.workerRequest.execution.cacheHints.allowL1)
        #expect(translated.workerRequest.execution.cacheHints.allowL2)
        #expect(translated.workerRequest.execution.cacheHints.persistL2)
        #expect(translated.workerRequest.execution.cacheHints.preferHotPrefix)
    }

    @Test("request contracts decode preset and workflow shaping metadata across endpoint variants")
    func requestContractsDecodePresetAndWorkflowMetadata() throws {
        let decoder = JSONDecoder()

        let chat = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "messages": [{ "role": "user", "content": "hello" }],
                  "preset_id": "deep_reasoning",
                  "workflow": "tool_followup",
                  "workflow_run_id": "wf-1",
                  "workflow_node_id": "node-1"
                }
                """.utf8
            )
        )
        let responses = try decoder.decode(
            OpenAIResponsesRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "input": "hello",
                  "preset_id": "deep_reasoning",
                  "workflow": "tool_followup",
                  "workflow_run_id": "wf-1",
                  "workflow_node_id": "node-1"
                }
                """.utf8
            )
        )

        #expect(chat.presetID == "deep_reasoning")
        #expect(chat.workflow == .toolFollowup)
        #expect(chat.workflowRunID == "wf-1")
        #expect(chat.workflowNodeID == "node-1")
        #expect(responses.presetID == "deep_reasoning")
        #expect(responses.workflow == .toolFollowup)
        #expect(responses.workflowRunID == "wf-1")
        #expect(responses.workflowNodeID == "node-1")
    }

    @Test("equivalent endpoint requests shape into the same worker metadata for one logical session")
    func equivalentEndpointRequestsShapeIntoSameWorkerMetadata() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-shaped" })

        let chatTranslated = try translator.translate(
            translator.normalize(
                OpenAIChatCompletionsRequest(
                    model: "melix-dev-text",
                    messages: [.init(role: "user", content: "Explain the cache.")],
                    sessionID: "session-shaped",
                    presetID: "deep_reasoning",
                    workflow: .toolFollowup,
                    workflowRunID: "wf-1",
                    workflowNodeID: "node-1"
                )
            ),
            modelHandle: "melix-dev-text::swift"
        )
        let completionsTranslated = try translator.translate(
            translator.normalize(
                OpenAICompletionsRequest(
                    model: "melix-dev-text",
                    prompt: "Explain the cache.",
                    sessionID: "session-shaped",
                    presetID: "deep_reasoning",
                    workflow: .toolFollowup,
                    workflowRunID: "wf-1",
                    workflowNodeID: "node-1"
                )
            ),
            modelHandle: "melix-dev-text::swift"
        )
        let responsesTranslated = try translator.translate(
            translator.normalize(
                OpenAIResponsesRequest(
                    model: "melix-dev-text",
                    input: .text("Explain the cache."),
                    sessionID: "session-shaped",
                    presetID: "deep_reasoning",
                    workflow: .toolFollowup,
                    workflowRunID: "wf-1",
                    workflowNodeID: "node-1"
                )
            ),
            modelHandle: "melix-dev-text::swift"
        )
        let messagesTranslated = try translator.translate(
            translator.normalize(
                MelixMessagesRequest(
                    model: "melix-dev-text",
                    messages: [.init(role: "user", content: "Explain the cache.")],
                    sessionID: "session-shaped",
                    presetID: "deep_reasoning",
                    workflow: .toolFollowup,
                    workflowRunID: "wf-1",
                    workflowNodeID: "node-1"
                )
            ),
            modelHandle: "melix-dev-text::swift"
        )

        let variants = [
            chatTranslated.workerRequest,
            completionsTranslated.workerRequest,
            responsesTranslated.workerRequest,
            messagesTranslated.workerRequest,
        ]

        for request in variants {
            #expect(request.execution.id.sessionID == "session-shaped")
            #expect(request.execution.id.branchID == "branch-main")
            #expect(request.execution.id.workflowRunID == "wf-1")
            #expect(request.execution.id.workflowNodeID == "node-1")
            #expect(request.execution.scheduling.lane == "text.prefill.hot")
            #expect(request.execution.scheduling.priority == 120)
            #expect(request.execution.scheduling.admissionPolicy == "workflow.tool_followup")
            #expect(request.execution.cacheHints.cachePolicy == "session-hot")
            #expect(request.execution.ext["melix.preset_id"] == "deep_reasoning")
            #expect(request.execution.ext["melix.workflow"] == "tool_followup")
            #expect(request.sampling.temperature == 0.2)
            #expect(request.sampling.maxOutputTokens == 512)
        }
    }

    @Test("explicit request fields override preset defaults while workflow routing remains stable")
    func explicitRequestFieldsOverridePresetDefaultsWhileWorkflowRoutingRemainsStable() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-override" })
        let translated = try translator.translate(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Continue"),
                temperature: 0.8,
                maxTokens: 64,
                sessionID: "session-override",
                branchID: "branch-alt",
                saveBoundarySnapshot: false,
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-override",
                workflowNodeID: "node-override"
            ),
            modelHandle: "melix-dev-text::swift"
        )

        #expect(translated.workerRequest.sampling.temperature == 0.8)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 64)
        #expect(translated.workerRequest.execution.id.branchID == "branch-alt")
        #expect(translated.workerRequest.execution.cacheHints.saveBoundarySnapshot == false)
        #expect(translated.workerRequest.execution.scheduling.lane == "text.prefill.hot")
        #expect(translated.workerRequest.execution.scheduling.priority == 120)
    }

    @Test("endpoint-specific translate wrappers delegate through shared workflow-aware shaping")
    func endpointSpecificTranslateWrappersDelegateThroughSharedShaping() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-wrapper" })

        let completions = try translator.translate(
            OpenAICompletionsRequest(
                model: "melix-dev-text",
                prompt: "Continue",
                sessionID: "session-wrapper",
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-wrapper",
                workflowNodeID: "node-wrapper"
            ),
            modelHandle: "melix-dev-text::swift"
        )
        let responses = try translator.translate(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Continue"),
                sessionID: "session-wrapper",
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-wrapper",
                workflowNodeID: "node-wrapper"
            ),
            modelHandle: "melix-dev-text::swift"
        )
        let messages = try translator.translate(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Continue")],
                sessionID: "session-wrapper",
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-wrapper",
                workflowNodeID: "node-wrapper"
            ),
            modelHandle: "melix-dev-text::swift"
        )

        for request in [completions.workerRequest, responses.workerRequest, messages.workerRequest] {
            #expect(request.execution.id.workflowRunID == "wf-wrapper")
            #expect(request.execution.scheduling.lane == "text.prefill.hot")
            #expect(request.execution.ext["melix.workflow"] == "tool_followup")
        }
    }

    @Test("endpoint response contracts encode their public discriminators")
    func endpointResponseContractsEncodeExpectedDiscriminators() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]

        let completionChunk = OpenAICompletionChunk(
            id: "cmpl-1",
            object: "text_completion.chunk",
            model: "melix-dev-text",
            choices: [.init(index: 0, text: "hello", finishReason: nil)]
        )
        let responsesEvent = OpenAIResponseEvent(type: "response.output_text.delta", responseID: "resp-1")
        let messagesEvent = MelixMessagesEvent(type: "message.delta", messageID: "msg-1")

        let completionPayload = try String(
            decoding: encoder.encode(completionChunk),
            as: UTF8.self
        )
        let responsesPayload = try String(
            decoding: encoder.encode(responsesEvent),
            as: UTF8.self
        )
        let messagesPayload = try String(
            decoding: encoder.encode(messagesEvent),
            as: UTF8.self
        )

        #expect(completionPayload.contains("\"object\":\"text_completion.chunk\""))
        #expect(responsesPayload.contains("\"type\":\"response.output_text.delta\""))
        #expect(responsesPayload.contains("\"response_id\":\"resp-1\""))
        #expect(messagesPayload.contains("\"type\":\"message.delta\""))
        #expect(messagesPayload.contains("\"message_id\":\"msg-1\""))
    }
}
