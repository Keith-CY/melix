#if canImport(MLX)
@preconcurrency import MLX

public struct TurboQuantFusedAttentionLaunchPlan: Equatable {
    public let gridX: Int
    public let gridY: Int
    public let gridZ: Int
    public let threadGroupX: Int
    public let sharedScoreCount: Int
    public let scoreDotProductsPerQueryHead: Int
    public let scoreReductionLaneCount: Int
    public let scoreReductionSimdgroupCount: Int
    public let usesThreadgroupSharedScores: Bool
    public let usesThreadgroupParallelScoreReduction: Bool
    public let usesOnlineSoftmax: Bool
}

public func turboQuantFusedAttentionLaunchPlan(
    batchCount: Int,
    queryHeadCount: Int,
    kvHeadCount: Int,
    sequenceLength: Int,
    headDimension: Int,
    groupSize: Int
) -> TurboQuantFusedAttentionLaunchPlan? {
    guard batchCount > 0,
        queryHeadCount > 0,
        kvHeadCount > 0,
        sequenceLength > 0,
        sequenceLength <= 4096,
        headDimension > 0,
        headDimension <= 256,
        headDimension % 8 == 0,
        headDimension % 32 == 0,
        groupSize > 0,
        headDimension % groupSize == 0,
        queryHeadCount % kvHeadCount == 0
    else {
        return nil
    }

    return TurboQuantFusedAttentionLaunchPlan(
        gridX: 32,
        gridY: queryHeadCount,
        gridZ: batchCount,
        threadGroupX: 32,
        sharedScoreCount: 0,
        scoreDotProductsPerQueryHead: sequenceLength,
        scoreReductionLaneCount: min(32, headDimension),
        scoreReductionSimdgroupCount: 1,
        usesThreadgroupSharedScores: false,
        usesThreadgroupParallelScoreReduction: true,
        usesOnlineSoftmax: true
    )
}

