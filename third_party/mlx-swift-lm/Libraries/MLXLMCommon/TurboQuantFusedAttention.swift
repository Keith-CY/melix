#if canImport(MLX)
@preconcurrency import MLX

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
    let elementCount = batchCount * queryHeadCount * headDimension
    let threadGroupSize = min(256, headDimension)
    let attentionScale = MLXArray([scale])
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
            ],
            outputNames: ["output"],
            source: """
                uint elem = thread_position_in_grid.x;
                uint dim = elem % HEAD_DIMENSION;
                uint queryHead = (elem / HEAD_DIMENSION) % QUERY_HEAD_COUNT;
                uint batch = elem / (HEAD_DIMENSION * QUERY_HEAD_COUNT);
                uint kvHead = queryHead / QUERY_REPEATS;

                float maxScore = -3.402823466e+38f;
                for (uint token = 0; token < SEQUENCE_LENGTH; token++) {
                    float dot = 0.0f;
                    for (uint keyDim = 0; keyDim < HEAD_DIMENSION; keyDim++) {
                        uint queryIndex = (batch * QUERY_HEAD_COUNT + queryHead) * HEAD_DIMENSION + keyDim;
                        uint keyWordIndex = ((batch * KV_HEAD_COUNT + kvHead) * SEQUENCE_LENGTH + token)
                            * PACKED_WORDS_PER_TOKEN + (keyDim >> 3);
                        uint keyWord = packedKeys[keyWordIndex];
                        uint keyByteShift = ((keyDim >> 1) & 0x3) << 3;
                        uint keyPackedByte = (keyWord >> keyByteShift) & 0xff;
                        uint keyQuantized = ((keyDim & 1) == 0) ? (keyPackedByte & 0x0f) : ((keyPackedByte >> 4) & 0x0f);
                        uint keyScaleIndex = ((batch * KV_HEAD_COUNT + kvHead) * SEQUENCE_LENGTH + token)
                            * GROUP_COUNT + (keyDim / GROUP_SIZE);
                        float keyValue = float(keyQuantized) * keyScales[keyScaleIndex] + keyBiases[keyScaleIndex];
                        dot += queries[queryIndex] * keyValue;
                    }
                    float score = dot * attentionScale[0];
                    maxScore = score > maxScore ? score : maxScore;
                }

                float normalizer = 0.0f;
                float accumulator = 0.0f;
                for (uint token = 0; token < SEQUENCE_LENGTH; token++) {
                    float dot = 0.0f;
                    for (uint keyDim = 0; keyDim < HEAD_DIMENSION; keyDim++) {
                        uint queryIndex = (batch * QUERY_HEAD_COUNT + queryHead) * HEAD_DIMENSION + keyDim;
                        uint keyWordIndex = ((batch * KV_HEAD_COUNT + kvHead) * SEQUENCE_LENGTH + token)
                            * PACKED_WORDS_PER_TOKEN + (keyDim >> 3);
                        uint keyWord = packedKeys[keyWordIndex];
                        uint keyByteShift = ((keyDim >> 1) & 0x3) << 3;
                        uint keyPackedByte = (keyWord >> keyByteShift) & 0xff;
                        uint keyQuantized = ((keyDim & 1) == 0) ? (keyPackedByte & 0x0f) : ((keyPackedByte >> 4) & 0x0f);
                        uint keyScaleIndex = ((batch * KV_HEAD_COUNT + kvHead) * SEQUENCE_LENGTH + token)
                            * GROUP_COUNT + (keyDim / GROUP_SIZE);
                        float keyValue = float(keyQuantized) * keyScales[keyScaleIndex] + keyBiases[keyScaleIndex];
                        dot += queries[queryIndex] * keyValue;
                    }

                    float weight = exp(dot * attentionScale[0] - maxScore);
                    normalizer += weight;

                    uint valueWordIndex = ((batch * KV_HEAD_COUNT + kvHead) * SEQUENCE_LENGTH + token)
                        * PACKED_WORDS_PER_TOKEN + (dim >> 3);
                    uint valueWord = packedValues[valueWordIndex];
                    uint valueByteShift = ((dim >> 1) & 0x3) << 3;
                    uint valuePackedByte = (valueWord >> valueByteShift) & 0xff;
                    uint valueQuantized = ((dim & 1) == 0) ? (valuePackedByte & 0x0f) : ((valuePackedByte >> 4) & 0x0f);
                    uint valueScaleIndex = ((batch * KV_HEAD_COUNT + kvHead) * SEQUENCE_LENGTH + token)
                        * GROUP_COUNT + (dim / GROUP_SIZE);
                    float value = float(valueQuantized) * valueScales[valueScaleIndex] + valueBiases[valueScaleIndex];
                    accumulator += weight * value;
                }

                output[elem] = accumulator / normalizer;
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
            ],
            template: [
                ("SEQUENCE_LENGTH", sequenceLength),
                ("HEAD_DIMENSION", headDimension),
                ("QUERY_HEAD_COUNT", queryHeadCount),
                ("KV_HEAD_COUNT", kvHeadCount),
                ("QUERY_REPEATS", queryRepeats),
                ("PACKED_WORDS_PER_TOKEN", packedWordsPerToken),
                ("GROUP_SIZE", groupSize),
                ("GROUP_COUNT", groupCount),
            ],
            grid: (elementCount, 1, 1),
            threadGroup: (threadGroupSize, 1, 1),
            outputShapes: [[batchCount, queryHeadCount, 1, headDimension]],
            outputDTypes: [.float32]
        )
    }
    return output[0]
}
#endif
