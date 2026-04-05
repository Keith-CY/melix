import Foundation
import MelixControlPlaneProtocol

public enum ImageDefaultsValidationError: Error, Equatable, Sendable {
    case invalidSize
    case invalidSteps
    case invalidGuidance
    case invalidStrength
    case unsupportedGenerateModel
    case unsupportedEditModel

    public var code: String {
        switch self {
        case .invalidSize:
            return "invalid_image_size"
        case .invalidSteps:
            return "invalid_image_steps"
        case .invalidGuidance:
            return "invalid_image_guidance"
        case .invalidStrength:
            return "invalid_image_strength"
        case .unsupportedGenerateModel:
            return "unsupported_image_generate_model"
        case .unsupportedEditModel:
            return "unsupported_image_edit_model"
        }
    }

    public var message: String {
        switch self {
        case .invalidSize:
            return "Image defaults require a WIDTHxHEIGHT size."
        case .invalidSteps:
            return "Image defaults require a positive step count."
        case .invalidGuidance:
            return "Image defaults require a non-negative guidance value."
        case .invalidStrength:
            return "Image defaults require strength to be greater than 0 and at most 1."
        case .unsupportedGenerateModel:
            return "The selected generate model does not support image generation."
        case .unsupportedEditModel:
            return "The selected edit model does not support image editing."
        }
    }
}

public struct ImageDefaultsPolicy: Equatable, Sendable {
    public let generateModelID: String
    public let editModelID: String
    public let size: String
    public let steps: UInt32
    public let guidance: Float
    public let strength: Float
    public let negativePrompt: String
    public let source: Melix_Controlplane_V1_ImageDefaultsSource
    public let updatedAtUnixMS: Int64

    public init(
        generateModelID: String,
        editModelID: String,
        size: String,
        steps: UInt32,
        guidance: Float,
        strength: Float,
        negativePrompt: String,
        source: Melix_Controlplane_V1_ImageDefaultsSource,
        updatedAtUnixMS: Int64
    ) {
        self.generateModelID = generateModelID
        self.editModelID = editModelID
        self.size = size
        self.steps = steps
        self.guidance = guidance
        self.strength = strength
        self.negativePrompt = negativePrompt
        self.source = source
        self.updatedAtUnixMS = updatedAtUnixMS
    }
}

private struct ImageDefaultsResolvedDefaults: Equatable, Sendable {
    let requestedGenerateModelID: String
    let requestedEditModelID: String
    let requestedSize: String
    let requestedSteps: UInt32
    let requestedGuidance: Float
    let requestedStrength: Float
    let requestedNegativePrompt: String
    let effectiveGenerateModelID: String
    let effectiveEditModelID: String
    let effectiveSize: String
    let effectiveSteps: UInt32
    let effectiveGuidance: Float
    let effectiveStrength: Float
    let effectiveNegativePrompt: String
    let source: Melix_Controlplane_V1_ImageDefaultsSource
    let updatedAtUnixMS: Int64
}

private struct PersistedImageDefaultsRecord: Codable, Equatable, Sendable {
    let generateModelID: String
    let editModelID: String
    let size: String
    let steps: UInt32
    let guidance: Float
    let strength: Float
    let negativePrompt: String
    let sourceRawValue: Int
    let updatedAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case generateModelID = "generate_model_id"
        case editModelID = "edit_model_id"
        case size
        case steps
        case guidance
        case strength
        case negativePrompt = "negative_prompt"
        case sourceRawValue = "source"
        case updatedAtUnixMS = "updated_at_unix_ms"
    }

    var source: Melix_Controlplane_V1_ImageDefaultsSource {
        Melix_Controlplane_V1_ImageDefaultsSource(rawValue: sourceRawValue) ?? .operatorOverride
    }
}

private struct ImageDefaultsDocument: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let record: PersistedImageDefaultsRecord?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case record
    }
}

