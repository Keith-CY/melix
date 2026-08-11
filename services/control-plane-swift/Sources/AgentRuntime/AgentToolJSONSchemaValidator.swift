import Foundation

enum AgentToolJSONSchemaValidationError: Error, Sendable, Equatable {
    case invalidSchema
    case invalidArguments
    case schemaViolation
}

/// Fail-closed validator for the JSON Schema vocabulary emitted by Melix's
/// built-ins and commonly returned by MCP servers. Unknown assertion keywords
/// make the catalog invalid instead of being silently ignored.
struct AgentToolJSONSchemaValidator: Sendable {
    private let allowRegularExpressions: Bool

    init(allowRegularExpressions: Bool = true) {
        self.allowRegularExpressions = allowRegularExpressions
    }

    private static let annotationKeywords: Set<String> = [
        "$anchor", "$comment", "$id", "$schema",
        "contentEncoding", "contentMediaType", "default", "deprecated",
        "description", "examples", "format", "readOnly", "title", "writeOnly",
    ]

    private static let assertionKeywords: Set<String> = [
        "$defs", "$ref", "additionalProperties", "allOf", "anyOf", "const",
        "contains", "definitions", "dependentRequired", "else", "enum",
        "exclusiveMaximum", "exclusiveMinimum", "if", "items", "maxContains",
        "maxItems", "maxLength", "maxProperties", "maximum", "minContains",
        "minItems", "minLength", "minProperties", "minimum", "multipleOf",
        "not", "nullable", "oneOf", "pattern", "patternProperties",
        "prefixItems", "properties", "propertyNames", "required", "then",
        "type", "uniqueItems",
    ]

