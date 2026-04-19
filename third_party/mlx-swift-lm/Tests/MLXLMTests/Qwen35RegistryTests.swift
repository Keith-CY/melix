// Copyright © 2026 Apple Inc.

import Foundation
import MLX
@testable import MLXLLM
import MLXLMCommon
import XCTest

final class Qwen35RegistryTests: XCTestCase {

    func testRegistrySupportsQwen35ModelTypesAndNestedTextConfig() async throws {
        let json =
            """
            {
              "model_type": "qwen3_5",
              "text_config": {
                "model_type": "qwen3_5_text",
                "hidden_size": 8,
                "num_hidden_layers": 2,
                "intermediate_size": 16,
                "num_attention_heads": 2,
                "num_key_value_heads": 1,
                "head_dim": 4,
                "linear_num_value_heads": 2,
                "linear_num_key_heads": 1,
                "linear_key_head_dim": 4,
                "linear_value_head_dim": 4,
                "linear_conv_kernel_dim": 2,
                "vocab_size": 16,
                "full_attention_interval": 2,
                "rope_theta": 100000.0,
                "partial_rotary_factor": 0.25,
                "rms_norm_eps": 0.000001,
                "tie_word_embeddings": false,
                "attention_bias": false
              }
            }
            """

        let baseConfiguration = try JSONDecoder().decode(
            BaseConfiguration.self, from: json.data(using: .utf8)!)
        XCTAssertEqual(baseConfiguration.modelType, "qwen3_5")

        let supportsQwen35 = await LLMTypeRegistry.shared.supportsModelType("qwen3_5")
        let supportsQwen35MoE = await LLMTypeRegistry.shared.supportsModelType("qwen3_5_moe")
        let supportsQwen35Text = await LLMTypeRegistry.shared.supportsModelType("qwen3_5_text")

        XCTAssertTrue(supportsQwen35)
        XCTAssertTrue(supportsQwen35MoE)
        XCTAssertTrue(supportsQwen35Text)
    }

    func testQwen35RegistryCreatesModelsFromConfigFiles() async throws {
        try await withTemporaryDefaultMetallib {
            let textURL = try writeTemporaryConfig(
                textConfigurationJSON(modelType: "qwen3_5_text", numExperts: 0)
            )
            let baseURL = try writeTemporaryConfig(
                """
                {
                  "model_type": "qwen3_5",
                  "text_config": \(textConfigurationJSON(modelType: "qwen3_5_text", numExperts: 0))
                }
                """
            )
            let moeURL = try writeTemporaryConfig(
                """
                {
                  "model_type": "qwen3_5_moe",
                  "text_config": \(textConfigurationJSON(modelType: "qwen3_5_text", numExperts: 2))
                }
                """
            )

            let textModel = try await LLMTypeRegistry.shared.createModel(
                configuration: textURL,
                modelType: "qwen3_5_text"
            )
            let baseModel = try await LLMTypeRegistry.shared.createModel(
                configuration: baseURL,
                modelType: "qwen3_5"
            )
            let moeModel = try await LLMTypeRegistry.shared.createModel(
                configuration: moeURL,
                modelType: "qwen3_5_moe"
            )

            XCTAssertTrue(textModel is Qwen35TextModel)
            XCTAssertTrue(baseModel is Qwen35Model)
            XCTAssertTrue(moeModel is Qwen35MoEModel)
        }
    }

    func testModelTypeRegistryCreateAndUnsupportedPaths() async throws {
        try await withTemporaryDefaultMetallib {
            let registry = ModelTypeRegistry()
            let configuration = try decodeTextConfiguration(modelType: "qwen3_5_text")
            let configURL = try writeTemporaryConfig(
                textConfigurationJSON(modelType: "qwen3_5_text", numExperts: 0)
            )

            let supportsBeforeRegistration = await registry.supportsModelType("qwen3_5_text")
            XCTAssertFalse(supportsBeforeRegistration)

            await registry.registerModelType("qwen3_5_text") { _ in
                Qwen35TextModel(configuration)
            }

            let supportsAfterRegistration = await registry.supportsModelType("qwen3_5_text")
            XCTAssertTrue(supportsAfterRegistration)
            let model = try await registry.createModel(
                configuration: configURL,
                modelType: "qwen3_5_text"
            )
            XCTAssertTrue(model is Qwen35TextModel)

            do {
                _ = try await registry.createModel(configuration: configURL, modelType: "missing")
                XCTFail("Expected an unsupported model type error.")
            } catch ModelFactoryError.unsupportedModelType(let modelType) {
                XCTAssertEqual(modelType, "missing")
            }
        }
    }

