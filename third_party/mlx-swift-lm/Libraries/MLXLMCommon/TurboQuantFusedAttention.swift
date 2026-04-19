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
        groupSize % 8 == 0,
        headDimension % groupSize == 0,
        queryHeadCount % kvHeadCount == 0
    else {
        return nil
    }

    let packedWordsPerToken = headDimension / 8
    return TurboQuantFusedAttentionLaunchPlan(
        gridX: 32,
        gridY: queryHeadCount,
        gridZ: batchCount,
        threadGroupX: 32,
        sharedScoreCount: 0,
        scoreDotProductsPerQueryHead: sequenceLength,
        scoreReductionLaneCount: min(32, packedWordsPerToken),
        scoreReductionSimdgroupCount: 1,
        usesThreadgroupSharedScores: false,
        usesThreadgroupParallelScoreReduction: true,
        usesOnlineSoftmax: true
    )
}

/// Quantize one decode key/value token into MLX's q4 affine tuple layout.
///
/// The cache append path still owns storage writes, but this combines key and
/// value quantization for single-token decode into one custom Metal dispatch.
/// Unsupported shapes return nil so callers can preserve MLX's native
/// quantization fallback.
public func fusedQ4AffineKeyValueQuantizedForDecode(
    keys: MLXArray,
    values: MLXArray,
    groupSize: Int = 64,
    bits: Int = 4,
    mode: QuantizationMode = .affine
) -> (QuantizedKVCacheTuple, QuantizedKVCacheTuple)? {
    guard bits == 4, mode == .affine,
        keys.shape.count == 4,
        values.shape.count == 4,
        keys.shape == values.shape,
        keys.dtype == values.dtype
    else {
        return nil
    }

    let batchCount = keys.dim(0)
    let kvHeadCount = keys.dim(1)
    let tokenCount = keys.dim(2)
    let headDimension = keys.dim(3)
    guard batchCount > 0,
        kvHeadCount > 0,
        tokenCount == 1,
        headDimension > 0,
        headDimension % 8 == 0,
        groupSize > 0,
        groupSize % 8 == 0,
        headDimension % groupSize == 0
    else {
        return nil
    }

    let packedWordsPerToken = headDimension / 8
    let groupCount = headDimension / groupSize
    let packedWordsPerGroup = groupSize / 8
    let quantizationGroupCount = batchCount * kvHeadCount * groupCount
    let outputDType = keys.dtype
    let output = Device.withDefaultDevice(.gpu) {
        let kernel = MLXFast.metalKernel(
            name: "melix_turboquant_q4_affine_key_value_quantize_decode",
            inputNames: ["keys", "values"],
            outputNames: [
                "packedKeys",
                "keyScales",
                "keyBiases",
                "packedValues",
                "valueScales",
                "valueBiases",
            ],
            source: """
                uint groupIndex = thread_position_in_grid.x;
                bool isValue = groupIndex >= QUANTIZATION_GROUP_COUNT;
                uint localGroupIndex = isValue ? groupIndex - QUANTIZATION_GROUP_COUNT : groupIndex;
                uint group = localGroupIndex % GROUP_COUNT;
                uint head = (localGroupIndex / GROUP_COUNT) % KV_HEAD_COUNT;
                uint batch = localGroupIndex / (GROUP_COUNT * KV_HEAD_COUNT);
                uint inputBase = (batch * KV_HEAD_COUNT + head) * HEAD_DIMENSION
                    + group * GROUP_SIZE;

                float minValue = 3.402823466e+38f;
                float maxValue = -3.402823466e+38f;
                for (uint offset = 0; offset < GROUP_SIZE; offset++) {
                    float value = isValue ? float(values[inputBase + offset])
                        : float(keys[inputBase + offset]);
                    minValue = min(minValue, value);
                    maxValue = max(maxValue, value);
                }

                float scale = (minValue - maxValue) * 0.0625f;
                float bias = maxValue;
                uint scaleIndex = (batch * KV_HEAD_COUNT + head) * GROUP_COUNT + group;
                if (isValue) {
                    valueScales[scaleIndex] = static_cast<T>(scale);
                    valueBiases[scaleIndex] = static_cast<T>(bias);
                } else {
                    keyScales[scaleIndex] = static_cast<T>(scale);
                    keyBiases[scaleIndex] = static_cast<T>(bias);
                }

                for (uint packedWord = 0; packedWord < PACKED_WORDS_PER_GROUP; packedWord++) {
                    uint packed = 0;
                    for (uint slot = 0; slot < 8; slot++) {
                        uint elementOffset = packedWord * 8 + slot;
                        float value = isValue ? float(values[inputBase + elementOffset])
                            : float(keys[inputBase + elementOffset]);
                        float qFloat = fabs(scale) > 1.0e-20f ? round((value - bias) / scale) : 0.0f;
                        uint q = uint(clamp(qFloat, 0.0f, 15.0f));
                        packed |= q << (slot * 4);
                    }
                    uint packedIndex = (batch * KV_HEAD_COUNT + head) * PACKED_WORDS_PER_TOKEN
                        + group * PACKED_WORDS_PER_GROUP + packedWord;
                    if (isValue) {
                        packedValues[packedIndex] = packed;
                    } else {
                        packedKeys[packedIndex] = packed;
                    }
                }
                """,
            ensureRowContiguous: true
        )
        return kernel(
            [keys, values],
            template: [
                ("T", outputDType),
                ("HEAD_DIMENSION", headDimension),
                ("KV_HEAD_COUNT", kvHeadCount),
                ("GROUP_SIZE", groupSize),
                ("GROUP_COUNT", groupCount),
                ("PACKED_WORDS_PER_TOKEN", packedWordsPerToken),
                ("PACKED_WORDS_PER_GROUP", packedWordsPerGroup),
                ("QUANTIZATION_GROUP_COUNT", quantizationGroupCount),
            ],
            grid: (quantizationGroupCount * 2, 1, 1),
            threadGroup: (1, 1, 1),
            outputShapes: [
                [batchCount, kvHeadCount, 1, packedWordsPerToken],
                [batchCount, kvHeadCount, 1, groupCount],
                [batchCount, kvHeadCount, 1, groupCount],
                [batchCount, kvHeadCount, 1, packedWordsPerToken],
                [batchCount, kvHeadCount, 1, groupCount],
                [batchCount, kvHeadCount, 1, groupCount],
            ],
            outputDTypes: [
                .uint32,
                outputDType,
                outputDType,
                .uint32,
                outputDType,
                outputDType,
            ]
        )
    }

    return (
        (output[0], output[1], output[2]),
        (output[3], output[4], output[5])
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
    sequenceLength: Int? = nil,
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
    let storageSequenceLength = quantizedKeys.0.dim(2)
    let effectiveSequenceLength = sequenceLength ?? storageSequenceLength
    let packedWordsPerToken = headDimension / 8
    let groupCount = (headDimension + groupSize - 1) / groupSize
    guard let launchPlan = turboQuantFusedAttentionLaunchPlan(
        batchCount: batchCount,
        queryHeadCount: queryHeadCount,
        kvHeadCount: kvHeadCount,
        sequenceLength: effectiveSequenceLength,
        headDimension: headDimension,
        groupSize: groupSize
    ) else {
        return nil
    }

    guard batchCount > 0,
        queryHeadCount > 0,
        queryLength == 1,
        kvHeadCount > 0,
        effectiveSequenceLength > 0,
        storageSequenceLength >= effectiveSequenceLength,
        headDimension > 0,
        headDimension % 8 == 0,
        groupSize > 0,
        groupSize % 8 == 0,
        headDimension % groupSize == 0,
        queryHeadCount % kvHeadCount == 0
    else {
        return nil
    }

    guard quantizedKeys.0.shape == [batchCount, kvHeadCount, storageSequenceLength, packedWordsPerToken],
        quantizedValues.0.shape == [batchCount, kvHeadCount, storageSequenceLength, packedWordsPerToken],
        quantizedKeys.1.shape == [batchCount, kvHeadCount, storageSequenceLength, groupCount],
        keyBiases.shape == [batchCount, kvHeadCount, storageSequenceLength, groupCount],
        quantizedValues.1.shape == [batchCount, kvHeadCount, storageSequenceLength, groupCount],
        valueBiases.shape == [batchCount, kvHeadCount, storageSequenceLength, groupCount]
    else {
        return nil
    }

    let queryRepeats = queryHeadCount / kvHeadCount
    let attentionScale = MLXArray([scale])
    let sequenceLengthScalar = MLXArray([Int32(effectiveSequenceLength)])
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
                uint packedWordLane = thread_position_in_threadgroup.x;
                uint queryHead = thread_position_in_grid.y;
                uint batch = thread_position_in_grid.z;
                uint kvHead = queryHead / QUERY_REPEATS;
                uint outputBase = (batch * QUERY_HEAD_COUNT + queryHead) * HEAD_DIMENSION;
                uint sequenceLength = uint(sequenceLengthInput[0]);
                bool activeLane = packedWordLane < PACKED_WORDS_PER_TOKEN;
                uint dimBase = packedWordLane << 3;

                float accumulators[8];
                for (uint slot = 0; slot < 8; slot++) {
                    accumulators[slot] = 0.0f;
                }
                float maxScore = -3.402823466e+38f;
                float normalizer = 0.0f;
                for (uint token = 0; token < sequenceLength; token++) {
                    float partialScore = 0.0f;
                    if (activeLane) {
                        uint keyWordIndex = ((batch * KV_HEAD_COUNT + kvHead) * CACHE_SEQUENCE_LENGTH + token)
                            * PACKED_WORDS_PER_TOKEN + packedWordLane;
                        uint keyWord = packedKeys[keyWordIndex];
                        uint keyScaleIndex = ((batch * KV_HEAD_COUNT + kvHead) * CACHE_SEQUENCE_LENGTH + token)
                            * GROUP_COUNT + (dimBase / GROUP_SIZE);
                        float keyScale = keyScales[keyScaleIndex];
                        float keyBias = keyBiases[keyScaleIndex];
                        partialScore += queries[outputBase + dimBase + 0]
                            * (float((keyWord >> 0) & 0x0f) * keyScale + keyBias);
                        partialScore += queries[outputBase + dimBase + 1]
                            * (float((keyWord >> 4) & 0x0f) * keyScale + keyBias);
                        partialScore += queries[outputBase + dimBase + 2]
                            * (float((keyWord >> 8) & 0x0f) * keyScale + keyBias);
                        partialScore += queries[outputBase + dimBase + 3]
                            * (float((keyWord >> 12) & 0x0f) * keyScale + keyBias);
                        partialScore += queries[outputBase + dimBase + 4]
                            * (float((keyWord >> 16) & 0x0f) * keyScale + keyBias);
                        partialScore += queries[outputBase + dimBase + 5]
                            * (float((keyWord >> 20) & 0x0f) * keyScale + keyBias);
                        partialScore += queries[outputBase + dimBase + 6]
                            * (float((keyWord >> 24) & 0x0f) * keyScale + keyBias);
                        partialScore += queries[outputBase + dimBase + 7]
                            * (float((keyWord >> 28) & 0x0f) * keyScale + keyBias);
                    }

                    float score = simd_sum(partialScore) * attentionScale[0];
                    float newMaxScore = score > maxScore ? score : maxScore;
                    float rescale = normalizer > 0.0f ? exp(maxScore - newMaxScore) : 0.0f;
                    float weight = exp(score - newMaxScore);
                    normalizer = normalizer * rescale + weight;
                    maxScore = newMaxScore;

                    if (activeLane) {
                        uint valueWordIndex = ((batch * KV_HEAD_COUNT + kvHead) * CACHE_SEQUENCE_LENGTH + token)
                            * PACKED_WORDS_PER_TOKEN + packedWordLane;
                        uint valueWord = packedValues[valueWordIndex];
                        uint valueScaleIndex = ((batch * KV_HEAD_COUNT + kvHead) * CACHE_SEQUENCE_LENGTH + token)
                            * GROUP_COUNT + (dimBase / GROUP_SIZE);
                        float valueScale = valueScales[valueScaleIndex];
                        float valueBias = valueBiases[valueScaleIndex];
                        accumulators[0] = accumulators[0] * rescale
                            + weight * (float((valueWord >> 0) & 0x0f) * valueScale + valueBias);
                        accumulators[1] = accumulators[1] * rescale
                            + weight * (float((valueWord >> 4) & 0x0f) * valueScale + valueBias);
                        accumulators[2] = accumulators[2] * rescale
                            + weight * (float((valueWord >> 8) & 0x0f) * valueScale + valueBias);
                        accumulators[3] = accumulators[3] * rescale
                            + weight * (float((valueWord >> 12) & 0x0f) * valueScale + valueBias);
                        accumulators[4] = accumulators[4] * rescale
                            + weight * (float((valueWord >> 16) & 0x0f) * valueScale + valueBias);
                        accumulators[5] = accumulators[5] * rescale
                            + weight * (float((valueWord >> 20) & 0x0f) * valueScale + valueBias);
                        accumulators[6] = accumulators[6] * rescale
                            + weight * (float((valueWord >> 24) & 0x0f) * valueScale + valueBias);
                        accumulators[7] = accumulators[7] * rescale
                            + weight * (float((valueWord >> 28) & 0x0f) * valueScale + valueBias);
                    }
                }

                if (activeLane) {
                    float reciprocalNormalizer = 1.0f / max(normalizer, 1.0e-20f);
                    for (uint slot = 0; slot < 8; slot++) {
                        output[outputBase + dimBase + slot] = accumulators[slot] * reciprocalNormalizer;
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
                ("CACHE_SEQUENCE_LENGTH", storageSequenceLength),
                ("GROUP_SIZE", groupSize),
                ("GROUP_COUNT", groupCount),
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