    func validateSchemaDefinition(_ schemaJSON: String) throws {
        let schema = try parse(schemaJSON, invalidAs: .invalidSchema)
        guard schema.objectValue != nil else {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        try validateSchemaNode(schema, root: schema, visitedRefs: [], depth: 0)
    }

    func validate(argumentsJSON: String, schemaJSON: String) throws {
        let arguments = try parse(argumentsJSON, invalidAs: .invalidArguments)
        guard arguments.objectValue != nil else {
            throw AgentToolJSONSchemaValidationError.invalidArguments
        }
        let schema = try parse(schemaJSON, invalidAs: .invalidSchema)
        guard schema.objectValue != nil else {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        try validateSchemaNode(schema, root: schema, visitedRefs: [], depth: 0)
        guard try matches(arguments, schema: schema, root: schema, depth: 0) else {
            throw AgentToolJSONSchemaValidationError.schemaViolation
        }
    }

    private func parse(
        _ json: String,
        invalidAs mappedError: AgentToolJSONSchemaValidationError
    ) throws -> StructuredJSONValue {
        do {
            return try StructuredJSONValue.parse(text: json)
        } catch {
            throw mappedError
        }
    }

    private func validateSchemaNode(
        _ schema: StructuredJSONValue,
        root: StructuredJSONValue,
        visitedRefs: Set<String>,
        depth: Int
    ) throws {
        guard depth <= 64 else {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        if case .bool = schema {
            return
        }
        guard let object = schema.objectValue else {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        if !allowRegularExpressions,
           object["pattern"] != nil || object["patternProperties"] != nil {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        for keyword in object.keys where
            !Self.annotationKeywords.contains(keyword)
                && !Self.assertionKeywords.contains(keyword) {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }

        if let type = object["type"] {
            let types: [String]
            if let value = type.stringValue {
                types = [value]
            } else if let values = type.arrayValue,
                      values.allSatisfy({ $0.stringValue != nil }) {
                types = values.compactMap(\.stringValue)
            } else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
            let supported = Set(["array", "boolean", "integer", "null", "number", "object", "string"])
            guard !types.isEmpty, Set(types).count == types.count,
                  types.allSatisfy(supported.contains) else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
        }
        if let nullable = object["nullable"], bool(nullable) == nil {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        if let values = object["enum"]?.arrayValue, values.isEmpty {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        } else if object["enum"] != nil, object["enum"]?.arrayValue == nil {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }

        for key in ["properties", "patternProperties", "$defs", "definitions"] {
            guard let value = object[key] else { continue }
            guard let children = value.objectValue else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
            for (name, child) in children {
                if key == "patternProperties" {
                    guard validRegex(name) else {
                        throw AgentToolJSONSchemaValidationError.invalidSchema
                    }
                }
                try validateSchemaNode(
                    child,
                    root: root,
                    visitedRefs: visitedRefs,
                    depth: depth + 1
                )
            }
        }
        for key in ["additionalProperties", "items", "contains", "not", "propertyNames", "if", "then", "else"] {
            guard let child = object[key] else { continue }
            try validateSchemaNode(
                child,
                root: root,
                visitedRefs: visitedRefs,
                depth: depth + 1
            )
        }
        if let prefixItems = object["prefixItems"] {
            guard let children = prefixItems.arrayValue else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
            for child in children {
                try validateSchemaNode(child, root: root, visitedRefs: visitedRefs, depth: depth + 1)
            }
        }
        for key in ["allOf", "anyOf", "oneOf"] {
            guard let value = object[key] else { continue }
            guard let children = value.arrayValue, !children.isEmpty else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
            for child in children {
                try validateSchemaNode(child, root: root, visitedRefs: visitedRefs, depth: depth + 1)
            }
        }
        if let ref = object["$ref"] {
            guard let reference = ref.stringValue,
                  reference.hasPrefix("#"),
                  let target = resolve(reference: reference, root: root) else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
            if !visitedRefs.contains(reference) {
                var refs = visitedRefs
                refs.insert(reference)
                try validateSchemaNode(target, root: root, visitedRefs: refs, depth: depth + 1)
            }
        }
        if let required = object["required"] {
            guard let values = required.arrayValue,
                  values.allSatisfy({ $0.stringValue != nil }),
                  Set(values.compactMap(\.stringValue)).count == values.count else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
        }
        if let dependent = object["dependentRequired"] {
            guard let dependencies = dependent.objectValue else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
            for value in dependencies.values {
                guard let names = value.arrayValue,
                      names.allSatisfy({ $0.stringValue != nil }) else {
                    throw AgentToolJSONSchemaValidationError.invalidSchema
                }
            }
        }
        for key in ["minLength", "maxLength", "minItems", "maxItems", "minContains", "maxContains", "minProperties", "maxProperties"] {
            if let value = object[key], nonnegativeInteger(value) == nil {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
        }
        for key in ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"] {
            if let value = object[key], number(value) == nil {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
        }
        if let multiple = object["multipleOf"],
           !(number(multiple).map { $0 > 0 } ?? false) {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        if let pattern = object["pattern"],
           !(pattern.stringValue.map(validRegex) ?? false) {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
        if let unique = object["uniqueItems"], bool(unique) == nil {
            throw AgentToolJSONSchemaValidationError.invalidSchema
        }
    }

    private func matches(
        _ value: StructuredJSONValue,
        schema: StructuredJSONValue,
        root: StructuredJSONValue,
        depth: Int
    ) throws -> Bool {
        guard depth <= 64 else { return false }
        if case .bool(let allowed) = schema { return allowed }
        guard let object = schema.objectValue else { return false }

        if object["nullable"].flatMap(bool) == true, case .null = value {
            return true
        }
        if let reference = object["$ref"]?.stringValue,
           let target = resolve(reference: reference, root: root),
           try !matches(value, schema: target, root: root, depth: depth + 1) {
            return false
        }
        if let type = object["type"], !matchesType(value, declaration: type) {
            return false
        }
        if let constant = object["const"], constant != value { return false }
        if let choices = object["enum"]?.arrayValue, !choices.contains(value) { return false }

        if let schemas = object["allOf"]?.arrayValue {
            for child in schemas where try !matches(value, schema: child, root: root, depth: depth + 1) {
                return false
            }
        }
        if let schemas = object["anyOf"]?.arrayValue {
            var matched = false
            for child in schemas where try matches(value, schema: child, root: root, depth: depth + 1) {
                matched = true
            }
            if !matched { return false }
        }
        if let schemas = object["oneOf"]?.arrayValue {
            var count = 0
            for child in schemas where try matches(value, schema: child, root: root, depth: depth + 1) {
                count += 1
            }
            if count != 1 { return false }
        }
        if let child = object["not"], try matches(value, schema: child, root: root, depth: depth + 1) {
            return false
        }
        if let condition = object["if"] {
            let conditionMatched = try matches(value, schema: condition, root: root, depth: depth + 1)
            if conditionMatched, let thenSchema = object["then"],
               try !matches(value, schema: thenSchema, root: root, depth: depth + 1) {
                return false
            }
            if !conditionMatched, let elseSchema = object["else"],
               try !matches(value, schema: elseSchema, root: root, depth: depth + 1) {
                return false
            }
        }

        if let string = value.stringValue {
            if let minimum = object["minLength"].flatMap(nonnegativeInteger), string.count < minimum { return false }
            if let maximum = object["maxLength"].flatMap(nonnegativeInteger), string.count > maximum { return false }
            if let pattern = object["pattern"]?.stringValue, !regex(pattern, matches: string) { return false }
        }
        if let numeric = number(value) {
            if let minimum = object["minimum"].flatMap(number), numeric < minimum { return false }
            if let maximum = object["maximum"].flatMap(number), numeric > maximum { return false }
            if let minimum = object["exclusiveMinimum"].flatMap(number), numeric <= minimum { return false }
            if let maximum = object["exclusiveMaximum"].flatMap(number), numeric >= maximum { return false }
            if let multiple = object["multipleOf"].flatMap(number) {
                let quotient = numeric / multiple
                if abs(quotient.rounded() - quotient) > 1e-10 { return false }
            }
        }
        if let array = value.arrayValue {
            if let minimum = object["minItems"].flatMap(nonnegativeInteger), array.count < minimum { return false }
            if let maximum = object["maxItems"].flatMap(nonnegativeInteger), array.count > maximum { return false }
            if object["uniqueItems"].flatMap(bool) == true {
                let canonical = try array.map(canonicalJSON)
                if Set(canonical).count != canonical.count { return false }
            }
            let prefixes = object["prefixItems"]?.arrayValue ?? []
            for (index, child) in prefixes.enumerated() where index < array.count {
                if try !matches(array[index], schema: child, root: root, depth: depth + 1) { return false }
            }
            if let items = object["items"] {
                for item in array.dropFirst(prefixes.count) where
                    try !matches(item, schema: items, root: root, depth: depth + 1) {
                    return false
                }
            }
            if let contains = object["contains"] {
                var count = 0
                for item in array where try matches(item, schema: contains, root: root, depth: depth + 1) {
                    count += 1
                }
                let minimum = object["minContains"].flatMap(nonnegativeInteger) ?? 1
                let maximum = object["maxContains"].flatMap(nonnegativeInteger) ?? Int.max
                if count < minimum || count > maximum { return false }
            }
        }
        if let dictionary = value.objectValue {
            if let minimum = object["minProperties"].flatMap(nonnegativeInteger), dictionary.count < minimum { return false }
            if let maximum = object["maxProperties"].flatMap(nonnegativeInteger), dictionary.count > maximum { return false }
            let properties = object["properties"]?.objectValue ?? [:]
            let patterns = object["patternProperties"]?.objectValue ?? [:]
            let required = Set(object["required"]?.arrayValue?.compactMap(\.stringValue) ?? [])
            if !required.isSubset(of: Set(dictionary.keys)) { return false }
            for (key, item) in dictionary {
                if let property = properties[key],
                   try !matches(item, schema: property, root: root, depth: depth + 1) {
                    return false
                }
                var matchedPattern = false
                for (pattern, child) in patterns where regex(pattern, matches: key) {
                    matchedPattern = true
                    if try !matches(item, schema: child, root: root, depth: depth + 1) { return false }
                }
                if properties[key] == nil, !matchedPattern, let additional = object["additionalProperties"],
                   try !matches(item, schema: additional, root: root, depth: depth + 1) {
                    return false
                }
                if let propertyNames = object["propertyNames"],
                   try !matches(.string(key), schema: propertyNames, root: root, depth: depth + 1) {
                    return false
                }
            }
            if let dependencies = object["dependentRequired"]?.objectValue {
                for (key, dependency) in dependencies where dictionary[key] != nil {
                    let requiredKeys = Set(dependency.arrayValue?.compactMap(\.stringValue) ?? [])
                    if !requiredKeys.isSubset(of: Set(dictionary.keys)) { return false }
                }
            }
        }
        return true
    }

    private func matchesType(_ value: StructuredJSONValue, declaration: StructuredJSONValue) -> Bool {
        let types = declaration.stringValue.map { [$0] }
            ?? declaration.arrayValue?.compactMap(\.stringValue)
            ?? []
        return types.contains { type in
            switch (type, value) {
            case ("object", .object), ("array", .array), ("string", .string),
                 ("boolean", .bool), ("null", .null), ("number", .number):
                return true
            case ("integer", .number(let number)):
                return number.isFinite && number.rounded() == number
            default:
                return false
            }
        }
    }

    private func number(_ value: StructuredJSONValue) -> Double? {
        guard case .number(let number) = value, number.isFinite else { return nil }
        return number
    }

    private func nonnegativeInteger(_ value: StructuredJSONValue) -> Int? {
        guard let number = number(value), number >= 0, number.rounded() == number,
              number <= Double(Int.max) else { return nil }
        return Int(number)
    }

    private func bool(_ value: StructuredJSONValue) -> Bool? {
        guard case .bool(let bool) = value else { return nil }
        return bool
    }

    private func validRegex(_ pattern: String) -> Bool {
        (try? NSRegularExpression(pattern: pattern)) != nil
    }

    private func regex(_ pattern: String, matches value: String) -> Bool {
        guard let expression = try? NSRegularExpression(pattern: pattern) else { return false }
        let range = NSRange(location: 0, length: value.utf16.count)
        return expression.firstMatch(in: value, range: range) != nil
    }

    private func canonicalJSON(_ value: StructuredJSONValue) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return String(decoding: try encoder.encode(value), as: UTF8.self)
    }

    private func resolve(
        reference: String,
        root: StructuredJSONValue
    ) -> StructuredJSONValue? {
        guard reference.hasPrefix("#") else { return nil }
        let fragment = String(reference.dropFirst())
        guard !fragment.isEmpty else { return root }
        guard fragment.hasPrefix("/") else { return nil }
        var current = root
        for encodedPart in fragment.dropFirst().split(separator: "/", omittingEmptySubsequences: false) {
            let part = encodedPart
                .replacingOccurrences(of: "~1", with: "/")
                .replacingOccurrences(of: "~0", with: "~")
            if let object = current.objectValue, let next = object[part] {
                current = next
            } else if let array = current.arrayValue,
                      let index = Int(part), array.indices.contains(index) {
                current = array[index]
            } else {
                return nil
            }
        }
        return current
    }
}