/// Melix vendored q4 affine decode attention route.
///
/// This fuses score, softmax, and value accumulation for one-token decode over
/// MLX's packed q4 affine KV-cache layout. Unsupported masks, quantization modes,
/// and non-decode shapes return nil so callers can fall back to the upstream
/// quantized reference path.
public func fusedQ4ScaledDotProductAttention(
    queries: MLXArray,
    quantizedKeys: (MLXArray, MLXArray, MLXArray?),
    quantizedValues: (MLXArray, MLXArray, MLXArray?),
    scale: Float,
    mask: MLXFast.ScaledDotProductAttentionMaskMode = .none,
    groupSize: Int = 64,
    bits: Int = 8,
    mode: QuantizationMode = .affine
) -> MLXArray? {
    guard bits == 4, mode == .affine else { return nil }
    switch mask {
    case .none, .causal:
        break
    case .array, .arrays:
        return nil
    }

    guard queries.shape.count == 4,
        quantizedKeys.0.shape.count == 4,
        quantizedValues.0.shape.count == 4,
        quantizedKeys.1.shape.count == 4,
        quantizedValues.1.shape.count == 4,
        let keyBiases = quantizedKeys.2,
        let valueBiases = quantizedValues.2,
        keyBiases.shape.count == 4,
        valueBiases.shape.count == 4
    else {
        return nil
    }

    let batchCount = queries.dim(0)
    let queryHeadCount = queries.dim(1)
    let queryLength = queries.dim(2)
    let headDimension = queries.dim(3)
    let kvHeadCount = quantizedKeys.0.dim(1)
    let sequenceLength = quantizedKeys.0.dim(2)
    let packedWordsPerToken = headDimension / 8
    let groupCount = (headDimension + groupSize - 1) / groupSize
    guard let launchPlan = turboQuantFusedAttentionLaunchPlan(
        batchCount: batchCount,
        queryHeadCount: queryHeadCount,
        kvHeadCount: kvHeadCount,
        sequenceLength: sequenceLength,
        headDimension: headDimension,
        groupSize: groupSize
    ) else {
        return nil
    }

    guard batchCount > 0,
        queryHeadCount > 0,
        queryLength == 1,
        kvHeadCount > 0,
        sequenceLength > 0,
        headDimension > 0,
        headDimension % 8 == 0,
        groupSize > 0,
        headDimension % groupSize == 0,
        queryHeadCount % kvHeadCount == 0
    else {
        return nil
    }

    guard quantizedKeys.0.shape == [batchCount, kvHeadCount, sequenceLength, packedWordsPerToken],
        quantizedValues.0.shape == [batchCount, kvHeadCount, sequenceLength, packedWordsPerToken],
        quantizedKeys.1.shape == [batchCount, kvHeadCount, sequenceLength, groupCount],
        keyBiases.shape == [batchCount, kvHeadCount, sequenceLength, groupCount],
        quantizedValues.1.shape == [batchCount, kvHeadCount, sequenceLength, groupCount],
        valueBiases.shape == [batchCount, kvHeadCount, sequenceLength, groupCount]
    else {
        return nil
    }

    let queryRepeats = queryHeadCount / kvHeadCount
    let scoreSimdgroupCount = launchPlan.scoreReductionSimdgroupCount
    let dimensionsPerLane = (headDimension + 31) / 32
    let attentionScale = MLXArray([scale])
    let sequenceLengthScalar = MLXArray([Int32(sequenceLength)])
    let output = Device.withDefaultDevice(.gpu) {
        let kernel = MLXFast.metalKernel(
            name: "melix_turboquant_q4_affine_fused_decode_attention",
            inputNames: [
                "queries",
                "packedKeys",
                "keyScales",
                "keyBiases",
                "packedValues",
                "valueScales",
                "valueBiases",
                "attentionScale",
                "sequenceLengthInput",
            ],
            outputNames: ["output"],
            source: """
                uint dim = thread_position_in_threadgroup.x;
                uint queryHead = thread_position_in_grid.y;
                uint batch = thread_position_in_grid.z;
                uint kvHead = queryHead / QUERY_REPEATS;
                uint outputBase = (batch * QUERY_HEAD_COUNT + queryHead) * HEAD_DIMENSION;
                uint sequenceLength = uint(sequenceLengthInput[0]);

                float accumulators[DIMS_PER_LANE];
                for (uint slot = 0; slot < DIMS_PER_LANE; slot++) {
                    accumulators[slot] = 0.0f;
                }
                float maxScore = -3.402823466e+38f;
                float normalizer = 0.0f;
                for (uint token = 0; token < sequenceLength; token++) {
                    float partialScore = 0.0f;
                    for (uint slot = 0; slot < DIMS_PER_LANE; slot++) {
                        uint valueDim = dim + slot * 32;
                        if (valueDim >= HEAD_DIMENSION) {
                            continue;
                        }
                        uint queryIndex = outputBase + valueDim;
                        uint keyWordIndex = ((batch * KV_HEAD_COUNT + kvHead) * sequenceLength + token)
                            * PACKED_WORDS_PER_TOKEN + (valueDim >> 3);
                        uint keyWord = packedKeys[keyWordIndex];
                        uint keyByteShift = ((valueDim >> 1) & 0x3) << 3;
                        uint keyPackedByte = (keyWord >> keyByteShift) & 0xff;
                        uint keyQuantized = ((valueDim & 1) == 0)
                            ? (keyPackedByte & 0x0f)
                            : ((keyPackedByte >> 4) & 0x0f);
                        uint keyScaleIndex = ((batch * KV_HEAD_COUNT + kvHead) * sequenceLength + token)
                            * GROUP_COUNT + (valueDim / GROUP_SIZE);
                        float keyValue = float(keyQuantized) * keyScales[keyScaleIndex] + keyBiases[keyScaleIndex];
                        partialScore += queries[queryIndex] * keyValue;
                    }

                    float score = simd_sum(partialScore) * attentionScale[0];
                    float newMaxScore = score > maxScore ? score : maxScore;
                    float rescale = normalizer > 0.0f ? exp(maxScore - newMaxScore) : 0.0f;
                    float weight = exp(score - newMaxScore);
                    normalizer = normalizer * rescale + weight;
                    maxScore = newMaxScore;

                    for (uint slot = 0; slot < DIMS_PER_LANE; slot++) {
                        uint valueDim = dim + slot * 32;
                        if (valueDim >= HEAD_DIMENSION) {
                            continue;
                        }
                        uint valueWordIndex = ((batch * KV_HEAD_COUNT + kvHead) * sequenceLength + token)
                            * PACKED_WORDS_PER_TOKEN + (valueDim >> 3);
                        uint valueWord = packedValues[valueWordIndex];
                        uint valueByteShift = ((valueDim >> 1) & 0x3) << 3;
                        uint valuePackedByte = (valueWord >> valueByteShift) & 0xff;
                        uint valueQuantized = ((valueDim & 1) == 0)
                            ? (valuePackedByte & 0x0f)
                            : ((valuePackedByte >> 4) & 0x0f);
                        uint valueScaleIndex = ((batch * KV_HEAD_COUNT + kvHead) * sequenceLength + token)
                            * GROUP_COUNT + (valueDim / GROUP_SIZE);
                        float value = float(valueQuantized) * valueScales[valueScaleIndex] + valueBiases[valueScaleIndex];
                        accumulators[slot] = accumulators[slot] * rescale + weight * value;
                    }
                }

                for (uint slot = 0; slot < DIMS_PER_LANE; slot++) {
                    uint valueDim = dim + slot * 32;
                    if (valueDim < HEAD_DIMENSION) {
                        output[outputBase + valueDim] = accumulators[slot] / max(normalizer, 1.0e-20f);
                    }
                }
                """,
            ensureRowContiguous: true
        )
        return kernel(
            [
                queries,
                quantizedKeys.0,
                quantizedKeys.1,
                keyBiases,
                quantizedValues.0,
                quantizedValues.1,
                valueBiases,
                attentionScale,
                sequenceLengthScalar,
            ],
            template: [
                ("HEAD_DIMENSION", headDimension),
                ("QUERY_HEAD_COUNT", queryHeadCount),
                ("KV_HEAD_COUNT", kvHeadCount),
                ("QUERY_REPEATS", queryRepeats),
                ("PACKED_WORDS_PER_TOKEN", packedWordsPerToken),
                ("GROUP_SIZE", groupSize),
                ("GROUP_COUNT", groupCount),
                ("SCORE_SIMDGROUP_COUNT", scoreSimdgroupCount),
                ("DIMS_PER_LANE", dimensionsPerLane),
            ],
            grid: (launchPlan.gridX, launchPlan.gridY, launchPlan.gridZ),
            threadGroup: (launchPlan.threadGroupX, 1, 1),
            outputShapes: [[batchCount, queryHeadCount, 1, headDimension]],
            outputDTypes: [.float32]
        )
    }
    return output[0]
}
#endif
