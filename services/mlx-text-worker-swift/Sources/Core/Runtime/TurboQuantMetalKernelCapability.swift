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
}
#endif
