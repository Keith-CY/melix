import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

struct ToolParserRegistryTests {
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
