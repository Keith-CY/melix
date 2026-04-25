import Foundation
import MLX
import MLXFast
import MLXLMCommon
import MLXNN

public struct DFlashTargetForwardResult {
    public let logits: MLXArray
    public let hidden: MLXArray

    public init(logits: MLXArray, hidden: MLXArray) {
        self.logits = logits
        self.hidden = hidden
    }
}

public protocol DFlashTargetModel {
    var dflashHiddenSize: Int { get }
    var dflashLayerCount: Int { get }

    func dflashTokenEmbeddings(_ tokenIDs: MLXArray) throws -> MLXArray
    func dflashLogits(fromHiddenStates hiddenStates: MLXArray) throws -> MLXArray
    func dflashForward(
        input: LMInput.Text,
        cache: [KVCache]?,
        targetLayerIDs: [Int]
    ) throws -> DFlashTargetForwardResult
}

public struct DFlashDraftConfiguration: Codable, Sendable {
    public var hiddenSize: Int
    public var hiddenLayers: Int
    public var intermediateSize: Int
    public var attentionHeads: Int
    public var kvHeads: Int
    public var headDim: Int
    public var rmsNormEps: Float
    public var vocabularySize: Int
    public var ropeTheta: Float
    public var maxPositionEmbeddings: Int
    public var attentionBias: Bool
    public var blockSize: Int
    public var numTargetLayers: Int
    public var targetLayerIDs: [Int]
    public var maskTokenID: Int
    public var ropeScaling: [String: StringOrNumber]?

    private enum CodingKeys: String, CodingKey {
        case hiddenSize = "hidden_size"
        case hiddenLayers = "num_hidden_layers"
        case intermediateSize = "intermediate_size"
        case attentionHeads = "num_attention_heads"
        case kvHeads = "num_key_value_heads"
        case headDim = "head_dim"
        case rmsNormEps = "rms_norm_eps"
        case vocabularySize = "vocab_size"
        case ropeTheta = "rope_theta"
        case maxPositionEmbeddings = "max_position_embeddings"
        case attentionBias = "attention_bias"
        case blockSize = "block_size"
        case numTargetLayers = "num_target_layers"
        case targetLayerIDs = "target_layer_ids"
        case maskTokenID = "mask_token_id"
        case ropeScaling = "rope_scaling"
        case dflashConfig = "dflash_config"
    }

    private enum DFlashConfigKeys: String, CodingKey {
        case targetLayerIDs = "target_layer_ids"
        case maskTokenID = "mask_token_id"
    }

