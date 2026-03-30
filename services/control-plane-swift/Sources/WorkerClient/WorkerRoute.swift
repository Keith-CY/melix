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
    case pythonImage = "python_image"

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
        case .workerRoutePythonImage:
            self = .pythonImage
        default:
            return nil
        }
    }

    public var defaultSchedulingLane: String {
        switch self {
        case .pythonOCR, .pythonVLM:
            return "multimodal.vision.background"
        case .pythonTranscription:
            return "multimodal.audio.transcription.background"
        case .pythonSpeech:
            return "multimodal.audio.speech.background"
        case .pythonImage:
            return "image.generate.background"
        default:
            return "text.decode.interactive"
        }
    }

    public var workerSourceID: String {
        switch self {
        case .swiftText:
            return "swift-text-worker"
        case .pythonOCR, .pythonVLM, .pythonTranscription, .pythonSpeech:
            return "python-multimodal-worker"
        case .pythonImage:
            return "python-image-worker"
        default:
            return "python-worker"
        }
    }

    public var isMultimodalBackgroundRoute: Bool {
        switch self {
        case .pythonOCR, .pythonVLM, .pythonTranscription, .pythonSpeech, .pythonImage:
            return true
        default:
            return false
        }
    }

    public var isPhaseAwareTextRoute: Bool {
        switch self {
        case .swiftText, .pythonCompatibility:
            return true
        default:
            return false
        }
    }

    public var supportsPhaseAwareExecution: Bool {
        switch self {
        case .swiftText, .pythonCompatibility, .pythonVLM:
            return true
        default:
            return false
        }
    }
}
