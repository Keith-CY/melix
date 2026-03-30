import Foundation
import MelixControlPlaneProtocol

public enum ChatTemplatePolicyError: Error, Equatable {
    case kwargsMustBeJSONObject(String)
    case invalidModelSettingsJSON(String)

    public var operatorMessage: String {
        switch self {
        case let .kwargsMustBeJSONObject(field):
            return "\(field) must be a JSON object."
        case let .invalidModelSettingsJSON(field):
            return "Model setting \(field) must contain valid JSON."
        }
    }
}

public struct ChatTemplateSelection: Sendable, Equatable {
    public let values: [String: StructuredJSONValue]
    public let source: String

    public init(
        values: [String: StructuredJSONValue],
        source: String
    ) {
        self.values = values
        self.source = source
    }
}

public struct ModelChatTemplatePolicy: Sendable, Equatable {
    public let modelValues: [String: StructuredJSONValue]
    public let forcedValues: [String: StructuredJSONValue]

    public init?(
        modelSettings: Melix_Controlplane_V1_ModelSettings
    ) throws {
        let modelValues = try Self.parseJSONValue(
            modelSettings.ext["chat_template_kwargs"],
            field: "chat_template_kwargs"
        )
        let forcedValues = try Self.parseJSONValue(
            modelSettings.ext["chat_template_forced_kwargs"],
            field: "chat_template_forced_kwargs"
        )

        guard !modelValues.isEmpty || !forcedValues.isEmpty else {
            return nil
        }

        self.modelValues = modelValues
        self.forcedValues = forcedValues
    }

    private static func parseJSONValue(
        _ rawValue: String?,
        field: String
    ) throws -> [String: StructuredJSONValue] {
        guard let rawValue else {
            return [:]
        }
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return [:]
        }

        let value: StructuredJSONValue
        do {
            value = try StructuredJSONValue.parse(text: trimmed)
        } catch {
            throw ChatTemplatePolicyError.invalidModelSettingsJSON(field)
        }

        guard case let .object(object) = value else {
            throw ChatTemplatePolicyError.kwargsMustBeJSONObject(field)
        }
        return object
    }
}

public struct ResolvedChatTemplatePolicy: Sendable, Equatable {
    public let effectiveValues: [String: StructuredJSONValue]
    public let source: String
    public let modelValues: [String: StructuredJSONValue]
    public let requestValues: [String: StructuredJSONValue]
    public let forcedValues: [String: StructuredJSONValue]

    public init(
        effectiveValues: [String: StructuredJSONValue],
        source: String,
        modelValues: [String: StructuredJSONValue] = [:],
        requestValues: [String: StructuredJSONValue] = [:],
        forcedValues: [String: StructuredJSONValue] = [:]
    ) {
        self.effectiveValues = effectiveValues
        self.source = source
        self.modelValues = modelValues
        self.requestValues = requestValues
        self.forcedValues = forcedValues
    }

    public var forcedKeys: [String] {
        forcedValues.keys.sorted()
    }

    var effectiveJSONString: String? {
        jsonString(for: effectiveValues)
    }

    var modelJSONString: String? {
        jsonString(for: modelValues)
    }

    var requestJSONString: String? {
        jsonString(for: requestValues)
    }

    var forcedJSONString: String? {
        jsonString(for: forcedValues)
    }

    var continueFinalMessageEnabled: Bool {
        guard case let .bool(enabled)? = effectiveValues["continue_final_message"] else {
            return false
        }
        return enabled
    }

    private func jsonString(
        for values: [String: StructuredJSONValue]
    ) -> String? {
        guard !values.isEmpty else {
            return nil
        }
        return try? StructuredJSONValue.object(values).canonicalJSONString()
    }
}

public struct ChatTemplateRequestConfiguration: Codable, Sendable, Equatable {
    public let values: [String: StructuredJSONValue]

    public init(values: [String: StructuredJSONValue]) {
        self.values = values
    }

    public init(from decoder: Decoder) throws {
        let value = try StructuredJSONValue(from: decoder)
        guard case let .object(object) = value else {
            throw ChatTemplatePolicyError.kwargsMustBeJSONObject("chat_template_kwargs")
        }
        self.values = object
    }

    public func encode(to encoder: Encoder) throws {
        try StructuredJSONValue.object(values).encode(to: encoder)
    }

    public func resolvedSelection() -> ChatTemplateSelection {
        ChatTemplateSelection(values: values, source: "request")
    }
}

public struct ChatTemplatePolicyRegistry: Sendable {
    public init() {}

    func resolve(
        requested: ChatTemplateSelection?,
        modelPolicy: ModelChatTemplatePolicy?
    ) -> ResolvedChatTemplatePolicy? {
        let modelValues = modelPolicy?.modelValues ?? [:]
        let requestValues = requested?.values ?? [:]
        let forcedValues = modelPolicy?.forcedValues ?? [:]

        guard !modelValues.isEmpty || !requestValues.isEmpty || !forcedValues.isEmpty else {
            return nil
        }

        var effectiveValues = modelValues
        for (key, value) in requestValues {
            effectiveValues[key] = value
        }
        for (key, value) in forcedValues {
            effectiveValues[key] = value
        }

        let source = [
            modelValues.isEmpty ? nil : "model",
            requestValues.isEmpty ? nil : requested?.source ?? "request",
            forcedValues.isEmpty ? nil : "forced",
        ]
        .compactMap { $0 }
        .joined(separator: "+")

        return ResolvedChatTemplatePolicy(
            effectiveValues: effectiveValues,
            source: source,
            modelValues: modelValues,
            requestValues: requestValues,
            forcedValues: forcedValues
        )
    }
}
