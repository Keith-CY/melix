import Foundation
import Testing
@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

struct TextEndpointContractTests {
    @Test("multimodal normalization errors expose operator-facing messages")
    func multimodalNormalizationErrorsExposeOperatorMessages() {
        #expect(
            MultimodalRequestNormalizationError.missingValue("input_image").operatorMessage
                == "input_image is required."
        )
        #expect(
            MultimodalRequestNormalizationError.invalidBase64("image").operatorMessage
                == "image_base64 must be valid base64."
        )
        #expect(
            MultimodalRequestNormalizationError.unsupportedPartType("video").operatorMessage
                == "Unsupported multimodal part type: video."
        )
    }

    @Test("normalized text messages flatten non-empty text parts into content")
    func normalizedTextMessagesFlattenNonEmptyTextPartsIntoContent() {
        var first = Melix_Worker_V1_MessagePart()
        first.text = "alpha"
        var second = Melix_Worker_V1_MessagePart()
        second.text = ""
        var third = Melix_Worker_V1_MessagePart()
        third.text = "beta"

        let message = NormalizedTextMessage(role: "user", parts: [first, second, third])

        #expect(message.content == "alpha\nbeta")
    }

    @Test("stream options encode include_usage across public contracts")
    func streamOptionsEncodeIncludeUsageAcrossPublicContracts() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let decoder = JSONDecoder()

        let streamOptions = OpenAIStreamOptions(includeUsage: true)
        let encoded = try encoder.encode(streamOptions)
        let encodedJSON = String(decoding: encoded, as: UTF8.self)
        #expect(encodedJSON.contains("\"include_usage\":true"))

        let decoded = try decoder.decode(OpenAIStreamOptions.self, from: encoded)
        #expect(decoded.includeUsage == true)
    }

    @Test("reasoning controls decode across shipped text endpoints")
    func reasoningControlsDecodeAcrossShippedTextEndpoints() throws {
        let decoder = JSONDecoder()

        let chat = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "enable_thinking": true,
                  "reasoning_effort": "high",
                  "messages": [
                    { "role": "user", "content": "Think carefully." }
                  ]
                }
                """.utf8
            )
        )
        let completions = try decoder.decode(
            OpenAICompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "enable_thinking": false,
                  "reasoning_effort": "low",
                  "prompt": "Answer without hidden reasoning."
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
                  "enable_thinking": true,
                  "reasoning_effort": "medium",
                  "input": "Use hidden reasoning."
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
                  "enable_thinking": true,
                  "reasoning_effort": "high",
                  "messages": [
                    { "role": "user", "content": "Use hidden reasoning." }
                  ]
                }
                """.utf8
            )
        )

        #expect(chat.enableThinking == true)
        #expect(chat.reasoningEffort == "high")
        #expect(completions.enableThinking == false)
        #expect(completions.reasoningEffort == "low")
        #expect(responses.enableThinking == true)
        #expect(responses.reasoningEffort == "medium")
        #expect(messages.enableThinking == true)
        #expect(messages.reasoningEffort == "high")
    }

    @Test("reasoning resolver emits shared execution metadata across endpoint variants")
    func reasoningResolverEmitsSharedExecutionMetadataAcrossEndpointVariants() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "reasoning-policy" })
        let chat = OpenAIChatCompletionsRequest(
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Think carefully.")],
            enableThinking: true,
            reasoningEffort: "high"
        )
        let completions = OpenAICompletionsRequest(
            model: "melix-dev-text",
            prompt: "Think carefully.",
            enableThinking: true,
            reasoningEffort: "high"
        )
        let responses = OpenAIResponsesRequest(
            model: "melix-dev-text",
            input: .text("Think carefully."),
            enableThinking: true,
            reasoningEffort: "high"
        )
        let messages = MelixMessagesRequest(
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Think carefully.")],
            enableThinking: true,
            reasoningEffort: "high"
        )

        let translated = try [
            translator.translate(chat, modelHandle: "worker-text"),
            translator.translate(completions, modelHandle: "worker-text"),
            translator.translate(responses, modelHandle: "worker-text"),
            translator.translate(messages, modelHandle: "worker-text"),
        ]

        for request in translated {
            #expect(request.workerRequest.execution.reasoning.enabled)
            #expect(request.workerRequest.execution.reasoning.separateStream)
            #expect(request.workerRequest.execution.reasoning.modeSource == "request")
            #expect(request.workerRequest.execution.reasoning.effort == "high")
            #expect(request.workerRequest.execution.ext["melix.reasoning.mode"] == "enabled")
            #expect(request.workerRequest.execution.ext["melix.reasoning.mode_source"] == "request")
            #expect(request.workerRequest.execution.ext["melix.reasoning.effort"] == "high")
        }
    }

    @Test("reasoning policy resolver covers template explicit-disable and family auto-detect precedence")
    func reasoningPolicyResolverCoversTemplateExplicitDisableAndFamilyAutoDetectPrecedence() {
        let resolver = ReasoningPolicyResolver()
        let templatePolicy = ResolvedChatTemplatePolicy(
            effectiveValues: [
                "enable_thinking": .bool(true),
                "reasoning_effort": .string(" HIGH ")
            ],
            source: "request"
        )

        let templateResolved = resolver.resolve(
            modelID: "melix-dev-text",
            explicitEnableThinking: nil,
            explicitEffort: nil,
            templatePolicy: templatePolicy,
            messagesThinking: nil,
            preset: nil,
            modelDefault: .init(type: "adaptive", budgetTokens: 321),
            continuityAvailable: true
        )
        #expect(templateResolved.mode == "enabled")
        #expect(templateResolved.modeSource == "template")
        #expect(templateResolved.effort == "high")
        #expect(templateResolved.config?.budgetTokens == 321)
        #expect(templateResolved.continuityRehydrated == false)

        let explicitlyDisabled = resolver.resolve(
            modelID: "melix-dev-text",
            explicitEnableThinking: false,
            explicitEffort: " LOW ",
            templatePolicy: templatePolicy,
            messagesThinking: nil,
            preset: .init(type: "enabled", budgetTokens: 512),
            modelDefault: nil,
            continuityAvailable: true
        )
        #expect(explicitlyDisabled.mode == "off")
        #expect(explicitlyDisabled.modeSource == "request")
        #expect(explicitlyDisabled.effort == "low")
        #expect(explicitlyDisabled.continuityRehydrated == false)

        let families = [
            ("Qwen3-8B", "qwen"),
            ("DeepSeek-R1", "deepseek"),
            ("gpt-oss-20b", "gpt-oss")
        ]
        for (modelID, family) in families {
            let resolved = resolver.resolve(
                modelID: modelID,
                explicitEnableThinking: nil,
                explicitEffort: nil,
                templatePolicy: nil,
                messagesThinking: nil,
                preset: nil,
                modelDefault: nil,
                continuityAvailable: true
            )
            #expect(resolved.mode == "adaptive")
            #expect(resolved.modeSource == "family_auto_detect")
            #expect(resolved.autoDetectModelFamily == family)
            #expect(resolved.continuityRehydrated == false)
        }

        let autoDetectedRequest = try? ChatRequestTranslator(requestIDGenerator: { "reasoning-auto-detect" })
            .translate(
                OpenAIChatCompletionsRequest(
                    model: "Qwen3-8B",
                    messages: [.init(role: "user", content: "Think carefully.")]
                ),
                modelHandle: "worker-text"
            )
        #expect(autoDetectedRequest?.workerRequest.execution.ext["melix.reasoning.auto_detect_model_family"] == "qwen")
        #expect(autoDetectedRequest?.workerRequest.execution.reasoning.autoDetectModelFamily == "qwen")
    }

    @Test("reasoning suppressions have lowest precedence and only apply as fallback")
    func reasoningSuppressionsHaveLowestPrecedenceAndOnlyApplyAsFallback() {
        let resolver = ReasoningPolicyResolver()
        let templatePolicy = ResolvedChatTemplatePolicy(
            effectiveValues: ["enable_thinking": .bool(true)],
            source: "request"
        )

        let templateResolved = resolver.resolve(
            modelID: "plain-text-model",
            explicitEnableThinking: nil,
            explicitEffort: nil,
            templatePolicy: templatePolicy,
            messagesThinking: nil,
            preset: nil,
            modelDefault: nil,
            suppressForStructuredOutput: true
        )
        #expect(templateResolved.mode == "enabled")
        #expect(templateResolved.modeSource == "template")

        let familyResolved = resolver.resolve(
            modelID: "Qwen3-8B",
            explicitEnableThinking: nil,
            explicitEffort: nil,
            templatePolicy: nil,
            messagesThinking: nil,
            preset: nil,
            modelDefault: nil,
            suppressForStructuredOutput: true
        )
        #expect(familyResolved.mode == "adaptive")
        #expect(familyResolved.modeSource == "family_auto_detect")

        let suppressed = resolver.resolve(
            modelID: "plain-text-model",
            explicitEnableThinking: nil,
            explicitEffort: nil,
            templatePolicy: nil,
            messagesThinking: nil,
            preset: nil,
            modelDefault: nil,
            suppressForStructuredOutput: true
        )
        #expect(suppressed.mode == "off")
        #expect(suppressed.modeSource == "structured_output_suppression")
    }

    @Test("reasoning continuity store rejects blank inputs and defaults blank branches")
    func reasoningContinuityStoreRejectsBlankInputsAndDefaultsBlankBranches() async {
        let store = ReasoningContinuityStore()

        #expect(
            await store.record(sessionID: " ", branchID: "branch-main", requestID: "req", reasoningText: "hidden")
                == nil
        )
        #expect(
            await store.record(sessionID: "session", branchID: "branch-main", requestID: " ", reasoningText: "hidden")
                == nil
        )
        #expect(
            await store.record(sessionID: "session", branchID: "branch-main", requestID: "req", reasoningText: " ")
                == nil
        )

        let record = await store.record(
            sessionID: " session ",
            branchID: " ",
            requestID: " req ",
            reasoningText: " hidden "
        )
        #expect(record?.sessionID == "session")
        #expect(record?.branchID == "branch-main")
        #expect(record?.requestID == "req")
        #expect(record?.reasoningText == "hidden")
        #expect(await store.latest(sessionID: " ", branchID: "branch-main") == nil)
        #expect(await store.latest(sessionID: "session", branchID: " ")?.continuityKey == "session::branch-main::req")
    }

    @Test("request contracts preserve message names across text endpoints")
    func requestContractsPreserveMessageNamesAcrossTextEndpoints() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "named-message-contract" })

        let chat = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "messages": [
                    { "role": "assistant", "name": "planner", "content": "Draft answer." }
                  ]
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
                  "input": [
                    { "role": "assistant", "name": "planner", "content": "Draft answer." }
                  ]
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
                  "messages": [
                    { "role": "assistant", "name": "planner", "content": "Draft answer." }
                  ]
                }
                """.utf8
            )
        )

        #expect(chat.messages[0].name == "planner")
        #expect({
            if case let .messages(responseMessages) = responses.input {
                return responseMessages[0].name
            }
            return nil
        }() == "planner")
        #expect(messages.messages[0].name == "planner")

        let translated = try translator.translate(chat, modelHandle: "worker-text")
        #expect(translated.workerRequest.messages[0].name == "planner")
    }

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

    @Test("messages requests decode block content thinking metadata and stop sequences")
    func messagesRequestsDecodeBlockContentThinkingMetadataAndStopSequences() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "msg-thinking-contract" })

        let request = try decoder.decode(
            MelixMessagesRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "system": [
                    { "type": "text", "text": "Be terse." }
                  ],
                  "stream": true,
                  "stop_sequences": ["</final>"],
                  "metadata": { "user_id": "operator-1" },
                  "thinking": { "type": "enabled", "budget_tokens": 64 },
                  "messages": [
                    {
                      "role": "assistant",
                      "content": [
                        { "type": "thinking", "thinking": "trace" },
                        { "type": "text", "text": "draft" }
                      ]
                    },
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Continue." }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        #expect(request.system == "Be terse.")
        #expect(request.systemBlocks == [.init(type: .text, text: "Be terse.")] as [MelixMessagesContentBlock]?)
        #expect(request.messages[0].content == "trace\ndraft")
        #expect(request.messages[0].contentBlocks == [
            .init(type: .thinking, thinking: "trace"),
            .init(type: .text, text: "draft"),
        ] as [MelixMessagesContentBlock]?)
        #expect(request.metadata?.userID == "operator-1")
        #expect(request.stopSequences == ["</final>"])
        #expect(request.thinking == .init(type: "enabled", budgetTokens: 64))

        let normalized = try translator.normalize(request)
        #expect(normalized.stopSequences == ["</final>"])
        #expect(normalized.userID == "operator-1")
        #expect(normalized.thinking == .init(type: "enabled", budgetTokens: 64))
        #expect(normalized.messages[0].parts.map(\.text) == ["Be terse."])
        #expect(normalized.messages[1].parts.map(\.text) == ["trace", "draft"])

        let translated = try translator.translate(normalized, modelHandle: "worker-text")
        #expect(translated.workerRequest.sampling.stop == ["</final>"])
        #expect(translated.workerRequest.execution.reasoning.enabled == true)
        #expect(translated.workerRequest.execution.reasoning.separateStream == true)
        #expect(translated.workerRequest.execution.ext["melix.messages.user_id"] == "operator-1")
        #expect(translated.workerRequest.execution.ext["melix.messages.thinking.type"] == "enabled")
        #expect(translated.workerRequest.execution.ext["melix.messages.thinking.budget_tokens"] == "64")
        #expect(translated.workerRequest.execution.ext["melix.reasoning.budget_tokens"] == "64")
        #expect(translated.workerRequest.execution.ext["melix.reasoning.enforcement"] == "control-plane")
        #expect(translated.workerRequest.execution.ext["melix.reasoning.overflow_behavior"] == "close_stream")
    }

    @Test("chat completions request decodes stop aliases into normalized stop sequences")
    func chatCompletionsRequestDecodesStopAliases() throws {
        let decoder = JSONDecoder()

        let requestWithArrayStop = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "stop": ["</final>"],
                  "messages": [
                    { "role": "user", "content": "Hello" }
                  ]
                }
                """.utf8
            )
        )
        let requestWithLegacyStopSequences = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "stop_sequences": "</legacy>",
                  "messages": [
                    { "role": "user", "content": "Hello" }
                  ]
                }
                """.utf8
            )
        )

        #expect(requestWithArrayStop.stopSequences == ["</final>"])
        #expect(requestWithLegacyStopSequences.stopSequences == ["</legacy>"])
    }

    @Test("chat completions request encodes stop aliases back into OpenAI stop fields")
    func chatCompletionsRequestEncodesStopAliases() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]

        let singleStop = OpenAIChatCompletionsRequest(
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Hello")],
            stopSequences: ["</final>"]
        )
        let manyStops = OpenAIChatCompletionsRequest(
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Hello")],
            stopSequences: ["</final>", "</alt>"]
        )

        let singleEncoded = try #require(
            JSONSerialization.jsonObject(with: encoder.encode(singleStop)) as? [String: Any]
        )
        let manyEncoded = try #require(
            JSONSerialization.jsonObject(with: encoder.encode(manyStops)) as? [String: Any]
        )

        #expect(singleEncoded["stop"] as? String == "</final>")
        #expect(singleEncoded["stop_sequences"] == nil)
        #expect(manyEncoded["stop"] as? [String] == ["</final>", "</alt>"])
    }

    @Test("ocr execution policy stays disabled when model settings do not declare OCR defaults")
    func ocrExecutionPolicyStaysDisabledWithoutModelDefaults() {
        let policy = OCRExecutionPolicy(modelSettings: .init())

        #expect(policy == nil)
    }

    @Test("messages request initializers encode block content and skip empty thinking blocks")
    func messagesRequestInitializersEncodeBlockContentAndSkipEmptyThinkingBlocks() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "msg-init-roundtrip" })

        let request = MelixMessagesRequest(
            model: "melix-dev-text",
            messages: [
                .init(
                    role: "assistant",
                    contentBlocks: [
                        .init(type: .thinking, thinking: ""),
                        .init(type: .text, text: "draft"),
                    ]
                ),
                .init(role: "user", content: "Ship it."),
            ],
            systemBlocks: [.init(type: .text, text: "Be terse.")],
            stream: false,
            temperature: 0.2,
            topP: 0.8,
            maxTokens: 32,
            stopSequences: ["</final>"],
            metadata: .init(userID: "operator-2"),
            thinking: .init(type: "enabled", budgetTokens: 12),
            sessionID: "session-3",
            branchID: "branch-2",
            parentRequestID: "req-3",
            restoreSnapshotID: "snap-3",
            saveBoundarySnapshot: true,
            presetID: "preset-1",
            workflow: .toolFollowup,
            workflowRunID: "run-1",
            workflowNodeID: "node-1"
        )

        let encoded = try encoder.encode(request)
        let encodedJSON = String(decoding: encoded, as: UTF8.self)
        #expect(encodedJSON.contains("\"system\":["))
        #expect(encodedJSON.contains("\"content\":["))
        #expect(encodedJSON.contains("\"user_id\":\"operator-2\""))
        #expect(encodedJSON.contains("\"workflow\":\"tool_followup\""))
        #expect(encodedJSON.contains("\"workflow_node_id\":\"node-1\""))

        let decoded = try decoder.decode(MelixMessagesRequest.self, from: encoded)
        #expect(decoded.systemBlocks == [.init(type: .text, text: "Be terse.")] as [MelixMessagesContentBlock]?)
        #expect(decoded.metadata == .init(userID: "operator-2"))
        #expect(decoded.messages[0].contentBlocks == [
            .init(type: .thinking, thinking: ""),
            .init(type: .text, text: "draft"),
        ] as [MelixMessagesContentBlock]?)
        #expect(decoded.messages[1] == .init(role: "user", content: "Ship it."))

        let normalized = try translator.normalize(decoded)
        #expect(normalized.messages[0].parts.map(\.text) == ["Be terse."])
        #expect(normalized.messages[1].parts.map(\.text) == ["draft"])
        #expect(normalized.messages[2].parts.map(\.text) == ["Ship it."])
    }

    @Test("adaptive thinking resolves from model policy preset and request overrides")
    func adaptiveThinkingResolvesFromModelPolicyPresetAndRequestOverrides() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "adaptive-thinking" })

        let modelPolicyTranslated = try translator.translate(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain the cache.")]
            ),
            modelHandle: "melix-dev-text::swift"
        )
        #expect(modelPolicyTranslated.workerRequest.execution.reasoning.enabled)
        #expect(modelPolicyTranslated.workerRequest.execution.ext["melix.reasoning.mode"] == "adaptive")
        #expect(modelPolicyTranslated.workerRequest.execution.ext["melix.reasoning.source"] == "model")
        #expect(modelPolicyTranslated.workerRequest.execution.ext["melix.reasoning.budget_tokens"] == "192")
        #expect(modelPolicyTranslated.workerRequest.execution.ext["melix.messages.thinking.type"] == "adaptive")
        #expect(modelPolicyTranslated.workerRequest.execution.ext["melix.messages.thinking.budget_tokens"] == "192")

        let presetTranslated = try translator.translate(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain the cache.")],
                presetID: "deep_reasoning"
            ),
            modelHandle: "melix-dev-text::swift"
        )
        #expect(presetTranslated.workerRequest.execution.reasoning.enabled)
        #expect(presetTranslated.workerRequest.execution.ext["melix.reasoning.mode"] == "enabled")
        #expect(presetTranslated.workerRequest.execution.ext["melix.reasoning.source"] == "preset")
        #expect(presetTranslated.workerRequest.execution.ext["melix.reasoning.budget_tokens"] == "512")
        #expect(presetTranslated.workerRequest.execution.ext["melix.messages.thinking.type"] == "enabled")
        #expect(presetTranslated.workerRequest.execution.ext["melix.messages.thinking.budget_tokens"] == "512")

        let requestOverrideTranslated = try translator.translate(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain the cache.")],
                thinking: .init(type: "disabled"),
                presetID: "deep_reasoning"
            ),
            modelHandle: "melix-dev-text::swift"
        )
        #expect(requestOverrideTranslated.workerRequest.execution.reasoning.enabled == false)
        #expect(requestOverrideTranslated.workerRequest.execution.ext["melix.reasoning.mode"] == "off")
        #expect(requestOverrideTranslated.workerRequest.execution.ext["melix.reasoning.source"] == "request")
        #expect(requestOverrideTranslated.workerRequest.execution.ext["melix.messages.thinking.type"] == nil)
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

    @Test("responses message inputs preserve harmony metadata")
    func responsesMessageInputsPreserveHarmonyMetadata() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator()

        let request = try decoder.decode(
            OpenAIResponsesRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "input": [
                    { "role": "developer", "content": "Use tools carefully." },
                    { "role": "assistant", "channel": "analysis", "content": "Need to call the weather tool." },
                    {
                      "role": "assistant",
                      "channel": "commentary",
                      "recipient": "functions.get_weather",
                      "content_type": "json",
                      "content": "{\\"location\\":\\"Tokyo\\"}"
                    },
                    {
                      "role": "functions.get_weather",
                      "channel": "commentary",
                      "recipient": "assistant",
                      "content": "{\\"temperature\\":20}"
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try translator.normalize(request)

        #expect(normalized.messages.count == 4)
        #expect(normalized.messages[1].harmonyMetadata?.channel == "analysis")
        #expect(normalized.messages[2].harmonyMetadata?.channel == "commentary")
        #expect(normalized.messages[2].harmonyMetadata?.recipient == "functions.get_weather")
        #expect(normalized.messages[2].harmonyMetadata?.contentType == "json")
        #expect(normalized.messages[3].role == "functions.get_weather")
        #expect(normalized.messages[3].harmonyMetadata?.recipient == "assistant")
    }

    @Test("harmony-compatible responses requests translate into shared execution requests")
    func harmonyResponsesRequestsTranslateIntoSharedExecutionRequests() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "resp-harmony" })

        let translated = try translator.translate(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .messages([
                    .init(role: "developer", content: "Use tools carefully."),
                    .init(role: "assistant", content: "Need to call the weather tool.", channel: "analysis"),
                    .init(
                        role: "assistant",
                        content: #"{"location":"Tokyo"}"#,
                        channel: "commentary",
                        recipient: "functions.get_weather",
                        contentType: "json"
                    ),
                    .init(
                        role: "functions.get_weather",
                        content: #"{"temperature":20}"#,
                        channel: "commentary",
                        recipient: "assistant"
                    ),
                ]),
                stream: true
            ),
            modelHandle: "melix-dev-text::swift"
        )

        #expect(translated.workerRequest.execution.ext["melix.harmony"] == "true")
        #expect(translated.workerRequest.execution.ext["melix.harmony.message.1.role"] == "assistant")
        #expect(translated.workerRequest.execution.ext["melix.harmony.message.1.channel"] == "analysis")
        #expect(translated.workerRequest.execution.ext["melix.harmony.message.2.channel"] == "commentary")
        #expect(translated.workerRequest.execution.ext["melix.harmony.message.2.recipient"] == "functions.get_weather")
        #expect(translated.workerRequest.execution.ext["melix.harmony.message.2.content_type"] == "json")
        #expect(translated.workerRequest.execution.ext["melix.harmony.message.3.role"] == "functions.get_weather")
        #expect(translated.workerRequest.execution.ext["melix.harmony.message.3.recipient"] == "assistant")
        #expect(translated.workerRequest.messages[2].parts.first?.text == #"{"location":"Tokyo"}"#)
    }

    @Test("chat request contracts decode multimodal content arrays and normalize worker parts")
    func chatRequestContractsDecodeMultimodalContentArrays() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator()

        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-ocr",
                  "stream": true,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Extract the image text." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                            "format": "png",
                            "filename": "fixture.png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try translator.normalizeMultimodalChat(request)
        let message = try #require(normalized.messages.first)

        #expect(request.messages.first?.hasMultimodalContent == true)
        #expect(message.role == "user")
        #expect(message.parts.count == 2)
        #expect(message.parts[0].text == "Extract the image text.")
        #expect(message.parts[1].imageBytes == Data("hello".utf8))
        #expect(message.parts[1].media.mimeType == "image/png")
    }

    @Test("chat request contracts preserve input-image urls in multimodal content arrays")
    func chatRequestContractsDecodeMultimodalImageURLs() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator()

        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": true,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Describe the image." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "url": "https://example.com/fixture.png",
                            "mime_type": "image/png",
                            "filename": "fixture.png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try translator.normalizeMultimodalChat(request)
        let message = try #require(normalized.messages.first)

        #expect(message.parts.count == 2)
        #expect(message.parts[1].imageUri == "https://example.com/fixture.png")
        #expect(message.parts[1].media.sourceKind == .mediaSourceUri)
        #expect(message.parts[1].media.mimeType == "image/png")
        #expect(message.parts[1].media.filename == "fixture.png")
    }

    @Test("ocr model policies shape multimodal requests with default sampling and stop sequences")
    func ocrModelPoliciesShapeMultimodalRequestsWithDefaultSamplingAndStopSequences() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator()
        let model = ModelCatalog.devOCRModel()

        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-ocr",
                  "stream": true,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        {
                          "type": "input_image",
                          "input_image": {
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                            "format": "png",
                            "filename": "fixture.png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try translator.normalizeMultimodalChat(request)
        let translated = try translator.translate(
            normalized,
            modelHandle: "melix-dev-ocr::python",
            modelOCRPolicy: OCRExecutionPolicy(modelSettings: model.settings)
        )

        #expect(translated.workerRequest.sampling.temperature == 0)
        #expect(translated.workerRequest.sampling.topP == 1)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 256)
        #expect(translated.workerRequest.sampling.stop == ["<ocr:end>"])
        #expect(translated.workerRequest.execution.ext["melix.ocr.prompt_profile_id"] == "ocr-default-v1")
        #expect(translated.workerRequest.execution.ext["melix.ocr.prompt_source"] == "model_auto_prompt")
        #expect(translated.workerRequest.execution.ext["melix.ocr.sampling_source"] == "model")
    }

    @Test("ocr request overrides win over model sampling defaults")
    func ocrRequestOverridesWinOverModelSamplingDefaults() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator()
        let model = ModelCatalog.devOCRModel()

        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-ocr",
                  "stream": true,
                  "temperature": 0.4,
                  "top_p": 0.8,
                  "max_tokens": 32,
                  "stop": ["BODY"],
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Read the header only." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                            "format": "png",
                            "filename": "fixture.png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try translator.normalizeMultimodalChat(request)
        let translated = try translator.translate(
            normalized,
            modelHandle: "melix-dev-ocr::python",
            modelOCRPolicy: OCRExecutionPolicy(modelSettings: model.settings)
        )

        #expect(translated.workerRequest.sampling.temperature == 0.4)
        #expect(translated.workerRequest.sampling.topP == 0.8)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 32)
        #expect(translated.workerRequest.sampling.stop == ["BODY"])
        #expect(translated.workerRequest.execution.ext["melix.ocr.prompt_source"] == "request")
        #expect(translated.workerRequest.execution.ext["melix.ocr.sampling_source"] == "request")
        #expect(translated.workerRequest.execution.ext["melix.ocr.stop_sequences"] == "BODY")
    }

    @Test("ocr model policies fall back to imported generation-config sampling defaults")
    func ocrModelPoliciesFallbackToImportedGenerationConfigSamplingDefaults() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator()
        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        modelSettings.ext["ocr_prompt_template"] = "OCR instruction: {prompt}"
        modelSettings.ext["ocr_auto_prompt"] = "Extract the text from the image exactly as written."
        modelSettings.ext["melix.generation_config.temperature"] = "0.15"
        modelSettings.ext["melix.generation_config.top_p"] = "0.92"
        modelSettings.ext["melix.generation_config.max_tokens"] = "384"

        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-ocr",
                  "stream": true,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        {
                          "type": "input_image",
                          "input_image": {
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                            "format": "png",
                            "filename": "fixture.png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try translator.normalizeMultimodalChat(request)
        let translated = try translator.translate(
            normalized,
            modelHandle: "melix-dev-ocr::python",
            modelOCRPolicy: OCRExecutionPolicy(modelSettings: modelSettings)
        )

        #expect(translated.workerRequest.sampling.temperature == 0.15)
        #expect(translated.workerRequest.sampling.topP == 0.92)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 384)
        #expect(translated.workerRequest.execution.ext["melix.ocr.sampling_source"] == "model")
    }

    @Test("chat request contracts accept image-only multimodal content")
    func chatRequestContractsDecodeImageOnlyMultimodalContent() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator()

        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": true,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        {
                          "type": "input_image",
                          "input_image": {
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                            "filename": "image-only.png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try translator.normalizeMultimodalChat(request)
        let message = try #require(normalized.messages.first)

        #expect(message.parts.count == 1)
        #expect(message.content.isEmpty)
        #expect(message.parts[0].imageBytes == Data("hello".utf8))
        #expect(message.parts[0].media.filename == "image-only.png")
    }

    @Test("chat request messages round-trip text and multimodal content payloads")
    func chatRequestMessagesRoundTripTextAndMultimodalContentPayloads() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let decoder = JSONDecoder()

        let textMessage = OpenAIChatCompletionsRequest.Message(role: "user", content: "hello")
        let encodedText = try encoder.encode(textMessage)
        let decodedText = try decoder.decode(OpenAIChatCompletionsRequest.Message.self, from: encodedText)

        #expect(decodedText.role == "user")
        #expect(decodedText.content == "hello")
        #expect(decodedText.contentParts == nil)
        #expect(decodedText.hasMultimodalContent == false)

        let multimodalMessage = OpenAIChatCompletionsRequest.Message(
            role: "user",
            contentParts: [
                .init(type: .text, text: "Describe the image."),
                .init(
                    type: .inputImage,
                    inputImage: .init(
                        data: "aGVsbG8=",
                        mimeType: "image/png",
                        format: "png",
                        filename: "fixture.png"
                    )
                ),
            ]
        )
        let encodedMultimodal = try encoder.encode(multimodalMessage)
        let decodedMultimodal = try decoder.decode(
            OpenAIChatCompletionsRequest.Message.self,
            from: encodedMultimodal
        )

        #expect(decodedMultimodal.role == "user")
        #expect(decodedMultimodal.content == "Describe the image.")
        #expect(decodedMultimodal.hasMultimodalContent)
        #expect(decodedMultimodal.contentParts?.count == 2)
        #expect(String(decoding: encodedMultimodal, as: UTF8.self).contains("\"content\":["))
    }

    @Test("multimodal chat normalization preserves text-only and multimodal messages in order")
    func multimodalChatNormalizationPreservesTextOnlyAndMultimodalMessagesInOrder() throws {
        let translator = ChatRequestTranslator()
        let request = OpenAIChatCompletionsRequest(
            model: "melix-dev-vlm",
            messages: [
                .init(role: "system", content: "Be terse."),
                .init(
                    role: "user",
                    contentParts: [
                        .init(type: .text, text: "Describe the image."),
                        .init(
                            type: .inputImage,
                            inputImage: .init(
                                data: "aGVsbG8=",
                                mimeType: "image/png",
                                format: "png",
                                filename: "fixture.png"
                            )
                        ),
                    ]
                ),
            ],
            stream: true
        )

        let normalized = try translator.normalizeMultimodalChat(request)

        #expect(normalized.messages.count == 2)
        #expect(normalized.messages[0] == NormalizedTextMessage(role: "system", content: "Be terse."))
        #expect(normalized.messages[1].role == "user")
        #expect(normalized.messages[1].content == "Describe the image.")
        #expect(normalized.messages[1].parts.count == 2)
        #expect(normalized.messages[1].parts[1].imageBytes == Data("hello".utf8))
    }

    @Test("equivalent single-turn requests normalize to the same internal text shape")
    func equivalentSingleTurnRequestsNormalizeToSameShape() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-normalized" })

        let chat = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain cache routing.")],
                stream: true,
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )
        let completions = try translator.normalize(
            OpenAICompletionsRequest(
                model: "melix-dev-text",
                prompt: "Explain cache routing.",
                stream: true,
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )
        let responses = try translator.normalize(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Explain cache routing."),
                stream: true,
                temperature: 0.2,
                topP: 0.9,
                maxTokens: 128
            )
        )
        let messages = try translator.normalize(
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
    func systemFieldsNormalizeConsistently() throws {
        let translator = ChatRequestTranslator()

        let chat = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [
                    .init(role: "system", content: "Be terse."),
                    .init(role: "user", content: "Summarize the queue."),
                ]
            )
        )
        let responses = try translator.normalize(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Summarize the queue."),
                instructions: "Be terse."
            )
        )
        let messages = try translator.normalize(
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
    func responsesMessageInputsNormalizeWithoutLosingRoleOrdering() throws {
        let translator = ChatRequestTranslator()
        let normalized = try translator.normalize(
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

    @Test("equivalent endpoint requests normalize shared execution metadata consistently")
    func equivalentEndpointRequestsNormalizeSharedExecutionMetadataConsistently() throws {
        let translator = ChatRequestTranslator()

        let chat = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain cache routing.")],
                stream: false,
                temperature: 0.3,
                topP: 0.85,
                maxTokens: 96,
                sessionID: "session-shared",
                branchID: "branch-alt",
                parentRequestID: "req-parent",
                restoreSnapshotID: "snap-001",
                saveBoundarySnapshot: false,
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-1",
                workflowNodeID: "node-1"
            )
        )
        let completions = try translator.normalize(
            OpenAICompletionsRequest(
                model: "melix-dev-text",
                prompt: "Explain cache routing.",
                stream: false,
                temperature: 0.3,
                topP: 0.85,
                maxTokens: 96,
                sessionID: "session-shared",
                branchID: "branch-alt",
                parentRequestID: "req-parent",
                restoreSnapshotID: "snap-001",
                saveBoundarySnapshot: false,
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-1",
                workflowNodeID: "node-1"
            )
        )
        let responses = try translator.normalize(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Explain cache routing."),
                stream: false,
                temperature: 0.3,
                topP: 0.85,
                maxTokens: 96,
                sessionID: "session-shared",
                branchID: "branch-alt",
                parentRequestID: "req-parent",
                restoreSnapshotID: "snap-001",
                saveBoundarySnapshot: false,
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-1",
                workflowNodeID: "node-1"
            )
        )
        let messages = try translator.normalize(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Explain cache routing.")],
                stream: false,
                temperature: 0.3,
                topP: 0.85,
                maxTokens: 96,
                sessionID: "session-shared",
                branchID: "branch-alt",
                parentRequestID: "req-parent",
                restoreSnapshotID: "snap-001",
                saveBoundarySnapshot: false,
                presetID: "deep_reasoning",
                workflow: .toolFollowup,
                workflowRunID: "wf-1",
                workflowNodeID: "node-1"
            )
        )

        for request in [chat, completions, responses, messages] {
            #expect(request.model == "melix-dev-text")
            #expect(request.stream == false)
            #expect(request.temperature == 0.3)
            #expect(request.topP == 0.85)
            #expect(request.maxTokens == 96)
            #expect(request.sessionID == "session-shared")
            #expect(request.branchID == "branch-alt")
            #expect(request.parentRequestID == "req-parent")
            #expect(request.restoreSnapshotID == "snap-001")
            #expect(request.saveBoundarySnapshot == false)
            #expect(request.presetID == "deep_reasoning")
            #expect(request.workflow == .toolFollowup)
            #expect(request.workflowRunID == "wf-1")
            #expect(request.workflowNodeID == "node-1")
        }
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

    @Test("chat translation wrapper falls back to imported generation-config defaults")
    func chatTranslationWrapperFallsBackToImportedGenerationConfigDefaults() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-chat-generation-config" })
        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.ext["melix.generation_config.temperature"] = "0.2"
        modelSettings.ext["melix.generation_config.top_p"] = "0.88"
        modelSettings.ext["melix.generation_config.max_tokens"] = "512"

        let normalized = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Hello")],
                sessionID: "session-wrapper"
            )
        )
        let translated = try translator.translate(
            normalized,
            modelHandle: "melix-dev-text::swift",
            modelSamplingPolicy: ModelSamplingPolicy(modelSettings: modelSettings)
        )

        #expect(translated.requestID == "req-chat-generation-config")
        #expect(translated.workerRequest.sampling.temperature == 0.2)
        #expect(translated.workerRequest.sampling.topP == 0.88)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 512)
    }

    @Test("chat translation wrapper falls back to gateway serving defaults when no model policy exists")
    func chatTranslationWrapperFallsBackToGatewayServingDefaults() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-chat-serving-defaults" })
        let normalized = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Hello")],
                sessionID: "session-serving-defaults"
            )
        )
        let translated = try translator.translate(
            normalized,
            modelHandle: "melix-dev-text::swift",
            gatewayServingDefaults: GatewayServingDefaultsPolicy(
                temperature: 0.35,
                topP: 0.92,
                maxTokens: 384,
                streamIntervalTokens: 3,
                maxConcurrentRequests: 5,
                concurrentProcessingEnabled: true,
                prefillBatchSize: 3,
                completionBatchSize: 2,
                accelerationMode: .speculativeDecode,
                draftModelID: "melix-dev-draft",
                numDraftTokens: 6
            )
        )

        #expect(translated.workerRequest.sampling.temperature == 0.35)
        #expect(translated.workerRequest.sampling.topP == 0.92)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 384)
        #expect(translated.workerRequest.execution.ext["melix.stream.interval_tokens"] == "3")
        #expect(translated.workerRequest.execution.ext["melix.gateway.max_concurrent_requests"] == "5")
        #expect(translated.workerRequest.execution.ext["melix.gateway.concurrent_processing"] == "true")
        #expect(translated.workerRequest.execution.ext["melix.gateway.prefill_batch_size"] == "3")
        #expect(translated.workerRequest.execution.ext["melix.gateway.completion_batch_size"] == "2")
        #expect(translated.workerRequest.execution.ext["melix.gateway.acceleration_mode"] == "speculative_decode")
        #expect(translated.workerRequest.execution.ext["melix.gateway.draft_model_id"] == "melix-dev-draft")
        #expect(translated.workerRequest.execution.ext["melix.gateway.num_draft_tokens"] == "6")
    }

    @Test("model generation config overrides gateway serving defaults while admission metadata stays gateway-owned")
    func modelGenerationConfigOverridesGatewayServingDefaultsWhileAdmissionMetadataStaysGatewayOwned() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-chat-serving-merge" })
        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.ext["melix.generation_config.temperature"] = "0.2"
        modelSettings.ext["melix.generation_config.top_p"] = "0.88"
        modelSettings.ext["melix.generation_config.max_tokens"] = "512"

        let normalized = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Hello")],
                sessionID: "session-serving-merge"
            )
        )
        let translated = try translator.translate(
            normalized,
            modelHandle: "melix-dev-text::swift",
            modelSamplingPolicy: ModelSamplingPolicy(modelSettings: modelSettings),
            gatewayServingDefaults: GatewayServingDefaultsPolicy(
                temperature: 0.35,
                topP: 0.92,
                maxTokens: 384,
                streamIntervalTokens: 4,
                maxConcurrentRequests: 6,
                concurrentProcessingEnabled: false,
                prefillBatchSize: 4,
                completionBatchSize: 3
            )
        )

        #expect(translated.workerRequest.sampling.temperature == 0.2)
        #expect(translated.workerRequest.sampling.topP == 0.88)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 512)
        #expect(translated.workerRequest.execution.ext["melix.stream.interval_tokens"] == "4")
        #expect(translated.workerRequest.execution.ext["melix.gateway.max_concurrent_requests"] == "6")
        #expect(translated.workerRequest.execution.ext["melix.gateway.concurrent_processing"] == "false")
        #expect(translated.workerRequest.execution.ext["melix.gateway.prefill_batch_size"] == "4")
        #expect(translated.workerRequest.execution.ext["melix.gateway.completion_batch_size"] == "3")
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
            try translator.normalize(
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
            try translator.normalize(
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
            try translator.normalize(
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
            try translator.normalize(
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
