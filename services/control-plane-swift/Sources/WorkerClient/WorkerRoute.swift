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

    public init?(metadataIdentifier rawValue: String?) {
        guard let rawValue else {
            return nil
        }
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch normalized {
        case "python_text_compatibility":
            self = .pythonCompatibility
        default:
            self.init(rawValue: normalized)
        }
    }

    public init?(capabilityIdentifier rawValue: String?) {
        guard let rawValue else {
            return nil
        }
        switch rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "text":
            self = .swiftText
        case "embedding":
            self = .pythonEmbedding
        case "rerank":
            self = .pythonRerank
        case "model_operations", "model_ops":
            self = .pythonModelOperations
        case "ocr":
            self = .pythonOCR
        case "vlm":
            self = .pythonVLM
        case "transcription":
            self = .pythonTranscription
        case "speech":
            self = .pythonSpeech
        case "image_generation", "image":
            self = .pythonImage
        default:
            return nil
        }
    }

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

    public var routeClass: Melix_Controlplane_V1_WorkerRouteClass {
        switch self {
        case .swiftText:
            return .workerRouteSwiftText
        case .pythonCompatibility:
            return .workerRoutePythonTextCompatibility
        case .pythonEmbedding:
            return .workerRoutePythonEmbedding
        case .pythonRerank:
            return .workerRoutePythonRerank
        case .pythonModelOperations:
            return .workerRoutePythonModelOperations
        case .pythonOCR:
            return .workerRoutePythonOcr
        case .pythonVLM:
            return .workerRoutePythonVlm
        case .pythonTranscription:
            return .workerRoutePythonTranscription
        case .pythonSpeech:
            return .workerRoutePythonSpeech
        case .pythonImage:
            return .workerRoutePythonImage
        }
    }

    public var metadataIdentifier: String {
        switch self {
        case .pythonCompatibility:
            return "python_text_compatibility"
        default:
            return rawValue
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
        case .swiftText:
            return true
        default:
            return false
        }
    }

    public var supportsPhaseAwareExecution: Bool {
        switch self {
        case .swiftText, .pythonVLM:
            return true
        default:
            return false
        }
    }
}