    public init(
        hiddenSize: Int = 0,
        hiddenLayers: Int = 0,
        intermediateSize: Int = 0,
        attentionHeads: Int = 1,
        kvHeads: Int = 1,
        headDim: Int = 1,
        rmsNormEps: Float = 1e-6,
        vocabularySize: Int = 0,
        ropeTheta: Float = 1_000_000,
        maxPositionEmbeddings: Int = 32768,
        attentionBias: Bool = false,
        blockSize: Int = 16,
        numTargetLayers: Int = 0,
        targetLayerIDs: [Int] = [],
        maskTokenID: Int = 0,
        ropeScaling: [String: StringOrNumber]? = nil
    ) {
        self.hiddenSize = hiddenSize
        self.hiddenLayers = hiddenLayers
        self.intermediateSize = intermediateSize
        self.attentionHeads = attentionHeads
        self.kvHeads = kvHeads
        self.headDim = headDim
        self.rmsNormEps = rmsNormEps
        self.vocabularySize = vocabularySize
        self.ropeTheta = ropeTheta
        self.maxPositionEmbeddings = maxPositionEmbeddings
        self.attentionBias = attentionBias
        self.blockSize = blockSize
        self.numTargetLayers = numTargetLayers
        self.targetLayerIDs = targetLayerIDs
        self.maskTokenID = maskTokenID
        self.ropeScaling = ropeScaling
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let nested = try? container.nestedContainer(keyedBy: DFlashConfigKeys.self, forKey: .dflashConfig)

        self.hiddenSize = try container.decodeIfPresent(Int.self, forKey: .hiddenSize) ?? 0
        self.hiddenLayers = try container.decodeIfPresent(Int.self, forKey: .hiddenLayers) ?? 0
        self.intermediateSize = try container.decodeIfPresent(Int.self, forKey: .intermediateSize) ?? 0
        self.attentionHeads = try container.decodeIfPresent(Int.self, forKey: .attentionHeads) ?? 1
        self.kvHeads = try container.decodeIfPresent(Int.self, forKey: .kvHeads) ?? 1
        self.headDim = try container.decodeIfPresent(Int.self, forKey: .headDim) ?? max(1, hiddenSize / max(attentionHeads, 1))
        self.rmsNormEps = try container.decodeIfPresent(Float.self, forKey: .rmsNormEps) ?? 1e-6
        self.vocabularySize = try container.decodeIfPresent(Int.self, forKey: .vocabularySize) ?? 0
        self.ropeTheta = try container.decodeIfPresent(Float.self, forKey: .ropeTheta) ?? 1_000_000
        self.maxPositionEmbeddings = try container.decodeIfPresent(Int.self, forKey: .maxPositionEmbeddings) ?? 32768
        self.attentionBias = try container.decodeIfPresent(Bool.self, forKey: .attentionBias) ?? false
        self.blockSize = try container.decodeIfPresent(Int.self, forKey: .blockSize) ?? 16
        self.numTargetLayers = try container.decodeIfPresent(Int.self, forKey: .numTargetLayers) ?? 0
        let nestedTargetLayerIDs = try nested?.decodeIfPresent([Int].self, forKey: .targetLayerIDs)
        let topLevelTargetLayerIDs = try container.decodeIfPresent([Int].self, forKey: .targetLayerIDs)
        self.targetLayerIDs = nestedTargetLayerIDs ?? topLevelTargetLayerIDs ?? []
        let nestedMaskTokenID = try nested?.decodeIfPresent(Int.self, forKey: .maskTokenID)
        let topLevelMaskTokenID = try container.decodeIfPresent(Int.self, forKey: .maskTokenID)
        self.maskTokenID = nestedMaskTokenID ?? topLevelMaskTokenID ?? 0
        self.ropeScaling = try container.decodeIfPresent([String: StringOrNumber].self, forKey: .ropeScaling)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(hiddenSize, forKey: .hiddenSize)
        try container.encode(hiddenLayers, forKey: .hiddenLayers)
        try container.encode(intermediateSize, forKey: .intermediateSize)
        try container.encode(attentionHeads, forKey: .attentionHeads)
        try container.encode(kvHeads, forKey: .kvHeads)
        try container.encode(headDim, forKey: .headDim)
        try container.encode(rmsNormEps, forKey: .rmsNormEps)
        try container.encode(vocabularySize, forKey: .vocabularySize)
        try container.encode(ropeTheta, forKey: .ropeTheta)
        try container.encode(maxPositionEmbeddings, forKey: .maxPositionEmbeddings)
        try container.encode(attentionBias, forKey: .attentionBias)
        try container.encode(blockSize, forKey: .blockSize)
        try container.encode(numTargetLayers, forKey: .numTargetLayers)
        try container.encodeIfPresent(ropeScaling, forKey: .ropeScaling)
        var nested = container.nestedContainer(keyedBy: DFlashConfigKeys.self, forKey: .dflashConfig)
        try nested.encode(targetLayerIDs, forKey: .targetLayerIDs)
        try nested.encode(maskTokenID, forKey: .maskTokenID)
    }
}

public enum DFlashModelError: LocalizedError {
    case missingRequiredConfiguration(String)
    case unsupportedStandaloneLanguageModel

    public var errorDescription: String? {
        switch self {
        case .missingRequiredConfiguration(let key):
            "DFlash draft configuration is missing required field '\(key)'."
        case .unsupportedStandaloneLanguageModel:
            "DFlash draft checkpoints are not standalone language models."
        }
    }
}

final class DFlashAttention: Module {
    let args: DFlashDraftConfiguration
    let scale: Float

    @ModuleInfo(key: "q_proj") var qProj: Linear
    @ModuleInfo(key: "k_proj") var kProj: Linear
    @ModuleInfo(key: "v_proj") var vProj: Linear
    @ModuleInfo(key: "o_proj") var oProj: Linear
    @ModuleInfo(key: "q_norm") var qNorm: RMSNorm
    @ModuleInfo(key: "k_norm") var kNorm: RMSNorm

    let rope: RoPE

