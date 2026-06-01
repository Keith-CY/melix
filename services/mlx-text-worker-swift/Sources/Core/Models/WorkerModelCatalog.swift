import Foundation
import MelixWorkerProtocol

struct WorkerModelCatalog: Sendable {
    private let environment: [String: String]
    private let models: [String: Melix_Worker_V1_ModelSpec]

    init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        self.environment = environment
        let devTextModel = Self.devTextModel(environment: environment)
        let devVisionModel = Self.devVisionModel(environment: environment)
        let devOCRModel = Self.devOCRModel(environment: environment)
        self.models = [
            devTextModel.modelID: devTextModel,
            devVisionModel.modelID: devVisionModel,
            devOCRModel.modelID: devOCRModel,
        ]
    }

    func get(_ modelID: String) -> Melix_Worker_V1_ModelSpec? {
        models[modelID]
    }

    static func devTextModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-text"
        model.modelPath = environment["MELIX_DEV_TEXT_MODEL_PATH"] ?? "models/melix-dev-text"
        model.modelKind = "text"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev"
        model.quantProfileID = "q4"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8_192
        var route = Melix_Worker_V1_RequestRouteDeclaration()
        route.task = .generateText
        route.supportedModalities = [.text]
        route.workerFamily = .text
        route.modelFamilyTarget = "text.llama"
        route.residencyPolicy = .singleResidency
        model.requestRoutes = [route]
        return model
    }

    static func devVisionModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-vlm"
        model.modelPath = environment["MELIX_DEV_VLM_MODEL_PATH"] ?? "models/melix-dev-vlm"
        model.modelKind = "vlm"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev-vlm"
        model.quantProfileID = "q4"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8_192
        var route = Melix_Worker_V1_RequestRouteDeclaration()
        route.task = .generateMultimodal
        route.supportedModalities = [.text, .image, .video]
        route.requiresAnyModality = [.image, .video]
        route.supportsNativeVideo = true
        route.workerFamily = .vision
        route.modelFamilyTarget = "vision.llava-v1"
        route.residencyPolicy = .allowMultiResidency
        model.requestRoutes = [route]
        return model
    }

    static func devOCRModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-ocr"
        model.modelPath = environment["MELIX_DEV_OCR_MODEL_PATH"] ?? "models/melix-dev-ocr"
        model.modelKind = "ocr"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev-ocr"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4_096
        model.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.ext["ocr_prompt_template"] = "OCR instruction: {prompt}"
        model.ext["ocr_auto_prompt"] = "Extract the text from the image exactly as written."
        model.ext["ocr_stop_sequences"] = "<ocr:end>"
        model.ext["ocr_sampling_profile_id"] = "ocr-deterministic"
        model.ext["ocr_default_temperature"] = "0.0"
        model.ext["ocr_default_top_p"] = "1.0"
        model.ext["ocr_default_max_tokens"] = "256"

        var route = Melix_Worker_V1_RequestRouteDeclaration()
        route.task = .generateMultimodal
        route.supportedModalities = [.text, .image]
        route.requiresAnyModality = [.image]
        route.workerFamily = .vision
        route.modelFamilyTarget = "vision.ocr-default"
        route.residencyPolicy = .singleResidency
        model.requestRoutes = [route]
        return model
    }
}
