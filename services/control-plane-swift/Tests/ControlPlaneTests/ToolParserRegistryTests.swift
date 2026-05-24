import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

struct ToolParserRegistryTests {
    @Test("registered parsers declare audit receipts for wire formats and selector surfaces")
    func registeredParsersDeclareAuditReceiptsForWireFormatsAndSelectorSurfaces() throws {
        let registry = ToolParserRegistry()
        let receipts = registry.auditReceipts()
        let registeredIDs = Set(registry.supportedModes().map(\.rawValue))

        #expect(Set(receipts.map(\.parserID)) == registeredIDs)
        #expect(receipts.allSatisfy { !$0.parserID.isEmpty })
        #expect(receipts.allSatisfy { !$0.parserKind.rawValue.isEmpty })
        #expect(receipts.allSatisfy { !$0.acceptedWireFormats.isEmpty })
        #expect(receipts.allSatisfy { !$0.selectorSurface.rawValue.isEmpty })
        #expect(receipts.allSatisfy { !$0.selectorSource.isEmpty })
        #expect(receipts.allSatisfy { !$0.requestContextMode.rawValue.isEmpty })
        #expect(receipts.allSatisfy { receipt in
            receipt.selectorSurface == .cli ? !receipt.exemptionReason.isEmpty : receipt.exemptionReason.isEmpty
        })

        let json = try #require(receipts.first { $0.parserID == "json" && $0.requestContextMode == .structuredJSON })
        #expect(json.parserKind == .structuredOutput)
        #expect(json.acceptedWireFormats == ["json_object"])

        let qwenTool = try #require(receipts.first { $0.parserID == "qwen" && $0.requestContextMode == .toolParser })
        #expect(qwenTool.parserKind == .toolCall)
        #expect(qwenTool.acceptedWireFormats == ["qwen_xml_tool_call"])

        let qwenReasoning = try #require(receipts.first { $0.parserID == "qwen" && $0.requestContextMode == .reasoning })
        #expect(qwenReasoning.acceptedWireFormats.contains("qwen_xml_tool_call"))
        #expect(qwenReasoning.acceptedWireFormats.contains("reasoning_channel_tags"))

        let plain = try #require(receipts.first { $0.parserID == "text" && $0.requestContextMode == .plain })
        #expect(plain.parserKind == .plainText)
        #expect(plain.acceptedWireFormats == ["raw_text"])

        let encoded = try JSONEncoder().encode(qwenTool)
        let jsonObject = try #require(
            try JSONSerialization.jsonObject(with: encoded) as? [String: Any]
        )
        #expect(Set(jsonObject.keys) == [
            "parser_id",
            "parser_kind",
            "accepted_wire_formats",
            "selector_surface",
            "selector_source",
            "request_context_mode",
            "exemption_reason",
        ])
    }

    @Test("API desktop and CLI selector declarations are parity audited")
    func apiDesktopAndCLISelectorDeclarationsAreParityAudited() {
        let registry = ToolParserRegistry()
        let selectorReceipts = registry.selectorAuditReceipts()
        let parserIDs = registry.supportedModes().map(\.rawValue)

        let api = selectorReceipts.filter { $0.selectorSurface == .api }
        let desktop = selectorReceipts.filter { $0.selectorSurface == .desktop }
        let cli = selectorReceipts.filter { $0.selectorSurface == .cli }

        #expect(api.map(\.parserID) == parserIDs)
        #expect(desktop.map(\.parserID) == parserIDs)
        #expect(cli.map(\.parserID) == parserIDs)
        #expect(api.allSatisfy { $0.selectorSource == "request.tool_parser" })
        #expect(desktop.allSatisfy { $0.selectorSource == "tooling_settings.builtin_tool_parser_modes" })
        #expect(cli.allSatisfy { $0.selectorSource == "none" })
        #expect(cli.allSatisfy {
            $0.exemptionReason == "CLI has no request-construction surface for tool parser selection; it reports remote model supported_parsers only."
        })
        #expect(api.allSatisfy { $0.exemptionReason.isEmpty })
        #expect(desktop.allSatisfy { $0.exemptionReason.isEmpty })
    }

    @Test("fixture request contexts cover JSON tool reasoning and plain parsers")
    func fixtureRequestContextsCoverJSONToolReasoningAndPlainParsers() {
        let contexts = ToolParserRegistry().requestContextFixtures()

        #expect(Set(contexts.map(\.requestContextMode)) == [.structuredJSON, .toolParser, .reasoning, .plain])
        #expect(contexts.contains { $0.parserID == "json" && $0.acceptedWireFormats == ["json_object"] })
        #expect(contexts.contains { $0.parserID == "qwen" && $0.acceptedWireFormats.contains("qwen_xml_tool_call") })
        #expect(contexts.contains {
            $0.parserID == "qwen"
                && $0.requestContextMode == .reasoning
                && $0.acceptedWireFormats.contains("reasoning_channel_tags")
        })
        #expect(contexts.contains { $0.parserID == "text" && $0.acceptedWireFormats == ["raw_text"] })
    }

    @Test("tool parser request contracts decode across endpoint variants")
    func toolParserRequestContractsDecodeAcrossEndpointVariants() throws {
        let decoder = JSONDecoder()

        let chat = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "stream": true,
                  "tool_parser": "qwen",
                  "messages": [
                    { "role": "user", "content": "Call a tool." }
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
                  "prompt": "Call a tool.",
                  "tool_parser": {
                    "mode": "mistral",
                    "namespaces": ["tools.math", "tools:web"],
                    "xml_fallback": true
                  }
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
                  "input": "Call a tool.",
                  "tool_parser": { "mode": "json" }
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
                  "stream": true,
                  "tool_parser": "xml",
                  "messages": [
                    { "role": "user", "content": "Call a tool." }
                  ]
                }
                """.utf8
            )
        )

        let chatSelection = try #require(try chat.toolParserSelection)
        let completionsSelection = try #require(try completions.toolParserSelection)
        let responsesSelection = try #require(try responses.toolParserSelection)
        let messagesSelection = try #require(try messages.toolParserSelection)

        #expect(chatSelection.mode == .qwen)
        #expect(completionsSelection.mode == .mistral)
        #expect(completionsSelection.namespaces == ["tools.math", "tools:web"])
        #expect(completionsSelection.fallbackMode == .xml)
        #expect(responsesSelection.mode == .json)
        #expect(messagesSelection.mode == .xml)
    }

    @Test("translated tool parser requests flow metadata into worker execution")
    func translatedToolParserRequestsFlowMetadataIntoWorkerExecution() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "resp-tool-parser" })
        let request = OpenAIResponsesRequest(
            model: "melix-dev-text",
            input: .text("Call a tool."),
            toolParser: .init(
                mode: .qwen,
                namespaces: ["tools.search", "tools.math"],
                xmlFallback: true
            )
        )

        let translated = try translator.translate(request, modelHandle: "worker-text")

        #expect(translated.workerRequest.execution.ext["melix.tool_parser.mode"] == "qwen")
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.source"] == "request")
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.namespaces"] == "tools.search,tools.math")
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.fallback_mode"] == "xml")
    }

    @Test("translated text requests attach request-local compatibility policy receipts")
    func translatedTextRequestsAttachRequestLocalCompatibilityPolicyReceipts() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-compat-policy" })
        let request = OpenAIChatCompletionsRequest(
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Call a tool and answer as JSON.")],
            enableThinking: true,
            reasoningEffort: "low",
            stream: true,
            responseFormat: StructuredOutputRequestFormat(
                type: .jsonSchema,
                jsonSchema: StructuredOutputJSONSchemaDefinition(
                    name: "answer",
                    schema: .object(["type": .string("object")]),
                    strict: true
                )
            ),
            toolParser: ToolParserRequestConfiguration(
                mode: .qwen,
                namespaces: ["tools.search"]
            ),
            tools: [
                OpenAIChatTool(
                    type: "function",
                    function: OpenAIChatTool.FunctionDefinition(
                        name: "search",
                        description: "Search documents",
                        parameters: .object(["type": .string("object")])
                    )
                ),
            ],
            toolChoice: .mode("required")
        )

        let translated = try translator.translate(request, modelHandle: "worker-text")
        let ext = translated.workerRequest.execution.ext
        let receipt = try #require(ext["melix.compat.policy_receipt_json"])

        #expect(ext["melix.compat.compat_surface"] == "openai.chat.completions")
        #expect(ext["melix.compat.stream_mode"] == "stream")
        #expect(ext["melix.compat.reasoning_mode"] == "enabled")
        #expect(ext["melix.compat.reasoning_source"] == "request")
        #expect(ext["melix.compat.reasoning_effort"] == "low")
        #expect(ext["melix.compat.tool_parser_mode"] == "qwen")
        #expect(ext["melix.compat.tool_parser_source"] == "request")
        #expect(ext["melix.compat.tool_namespaces"] == "tools.search")
        #expect(ext["melix.compat.tool_choice_requested"] == "required")
        #expect(ext["melix.compat.tool_choice_resolved"] == "required")
        #expect(ext["melix.compat.structured_output_mode"] == "json_schema")
        #expect(ext["melix.compat.output_modalities"] == "text")
        #expect(ext["melix.compat.effective_config_hash"]?.isEmpty == false)
        #expect(receipt.contains(#""compat_surface":"openai.chat.completions""#))
        #expect(receipt.contains(#""tool_namespaces":["tools.search"]"#))
        #expect(receipt.contains(#""effective_config_hash":"\#(ext["melix.compat.effective_config_hash"] ?? "")""#))
    }

    @Test("multimodal tool parser requests preserve image parts and execution metadata")
    func multimodalToolParserRequestsPreserveImagePartsAndExecutionMetadata() throws {
        let decoder = JSONDecoder()
        let translator = ChatRequestTranslator(requestIDGenerator: { "chat-vlm-tool-parser" })
        let request = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-vlm",
                  "stream": true,
                  "tool_parser": {
                    "mode": "qwen",
                    "namespaces": ["tools.vision"],
                    "xml_fallback": true
                  },
                  "messages": [
                    {
                      "role": "user",
                      "content": [
                        { "type": "text", "text": "Call the tool for this image." },
                        {
                          "type": "input_image",
                          "input_image": {
                            "url": "file:///tmp/fixture.png",
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
        let translated = try translator.translate(normalized, modelHandle: "worker-vlm")
        let message = try #require(translated.workerRequest.messages.first)

        #expect(message.parts.count == 2)
        #expect(message.parts[0].text == "Call the tool for this image.")
        #expect(message.parts[1].imageUri == "file:///tmp/fixture.png")
        #expect(message.parts[1].media.mimeType == "image/png")
        #expect(message.parts[1].media.filename == "fixture.png")
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.mode"] == "qwen")
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.source"] == "request")
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.namespaces"] == "tools.vision")
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.fallback_mode"] == "xml")
    }

    @Test("tool parser model defaults apply and request overrides win")
    func toolParserModelDefaultsApplyAndRequestOverridesWin() throws {
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.ext["tool_parser_mode"] = "gemma"
        settings.ext["tool_parser_namespaces"] = "tools.weather,tools.math"
        settings.ext["tool_parser_xml_fallback"] = "true"

        let modelSelection = try #require(ToolParserSelection(modelSettings: settings))
        let shaper = TextRequestShaper()

        let request = makeNormalizedRequest()
        let shapedWithModel = shaper.shape(request, modelToolParser: modelSelection)
        let shapedWithOverride = shaper.shape(
            makeNormalizedRequest(
                toolParser: ToolParserSelection(
                    mode: .qwen,
                    namespaces: ["tools.search"],
                    source: "request"
                )
            ),
            modelToolParser: modelSelection
        )

        #expect(shapedWithModel.toolParser == modelSelection)
        #expect(shapedWithOverride.toolParser?.mode == .qwen)
        #expect(shapedWithOverride.toolParser?.source == "request")
        #expect(shapedWithOverride.toolParser?.namespaces == ["tools.search"])
    }

    @Test("mcp tool catalogs auto inject namespaces and default parser selection")
    func mcpToolCatalogsAutoInjectNamespacesAndDefaultParserSelection() {
        let shaper = TextRequestShaper()
        let catalog = MCPToolCatalog(
            configPath: "/tmp/mcp-tools.json",
            defaultParserMode: .json,
            sources: [
                .init(
                    sourceID: "filesystem",
                    enabled: true,
                    namespaces: ["tools.fs.read", "tools.fs.write"]
                ),
                .init(
                    sourceID: "disabled-search",
                    enabled: false,
                    namespaces: ["tools.search"]
                ),
                .init(
                    sourceID: "math",
                    enabled: true,
                    namespaces: ["tools.math"]
                ),
            ]
        )

        let shaped = shaper.shape(
            makeNormalizedRequest(),
            mcpToolCatalog: catalog
        )

        #expect(shaped.toolParser?.mode == .json)
        #expect(shaped.toolParser?.source == "mcp")
        #expect(shaped.toolParser?.namespaces == ["tools.fs.read", "tools.fs.write", "tools.math"])
        #expect(shaped.toolParser?.mcpSourceIDs == ["filesystem", "math"])
    }

    @Test("mcp tool catalogs merge into model defaults without losing model parser mode")
    func mcpToolCatalogsMergeIntoModelDefaultsWithoutLosingModelParserMode() throws {
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.ext["tool_parser_mode"] = "gemma"
        settings.ext["tool_parser_namespaces"] = "tools.weather"
        let modelSelection = try #require(ToolParserSelection(modelSettings: settings))
        let shaper = TextRequestShaper()
        let catalog = MCPToolCatalog(
            configPath: "/tmp/mcp-tools.json",
            defaultParserMode: .json,
            sources: [
                .init(
                    sourceID: "filesystem",
                    enabled: true,
                    namespaces: ["tools.fs.read", "tools.weather"]
                ),
            ]
        )

        let shaped = shaper.shape(
            makeNormalizedRequest(),
            modelToolParser: modelSelection,
            mcpToolCatalog: catalog
        )

        #expect(shaped.toolParser?.mode == .gemma)
        #expect(shaped.toolParser?.source == "model")
        #expect(shaped.toolParser?.namespaces == ["tools.weather", "tools.fs.read"])
        #expect(shaped.toolParser?.mcpSourceIDs == ["filesystem"])
    }

    @Test("mcp tool catalogs preserve explicit text parser opt out")
    func mcpToolCatalogsPreserveExplicitTextParserOptOut() {
        let shaper = TextRequestShaper()
        let catalog = MCPToolCatalog(
            configPath: "/tmp/mcp-tools.json",
            defaultParserMode: .json,
            sources: [
                .init(
                    sourceID: "filesystem",
                    enabled: true,
                    namespaces: ["tools.fs.read"]
                ),
            ]
        )
        let requested = ToolParserSelection(
            mode: .text,
            namespaces: [],
            source: "request"
        )

        let shaped = shaper.shape(
            makeNormalizedRequest(toolParser: requested),
            mcpToolCatalog: catalog
        )

        #expect(shaped.toolParser == requested)
        #expect(shaped.toolParser?.mcpSourceIDs.isEmpty == true)
    }

    @Test("mcp tool catalogs do not create parser selection when no enabled namespaces remain")
    func mcpToolCatalogsDoNotCreateParserSelectionWhenNoEnabledNamespacesRemain() {
        let shaper = TextRequestShaper()
        let catalog = MCPToolCatalog(
            configPath: "/tmp/mcp-tools.json",
            defaultParserMode: .json,
            sources: [
                .init(
                    sourceID: "disabled-search",
                    enabled: false,
                    namespaces: ["tools.search"]
                ),
            ]
        )

        let shaped = shaper.shape(
            makeNormalizedRequest(),
            mcpToolCatalog: catalog
        )

        #expect(shaped.toolParser == nil)
    }

    @Test("vlm family metadata supplies model-default tool parser selection")
    func vlmFamilyMetadataSuppliesModelDefaultToolParserSelection() throws {
        let modelSelection = try #require(ToolParserSelection(modelSettings: ModelCatalog.devVLMModel().settings))

        #expect(modelSelection.mode == .qwen)
        #expect(modelSelection.source == "model")
        #expect(modelSelection.namespaces == ["tools.vision"])
        #expect(modelSelection.fallbackMode == .xml)
    }

    @Test("tool parser validation rejects invalid namespaces")
    func toolParserValidationRejectsInvalidNamespaces() {
        #expect(throws: ToolParserConfigurationError.self) {
            try ToolParserRequestConfiguration(
                mode: .qwen,
                namespaces: ["bad namespace"],
                xmlFallback: false
            ).resolvedSelection()
        }
    }

    private func makeNormalizedRequest(
        toolParser: ToolParserSelection? = nil
    ) -> NormalizedTextRequest {
        NormalizedTextRequest(
            endpoint: .responses,
            model: "melix-dev-text",
            messages: [
                .init(role: "user", content: "Call a tool."),
            ],
            stream: true,
            temperature: nil,
            topP: nil,
            maxTokens: nil,
            sessionID: nil,
            branchID: nil,
            parentRequestID: nil,
            restoreSnapshotID: nil,
            saveBoundarySnapshot: nil,
            toolParser: toolParser
        )
    }
}