public actor ImageDefaultsStore {
    private let storeURL: URL
    private let fileManager: FileManager
    private let nowUnixMS: @Sendable () -> Int64
    private let defaults: PersistedImageDefaultsRecord
    private var record: PersistedImageDefaultsRecord?

    public init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        nowUnixMS: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.fileManager = fileManager
        self.nowUnixMS = nowUnixMS
        self.storeURL = Self.resolveStoreURL(environment: environment, fileManager: fileManager)
        self.defaults = Self.resolveDefaults(environment: environment)
        self.record = Self.loadRecord(from: self.storeURL, fileManager: fileManager)
    }

    public init(
        storeURL: URL,
        defaults: [String: String],
        fileManager: FileManager = .default,
        nowUnixMS: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.fileManager = fileManager
        self.nowUnixMS = nowUnixMS
        self.storeURL = storeURL
        self.defaults = Self.resolveDefaults(environment: defaults)
        self.record = Self.loadRecord(from: storeURL, fileManager: fileManager)
    }

    public func storePath() -> String {
        storeURL.path
    }

    public func apply(
        command: Melix_Controlplane_V1_ApplyImageDefaults,
        models: [Melix_Controlplane_V1_ModelSummary]
    ) throws {
        let generateModelID = command.generateModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let editModelID = command.editModelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let size = command.size.trimmingCharacters(in: .whitespacesAndNewlines)
        let negativePrompt = command.negativePrompt.trimmingCharacters(in: .whitespacesAndNewlines)

        guard Self.isValidImageSize(size) else {
            throw ImageDefaultsValidationError.invalidSize
        }
        guard command.steps > 0 else {
            throw ImageDefaultsValidationError.invalidSteps
        }
        guard command.guidance >= 0 else {
            throw ImageDefaultsValidationError.invalidGuidance
        }
        guard command.strength > 0, command.strength <= 1 else {
            throw ImageDefaultsValidationError.invalidStrength
        }
        if generateModelID.isEmpty == false && Self.supportsImageRole(.generate, modelID: generateModelID, models: models) == false {
            throw ImageDefaultsValidationError.unsupportedGenerateModel
        }
        if editModelID.isEmpty == false && Self.supportsImageRole(.edit, modelID: editModelID, models: models) == false {
            throw ImageDefaultsValidationError.unsupportedEditModel
        }

        let updated = PersistedImageDefaultsRecord(
            generateModelID: generateModelID,
            editModelID: editModelID,
            size: size,
            steps: command.steps,
            guidance: command.guidance,
            strength: command.strength,
            negativePrompt: negativePrompt,
            sourceRawValue: Melix_Controlplane_V1_ImageDefaultsSource.operatorOverride.rawValue,
            updatedAtUnixMS: nowUnixMS()
        )
        record = updated
        try persist()
    }

    public func resolvedDefaults(
        models: [Melix_Controlplane_V1_ModelSummary]
    ) -> ImageDefaultsPolicy {
        let resolved = Self.resolve(record: record, defaults: defaults, models: models)
        return ImageDefaultsPolicy(
            generateModelID: resolved.effectiveGenerateModelID,
            editModelID: resolved.effectiveEditModelID,
            size: resolved.effectiveSize,
            steps: resolved.effectiveSteps,
            guidance: resolved.effectiveGuidance,
            strength: resolved.effectiveStrength,
            negativePrompt: resolved.effectiveNegativePrompt,
            source: resolved.source,
            updatedAtUnixMS: resolved.updatedAtUnixMS
        )
    }

    public func summary(
        models: [Melix_Controlplane_V1_ModelSummary]
    ) -> Melix_Controlplane_V1_ImageDefaultsSummary {
        let resolved = Self.resolve(record: record, defaults: defaults, models: models)
        var summary = Melix_Controlplane_V1_ImageDefaultsSummary()
        summary.requestedGenerateModelID = resolved.requestedGenerateModelID
        summary.requestedEditModelID = resolved.requestedEditModelID
        summary.requestedSize = resolved.requestedSize
        summary.requestedSteps = resolved.requestedSteps
        summary.requestedGuidance = resolved.requestedGuidance
        summary.requestedStrength = resolved.requestedStrength
        summary.requestedNegativePrompt = resolved.requestedNegativePrompt
        summary.effectiveGenerateModelID = resolved.effectiveGenerateModelID
        summary.effectiveEditModelID = resolved.effectiveEditModelID
        summary.effectiveSize = resolved.effectiveSize
        summary.effectiveSteps = resolved.effectiveSteps
        summary.effectiveGuidance = resolved.effectiveGuidance
        summary.effectiveStrength = resolved.effectiveStrength
        summary.effectiveNegativePrompt = resolved.effectiveNegativePrompt
        summary.source = resolved.source
        summary.updatedAtUnixMs = resolved.updatedAtUnixMS
        return summary
    }

    private func persist() throws {
        let document = ImageDefaultsDocument(schemaVersion: 1, record: record)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(document)
        if fileManager.fileExists(atPath: storeURL.deletingLastPathComponent().path) == false {
            try fileManager.createDirectory(
                at: storeURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
        }
        try data.write(to: storeURL, options: [.atomic])
    }

    private static func resolve(
        record: PersistedImageDefaultsRecord?,
        defaults: PersistedImageDefaultsRecord,
        models: [Melix_Controlplane_V1_ModelSummary]
    ) -> ImageDefaultsResolvedDefaults {
        let requested = record ?? defaults
        let source = record?.source ?? defaults.source
        let requestedGenerateModelID = requested.generateModelID
        let requestedEditModelID = requested.editModelID
        let effectiveGenerateModelID = resolveModelID(
            role: .generate,
            requestedModelID: requestedGenerateModelID,
            models: models
        )
        let effectiveEditModelID = resolveModelID(
            role: .edit,
            requestedModelID: requestedEditModelID,
            models: models
        )
        let generateModelDefaults = models.first(where: { $0.modelID == effectiveGenerateModelID }).map(modelDefaults)
        let editModelDefaults = models.first(where: { $0.modelID == effectiveEditModelID }).map(modelDefaults)

        return ImageDefaultsResolvedDefaults(
            requestedGenerateModelID: requestedGenerateModelID,
            requestedEditModelID: requestedEditModelID,
            requestedSize: requested.size,
            requestedSteps: requested.steps,
            requestedGuidance: requested.guidance,
            requestedStrength: requested.strength,
            requestedNegativePrompt: requested.negativePrompt,
            effectiveGenerateModelID: effectiveGenerateModelID,
            effectiveEditModelID: effectiveEditModelID,
            effectiveSize: requested.size.isEmpty ? (generateModelDefaults?.size ?? defaults.size) : requested.size,
            effectiveSteps: requested.steps == 0 ? (generateModelDefaults?.steps ?? defaults.steps) : requested.steps,
            effectiveGuidance: requested.guidance == 0 ? (generateModelDefaults?.guidance ?? defaults.guidance) : requested.guidance,
            effectiveStrength: requested.strength == 0 ? (editModelDefaults?.strength ?? defaults.strength) : requested.strength,
            effectiveNegativePrompt: requested.negativePrompt.isEmpty
                ? (generateModelDefaults?.negativePrompt ?? defaults.negativePrompt)
                : requested.negativePrompt,
            source: source,
            updatedAtUnixMS: record?.updatedAtUnixMS ?? 0
        )
    }

    private static func resolveModelID(
        role: RuntimeImageRole,
        requestedModelID: String,
        models: [Melix_Controlplane_V1_ModelSummary]
    ) -> String {
        if requestedModelID.isEmpty == false,
           supportsImageRole(role, modelID: requestedModelID, models: models) {
            return requestedModelID
        }

        return models
            .filter { supportsImageRole(role, model: $0) }
            .sorted {
                let lhsDefault = defaultWorkflowRole($0) == role
                let rhsDefault = defaultWorkflowRole($1) == role
                if lhsDefault != rhsDefault {
                    return lhsDefault && !rhsDefault
                }
                return $0.modelID < $1.modelID
            }
            .first?
            .modelID ?? ""
    }

    private static func supportsImageRole(
        _ role: RuntimeImageRole,
        modelID: String,
        models: [Melix_Controlplane_V1_ModelSummary]
    ) -> Bool {
        guard let model = models.first(where: { $0.modelID == modelID }) else {
            return false
        }
        return supportsImageRole(role, model: model)
    }

    private static func supportsImageRole(
        _ role: RuntimeImageRole,
        model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        guard model.kind == "image" || model.kind == "image_generation" else {
            return false
        }
        switch role {
        case .generate:
            if let explicit = explicitBool(model.settings.ext["melix.image.supports_generation"]) {
                return explicit
            }
            return model.supportedTasks.contains("image_generate")
                || model.settings.ext["melix.image.task_kind"]?.lowercased() != "image-text-to-image"
        case .edit:
            if let explicit = explicitBool(model.settings.ext["melix.image.supports_edit"]) {
                return explicit
            }
            return model.supportedTasks.contains("image_edit")
                || model.settings.ext["melix.image.task_kind"]?.lowercased() == "image-text-to-image"
        }
    }

    private static func explicitBool(_ rawValue: String?) -> Bool? {
        switch rawValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "true", "1", "yes", "on":
            return true
        case "false", "0", "no", "off":
            return false
        default:
            return nil
        }
    }

    private static func defaultWorkflowRole(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> RuntimeImageRole? {
        switch model.settings.ext["melix.image.default_workflow_role"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "generate":
            return .generate
        case "edit":
            return .edit
        default:
            return nil
        }
    }

    private static func modelDefaults(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> (size: String, steps: UInt32, guidance: Float, strength: Float, negativePrompt: String) {
        let ext = model.settings.ext
        let size = isValidImageSize(ext["melix.image.default_size"] ?? "") ? (ext["melix.image.default_size"] ?? "") : ""
        let steps = max(0, UInt32(ext["melix.image.default_steps"] ?? "") ?? 0)
        let guidance = Float(ext["melix.image.default_guidance"] ?? "") ?? 0
        let strength = Float(ext["melix.image.default_strength"] ?? "") ?? 0
        let negativePrompt = ext["melix.image.default_negative_prompt"] ?? ""
        return (size, steps, guidance, strength, negativePrompt)
    }

    private static func isValidImageSize(_ value: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let components = trimmed.split(separator: "x", maxSplits: 1)
        guard components.count == 2,
              let width = Int(components[0]),
              let height = Int(components[1]),
              width > 0,
              height > 0 else {
            return false
        }
        return true
    }

    private static func resolveStoreURL(
        environment: [String: String],
        fileManager: FileManager
    ) -> URL {
        if let explicit = environment["MELIX_IMAGE_DEFAULTS_STORE_PATH"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           explicit.isEmpty == false {
            return URL(fileURLWithPath: explicit)
        }
        let melixHomePath = environment["MELIX_HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        let melixHomeURL: URL
        if let melixHomePath, melixHomePath.isEmpty == false {
            melixHomeURL = URL(fileURLWithPath: melixHomePath, isDirectory: true)
        } else {
            let applicationSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
                ?? fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
            melixHomeURL = applicationSupport.appendingPathComponent("Melix", isDirectory: true)
        }
        return melixHomeURL.appendingPathComponent("state/image-defaults.json")
    }

    private static func resolveDefaults(
        environment: [String: String]
    ) -> PersistedImageDefaultsRecord {
        let size = isValidImageSize(environment["MELIX_IMAGE_DEFAULT_SIZE"] ?? "")
            ? environment["MELIX_IMAGE_DEFAULT_SIZE"]!.trimmingCharacters(in: .whitespacesAndNewlines)
            : "1024x1024"
        let steps = max(1, UInt32(environment["MELIX_IMAGE_DEFAULT_STEPS"] ?? "") ?? 28)
        let guidance = max(0, Float(environment["MELIX_IMAGE_DEFAULT_GUIDANCE"] ?? "") ?? 7.5)
        let strength = min(max(Float(environment["MELIX_IMAGE_DEFAULT_STRENGTH"] ?? "") ?? 1, 0.05), 1)
        let negativePrompt = environment["MELIX_IMAGE_DEFAULT_NEGATIVE_PROMPT"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let generateModelID = environment["MELIX_IMAGE_DEFAULT_GENERATE_MODEL_ID"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let editModelID = environment["MELIX_IMAGE_DEFAULT_EDIT_MODEL_ID"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let source: Melix_Controlplane_V1_ImageDefaultsSource =
            (environment["MELIX_IMAGE_DEFAULT_SIZE"] != nil
                || environment["MELIX_IMAGE_DEFAULT_STEPS"] != nil
                || environment["MELIX_IMAGE_DEFAULT_GUIDANCE"] != nil
                || environment["MELIX_IMAGE_DEFAULT_STRENGTH"] != nil
                || environment["MELIX_IMAGE_DEFAULT_NEGATIVE_PROMPT"] != nil
                || environment["MELIX_IMAGE_DEFAULT_GENERATE_MODEL_ID"] != nil
                || environment["MELIX_IMAGE_DEFAULT_EDIT_MODEL_ID"] != nil)
            ? .environmentDefaults
            : .builtInDefaults

        return PersistedImageDefaultsRecord(
            generateModelID: generateModelID,
            editModelID: editModelID,
            size: size,
            steps: steps,
            guidance: guidance,
            strength: strength,
            negativePrompt: negativePrompt,
            sourceRawValue: source.rawValue,
            updatedAtUnixMS: 0
        )
    }

    private static func loadRecord(
        from storeURL: URL,
        fileManager: FileManager
    ) -> PersistedImageDefaultsRecord? {
        guard fileManager.fileExists(atPath: storeURL.path),
              let data = try? Data(contentsOf: storeURL),
              let document = try? JSONDecoder().decode(ImageDefaultsDocument.self, from: data) else {
            return nil
        }
        return document.record
    }
}

private enum RuntimeImageRole: Sendable {
    case generate
    case edit
}
