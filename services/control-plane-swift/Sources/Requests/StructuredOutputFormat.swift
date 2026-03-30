import Foundation

public enum StructuredOutputMode: String, Codable, Sendable, Equatable {
    case text
    case jsonObject = "json_object"
    case jsonSchema = "json_schema"

    init(normalizedType: String) throws {
        switch normalizedType.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "", "text":
            self = .text
        case "json", "json_object":
            self = .jsonObject
        case "json_schema":
            self = .jsonSchema
        default:
            throw StructuredOutputFormatError.unsupportedType(normalizedType)
        }
    }
}

public enum StructuredOutputFormatError: Error, Equatable {
    case unsupportedType(String)
    case missingJSONSchemaDefinition
    case schemaRootMustBeObject

    public var operatorMessage: String {
        switch self {
        case let .unsupportedType(type):
            return "Unsupported structured output type: \(type)."
        case .missingJSONSchemaDefinition:
            return "response_format json_schema requests must include json_schema."
        case .schemaRootMustBeObject:
            return "response_format json_schema.schema must be a JSON object."
        }
    }
}

public enum StructuredJSONValue: Sendable, Codable, Equatable {
    case object([String: StructuredJSONValue])
    case array([StructuredJSONValue])
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let object = try? container.decode([String: StructuredJSONValue].self) {
            self = .object(object)
        } else if let array = try? container.decode([StructuredJSONValue].self) {
            self = .array(array)
        } else if let string = try? container.decode(String.self) {
            self = .string(string)
        } else if let bool = try? container.decode(Bool.self) {
            self = .bool(bool)
        } else if let number = try? container.decode(Double.self) {
            self = .number(number)
        } else if container.decodeNil() {
            self = .null
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value.")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case let .object(object):
            try container.encode(object)
        case let .array(array):
            try container.encode(array)
        case let .string(string):
            try container.encode(string)
        case let .number(number):
            try container.encode(number)
        case let .bool(bool):
            try container.encode(bool)
        case .null:
            try container.encodeNil()
        }
    }

    init(any value: Any) throws {
        switch value {
        case let value as [String: Any]:
            self = .object(try value.mapValues(StructuredJSONValue.init(any:)))
        case let value as [Any]:
            self = .array(try value.map(StructuredJSONValue.init(any:)))
        case let value as String:
            self = .string(value)
        case let value as Bool:
            self = .bool(value)
        case let value as NSNumber:
            if CFGetTypeID(value) == CFBooleanGetTypeID() {
                self = .bool(value.boolValue)
            } else {
                self = .number(value.doubleValue)
            }
        case _ as NSNull:
            self = .null
        default:
            throw StructuredOutputValidationFailure(
                code: "invalid_json_output",
                message: "Model output did not produce valid JSON.",
                details: ["reason": "Unsupported JSON root value."]
            )
        }
    }

    var jsonObject: Any {
        switch self {
        case let .object(object):
            object.mapValues(\.jsonObject)
        case let .array(array):
            array.map(\.jsonObject)
        case let .string(string):
            string
        case let .number(number):
            NSNumber(value: number)
        case let .bool(bool):
            bool
        case .null:
            NSNull()
        }
    }

    var objectValue: [String: StructuredJSONValue]? {
        guard case let .object(object) = self else {
            return nil
        }
        return object
    }

    var arrayValue: [StructuredJSONValue]? {
        guard case let .array(array) = self else {
            return nil
        }
        return array
    }

    var stringValue: String? {
        guard case let .string(string) = self else {
            return nil
        }
        return string
    }

    static func parse(text: String) throws -> StructuredJSONValue {
        let data = Data(text.utf8)
        let object: Any
        do {
            object = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw StructuredOutputValidationFailure(
                code: "invalid_json_output",
                message: "Model output did not produce valid JSON.",
                details: ["reason": error.localizedDescription]
            )
        }
        return try StructuredJSONValue(any: object)
    }

    func canonicalJSONString() throws -> String {
        let data = try JSONSerialization.data(withJSONObject: jsonObject, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }
}

public struct StructuredOutputJSONSchemaDefinition: Codable, Sendable, Equatable {
    public let name: String
    public let schema: StructuredJSONValue
    public let strict: Bool?

    enum CodingKeys: String, CodingKey {
        case name
        case schema
        case strict
    }

    public init(
        name: String,
        schema: StructuredJSONValue,
        strict: Bool? = nil
    ) {
        self.name = name
        self.schema = schema
        self.strict = strict
    }
}

public struct StructuredOutputRequestFormat: Codable, Sendable, Equatable {
    public let type: StructuredOutputMode
    public let jsonSchema: StructuredOutputJSONSchemaDefinition?

