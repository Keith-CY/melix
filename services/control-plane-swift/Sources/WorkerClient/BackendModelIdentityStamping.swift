import MelixWorkerProtocol

enum BackendModelIdentityStamping {
    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_GenerateRequest
    ) {
        request.execution.modelHandle = binding.handle
        request.execution.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_PrefillRequest
    ) {
        request.execution.modelHandle = binding.handle
        request.execution.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_DecodeRequest
    ) {
        request.execution.modelHandle = binding.handle
        request.execution.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_EmbedRequest
    ) {
        request.modelHandle = binding.handle
        request.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_RerankRequest
    ) {
        request.modelHandle = binding.handle
        request.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_TranscribeRequest
    ) {
        request.modelHandle = binding.handle
        request.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_SpeakRequest
    ) {
        request.modelHandle = binding.handle
        request.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_ImageGenerateRequest
    ) {
        request.modelHandle = binding.handle
        request.backendIdentity = binding.identity
    }

    static func stamp(
        _ binding: ModelCatalog.BackendRouteBinding,
        on request: inout Melix_Worker_V1_ImageEditRequest
    ) {
        request.modelHandle = binding.handle
        request.backendIdentity = binding.identity
    }
}
