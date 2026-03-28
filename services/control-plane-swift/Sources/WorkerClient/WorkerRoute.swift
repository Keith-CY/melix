import MelixControlPlaneProtocol

public enum WorkerRouteKind: String, Sendable, Equatable {
    case swiftText = "swift_text"
    case pythonCompatibility = "python_compatibility"
    case pythonEmbedding = "python_embedding"
    case pythonRerank = "python_rerank"
    case pythonModelOperations = "python_model_operations"

    public init?(routeClass: Melix_Controlplane_V1_WorkerRouteClass) {
        switch routeClass {
        case .workerRouteSwiftText:
            self = .swiftText
        case .workerRoutePythonTextCompatibility:
            self = .pythonCompatibility
        case .workerRoutePythonEmbedding:
            self = .pythonEmbedding
        case .workerRoutePythonRerank:
            self = .pythonRerank
        case .workerRoutePythonModelOperations:
            self = .pythonModelOperations
        default:
            return nil
        }
    }
}