    enum CodingKeys: String, CodingKey {
        case type
        case jsonSchema = "json_schema"
    }

    public init(
        type: StructuredOutputMode,
        jsonSchema: StructuredOutputJSONSchemaDefinition? = nil
    ) {
        self.type = type
        self.jsonSchema = jsonSchema
    }

    public init(from decoder: Decoder) throws {
        let singleValue = try decoder.singleValueContainer()
        if let type = try? singleValue.decode(String.self) {
            self.type = try StructuredOutputMode(normalizedType: type)
            self.jsonSchema = nil
            return
        }

        let container = try decoder.container(keyedBy: CodingKeys.self)
        let rawType = try container.decode(String.self, forKey: .type)
        self.type = try StructuredOutputMode(normalizedType: rawType)
        self.jsonSchema = try container.decodeIfPresent(StructuredOutputJSONSchemaDefinition.self, forKey: .jsonSchema)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type.rawValue, forKey: .type)
        try container.encodeIfPresent(jsonSchema, forKey: .jsonSchema)
    }

    public func resolvedConfiguration() throws -> StructuredOutputConfiguration {
        switch type {
        case .text:
            return StructuredOutputConfiguration(mode: .text)
        case .jsonObject:
            return StructuredOutputConfiguration(mode: .jsonObject)
        case .jsonSchema:
            guard let jsonSchema else {
                throw StructuredOutputFormatError.missingJSONSchemaDefinition
            }
            guard jsonSchema.schema.objectValue != nil else {
                throw StructuredOutputFormatError.schemaRootMustBeObject
            }
            return StructuredOutputConfiguration(
                mode: .jsonSchema,
                schemaName: jsonSchema.name,
                schema: jsonSchema.schema,
                strict: jsonSchema.strict ?? false
            )
        }
    }
}

public struct StructuredOutputConfiguration: Sendable, Equatable {
    public let mode: StructuredOutputMode
    public let schemaName: String?
    public let schema: StructuredJSONValue?
    public let strict: Bool

    public init(
        mode: StructuredOutputMode,
        schemaName: String? = nil,
        schema: StructuredJSONValue? = nil,
        strict: Bool = false
    ) {
        self.mode = mode
        self.schemaName = schemaName?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            ? schemaName?.trimmingCharacters(in: .whitespacesAndNewlines)
            : nil
        self.schema = schema
        self.strict = strict
    }

    public var isEnabled: Bool {
        mode != .text
    }

    public var prefillHint: String {
        switch mode {
        case .text:
            ""
        case .jsonObject:
            "json-object"
        case .jsonSchema:
            "json-schema"
        }
    }

    public var schemaJSONString: String? {
        guard let schema else {
            return nil
        }
        return try? schema.canonicalJSONString()
    }

    init?(executionExt: [String: String]) {
        guard let rawMode = executionExt["melix.structured_output.mode"] else {
            return nil
        }
        guard let mode = try? StructuredOutputMode(normalizedType: rawMode) else {
            return nil
        }
        let schema: StructuredJSONValue?
        if let rawSchema = executionExt["melix.structured_output.schema_json"] {
            schema = try? StructuredJSONValue.parse(text: rawSchema)
        } else {
            schema = nil
        }
        let strict = executionExt["melix.structured_output.strict"] == "true"
        self.init(
            mode: mode,
            schemaName: executionExt["melix.structured_output.schema_name"],
            schema: schema,
            strict: strict
        )
    }
}

public struct StructuredOutputValidationFailure: Error, Sendable, Equatable {
    public let code: String
    public let message: String
    public let details: [String: String]

    public init(
        code: String,
        message: String,
        details: [String: String] = [:]
    ) {
        self.code = code
        self.message = message
        self.details = details
    }
}

public struct StructuredOutputValidator: Sendable {
    public init() {}

    public func validate(
        outputText: String,
        against configuration: StructuredOutputConfiguration
    ) throws {
        guard configuration.isEnabled else {
            return
        }

        let trimmed = outputText.trimmingCharacters(in: .whitespacesAndNewlines)
        // Allow tool-only terminal messages to complete without text payloads.
        guard !trimmed.isEmpty else {
            return
        }

        let value = try StructuredJSONValue.parse(text: trimmed)
        switch configuration.mode {
        case .text:
            return
        case .jsonObject:
            guard value.objectValue != nil else {
                throw StructuredOutputValidationFailure(
                    code: "invalid_json_output",
                    message: "Structured output requested a JSON object, but the model returned a different JSON value.",
                    details: [
                        "expected": "object",
                        "path": "$",
                    ]
                )
            }
        case .jsonSchema:
            guard let schema = configuration.schema else {
                throw StructuredOutputValidationFailure(
                    code: "schema_validation_failed",
                    message: "Structured output requested JSON Schema validation, but no schema was available.",
                    details: ["path": "$"]
                )
            }
            try validate(value: value, against: schema, path: "$", strict: configuration.strict)
        }
    }

