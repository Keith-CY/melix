import Foundation
import Testing
import MelixControlPlaneProtocol

@testable import MelixControlPlaneCore

struct StructuredOutputValidationTests {
    @Test("structured output request contracts decode across endpoint variants")
    func structuredOutputRequestContractsDecodeAcrossEndpointVariants() throws {
        let decoder = JSONDecoder()

        let chat = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "stream": true,
                  "response_format": { "type": "json_object" },
                  "messages": [
                    { "role": "user", "content": "Return JSON." }
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
                  "input": "Return JSON.",
                  "text": {
                    "format": {
                      "type": "json_schema",
                      "json_schema": {
                        "name": "answer_contract",
                        "schema": {
                          "type": "object",
                          "properties": {
                            "answer": { "type": "string" }
                          },
                          "required": ["answer"]
                        },
                        "strict": true
                      }
                    }
                  }
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
                  "response_format": "json_object",
                  "messages": [
                    { "role": "user", "content": "Return JSON." }
                  ]
                }
                """.utf8
            )
        )

        let chatFormat = try #require(try chat.structuredOutputConfiguration)
        let responsesFormat = try #require(try responses.structuredOutputConfiguration)
        let messagesFormat = try #require(try messages.structuredOutputConfiguration)

        #expect(chatFormat.mode == .jsonObject)
        #expect(responsesFormat.mode == .jsonSchema)
        #expect(responsesFormat.schemaName == "answer_contract")
        #expect(responsesFormat.strict)
        #expect(messagesFormat.mode == .jsonObject)
    }

    @Test("translated structured output requests flow metadata into worker execution")
    func translatedStructuredOutputRequestsFlowMetadataIntoWorkerExecution() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "resp-structured" })
        let request = OpenAIResponsesRequest(
            model: "melix-dev-text",
            input: .text("Return JSON."),
            text: .init(
                format: StructuredOutputRequestFormat(
                    type: .jsonSchema,
                    jsonSchema: StructuredOutputJSONSchemaDefinition(
                        name: "answer_contract",
                        schema: .object([
                            "type": .string("object"),
                            "properties": .object([
                                "answer": .object([
                                    "type": .string("string"),
                                ]),
                            ]),
                            "required": .array([
                                .string("answer"),
                            ]),
                        ]),
                        strict: true
                    )
                )
            )
        )

        let translated = try translator.translate(request, modelHandle: "worker-text")

        #expect(translated.workerRequest.execution.ext["melix.structured_output.mode"] == "json_schema")
        #expect(translated.workerRequest.execution.ext["melix.structured_output.schema_name"] == "answer_contract")
        #expect(translated.workerRequest.execution.ext["melix.structured_output.strict"] == "true")
        #expect(translated.workerRequest.execution.ext["melix.structured_output.schema_json"]?.contains("\"answer\"") == true)
        #expect(translated.workerRequest.execution.acceleration.prefillHint == "json-schema")
    }

    @Test("json only structured output suppresses model default tool parser when tools are absent")
    func jsonOnlyStructuredOutputSuppressesModelDefaultToolParserWhenToolsAreAbsent() throws {
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.ext["tool_parser_mode"] = "qwen"
        settings.ext["tool_parser_namespaces"] = "tools.text"
        let modelToolParser = try #require(ToolParserSelection(modelSettings: settings))
        let shaper = TextRequestShaper()

        let request = NormalizedTextRequest(
            endpoint: .responses,
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Return JSON only.")],
            stream: true,
            temperature: nil,
            topP: nil,
            maxTokens: nil,
            sessionID: nil,
            branchID: nil,
            parentRequestID: nil,
            restoreSnapshotID: nil,
            saveBoundarySnapshot: nil,
            structuredOutput: StructuredOutputConfiguration(mode: .jsonObject)
        )

        let shaped = shaper.shape(request, modelToolParser: modelToolParser)
        let translated = try ChatRequestTranslator(requestIDGenerator: { "json-tool-gate" })
            .translate(request, modelHandle: "worker-text", modelToolParser: modelToolParser)

        #expect(shaped.toolParser == nil)
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.mode"] == nil)
        #expect(translated.workerRequest.execution.ext["melix.tool_parser.suppressed_reason"] == "structured_output_json_without_tools")
    }

    @Test("explicit tool parser survives json structured output gating")
    func explicitToolParserSurvivesJSONStructuredOutputGating() throws {
        let shaper = TextRequestShaper()
        let request = NormalizedTextRequest(
            endpoint: .responses,
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Return JSON and call a tool.")],
            stream: true,
            temperature: nil,
            topP: nil,
            maxTokens: nil,
            sessionID: nil,
            branchID: nil,
            parentRequestID: nil,
            restoreSnapshotID: nil,
            saveBoundarySnapshot: nil,
            structuredOutput: StructuredOutputConfiguration(mode: .jsonObject),
            toolParser: ToolParserSelection(mode: .qwen, namespaces: ["tools.text"], source: "request")
        )

        let shaped = shaper.shape(request)

        #expect(shaped.toolParser?.mode == .qwen)
        #expect(shaped.toolParser?.source == "request")
        #expect(shaped.toolParser?.namespaces == ["tools.text"])
    }

    @Test("structured output validator enforces strict schema rules")
    func structuredOutputValidatorEnforcesStrictSchemaRules() throws {
        let validator = StructuredOutputValidator()
        let configuration = StructuredOutputConfiguration(
            mode: .jsonSchema,
            schemaName: "answer_contract",
            schema: .object([
                "type": .string("object"),
                "properties": .object([
                    "answer": .object([
                        "type": .string("string"),
                    ]),
                ]),
                "required": .array([
                    .string("answer"),
                ]),
            ]),
            strict: true
        )

        try validator.validate(outputText: "{\"answer\":\"done\"}", against: configuration)

        #expect(throws: StructuredOutputValidationFailure.self) {
            try validator.validate(
                outputText: "{\"answer\":\"done\",\"extra\":true}",
                against: configuration
            )
        }
    }

    @Test("structured output validator enforces json object mode")
    func structuredOutputValidatorEnforcesJSONMode() throws {
        let validator = StructuredOutputValidator()
        let configuration = StructuredOutputConfiguration(mode: .jsonObject)

        try validator.validate(outputText: "{\"ok\":true}", against: configuration)

        #expect(throws: StructuredOutputValidationFailure.self) {
            try validator.validate(outputText: "[1,2,3]", against: configuration)
        }
    }

    @Test("structured output translate overloads preserve endpoint contracts and messages encoding")
    func structuredOutputTranslateOverloadsPreserveEndpointContracts() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-structured-overloads" })
        let jsonObjectFormat = StructuredOutputRequestFormat(type: .jsonObject)
        let jsonSchemaFormat = StructuredOutputRequestFormat(
            type: .jsonSchema,
            jsonSchema: StructuredOutputJSONSchemaDefinition(
                name: "answer_contract",
                schema: .object([
                    "type": .string("object"),
                    "properties": .object([
                        "answer": .object([
                            "type": .string("string"),
                        ]),
                    ]),
                    "required": .array([
                        .string("answer"),
                    ]),
                ]),
                strict: true
            )
        )
        let chat = OpenAIChatCompletionsRequest(
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Return JSON.")],
            responseFormat: jsonObjectFormat
        )
        let completions = OpenAICompletionsRequest(
            model: "melix-dev-text",
            prompt: "Return JSON.",
            responseFormat: jsonObjectFormat
        )
        let responses = OpenAIResponsesRequest(
            model: "melix-dev-text",
            input: .text("Return JSON."),
            workflowNodeID: "node-structured",
            text: .init(format: jsonSchemaFormat)
        )
        let messages = MelixMessagesRequest(
            model: "melix-dev-text",
            messages: [.init(role: "user", content: "Return JSON.")],
            responseFormat: jsonObjectFormat
        )

        let chatTranslated = try translator.translate(chat, modelHandle: "worker-text")
        let completionsTranslated = try translator.translate(completions, modelHandle: "worker-text")
        let responsesNormalized = try translator.normalize(responses)
        let responsesTranslated = try translator.translate(responses, modelHandle: "worker-text")
        let messagesTranslated = try translator.translate(messages, modelHandle: "worker-text")
        let encodedMessages = try JSONEncoder().encode(messages)
        let encodedMessagesText = try #require(String(data: encodedMessages, encoding: .utf8))

        #expect(chatTranslated.workerRequest.execution.ext["melix.structured_output.mode"] == "json_object")
        #expect(completionsTranslated.workerRequest.execution.ext["melix.structured_output.mode"] == "json_object")
        #expect(responsesNormalized.workflowNodeID == "node-structured")
        #expect(responsesNormalized.structuredOutput?.mode == .jsonSchema)
        #expect(responsesTranslated.workerRequest.execution.ext["melix.structured_output.mode"] == "json_schema")
        #expect(messagesTranslated.workerRequest.execution.ext["melix.structured_output.mode"] == "json_object")
        #expect(encodedMessagesText.contains("\"response_format\""))
        #expect(encodedMessagesText.contains("\"json_object\""))
    }
}