    func testTinyQwen35TextModelForwardCoversLinearAndFullAttentionLayers() throws {
        try withTemporaryDefaultMetallib {
            let configuration = try decodeTextConfiguration(
                modelType: "qwen3_5_text",
                numExperts: 0
            )
            let model = Qwen35TextModel(configuration)
            let cache = model.newCache(parameters: nil)

            let input = MLXArray([1, 2, 3])[.newAxis, .ellipsis]
            let output = model(input, cache: cache)

            XCTAssertEqual(output.shape, [1, 3, 64])
            XCTAssertEqual(model.vocabularySize, 64)
            XCTAssertEqual(model.kvHeads, [1, 1])
        }
    }

    func testTinyQwen35TextModelCoversMoEAndTiedEmbeddings() throws {
        try withTemporaryDefaultMetallib {
            let configuration = try decodeTextConfiguration(
                modelType: "qwen3_5_text",
                numExperts: 2,
                tieWordEmbeddings: true
            )
            let model = Qwen35TextModel(configuration)
            let output = model(MLXArray([1, 2])[.newAxis, .ellipsis], cache: nil)

            XCTAssertEqual(output.shape, [1, 2, 64])
            XCTAssertNil(model.sanitize(weights: ["lm_head.weight": MLXArray.zeros([64, 64])])[
                "lm_head.weight"])
        }
    }

    func testQwen35LinearAttentionCoversMaskAndCacheState() throws {
        try withTemporaryDefaultMetallib {
            let configuration = try decodeTextConfiguration(modelType: "qwen3_5_text")
            let layer = Qwen35GatedDeltaNet(configuration)
            let cache = MambaCache()
            let input = MLXArray.zeros([1, 2, 64])
            let mask = (MLXArray([1, 0])[.newAxis, .ellipsis] .== MLXArray(1))

            let first = layer(input, mask: mask, cache: cache)
            let second = layer(
                MLXArray.zeros([1, 1, 64]),
                mask: (MLXArray([1])[.newAxis, .ellipsis] .== MLXArray(1)),
                cache: cache
            )

            XCTAssertEqual(first.shape, [1, 2, 64])
            XCTAssertEqual(second.shape, [1, 1, 64])
        }
    }