    private func validate(
        value: StructuredJSONValue,
        against schema: StructuredJSONValue,
        path: String,
        strict: Bool
    ) throws {
        guard let schemaObject = schema.objectValue else {
            throw StructuredOutputValidationFailure(
                code: "schema_validation_failed",
                message: "Structured output schema at \(path) must be a JSON object.",
                details: ["path": path]
            )
        }

        if let constValue = schemaObject["const"], constValue != value {
            throw mismatch(path: path, reason: "Expected constant value \(describe(constValue)).")
        }

        if let enumValues = schemaObject["enum"]?.arrayValue,
           !enumValues.contains(value) {
            throw mismatch(path: path, reason: "Value must be one of the schema enum values.")
        }

        if let typeValue = schemaObject["type"] {
            let allowedTypes = try schemaTypes(from: typeValue, path: path)
            guard allowedTypes.contains(where: { matches(value: value, type: $0) }) else {
                throw mismatch(path: path, reason: "Expected \(allowedTypes.joined(separator: " or ")).")
            }
        }

        if let properties = schemaObject["properties"]?.objectValue {
            guard let object = value.objectValue else {
                throw mismatch(path: path, reason: "Expected object for schema properties.")
            }

            let required = Set(schemaObject["required"]?.arrayValue?.compactMap(\.stringValue) ?? [])
            for name in required where object[name] == nil {
                throw mismatch(path: path, reason: "Missing required property '\(name)'.")
            }

            for (name, propertySchema) in properties {
                guard let propertyValue = object[name] else {
                    continue
                }
                try validate(
                    value: propertyValue,
                    against: propertySchema,
                    path: "\(path).\(name)",
                    strict: strict
                )
            }

            let additionalProperties = schemaObject["additionalProperties"]
                ?? (strict ? .bool(false) : nil)
            let knownKeys = Set(properties.keys)
            for key in object.keys where !knownKeys.contains(key) {
                guard let additionalProperties else {
                    continue
                }
                switch additionalProperties {
                case .bool(true):
                    continue
                case .bool(false):
                    throw mismatch(path: "\(path).\(key)", reason: "Additional properties are not allowed.")
                default:
                    try validate(
                        value: object[key]!,
                        against: additionalProperties,
                        path: "\(path).\(key)",
                        strict: strict
                    )
                }
            }
        }

        if let items = schemaObject["items"] {
            guard let array = value.arrayValue else {
                throw mismatch(path: path, reason: "Expected array for schema items.")
            }
            for (index, item) in array.enumerated() {
                try validate(
                    value: item,
                    against: items,
                    path: "\(path)[\(index)]",
                    strict: strict
                )
            }
        }
    }

    private func schemaTypes(
        from value: StructuredJSONValue,
        path: String
    ) throws -> [String] {
        if let string = value.stringValue {
            return [string]
        }
        if let array = value.arrayValue {
            let values = array.compactMap(\.stringValue)
            guard values.count == array.count, !values.isEmpty else {
                throw mismatch(path: path, reason: "Schema type arrays must only contain strings.")
            }
            return values
        }
        throw mismatch(path: path, reason: "Schema type must be a string or array of strings.")
    }

    private func matches(
        value: StructuredJSONValue,
        type: String
    ) -> Bool {
        switch type {
        case "object":
            return value.objectValue != nil
        case "array":
            return value.arrayValue != nil
        case "string":
            return value.stringValue != nil
        case "number":
            if case .number = value {
                return true
            }
            return false
        case "integer":
            if case let .number(number) = value {
                return floor(number) == number
            }
            return false
        case "boolean":
            if case .bool = value {
                return true
            }
            return false
        case "null":
            if case .null = value {
                return true
            }
            return false
        default:
            return false
        }
    }

    private func mismatch(
        path: String,
        reason: String
    ) -> StructuredOutputValidationFailure {
        StructuredOutputValidationFailure(
            code: "schema_validation_failed",
            message: "Structured output failed JSON Schema validation at \(path): \(reason)",
            details: [
                "path": path,
                "reason": reason,
            ]
        )
    }

    private func describe(_ value: StructuredJSONValue) -> String {
        switch value {
        case let .string(string):
            "\"\(string)\""
        case let .number(number):
            number.formatted()
        case let .bool(bool):
            String(bool)
        case .null:
            "null"
        case .object, .array:
            (try? value.canonicalJSONString()) ?? "JSON"
        }
    }
}