    init(_ args: DFlashDraftConfiguration) {
        self.args = args
        self.scale = pow(Float(args.headDim), -0.5)

        _qProj.wrappedValue = Linear(args.hiddenSize, args.attentionHeads * args.headDim, bias: args.attentionBias)
        _kProj.wrappedValue = Linear(args.hiddenSize, args.kvHeads * args.headDim, bias: args.attentionBias)
        _vProj.wrappedValue = Linear(args.hiddenSize, args.kvHeads * args.headDim, bias: args.attentionBias)
        _oProj.wrappedValue = Linear(args.attentionHeads * args.headDim, args.hiddenSize, bias: args.attentionBias)
        _qNorm.wrappedValue = RMSNorm(dimensions: args.headDim, eps: args.rmsNormEps)
        _kNorm.wrappedValue = RMSNorm(dimensions: args.headDim, eps: args.rmsNormEps)

        let ropeScale: Float
        if let ropeScaling = args.ropeScaling,
           ropeScaling["type"] == .string("linear"),
           let factor = ropeScaling["factor"]?.asFloat() {
            ropeScale = 1 / factor
        } else {
            ropeScale = 1
        }
        self.rope = RoPE(
            dimensions: args.headDim,
            traditional: false,
            base: args.ropeTheta,
            scale: ropeScale
        )

        super.init()
    }

    func callAsFunction(
        _ hiddenStates: MLXArray,
        targetHidden: MLXArray,
        cache: KVCache?
    ) -> MLXArray {
        let batchSize = hiddenStates.dim(0)
        let queryLength = hiddenStates.dim(1)
        let contextLength = targetHidden.dim(1)

        var queries = qProj(hiddenStates)
            .reshaped(batchSize, queryLength, args.attentionHeads, args.headDim)
        queries = qNorm(queries).transposed(0, 2, 1, 3)

        var contextKeys = kProj(targetHidden)
            .reshaped(batchSize, contextLength, args.kvHeads, args.headDim)
        var proposalKeys = kProj(hiddenStates)
            .reshaped(batchSize, queryLength, args.kvHeads, args.headDim)
        var contextValues = vProj(targetHidden)
            .reshaped(batchSize, contextLength, args.kvHeads, args.headDim)
        var proposalValues = vProj(hiddenStates)
            .reshaped(batchSize, queryLength, args.kvHeads, args.headDim)

        contextKeys = kNorm(contextKeys).transposed(0, 2, 1, 3)
        proposalKeys = kNorm(proposalKeys).transposed(0, 2, 1, 3)
        contextValues = contextValues.transposed(0, 2, 1, 3)
        proposalValues = proposalValues.transposed(0, 2, 1, 3)

        let cacheOffset = cache?.offset ?? 0
        let proposalOffset = cacheOffset + max(contextLength - 1, 0)
        queries = rope(queries, offset: proposalOffset)
        contextKeys = rope(contextKeys, offset: cacheOffset)
        proposalKeys = rope(proposalKeys, offset: proposalOffset)

        let keys: MLXArray
        let values: MLXArray
        if let cache {
            let (cachedKeys, cachedValues) = cache.update(keys: contextKeys, values: contextValues)
            keys = concatenated([cachedKeys, proposalKeys], axis: 2)
            values = concatenated([cachedValues, proposalValues], axis: 2)
        } else {
            keys = concatenated([contextKeys, proposalKeys], axis: 2)
            values = concatenated([contextValues, proposalValues], axis: 2)
        }

        let output = MLXFast.scaledDotProductAttention(
            queries: queries,
            keys: keys,
            values: values,
            scale: scale,
            mask: .none
        )
        .transposed(0, 2, 1, 3)
        .reshaped(batchSize, queryLength, -1)

        return oProj(output)
    }
}

final class DFlashDecoderLayer: Module {
    @ModuleInfo(key: "self_attn") var attention: DFlashAttention
    @ModuleInfo(key: "input_layernorm") var inputLayerNorm: RMSNorm
    @ModuleInfo(key: "post_attention_layernorm") var postAttentionLayerNorm: RMSNorm

    let mlp: Qwen3MLP

    init(_ args: DFlashDraftConfiguration) {
        _attention.wrappedValue = DFlashAttention(args)
        _inputLayerNorm.wrappedValue = RMSNorm(dimensions: args.hiddenSize, eps: args.rmsNormEps)
        _postAttentionLayerNorm.wrappedValue = RMSNorm(dimensions: args.hiddenSize, eps: args.rmsNormEps)
        self.mlp = Qwen3MLP(dimensions: args.hiddenSize, hiddenDimensions: args.intermediateSize)
        super.init()
    }