    func testQwen35AttentionCoversScaledRopeVariants() throws {
        try withTemporaryDefaultMetallib {
            let yarnConfiguration = try decodeTextConfiguration(
                modelType: "qwen3_5_text",
                ropeScalingJSON:
                    #"""
                    {
                      "type": "yarn",
                      "factor": 2.0,
                      "original_max_position_embeddings": 16
                    }
                    """#
            )
            let longRopeConfiguration = try decodeTextConfiguration(
                modelType: "qwen3_5_text",
                ropeScalingJSON:
                    #"""
                    {
                      "type": "longrope",
                      "original_max_position_embeddings": 16,
                      "short_factor": [1.0, 1.0, 1.0, 1.0],
                      "long_factor": [1.0, 1.0, 1.0, 1.0]
                    }
                    """#
            )

            let input = MLXArray.zeros([1, 1, 64])
            let yarnOutput = Qwen35Attention(yarnConfiguration)(
                input, mask: .none, cache: nil)
            let longRopeOutput = Qwen35Attention(longRopeConfiguration)(
                input, mask: .none, cache: nil)

            XCTAssertEqual(yarnOutput.shape, [1, 1, 64])
            XCTAssertEqual(longRopeOutput.shape, [1, 1, 64])
        }
    }

    func testQwen35ConfigurationCoversRopeParametersAndImplicitHeadDim() throws {
        let json =
            """
            {
              \(textConfigurationBody(
                modelType: "qwen3_5_text",
                numExperts: 0,
                includeHeadDim: false
              )),
              "rope_parameters": {
                "rope_type": "default",
                "rope_theta": 123456.0,
                "partial_rotary_factor": 0.5
              }
            }
            """
        let configuration = try JSONDecoder().decode(
            Qwen35TextConfiguration.self,
            from: json.data(using: .utf8)!
        )

        XCTAssertEqual(configuration.headDim, 32)
        XCTAssertEqual(configuration.ropeTheta, 123456.0)
        XCTAssertEqual(configuration.partialRotaryFactor, 0.5)
        XCTAssertNotNil(configuration.ropeScaling?["type"])
    }

    func testQwen35ModelSanitizeRewritesLanguageModelKeysAndDropsVisionWeights() throws {
        try withTemporaryDefaultMetallib {
            let configuration = try decodeConfiguration(modelType: "qwen3_5")
            let model = Qwen35Model(configuration)
            let conv = MLXArray.zeros([1, 3, 2])
            let norm = MLXArray.zeros([64])

            let sanitized = model.sanitize(weights: [
                "vision_tower.blocks.0.weight": MLXArray.zeros([1]),
                "model.language_model.layers.0.linear_attn.conv1d.weight": conv,
                "model.language_model.model.norm.weight": norm,
                "model.norm.weight": norm,
            ])

            XCTAssertNil(sanitized["language_model.vision_tower.blocks.0.weight"])
            XCTAssertNotNil(sanitized["language_model.model.layers.0.linear_attn.conv1d.weight"])
            XCTAssertNotNil(sanitized["language_model.model.model.norm.weight"])
            XCTAssertNotNil(sanitized["language_model.model.norm.weight"])
            XCTAssertEqual(
                sanitized["language_model.model.layers.0.linear_attn.conv1d.weight"]?.shape,
                [1, 2, 3]
            )
        }
    }

    func testQwen35MoESanitizeSplitsExpertGateWeights() throws {
        try withTemporaryDefaultMetallib {
            let configuration = try decodeConfiguration(modelType: "qwen3_5_moe", numExperts: 2)
            let model = Qwen35MoEModel(configuration)
            let prefix = "language_model.model.layers.0.mlp"
            let gateUp = MLXArray.zeros([2, 4, 3])
            let down = MLXArray.zeros([2, 2, 3])

            let sanitized = model.sanitize(weights: [
                "vision_tower.blocks.0.weight": MLXArray.zeros([1]),
                "model.language_model.model.norm.weight": MLXArray.zeros([64]),
                "model.norm.weight": MLXArray.zeros([64]),
                "\(prefix).experts.gate_up_proj": gateUp,
                "\(prefix).experts.down_proj": down,
            ])

            XCTAssertNil(sanitized["language_model.vision_tower.blocks.0.weight"])
            XCTAssertNotNil(sanitized["language_model.model.model.norm.weight"])
            XCTAssertNotNil(sanitized["language_model.model.norm.weight"])
            XCTAssertNil(sanitized["\(prefix).experts.gate_up_proj"])
            XCTAssertNil(sanitized["\(prefix).experts.down_proj"])
            XCTAssertEqual(sanitized["\(prefix).switch_mlp.gate_proj.weight"]?.shape, [2, 2, 3])
            XCTAssertEqual(sanitized["\(prefix).switch_mlp.up_proj.weight"]?.shape, [2, 2, 3])
            XCTAssertEqual(sanitized["\(prefix).switch_mlp.down_proj.weight"]?.shape, [2, 2, 3])
        }
    }

    func testQwen35ConfigurationDecodesFlatTextConfigFallback() throws {
        try withTemporaryDefaultMetallib {
            let configuration = try decodeConfiguration(modelType: "qwen3_5", nestedTextConfig: false)
            let model = Qwen35Model(configuration)
            let output = model(MLXArray([1, 2])[.newAxis, .ellipsis], cache: nil)

            XCTAssertEqual(output.shape, [1, 2, 64])
            XCTAssertEqual(model.newCache(parameters: nil).count, 2)
            XCTAssertEqual(model.loraLayers.count, 2)
            XCTAssertEqual(model.languageModel.loraLayers.count, 2)
        }
    }

    func testGatedDeltaOpsFallbackCoversRepeatAndMaskShapes() throws {
        try withTemporaryDefaultMetallib {
            let q = MLXArray.ones([1, 2, 1, 32])
            let k = MLXArray.ones([1, 2, 1, 32])
            let v = MLXArray.ones([1, 2, 2, 2])
            let g = MLXArray.ones([1, 2, 2])
            let beta = MLXArray.ones([1, 2, 2])

            let mask1 = (MLXArray([1, 0])[.newAxis, .ellipsis] .== MLXArray(1))
            let mask2 = (MLXArray.ones([1, 2, 2]) .== MLXArray(1))
            let mask3 = (MLXArray.ones([1, 2, 2, 2]) .== MLXArray(1))

            let (out1, state1) = gatedDeltaOps(q: q, k: k, v: v, g: g, beta: beta, mask: mask1)
            let (out2, state2) = gatedDeltaOps(
                q: q, k: k, v: v, g: g, beta: beta, state: state1, mask: mask2)
            let (out3, state3) = gatedDeltaOps(
                q: q, k: k, v: v, g: g, beta: beta, state: state2, mask: mask3)
            let (out4, state4) = gatedDeltaOps(
                q: q, k: k, v: v, g: MLXArray.ones([1, 2, 2, 1]), beta: beta)

            XCTAssertEqual(out1.shape, [1, 2, 2, 2])
            XCTAssertEqual(out2.shape, [1, 2, 2, 2])
            XCTAssertEqual(out3.shape, [1, 2, 2, 2])
            XCTAssertEqual(out4.shape, [1, 2, 2, 2])
            XCTAssertEqual(state3.shape, [1, 2, 2, 32])
            XCTAssertEqual(state4.shape, [1, 2, 2, 32])
        }
    }

    func testGatedDeltaKernelCoversMaskedDispatchPlan() throws {
        try withTemporaryDefaultMetallib {
            let q = MLXArray.ones([1, 2, 1, 32])
            let k = MLXArray.ones([1, 2, 1, 32])
            let v = MLXArray.ones([1, 2, 2, 2])
            let g = MLXArray.ones([1, 2, 2])
            let beta = MLXArray.ones([1, 2, 2])
            let state = MLXArray.zeros([1, 2, 2, 32])
            let mask = (MLXArray([1, 0])[.newAxis, .ellipsis] .== MLXArray(1))

            let (out, newState) = gatedDeltaKernel(
                q: q, k: k, v: v, g: g, beta: beta, state: state, mask: mask)

            XCTAssertEqual(out.shape, [1, 2, 2, 2])
            XCTAssertEqual(newState.shape, [1, 2, 2, 32])
        }
    }

    private func decodeTextConfiguration(
        modelType: String,
        numExperts: Int = 0,
        tieWordEmbeddings: Bool = false,
        ropeScalingJSON: String? = nil
    ) throws -> Qwen35TextConfiguration {
        try JSONDecoder().decode(
            Qwen35TextConfiguration.self,
            from: textConfigurationJSON(
                modelType: modelType,
                numExperts: numExperts,
                tieWordEmbeddings: tieWordEmbeddings,
                ropeScalingJSON: ropeScalingJSON
            )
                .data(using: .utf8)!
        )
    }

    private func decodeConfiguration(
        modelType: String,
        numExperts: Int = 0,
        nestedTextConfig: Bool = true
    ) throws -> Qwen35Configuration {
        let json: String
        if nestedTextConfig {
            json =
                """
                {
                  "model_type": "\(modelType)",
                  "text_config": \(textConfigurationJSON(modelType: "qwen3_5_text", numExperts: numExperts))
                }
                """
        } else {
            json =
                """
                {
                  "model_type": "\(modelType)",
                  \(textConfigurationBody(modelType: "qwen3_5_text", numExperts: numExperts))
                }
                """
        }
        return try JSONDecoder().decode(Qwen35Configuration.self, from: json.data(using: .utf8)!)
    }

    private func textConfigurationJSON(
        modelType: String,
        numExperts: Int,
        tieWordEmbeddings: Bool = false,
        ropeScalingJSON: String? = nil
    ) -> String {
        """
        {
          \(textConfigurationBody(
            modelType: modelType,
            numExperts: numExperts,
            tieWordEmbeddings: tieWordEmbeddings,
            ropeScalingJSON: ropeScalingJSON
          ))
        }
        """
    }

    private func textConfigurationBody(
        modelType: String,
        numExperts: Int,
        tieWordEmbeddings: Bool = false,
        includeHeadDim: Bool = true,
        ropeScalingJSON: String? = nil
    ) -> String {
        let expertFields =
            numExperts > 0
            ? """
              ,
              "num_experts": \(numExperts),
              "num_experts_per_tok": 1,
              "decoder_sparse_step": 1,
              "shared_expert_intermediate_size": 16,
              "moe_intermediate_size": 16,
              "norm_topk_prob": true
              """
            : ""
        let headDimField = includeHeadDim ? #""head_dim": 32,"# : ""
        let ropeScalingField = ropeScalingJSON.map { #","rope_scaling": \#($0)"# } ?? ""

        return
            """
            "model_type": "\(modelType)",
            "hidden_size": 64,
            "num_hidden_layers": 2,
            "intermediate_size": 128,
            "num_attention_heads": 2,
            "num_key_value_heads": 1,
            \(headDimField)
            "linear_num_value_heads": 2,
            "linear_num_key_heads": 1,
            "linear_key_head_dim": 32,
            "linear_value_head_dim": 32,
            "linear_conv_kernel_dim": 2,
            "vocab_size": 64,
            "full_attention_interval": 2,
            "rope_theta": 100000.0,
            "partial_rotary_factor": 0.25,
            "rms_norm_eps": 0.000001,
            "tie_word_embeddings": \(tieWordEmbeddings),
            "attention_bias": false\(expertFields)\(ropeScalingField)
            """
    }

    private func writeTemporaryConfig(_ json: String) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        try json.write(to: url, atomically: true, encoding: .utf8)
        return url
    }

    private func withTemporaryDefaultMetallib<T>(_ operation: () throws -> T) throws -> T {
        let fileManager = FileManager.default
        guard let metallibURL = findLocalMLXMetallib() else {
            throw XCTSkip("No local mlx.metallib was found for the Qwen3.5 MLX smoke test.")
        }

        let temporaryDirectory = fileManager.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try fileManager.createDirectory(at: temporaryDirectory, withIntermediateDirectories: true)

        let defaultMetallibURL = temporaryDirectory.appendingPathComponent("default.metallib")
        try fileManager.createSymbolicLink(at: defaultMetallibURL, withDestinationURL: metallibURL)

        let originalDirectory = fileManager.currentDirectoryPath
        guard fileManager.changeCurrentDirectoryPath(temporaryDirectory.path) else {
            try? fileManager.removeItem(at: temporaryDirectory)
            XCTFail("Failed to switch into temporary MLX metallib directory.")
            return try operation()
        }

        defer {
            _ = fileManager.changeCurrentDirectoryPath(originalDirectory)
            try? fileManager.removeItem(at: temporaryDirectory)
        }

        return try operation()
    }

    private func withTemporaryDefaultMetallib<T>(_ operation: () async throws -> T) async throws -> T {
        let fileManager = FileManager.default
        guard let metallibURL = findLocalMLXMetallib() else {
            throw XCTSkip("No local mlx.metallib was found for the Qwen3.5 MLX smoke test.")
        }

        let temporaryDirectory = fileManager.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try fileManager.createDirectory(at: temporaryDirectory, withIntermediateDirectories: true)

        let defaultMetallibURL = temporaryDirectory.appendingPathComponent("default.metallib")
        try fileManager.createSymbolicLink(at: defaultMetallibURL, withDestinationURL: metallibURL)

        let originalDirectory = fileManager.currentDirectoryPath
        guard fileManager.changeCurrentDirectoryPath(temporaryDirectory.path) else {
            try? fileManager.removeItem(at: temporaryDirectory)
            XCTFail("Failed to switch into temporary MLX metallib directory.")
            return try await operation()
        }

        defer {
            _ = fileManager.changeCurrentDirectoryPath(originalDirectory)
            try? fileManager.removeItem(at: temporaryDirectory)
        }

        return try await operation()
    }

    private func findLocalMLXMetallib() -> URL? {
        let fileManager = FileManager.default
        let currentDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        let candidateRoots = [
            currentDirectory,
            currentDirectory.deletingLastPathComponent(),
            currentDirectory.deletingLastPathComponent().deletingLastPathComponent(),
        ]

        for root in candidateRoots {
            for prefix in [".venv", ".uv-cache"] {
                let searchRoot = root.appendingPathComponent(prefix, isDirectory: true)
                guard fileManager.fileExists(atPath: searchRoot.path) else {
                    continue
                }
                guard let enumerator = fileManager.enumerator(
                    at: searchRoot,
                    includingPropertiesForKeys: [.isRegularFileKey],
                    options: [.skipsHiddenFiles]
                ) else {
                    continue
                }

                for case let fileURL as URL in enumerator {
                    if fileURL.lastPathComponent == "mlx.metallib" {
                        return fileURL
                    }
                }
            }
        }

        return nil
    }
}
