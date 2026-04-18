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
}
#endif