    func callAsFunction(
        _ hiddenStates: MLXArray,
        targetHidden: MLXArray,
        cache: KVCache?
    ) -> MLXArray {
        let attentionOut = attention(
            inputLayerNorm(hiddenStates),
            targetHidden: targetHidden,
            cache: cache
        )
        let h = hiddenStates + attentionOut
        return h + mlp(postAttentionLayerNorm(h))
    }
}

public final class DFlashDraftModel: Module, LanguageModel {
    public let configuration: DFlashDraftConfiguration
    public let kvHeads: [Int]

    @ModuleInfo(key: "fc") var fc: Linear
    @ModuleInfo(key: "hidden_norm") var hiddenNorm: RMSNorm

    let layers: [DFlashDecoderLayer]
    let norm: RMSNorm

    public init(_ configuration: DFlashDraftConfiguration) throws {
        guard configuration.hiddenSize > 0 else {
            throw DFlashModelError.missingRequiredConfiguration("hidden_size")
        }
        guard configuration.hiddenLayers > 0 else {
            throw DFlashModelError.missingRequiredConfiguration("num_hidden_layers")
        }
        guard configuration.intermediateSize > 0 else {
            throw DFlashModelError.missingRequiredConfiguration("intermediate_size")
        }
        guard configuration.vocabularySize > 0 else {
            throw DFlashModelError.missingRequiredConfiguration("vocab_size")
        }
        guard !configuration.targetLayerIDs.isEmpty else {
            throw DFlashModelError.missingRequiredConfiguration("dflash_config.target_layer_ids")
        }

        self.configuration = configuration
        self.kvHeads = (0 ..< configuration.hiddenLayers).map { _ in configuration.kvHeads }
        _fc.wrappedValue = Linear(
            configuration.targetLayerIDs.count * configuration.hiddenSize,
            configuration.hiddenSize,
            bias: false
        )
        _hiddenNorm.wrappedValue = RMSNorm(dimensions: configuration.hiddenSize, eps: configuration.rmsNormEps)
        self.layers = (0 ..< configuration.hiddenLayers).map { _ in
            DFlashDecoderLayer(configuration)
        }
        self.norm = RMSNorm(dimensions: configuration.hiddenSize, eps: configuration.rmsNormEps)

        super.init()
    }

    public func callAsFunction(
        inputEmbeddings: MLXArray,
        targetHidden: MLXArray,
        cache: [KVCache]? = nil
    ) -> MLXArray {
        let normalizedTargetHidden = hiddenNorm(fc(targetHidden))
        var hiddenStates = inputEmbeddings

        for (index, layer) in layers.enumerated() {
            hiddenStates = layer(
                hiddenStates,
                targetHidden: normalizedTargetHidden,
                cache: cache?[index]
            )
        }

        return norm(hiddenStates)
    }

    public func prepare(_ input: LMInput, cache: [KVCache], windowSize: Int?) throws -> PrepareResult {
        throw DFlashModelError.unsupportedStandaloneLanguageModel
    }

    public func callAsFunction(_ input: LMInput.Text, cache: [KVCache]?, state: LMOutput.State?) -> LMOutput {
        fatalError("DFlash draft checkpoints require DFlash speculative decode.")
    }

    public func callAsFunction(_ inputs: MLXArray, cache: [KVCache]?) -> MLXArray {
        fatalError("DFlash draft checkpoints require target embeddings and target hidden states.")
    }

    public func newCache(parameters: GenerateParameters?) -> [KVCache] {
        (0 ..< configuration.hiddenLayers).map { _ in KVCacheSimple() }
    }
}

public func loadDFlashDraftConfiguration(directory: URL) throws -> DFlashDraftConfiguration {
    let data = try Data(contentsOf: directory.appendingPathComponent("config.json", isDirectory: false))
    return try JSONDecoder().decode(DFlashDraftConfiguration.self, from: data)
}

public func loadDFlashDraftModel(directory: URL) throws -> DFlashDraftModel {
    let configuration = try loadDFlashDraftConfiguration(directory: directory)
    let model = try DFlashDraftModel(configuration)
    try loadWeights(modelDirectory: directory, model: model)
    return model
}
