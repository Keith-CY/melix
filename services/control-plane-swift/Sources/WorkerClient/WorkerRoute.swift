import MelixControlPlaneProtocol

public enum WorkerRouteKind: String, Sendable, Equatable {
    case swiftText = "swift_text"
    case pythonCompatibility = "python_compatibility"
    case pythonEmbedding = "python_embedding"
    case pythonRerank = "python_rerank"
    case pythonModelOperations = "python_model_operations"
    case pythonOCR = "python_ocr"
    case pythonVLM = "python_vlm"
    case pythonTranscription = "python_transcription"
    case pythonSpeech = "python_speech"

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
        case .workerRoutePythonOcr:
            self = .pythonOCR
        case .workerRoutePythonVlm:
            self = .pythonVLM
        case .workerRoutePythonTranscription:
            self = .pythonTranscription
        case .workerRoutePythonSpeech:
            self = .pythonSpeech
        default:
            return nil
        }
    }
}
