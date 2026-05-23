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

    @Test("OpenAI chat tools flow into worker ToolConfig and select a parser")
    func openAIChatToolsFlowIntoWorkerToolConfig() throws {
        let request = try JSONDecoder().decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "stream": true,
                  "messages": [
                    { "role": "user", "content": "Check auth." }
                  ],
                  "tools": [
                    {
                      "type": "function",
                      "function": {
                        "name": "terminal",
                        "description": "Run a shell command.",
                        "parameters": {
                          "type": "object",
                          "properties": {
                            "command": { "type": "string" }
                          },
                          "required": ["command"]
                        }
                      }
                    }
                  ],
                  "tool_choice": "auto"
                }
                """.utf8
            )
        )
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-openai-tools" })
        let normalized = try translator.normalize(request)
        let translated = try translator.translate(normalized, modelHandle: "melix-dev-text::swift")
        let workerRequest = translated.workerRequest

        #expect(normalized.tools.map(\.name) == ["terminal"])
        #expect(normalized.toolChoice == "auto")
        #expect(workerRequest.execution.hasToolConfig)
        #expect(workerRequest.execution.toolConfig.schemaFormat == "openai_chat_tools")
        #expect(workerRequest.execution.toolConfig.schemaVersion == "2024-06")
        #expect(workerRequest.execution.toolConfig.parser == "xml")
        #expect(workerRequest.execution.toolConfig.toolChoice == "auto")
        #expect(workerRequest.execution.toolConfig.tools.count == 1)
        #expect(workerRequest.execution.toolConfig.tools[0].name == "terminal")
        #expect(workerRequest.execution.toolConfig.tools[0].description_p == "Run a shell command.")
        #expect(workerRequest.execution.toolConfig.tools[0].jsonSchema.contains("\"command\""))
        #expect(workerRequest.execution.ext["melix.tool_parser.mode"] == "xml")
        #expect(workerRequest.execution.ext["melix.tool_parser.source"] == "openai_tools")
        #expect(workerRequest.execution.ext["melix.tool_config.source"] == "openai_chat_tools")
        #expect(workerRequest.execution.ext["melix.tool_config.tool_count"] == "1")
    }

    @Test("OpenAI chat tools normalize structured choices and filter invalid entries")
    func openAIChatToolsNormalizeStructuredChoicesAndFilterInvalidEntries() throws {
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "messages": [
                    { "role": "user", "content": "Check auth." }
                  ],
                  "tools": [
                    {
                      "type": "function",
                      "function": {
                        "name": " terminal ",
                        "description": " ",
                        "parameters": {
                          "type": "object",
                          "properties": {
                            "command": { "type": "string" }
                          }
                        }
                      }
                    },
                    {
                      "type": "retrieval",
                      "function": { "name": "ignored" }
                    },
                    {
                      "type": "function",
                      "function": { "name": " " }
                    }
                  ],
                  "tool_choice": {
                    "type": "function",
                    "function": { "name": "terminal" }
                  }
                }
                """.utf8
            )
        )

        #expect(request.normalizedToolChoice == "{\"function\":{\"name\":\"terminal\"},\"type\":\"function\"}")
        let structuredChoice = try #require(request.toolChoice)
        let structuredChoiceJSON = String(decoding: try encoder.encode(structuredChoice), as: UTF8.self)
        #expect(structuredChoiceJSON == "{\"function\":{\"name\":\"terminal\"},\"type\":\"function\"}")

        let modeChoice = OpenAIChatToolChoice.mode(" required ")
        #expect(modeChoice.normalizedValue == "required")
        #expect(String(decoding: try encoder.encode(modeChoice), as: UTF8.self) == "\" required \"")
        #expect(OpenAIChatToolChoice.mode(" ").normalizedValue == nil)

        let normalizedTools = try request.normalizedTools
        #expect(normalizedTools.count == 1)
        #expect(normalizedTools[0].name == "terminal")
        #expect(normalizedTools[0].description == "")
        #expect(normalizedTools[0].jsonSchema.contains("\"command\""))

        let defaultSchemaTool = OpenAIChatTool(
            type: "function",
            function: .init(name: "ping")
        )
        let defaultSchemaDefinition = try #require(try defaultSchemaTool.normalizedDefinition())
        #expect(defaultSchemaDefinition.name == "ping")
        #expect(defaultSchemaDefinition.jsonSchema == "{}")

        let unsupportedTool = OpenAIChatTool(type: "web_search")
        #expect(try unsupportedTool.normalizedDefinition() == nil)
        let blankFunctionTool = OpenAIChatTool(type: "function", function: .init(name: " "))
        #expect(try blankFunctionTool.normalizedDefinition() == nil)
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

    @Test("prior assistant hidden-thought prefixes are stripped before prompt rebuild")
    func priorAssistantHiddenThoughtPrefixesAreStrippedBeforePromptRebuild() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "reasoning-history-strip" })
        let translated = try translator.translate(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [
                    .init(
                        role: "assistant",
                        content: "<think>hidden chain</think>\n<think>hidden continuation</think>Visible answer mentioning <think> literally."
                    ),
                    .init(role: "user", content: "Continue.")
                ]
            ),
            modelHandle: "worker-text"
        )

        let assistant = try #require(translated.workerRequest.messages.first)

        #expect(assistant.role == "assistant")
        #expect(assistant.parts.first?.text == "Visible answer mentioning <think> literally.")
        #expect(translated.workerRequest.execution.ext["melix.reasoning.history_strip_count"] == "2")
        #expect(
            !translated.workerRequest.messages
                .map(\.parts)
                .flatMap { $0 }
                .map(\.text)
                .joined(separator: "\n")
                .contains("hidden chain")
        )
    }

    @Test("prior assistant hidden-thought prefixes are stripped from every text part")
    func priorAssistantHiddenThoughtPrefixesAreStrippedFromEveryTextPart() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "reasoning-history-strip-parts" })
        let translated = try translator.translate(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [
                    .init(
                        role: "assistant",
                        contentBlocks: [
                            .init(type: .text, text: "<think>hidden first part</think>Visible first part."),
                            .init(type: .text, text: "\n<think>hidden second part</think>Visible second part."),
                        ]
                    ),
                    .init(role: "user", content: "Continue.")
                ]
            ),
            modelHandle: "worker-text"
        )

        let assistant = try #require(translated.workerRequest.messages.first)

        #expect(assistant.role == "assistant")
        #expect(assistant.parts.map(\.text) == ["Visible first part.", "Visible second part."])
        #expect(translated.workerRequest.execution.ext["melix.reasoning.history_strip_count"] == "2")
    }

    @Test("inline hidden-thought literals in assistant history are preserved")
    func inlineHiddenThoughtLiteralsInAssistantHistoryArePreserved() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "reasoning-history-literal" })
        let translated = try translator.translate(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [
                    .init(role: "assistant", content: "Visible <think> literal marker"),
                    .init(role: "user", content: "Continue.")
                ]
            ),
            modelHandle: "worker-text"
        )

        let assistant = try #require(translated.workerRequest.messages.first)

        #expect(assistant.parts.first?.text == "Visible <think> literal marker")
        #expect(translated.workerRequest.execution.ext["melix.reasoning.history_strip_count"] == "0")
    }

    @Test("prior assistant raw tool-call prefixes are stripped before prompt rebuild")
    func priorAssistantRawToolCallPrefixesAreStrippedBeforePromptRebuild() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "tool-call-history-strip" })
        let translated = try translator.translate(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [
                    .init(
                        role: "assistant",
                        content: """
                        <|tool_call>call:github_auth:github_auth_check()<tool_call|>
                        <think>hidden after tool</think>
                        <|tool_call>call:terminal:run_command{"command":"gh auth status"}<tool_call|>
                        Visible follow-up.
                        """
                    ),
                    .init(role: "user", content: "Continue.")
                ]
            ),
            modelHandle: "worker-text"
        )

        let assistant = try #require(translated.workerRequest.messages.first)

        #expect(assistant.role == "assistant")
        #expect(assistant.parts.first?.text == "\nVisible follow-up.")
        #expect(translated.workerRequest.execution.ext["melix.tool_call_history_strip_count"] == "2")
        #expect(translated.workerRequest.execution.ext["melix.reasoning.history_strip_count"] == "1")
        #expect(
            !translated.workerRequest.messages
                .map(\.parts)
                .flatMap { $0 }
                .map(\.text)
                .joined(separator: "\n")
                .contains("github_auth:github_auth_check")
        )
        #expect(
            !translated.workerRequest.messages
                .map(\.parts)
                .flatMap { $0 }
                .map(\.text)
                .joined(separator: "\n")
                .contains("hidden after tool")
        )
        #expect(
            !translated.workerRequest.messages
                .map(\.parts)
                .flatMap { $0 }
                .map(\.text)
                .joined(separator: "\n")
                .contains("terminal:run_command")
        )
    }

    @Test("inline raw tool-call literals in assistant history are preserved")
    func inlineRawToolCallLiteralsInAssistantHistoryArePreserved() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "tool-call-history-literal" })
        let translated = try translator.translate(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [
                    .init(role: "assistant", content: "Visible <|tool_call> literal marker"),
                    .init(role: "user", content: "Continue.")
                ]
            ),
            modelHandle: "worker-text"
        )

        let assistant = try #require(translated.workerRequest.messages.first)

        #expect(assistant.parts.first?.text == "Visible <|tool_call> literal marker")
        #expect(translated.workerRequest.execution.ext["melix.tool_call_history_strip_count"] == "0")
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
            modelDefault: .init(type: "adaptive", budgetTokens: 321)
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
            modelDefault: nil
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
                modelDefault: nil
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

    @Test("reasoning continuity store bounds retained entries and hidden text size")
    func reasoningContinuityStoreBoundsRetainedEntriesAndHiddenTextSize() async {
        let store = ReasoningContinuityStore(maxEntries: 2, maxReasoningTextUTF8Bytes: 8)

        _ = await store.record(
            sessionID: "session-a",
            branchID: "main",
            requestID: "req-a",
            reasoningText: "1234567890"
        )
        _ = await store.record(
            sessionID: "session-b",
            branchID: "main",
            requestID: "req-b",
            reasoningText: "abcdefghij"
        )
        _ = await store.record(
            sessionID: "session-c",
            branchID: "main",
            requestID: "req-c",
            reasoningText: "klmnopqrst"
        )

        #expect(await store.latest(sessionID: "session-a", branchID: "main") == nil)
        #expect(await store.latest(sessionID: "session-b", branchID: "main")?.reasoningText == "abcdefgh")
        #expect(await store.latest(sessionID: "session-c", branchID: "main")?.reasoningText == "klmnopqr")
    }

    @Test("reasoning continuity store updates existing branches and honors zero limits")
    func reasoningContinuityStoreUpdatesExistingBranchesAndHonorsZeroLimits() async {
        let updateStore = ReasoningContinuityStore(maxEntries: 1)

        _ = await updateStore.record(
            sessionID: "session-update",
            branchID: "main",
            requestID: "req-old",
            reasoningText: "old hidden"
        )
        _ = await updateStore.record(
            sessionID: "session-update",
            branchID: "main",
            requestID: "req-new",
            reasoningText: "new hidden"
        )

        #expect(await updateStore.latest(sessionID: "session-update", branchID: "main")?.requestID == "req-new")

        let zeroEntryStore = ReasoningContinuityStore(maxEntries: 0)
        let evictedRecord = await zeroEntryStore.record(
            sessionID: "session-zero-entry",
            branchID: "main",
            requestID: "req-zero-entry",
            reasoningText: "hidden"
        )
        #expect(evictedRecord?.requestID == "req-zero-entry")
        #expect(await zeroEntryStore.latest(sessionID: "session-zero-entry", branchID: "main") == nil)

        let zeroByteStore = ReasoningContinuityStore(maxReasoningTextUTF8Bytes: 0)
        let rejectedRecord = await zeroByteStore.record(
            sessionID: "session-zero-byte",
            branchID: "main",
            requestID: "req-zero-byte",
            reasoningText: "hidden"
        )
        #expect(rejectedRecord == nil)
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

    @Test("chat template cache fingerprint stores hashes not raw kwargs JSON")
    func chatTemplateCacheFingerprintStoresHashesNotRawKwargsJSON() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "chat-template-hash" })
        let translated = try translator.translate(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Use template kwargs.")],
                chatTemplateKwargs: .init(values: [
                    "enable_thinking": .bool(true),
                    "custom_flag": .string("enabled")
                ])
            ),
            modelHandle: "worker-text"
        )

        let effectiveJSON = try #require(
            translated.workerRequest.execution.ext["melix.chat_template_kwargs.effective_json"]
        )
        let scopeHash = translated.workerRequest.execution.scope.chatTemplateKwargsHash

        #expect(scopeHash != effectiveJSON)
        #expect(scopeHash.range(of: #"^[0-9a-f]{64}$"#, options: .regularExpression) != nil)
        #expect(translated.workerRequest.execution.ext["melix.cache.fingerprint.chat_template_kwargs"] == scopeHash)
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

    @Test("OpenAI multimodal chat normalization emits shared media part summary metadata")
    func openAIMultimodalChatNormalizationEmitsSharedMediaPartSummaryMetadata() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-media-summary" })
        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": false,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Inspect the media." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "data": "aW1hZ2U=",
                            "mime_type": "image/png",
                            "format": "png",
                            "filename": "inline.png"
                          }
                        },
                        {
                          "type": "input_audio",
                          "input_audio": {
                            "url": "file:///tmp/clip.wav",
                            "format": "wav",
                            "filename": "clip.wav"
                          }
                        },
                        {
                          "type": "input_video",
                          "input_video": {
                            "url": "/tmp/demo.mp4",
                            "format": "mp4",
                            "filename": "demo.mp4"
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
        let translated = try translator.translate(normalized, modelHandle: "worker-vlm")

        #expect(normalized.mediaPartsSummary.parts.count == 3)
        #expect(normalized.mediaPartsSummary.parts.map(\.mediaKind) == ["image", "audio", "video"])
        #expect(normalized.mediaPartsSummary.parts.map(\.sourceKind) == ["inline_bytes", "local", "local"])
        #expect(normalized.mediaPartsSummary.parts.map(\.turnIndex) == [0, 0, 0])
        #expect(normalized.mediaPartsSummary.parts.map(\.partIndex) == [1, 2, 3])
        #expect(normalized.mediaPartsSummary.parts[0].byteLength == 5)
        #expect(normalized.mediaPartsSummary.parts[0].stableDigest?.count == 64)
        #expect(normalized.mediaPartsSummary.parts[1].source == "file:///tmp/clip.wav")
        #expect(normalized.mediaPartsSummary.parts[2].source == "/tmp/demo.mp4")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.count"] == "3")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.contract"] == "shared_summary")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.0.kind"] == "image")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.0.source_kind"] == "inline_bytes")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.0.byte_length"] == "5")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.0.filename"] == "inline.png")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.1.source"] == "file:///tmp/clip.wav")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.2.source"] == "/tmp/demo.mp4")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.2.digest"]?.count == 64)
    }

    @Test("multimodal chat translation preserves two-turn image ordering in worker message parts")
    func multimodalChatTranslationPreservesTwoTurnImageOrderingInWorkerMessageParts() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-two-turn-images" })
        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": false,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "First turn first." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "url": "/tmp/turn-0-first.png",
                            "filename": "turn-0-first.png"
                          }
                        },
                        { "type": "text", "text": "Then second." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "url": "/tmp/turn-0-second.png",
                            "filename": "turn-0-second.png"
                          }
                        }
                      ]
                    },
                    {
                      "role": "assistant",
                      "content": "I see the first pair."
                    },
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Now compare this one." },
                        {
                          "type": "image_url",
                          "image_url": {
                            "url": "https://example.com/turn-2-first.png",
                            "filename": "turn-2-first.png"
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
        let translated = try translator.translate(normalized, modelHandle: "worker-vlm")
        let workerMessages = translated.workerRequest.messages

        #expect(workerMessages.count == 3)
        #expect(workerMessages[0].parts.map(\.text) == ["First turn first.", "", "Then second.", ""])
        #expect(workerMessages[0].parts[1].imageUri == "/tmp/turn-0-first.png")
        #expect(workerMessages[0].parts[3].imageUri == "/tmp/turn-0-second.png")
        #expect(workerMessages[2].parts[0].text == "Now compare this one.")
        #expect(workerMessages[2].parts[1].imageUri == "https://example.com/turn-2-first.png")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.count"] == "3")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.0.turn_index"] == "0")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.0.part_index"] == "1")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.0.source"] == "/tmp/turn-0-first.png")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.1.turn_index"] == "0")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.1.part_index"] == "3")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.1.source"] == "/tmp/turn-0-second.png")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.2.turn_index"] == "2")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.2.part_index"] == "1")
        #expect(translated.workerRequest.execution.ext["melix.media_parts.2.source"] == "https://example.com/turn-2-first.png")
        #expect(translated.workerRequest.execution.ext["melix.worker_content.contract"] == "ordered_message_parts")
        #expect(translated.workerRequest.execution.ext["melix.worker_content.media_order"] == "message_part_order")
    }

    @Test("legacy top-level chat images only inject when message-level media is absent")
    func legacyTopLevelChatImagesOnlyInjectWhenMessageLevelMediaIsAbsent() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-legacy-image" })
        let legacyOnly = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": false,
                  "image_url": "file:///tmp/legacy.png",
                  "messages": [
                    { "role": "system", "content": "Be precise." },
                    { "role": "user", "content": "Describe the legacy image." }
                  ]
                }
                """.utf8
            )
        )
        let mixed = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": false,
                  "image_url": "file:///tmp/legacy.png",
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Describe the message image." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "url": "file:///tmp/message-level.png",
                            "filename": "message-level.png"
                          }
                        }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let legacyTranslated = try translator.translate(legacyOnly, modelHandle: "worker-vlm")
        let mixedTranslated = try translator.translate(
            try translator.normalizeMultimodalChat(mixed),
            modelHandle: "worker-vlm"
        )
        let legacyUserMessage = try #require(legacyTranslated.workerRequest.messages.last)
        let legacyImagePart = try #require(legacyUserMessage.parts.last)

        #expect(legacyTranslated.workerRequest.messages[0].parts.count == 1)
        #expect(legacyUserMessage.parts.count == 2)
        #expect(legacyUserMessage.parts[0].text == "Describe the legacy image.")
        #expect(legacyImagePart.imageUri == "file:///tmp/legacy.png")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.media_parts.count"] == "1")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.media_parts.0.turn_index"] == "1")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.media_parts.0.part_index"] == "1")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.media_parts.0.source"] == "file:///tmp/legacy.png")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.legacy_image_fallback"] == "injected")

        #expect(mixedTranslated.workerRequest.messages[0].parts.count == 2)
        #expect(mixedTranslated.workerRequest.messages[0].parts[1].imageUri == "file:///tmp/message-level.png")
        #expect(mixedTranslated.workerRequest.execution.ext["melix.media_parts.count"] == "1")
        #expect(mixedTranslated.workerRequest.execution.ext["melix.media_parts.0.source"] == "file:///tmp/message-level.png")
        #expect(mixedTranslated.workerRequest.execution.ext["melix.legacy_image_fallback"] == nil)
    }

    @Test("text-only chat content arrays preserve ordered parts and allow legacy image fallback")
    func textOnlyChatContentArraysPreserveOrderedPartsAndAllowLegacyImageFallback() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-text-array-legacy" })
        let textOnlyArray = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": false,
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "First text part." },
                        { "type": "input_text", "text": "Second text part." }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )
        let textArrayWithLegacyImage = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": false,
                  "image_url": "file:///tmp/legacy-array.png",
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "First text part." },
                        { "type": "input_text", "text": "Second text part." }
                      ]
                    }
                  ]
                }
                """.utf8
            )
        )

        let textOnlyTranslated = try translator.translate(textOnlyArray, modelHandle: "worker-vlm")
        let legacyTranslated = try translator.translate(textArrayWithLegacyImage, modelHandle: "worker-vlm")
        let normalizedTextOnly = try translator.normalize(textOnlyArray)

        #expect(normalizedTextOnly.messages[0].parts.map(\.text) == [
            "First text part.",
            "Second text part.",
        ])
        #expect(textOnlyTranslated.workerRequest.messages[0].parts.map(\.text) == [
            "First text part.",
            "Second text part.",
        ])
        #expect(textOnlyTranslated.workerRequest.execution.ext["melix.media_parts.count"] == nil)
        #expect(
            textOnlyTranslated.workerRequest.execution.ext["melix.worker_content.contract"]
                == "ordered_message_parts"
        )
        #expect(textOnlyTranslated.workerRequest.execution.ext["melix.legacy_image_fallback"] == nil)

        #expect(legacyTranslated.workerRequest.messages[0].parts.map(\.text) == [
            "First text part.",
            "Second text part.",
            "",
        ])
        #expect(legacyTranslated.workerRequest.messages[0].parts[2].imageUri == "file:///tmp/legacy-array.png")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.media_parts.count"] == "1")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.media_parts.0.part_index"] == "2")
        #expect(legacyTranslated.workerRequest.execution.ext["melix.legacy_image_fallback"] == "injected")
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

    @Test("ocr token fallback stays short when gateway text defaults increase")
    func ocrTokenFallbackStaysShortWhenGatewayTextDefaultsIncrease() throws {
        let translator = ChatRequestTranslator()
        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"

        let normalized = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-ocr",
                messages: [.init(role: "user", content: "Read the image.")]
            )
        )
        let translated = try translator.translate(
            normalized,
            modelHandle: "melix-dev-ocr::python",
            modelOCRPolicy: OCRExecutionPolicy(modelSettings: modelSettings),
            gatewayServingDefaults: GatewayServingDefaultsPolicy(
                temperature: 0.35,
                topP: 0.92,
                maxTokens: 32_768,
                streamIntervalTokens: 3,
                maxConcurrentRequests: 5
            )
        )

        #expect(translated.workerRequest.sampling.maxOutputTokens == 256)
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

    @Test("chat completions default to non-stream while other text endpoints default to stream")
    func chatCompletionsDefaultToNonStreamWhileOtherTextEndpointsDefaultToStream() throws {
        let translator = ChatRequestTranslator()

        let chat = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Hello")]
            )
        )
        let completions = try translator.normalize(
            OpenAICompletionsRequest(
                model: "melix-dev-text",
                prompt: "Hello"
            )
        )
        let responses = try translator.normalize(
            OpenAIResponsesRequest(
                model: "melix-dev-text",
                input: .text("Hello")
            )
        )
        let messages = try translator.normalize(
            MelixMessagesRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Hello")]
            )
        )

        #expect(!chat.stream)
        #expect(completions.stream)
        #expect(responses.stream)
        #expect(messages.stream)
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
        #expect(!translated.stream)
        #expect(!translated.workerRequest.stream)
        #expect(translated.workerRequest.sampling.temperature == 0.7)
        #expect(translated.workerRequest.sampling.topP == 1.0)
        #expect(translated.workerRequest.sampling.maxOutputTokens == 32_768)
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
                numDraftTokens: 6,
                accelerationProfile: "throughput"
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
        #expect(translated.workerRequest.execution.ext["melix.gateway.acceleration_profile"] == "throughput")
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
        #expect(chatTranslated.workerRequest.execution.ext["melix.media_parts.contract"] == "shared_summary_empty")
        #expect(completionsTranslated.workerRequest.execution.ext["melix.media_parts.contract"] == "adapter_specific_text_only")
        #expect(completionsTranslated.workerRequest.execution.ext["melix.media_parts.adapter_scope"] == "completions")
        #expect(responsesTranslated.workerRequest.execution.ext["melix.media_parts.contract"] == "adapter_specific_text_only")
        #expect(responsesTranslated.workerRequest.execution.ext["melix.media_parts.adapter_scope"] == "responses")
        #expect(messagesTranslated.workerRequest.execution.ext["melix.media_parts.contract"] == "adapter_specific_text_only")
        #expect(messagesTranslated.workerRequest.execution.ext["melix.media_parts.adapter_scope"] == "messages")
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
