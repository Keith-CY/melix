import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

struct ChatTemplatePolicyTests {
    @Test("chat template kwargs request contracts decode across endpoint variants")
    func chatTemplateRequestContractsDecodeAcrossEndpointVariants() throws {
        let decoder = JSONDecoder()

        let chat = try decoder.decode(
            OpenAIChatCompletionsRequest.self,
            from: Data(
                """
                {
                  "model": "melix-dev-text",
                  "chat_template_kwargs": {
                    "continue_final_message": true,
                    "add_generation_prompt": false
                  },
                  "messages": [
                    { "role": "user", "content": "Continue the answer." }
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
                  "prompt": "Continue the answer.",
                  "chat_template_kwargs": {
                    "continue_final_message": true
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
                  "input": "Continue the answer.",
                  "chat_template_kwargs": {
                    "continue_final_message": true
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
                  "chat_template_kwargs": {
                    "continue_final_message": true
                  },
                  "messages": [
                    { "role": "user", "content": "Continue the answer." }
                  ]
                }
                """.utf8
            )
        )

        #expect(chat.chatTemplateSelection?.values["continue_final_message"] == .bool(true))
        #expect(chat.chatTemplateSelection?.values["add_generation_prompt"] == .bool(false))
        #expect(completions.chatTemplateSelection?.values["continue_final_message"] == .bool(true))
        #expect(responses.chatTemplateSelection?.values["continue_final_message"] == .bool(true))
        #expect(messages.chatTemplateSelection?.values["continue_final_message"] == .bool(true))
    }

    @Test("translated chat template kwargs flow metadata into worker execution")
    func translatedChatTemplateRequestsFlowMetadataIntoWorkerExecution() throws {
        let translator = ChatRequestTranslator(requestIDGenerator: { "resp-template" })
        let request = OpenAIResponsesRequest(
            model: "melix-dev-text",
            input: .text("Continue the answer."),
            chatTemplateKwargs: ChatTemplateRequestConfiguration(
                values: [
                    "continue_final_message": .bool(true),
                    "add_generation_prompt": .bool(false),
                ]
            )
        )

        let translated = try translator.translate(request, modelHandle: "worker-text")

        #expect(translated.workerRequest.execution.ext["melix.chat_template_kwargs.source"] == "request")
        #expect(
            translated.workerRequest.execution.ext["melix.chat_template_kwargs.effective_json"]
                == "{\"add_generation_prompt\":false,\"continue_final_message\":true}"
        )
        #expect(translated.workerRequest.execution.ext["melix.chat_template_kwargs.request_json"] != nil)
        #expect(translated.workerRequest.execution.ext["melix.chat_template_kwargs.forced_json"] == nil)
    }

    @Test("chat template policy resolves model defaults request overrides and forced keys deterministically")
    func chatTemplatePolicyResolvesModelDefaultsRequestOverridesAndForcedKeys() throws {
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.ext["chat_template_kwargs"] = "{\"chat_template\":\"model-template\",\"tokenize\":true}"
        settings.ext["chat_template_forced_kwargs"] = "{\"chat_template\":\"forced-template\",\"add_generation_prompt\":true}"
        let modelPolicy = try #require(try ModelChatTemplatePolicy(modelSettings: settings))
        let translator = ChatRequestTranslator(requestIDGenerator: { "req-template-policy" })
        let normalized = try translator.normalize(
            OpenAIChatCompletionsRequest(
                model: "melix-dev-text",
                messages: [.init(role: "user", content: "Continue the answer.")],
                chatTemplateKwargs: ChatTemplateRequestConfiguration(
                    values: [
                        "chat_template": .string("request-template"),
                        "continue_final_message": .bool(true),
                    ]
                )
            )
        )

        let translated = try translator.translate(
            normalized,
            modelHandle: "worker-text",
            modelChatTemplatePolicy: modelPolicy
        )

        #expect(translated.workerRequest.execution.ext["melix.chat_template_kwargs.source"] == "model+request+forced")
        #expect(
            translated.workerRequest.execution.ext["melix.chat_template_kwargs.effective_json"]
                == "{\"add_generation_prompt\":true,\"chat_template\":\"forced-template\",\"continue_final_message\":true,\"tokenize\":true}"
        )
        #expect(
            translated.workerRequest.execution.ext["melix.chat_template_kwargs.model_json"]
                == "{\"chat_template\":\"model-template\",\"tokenize\":true}"
        )
        #expect(
            translated.workerRequest.execution.ext["melix.chat_template_kwargs.request_json"]
                == "{\"chat_template\":\"request-template\",\"continue_final_message\":true}"
        )
        #expect(
            translated.workerRequest.execution.ext["melix.chat_template_kwargs.forced_json"]
                == "{\"add_generation_prompt\":true,\"chat_template\":\"forced-template\"}"
        )
        #expect(translated.workerRequest.execution.ext["melix.chat_template_kwargs.forced_keys"] == "add_generation_prompt,chat_template")
    }

    @Test("chat template kwargs reject non-object request payloads")
    func chatTemplateKwargsRejectNonObjectRequestPayloads() throws {
        let decoder = JSONDecoder()

        #expect(throws: ChatTemplatePolicyError.self) {
            _ = try decoder.decode(
                OpenAIResponsesRequest.self,
                from: Data(
                    """
                    {
                      "model": "melix-dev-text",
                      "input": "Continue the answer.",
                      "chat_template_kwargs": ["not-an-object"]
                    }
                    """.utf8
                )
            )
        }
    }
}
