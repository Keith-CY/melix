#if canImport(MLX)
@preconcurrency import MLX

enum TurboQuantMetalKernelCapability {
    static func runIdentitySmokeKernel(_ input: MLXArray) -> MLXArray {
        let elementCount = max(1, input.shape.reduce(1, *))
        let threadGroupSize = min(256, elementCount)
        let kernel = MLXFast.metalKernel(
            name: "melix_turboquant_identity_smoke",
            inputNames: ["input"],
            outputNames: ["output"],
            source: """
                uint elem = thread_position_in_grid.x;
                output[elem] = input[elem];
                """,
            ensureRowContiguous: true
        )
        let output = kernel(
            [input],
            grid: (elementCount, 1, 1),
            threadGroup: (threadGroupSize, 1, 1),
            outputShapes: [input.shape],
            outputDTypes: [input.dtype]
        )
        return output[0]
    }

    static func runMSEQ4ValueDecodeSmokeKernel(
        packedValues: MLXArray,
        weights: MLXArray,
        scales: MLXArray,
        biases: MLXArray,
        sequenceLength: Int,
        headDimension: Int,
        groupSize: Int
    ) -> MLXArray {
        precondition(sequenceLength > 0)
        precondition(headDimension > 0)
        precondition(groupSize > 0)

        let packedDimension = (headDimension + 1) / 2
        let groupCount = (headDimension + groupSize - 1) / groupSize
        let threadGroupSize = min(256, headDimension)
        let kernel = MLXFast.metalKernel(
            name: "melix_turboquant_mse_q4_value_decode_smoke",
            inputNames: ["packedValues", "weights", "scales", "biases"],
            outputNames: ["output"],
            source: """
                uint dim = thread_position_in_grid.x;
                float accumulator = 0.0f;
                for (uint token = 0; token < SEQUENCE_LENGTH; token++) {
                    uint packedIndex = token * PACKED_DIMENSION + (dim >> 1);
                    int packed = packedValues[packedIndex];
                    int quantized = ((dim & 1) == 0) ? (packed & 0x0f) : ((packed >> 4) & 0x0f);
                    uint group = dim / GROUP_SIZE;
                    uint scaleIndex = token * GROUP_COUNT + group;
                    float value = float(quantized) * scales[scaleIndex] + biases[scaleIndex];
                    accumulator += weights[token] * value;
                }
                output[dim] = accumulator;
                """,
            ensureRowContiguous: true
        )
        let output = kernel(
            [packedValues, weights, scales, biases],
            template: [
                ("SEQUENCE_LENGTH", sequenceLength),
                ("HEAD_DIMENSION", headDimension),
                ("PACKED_DIMENSION", packedDimension),
                ("GROUP_SIZE", groupSize),
                ("GROUP_COUNT", groupCount),
            ],
            grid: (headDimension, 1, 1),
            threadGroup: (threadGroupSize, 1, 1),
            outputShapes: [[headDimension]],
            outputDTypes: [.float32]
        )
        return output[0]
    }

