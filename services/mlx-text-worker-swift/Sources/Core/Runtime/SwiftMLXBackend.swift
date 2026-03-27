import Foundation
import MelixWorkerProtocol

#if canImport(MLXLMCommon)
import MLXLMCommon
#endif

struct RuntimeUnavailableError: LocalizedError {
    let message: String

    var errorDescription: String? {
        message
    }
}

struct AutoSwiftMLXBackend: TextRuntimeBackend {
    let runtimeName: String
    private let loader: @Sendable (String) async throws -> LoadedTextModel

    init(
        runtimeName: String? = nil,
        loader: (@Sendable (String) async throws -> Any)? = nil
    ) {
        if let loader {
            self.loader = { modelSource in
                LoadedTextModel(storage: try await loader(modelSource))
            }
        } else {
            #if canImport(MLXLMCommon)
            self.loader = { modelSource in
                LoadedTextModel(storage: try await MLXLMCommon.loadModel(id: modelSource))
            }
            #else
            self.loader = { _ in
                throw RuntimeUnavailableError(
                    message: "MLXLMCommon is not available in this build. Install the Swift MLX runtime dependencies before loading models."
                )
            }
            #endif
        }

        if let runtimeName {
            self.runtimeName = runtimeName
            return
        }

        #if canImport(MLXLMCommon)
        self.runtimeName = "mlx-swift-lm"
        #else
        self.runtimeName = "swift-mlx-unavailable"
        #endif
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        let modelSource = spec.modelPath.isEmpty ? spec.modelID : spec.modelPath
        return try await loader(modelSource)
    }
}