    static func runMSEQ4FusedAttentionSmokeKernel(
        query: MLXArray,
        packedKeys: MLXArray,
        keyScales: MLXArray,
        keyBiases: MLXArray,
        packedValues: MLXArray,
        valueScales: MLXArray,
        valueBiases: MLXArray,
        sequenceLength: Int,
        headDimension: Int,
        groupSize: Int
    ) -> MLXArray {
        precondition(sequenceLength > 0)
        precondition(headDimension > 0)
        precondition(groupSize > 0)

        let packedDimension = (headDimension + 1) / 2
        let groupCount = (headDimension + groupSize - 1) / groupSize
        let attentionScale = MLXArray([Float(1.0 / Double(headDimension).squareRoot())])
        let threadGroupSize = min(256, headDimension)
        let kernel = MLXFast.metalKernel(
            name: "melix_turboquant_mse_q4_fused_attention_smoke",
            inputNames: [
                "query",
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
                uint dim = thread_position_in_grid.x;
                float maxScore = -3.402823466e+38f;
                for (uint token = 0; token < SEQUENCE_LENGTH; token++) {
                    float dot = 0.0f;
                    for (uint keyDim = 0; keyDim < HEAD_DIMENSION; keyDim++) {
                        uint packedIndex = token * PACKED_DIMENSION + (keyDim >> 1);
                        int packed = packedKeys[packedIndex];
                        int quantized = ((keyDim & 1) == 0) ? (packed & 0x0f) : ((packed >> 4) & 0x0f);
                        uint group = keyDim / GROUP_SIZE;
                        uint scaleIndex = token * GROUP_COUNT + group;
                        float keyValue = float(quantized) * keyScales[scaleIndex] + keyBiases[scaleIndex];
                        dot += query[keyDim] * keyValue;
                    }
                    float score = dot * attentionScale[0];
                    maxScore = score > maxScore ? score : maxScore;
                }

                float normalizer = 0.0f;
                float accumulator = 0.0f;
                for (uint token = 0; token < SEQUENCE_LENGTH; token++) {
                    float dot = 0.0f;
                    for (uint keyDim = 0; keyDim < HEAD_DIMENSION; keyDim++) {
                        uint keyPackedIndex = token * PACKED_DIMENSION + (keyDim >> 1);
                        int keyPacked = packedKeys[keyPackedIndex];
                        int keyQuantized = ((keyDim & 1) == 0) ? (keyPacked & 0x0f) : ((keyPacked >> 4) & 0x0f);
                        uint keyGroup = keyDim / GROUP_SIZE;
                        uint keyScaleIndex = token * GROUP_COUNT + keyGroup;
                        float keyValue = float(keyQuantized) * keyScales[keyScaleIndex] + keyBiases[keyScaleIndex];
                        dot += query[keyDim] * keyValue;
                    }

                    float score = dot * attentionScale[0];
                    float weight = exp(score - maxScore);
                    normalizer += weight;

                    uint valuePackedIndex = token * PACKED_DIMENSION + (dim >> 1);
                    int valuePacked = packedValues[valuePackedIndex];
                    int valueQuantized = ((dim & 1) == 0) ? (valuePacked & 0x0f) : ((valuePacked >> 4) & 0x0f);
                    uint valueGroup = dim / GROUP_SIZE;
                    uint valueScaleIndex = token * GROUP_COUNT + valueGroup;
                    float value = float(valueQuantized) * valueScales[valueScaleIndex] + valueBiases[valueScaleIndex];
                    accumulator += weight * value;
                }
                output[dim] = accumulator / normalizer;
                """,
            ensureRowContiguous: true
        )
        let output = kernel(
            [
                query,
                packedKeys,
                keyScales,
                keyBiases,
                packedValues,
                valueScales,
                valueBiases,
                attentionScale,
            ],
            template: [
                ("SEQUENCE_LENGTH", sequenceLength),
                ("HEAD_DIMENSION", headDimension),
                ("PACKED_DIMENSION", packedDimension),
                ("GROUP_SIZE", groupSize),
                ("GROUP_COUNT", groupCount),
            ],
            grid: (headDimension, 1, 1),
            threadGroup: (threadGroupSize, 1, 1),
            outputShapes: [[headDimension]],
            outputDTypes: [.float32]
        )
        return output[0]
    }

    static func runMSEQ4FusedAttentionKernelFromQuantizedState(
        query: MLXArray,
        quantizedKeys: (MLXArray, MLXArray, MLXArray?),
        quantizedValues: (MLXArray, MLXArray, MLXArray?),
        batchIndex: Int = 0,
        headIndex: Int = 0,
        sequenceLength: Int,
        headDimension: Int,
        groupSize: Int,
        bits: Int
    ) -> MLXArray? {
        guard bits == 4 else {
            return nil
        }
        guard let keyBiases = quantizedKeys.2, let valueBiases = quantizedValues.2 else {
            return nil
        }
        guard sequenceLength > 0, headDimension > 0, groupSize > 0 else {
            return nil
        }
        guard headDimension % 8 == 0 else {
            return nil
        }
        guard quantizedKeys.0.dtype == DType.uint32, quantizedValues.0.dtype == DType.uint32 else {
            return nil
        }
        guard quantizedKeys.0.shape.count >= 4, quantizedValues.0.shape.count >= 4 else {
            return nil
        }
        guard quantizedKeys.0.dim(0) > batchIndex, quantizedValues.0.dim(0) > batchIndex else {
            return nil
        }
        guard quantizedKeys.0.dim(1) > headIndex, quantizedValues.0.dim(1) > headIndex else {
            return nil
        }
        guard quantizedKeys.0.dim(2) >= sequenceLength, quantizedValues.0.dim(2) >= sequenceLength else {
            return nil
        }

        let packedWordsPerToken = headDimension / 8
        let groupCount = (headDimension + groupSize - 1) / groupSize
        guard quantizedKeys.0.dim(3) >= packedWordsPerToken,
              quantizedValues.0.dim(3) >= packedWordsPerToken,
              quantizedKeys.1.dim(3) >= groupCount,
              quantizedValues.1.dim(3) >= groupCount,
              keyBiases.dim(3) >= groupCount,
              valueBiases.dim(3) >= groupCount
        else {
            return nil
        }

        let packedKeySlice = quantizedKeys.0[
            batchIndex, headIndex, ..<sequenceLength, 0 ..< packedWordsPerToken]
        let keyScaleSlice = quantizedKeys.1[
            batchIndex, headIndex, ..<sequenceLength, 0 ..< groupCount]
        let keyBiasSlice = keyBiases[
            batchIndex, headIndex, ..<sequenceLength, 0 ..< groupCount]
        let packedValueSlice = quantizedValues.0[
            batchIndex, headIndex, ..<sequenceLength, 0 ..< packedWordsPerToken]
        let valueScaleSlice = quantizedValues.1[
            batchIndex, headIndex, ..<sequenceLength, 0 ..< groupCount]
        let valueBiasSlice = valueBiases[
            batchIndex, headIndex, ..<sequenceLength, 0 ..< groupCount]

        return runMSEQ4FusedAttentionMLXQuantizedStateKernel(
            query: query,
            packedKeys: packedKeySlice,
            keyScales: keyScaleSlice,
            keyBiases: keyBiasSlice,
            packedValues: packedValueSlice,
            valueScales: valueScaleSlice,
            valueBiases: valueBiasSlice,
            sequenceLength: sequenceLength,
            headDimension: headDimension,
            groupSize: groupSize
        )
    }

    private static func runMSEQ4FusedAttentionMLXQuantizedStateKernel(
        query: MLXArray,
        packedKeys: MLXArray,
        keyScales: MLXArray,
        keyBiases: MLXArray,
        packedValues: MLXArray,
        valueScales: MLXArray,
        valueBiases: MLXArray,
        sequenceLength: Int,
        headDimension: Int,
        groupSize: Int
    ) -> MLXArray {
        let packedWordsPerToken = headDimension / 8
        let groupCount = (headDimension + groupSize - 1) / groupSize
        let attentionScale = MLXArray([Float(1.0 / Double(headDimension).squareRoot())])
        let threadGroupSize = min(256, headDimension)
        let kernel = MLXFast.metalKernel(
            name: "melix_turboquant_mse_q4_fused_attention_mlx_quantized_state",
            inputNames: [
                "query",
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
                uint dim = thread_position_in_grid.x;
                float maxScore = -3.402823466e+38f;
                for (uint token = 0; token < SEQUENCE_LENGTH; token++) {
                    float dot = 0.0f;
                    for (uint keyDim = 0; keyDim < HEAD_DIMENSION; keyDim++) {
                        uint wordIndex = token * PACKED_WORDS_PER_TOKEN + (keyDim >> 3);
                        uint word = packedKeys[wordIndex];
                        uint byteShift = ((keyDim >> 1) & 0x3) << 3;
                        uint packedByte = (word >> byteShift) & 0xff;
                        uint quantized = ((keyDim & 1) == 0) ? (packedByte & 0x0f) : ((packedByte >> 4) & 0x0f);
                        uint group = keyDim / GROUP_SIZE;
                        uint scaleIndex = token * GROUP_COUNT + group;
                        float keyValue = float(quantized) * keyScales[scaleIndex] + keyBiases[scaleIndex];
                        dot += query[keyDim] * keyValue;
                    }
                    float score = dot * attentionScale[0];
                    maxScore = score > maxScore ? score : maxScore;
                }

                float normalizer = 0.0f;
                float accumulator = 0.0f;
                for (uint token = 0; token < SEQUENCE_LENGTH; token++) {
                    float dot = 0.0f;
                    for (uint keyDim = 0; keyDim < HEAD_DIMENSION; keyDim++) {
                        uint keyWordIndex = token * PACKED_WORDS_PER_TOKEN + (keyDim >> 3);
                        uint keyWord = packedKeys[keyWordIndex];
                        uint keyByteShift = ((keyDim >> 1) & 0x3) << 3;
                        uint keyPackedByte = (keyWord >> keyByteShift) & 0xff;
                        uint keyQuantized = ((keyDim & 1) == 0) ? (keyPackedByte & 0x0f) : ((keyPackedByte >> 4) & 0x0f);
                        uint keyGroup = keyDim / GROUP_SIZE;
                        uint keyScaleIndex = token * GROUP_COUNT + keyGroup;
                        float keyValue = float(keyQuantized) * keyScales[keyScaleIndex] + keyBiases[keyScaleIndex];
                        dot += query[keyDim] * keyValue;
                    }

                    float score = dot * attentionScale[0];
                    float weight = exp(score - maxScore);
                    normalizer += weight;

                    uint valueWordIndex = token * PACKED_WORDS_PER_TOKEN + (dim >> 3);
                    uint valueWord = packedValues[valueWordIndex];
                    uint valueByteShift = ((dim >> 1) & 0x3) << 3;
                    uint valuePackedByte = (valueWord >> valueByteShift) & 0xff;
                    uint valueQuantized = ((dim & 1) == 0) ? (valuePackedByte & 0x0f) : ((valuePackedByte >> 4) & 0x0f);
                    uint valueGroup = dim / GROUP_SIZE;
                    uint valueScaleIndex = token * GROUP_COUNT + valueGroup;
                    float value = float(valueQuantized) * valueScales[valueScaleIndex] + valueBiases[valueScaleIndex];
                    accumulator += weight * value;
                }
                output[dim] = accumulator / normalizer;
                """,
            ensureRowContiguous: true
        )
        let output = kernel(
            [
                query,
                packedKeys,
                keyScales,
                keyBiases,
                packedValues,
                valueScales,
                valueBiases,
                attentionScale,
            ],
            template: [
                ("SEQUENCE_LENGTH", sequenceLength),
                ("HEAD_DIMENSION", headDimension),
                ("PACKED_WORDS_PER_TOKEN", packedWordsPerToken),
                ("GROUP_SIZE", groupSize),
                ("GROUP_COUNT", groupCount),
            ],
            grid: (headDimension, 1, 1),
            threadGroup: (threadGroupSize, 1, 1),
            outputShapes: [[headDimension]],
            outputDTypes: [.float32]
        )
        return output[0]
    }
}
#endif
