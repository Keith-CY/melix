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
    private static let maximumSchemaDepth = 64
    // A schema at the semantic limit can use one wrapper container plus an
    // object or array keyword container at every level. Bound the raw parser to
    // that exact worst case while the iterative value conversion avoids growing
    // the process stack before semantic validation runs.
    private static let maximumRawJSONNestingDepth = (maximumSchemaDepth * 2) + 1
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
        try validateRawJSONNesting(json, invalidAs: mappedError)
        do {
            return try IterativeStructuredJSONParser.parse(
                json,
                maximumNestingDepth: Self.maximumRawJSONNestingDepth
            )
        } catch {
            throw mappedError
        }
    }

    private func validateRawJSONNesting(
        _ json: String,
        invalidAs mappedError: AgentToolJSONSchemaValidationError
    ) throws {
        var depth = 0
        var isInsideString = false
        var isEscaping = false
        for byte in json.utf8 {
            if isInsideString {
                if isEscaping {
                    isEscaping = false
                } else if byte == 0x5C {
                    isEscaping = true
                } else if byte == 0x22 {
                    isInsideString = false
                }
                continue
            }
            switch byte {
            case 0x22:
                isInsideString = true
            case 0x5B, 0x7B:
                depth += 1
                guard depth <= Self.maximumRawJSONNestingDepth else {
                    throw mappedError
                }
            case 0x5D, 0x7D:
                depth -= 1
                guard depth >= 0 else {
                    throw mappedError
                }
            default:
                continue
            }
        }
    }

    private struct SchemaValidationWorkItem {
        let schema: StructuredJSONValue
        let visitedRefs: Set<String>
        let depth: Int
    }

    private func validateSchemaNode(
        _ schema: StructuredJSONValue,
        root: StructuredJSONValue,
        visitedRefs: Set<String>,
        depth: Int
    ) throws {
        var work = [SchemaValidationWorkItem(
            schema: schema,
            visitedRefs: visitedRefs,
            depth: depth
        )]
        while let item = work.popLast() {
            guard item.depth <= Self.maximumSchemaDepth else {
                throw AgentToolJSONSchemaValidationError.invalidSchema
            }
            if case .bool = item.schema {
                continue
            }
            guard let object = item.schema.objectValue else {
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
                    work.append(SchemaValidationWorkItem(
                        schema: child,
                        visitedRefs: item.visitedRefs,
                        depth: item.depth + 1
                    ))
                }
            }
            for key in ["additionalProperties", "items", "contains", "not", "propertyNames", "if", "then", "else"] {
                guard let child = object[key] else { continue }
                work.append(SchemaValidationWorkItem(
                    schema: child,
                    visitedRefs: item.visitedRefs,
                    depth: item.depth + 1
                ))
            }
            if let prefixItems = object["prefixItems"] {
                guard let children = prefixItems.arrayValue else {
                    throw AgentToolJSONSchemaValidationError.invalidSchema
                }
                for child in children {
                    work.append(SchemaValidationWorkItem(
                        schema: child,
                        visitedRefs: item.visitedRefs,
                        depth: item.depth + 1
                    ))
                }
            }
            for key in ["allOf", "anyOf", "oneOf"] {
                guard let value = object[key] else { continue }
                guard let children = value.arrayValue, !children.isEmpty else {
                    throw AgentToolJSONSchemaValidationError.invalidSchema
                }
                for child in children {
                    work.append(SchemaValidationWorkItem(
                        schema: child,
                        visitedRefs: item.visitedRefs,
                        depth: item.depth + 1
                    ))
                }
            }
            if let ref = object["$ref"] {
                guard let reference = ref.stringValue,
                      reference.hasPrefix("#"),
                      let target = resolve(reference: reference, root: root) else {
                    throw AgentToolJSONSchemaValidationError.invalidSchema
                }
                if !item.visitedRefs.contains(reference) {
                    var refs = item.visitedRefs
                    refs.insert(reference)
                    work.append(SchemaValidationWorkItem(
                        schema: target,
                        visitedRefs: refs,
                        depth: item.depth + 1
                    ))
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
    }

    private struct MatchEvaluation {
        let value: StructuredJSONValue
        let schema: StructuredJSONValue
        let root: StructuredJSONValue
        let depth: Int
    }

    private enum MatchWorkItem {
        case evaluate(MatchEvaluation)
        case all([MatchEvaluation])
        case any([MatchEvaluation])
        case exactlyOne([MatchEvaluation])
        case negated(MatchEvaluation)
        case conditional(
            value: StructuredJSONValue,
            condition: StructuredJSONValue,
            thenSchema: StructuredJSONValue?,
            elseSchema: StructuredJSONValue?,
            root: StructuredJSONValue,
            depth: Int
        )
        case countMatches([MatchEvaluation], minimum: Int, maximum: Int)
        case combineAll(Int)
        case combineAny(Int)
        case combineExactlyOne(Int)
        case combineCount(Int, minimum: Int, maximum: Int)
        case invert
        case resolveConditional(
            value: StructuredJSONValue,
            thenSchema: StructuredJSONValue?,
            elseSchema: StructuredJSONValue?,
            root: StructuredJSONValue,
            depth: Int
        )
    }

    private func matches(
        _ value: StructuredJSONValue,
        schema: StructuredJSONValue,
        root: StructuredJSONValue,
        depth: Int
    ) throws -> Bool {
        var work: [MatchWorkItem] = [.evaluate(MatchEvaluation(
            value: value,
            schema: schema,
            root: root,
            depth: depth
        ))]
        var results: [Bool] = []

        while let item = work.popLast() {
            switch item {
            case .evaluate(let evaluation):
                guard evaluation.depth <= Self.maximumSchemaDepth else {
                    results.append(false)
                    continue
                }
                if case .bool(let allowed) = evaluation.schema {
                    results.append(allowed)
                    continue
                }
                guard let object = evaluation.schema.objectValue else {
                    results.append(false)
                    continue
                }

                if object["nullable"].flatMap(bool) == true,
                   case .null = evaluation.value {
                    results.append(true)
                    continue
                }
                if let type = object["type"],
                   !matchesType(evaluation.value, declaration: type) {
                    results.append(false)
                    continue
                }
                if let constant = object["const"], constant != evaluation.value {
                    results.append(false)
                    continue
                }
                if let choices = object["enum"]?.arrayValue,
                   !choices.contains(evaluation.value) {
                    results.append(false)
                    continue
                }
                if let string = evaluation.value.stringValue {
                    if let minimum = object["minLength"].flatMap(nonnegativeInteger),
                       string.count < minimum {
                        results.append(false)
                        continue
                    }
                    if let maximum = object["maxLength"].flatMap(nonnegativeInteger),
                       string.count > maximum {
                        results.append(false)
                        continue
                    }
                    if let pattern = object["pattern"]?.stringValue,
                       !regex(pattern, matches: string) {
                        results.append(false)
                        continue
                    }
                }
                if let numeric = number(evaluation.value) {
                    if let minimum = object["minimum"].flatMap(number), numeric < minimum {
                        results.append(false)
                        continue
                    }
                    if let maximum = object["maximum"].flatMap(number), numeric > maximum {
                        results.append(false)
                        continue
                    }
                    if let minimum = object["exclusiveMinimum"].flatMap(number), numeric <= minimum {
                        results.append(false)
                        continue
                    }
                    if let maximum = object["exclusiveMaximum"].flatMap(number), numeric >= maximum {
                        results.append(false)
                        continue
                    }
                    if let multiple = object["multipleOf"].flatMap(number) {
                        let quotient = numeric / multiple
                        if abs(quotient.rounded() - quotient) > 1e-10 {
                            results.append(false)
                            continue
                        }
                    }
                }

                var clauses: [MatchWorkItem] = []
                let childDepth = evaluation.depth + 1
                if let reference = object["$ref"]?.stringValue,
                   let target = resolve(reference: reference, root: evaluation.root) {
                    clauses.append(.evaluate(MatchEvaluation(
                        value: evaluation.value,
                        schema: target,
                        root: evaluation.root,
                        depth: childDepth
                    )))
                }
                if let schemas = object["allOf"]?.arrayValue {
                    clauses.append(.all(schemas.map {
                        MatchEvaluation(
                            value: evaluation.value,
                            schema: $0,
                            root: evaluation.root,
                            depth: childDepth
                        )
                    }))
                }
                if let schemas = object["anyOf"]?.arrayValue {
                    clauses.append(.any(schemas.map {
                        MatchEvaluation(
                            value: evaluation.value,
                            schema: $0,
                            root: evaluation.root,
                            depth: childDepth
                        )
                    }))
                }
                if let schemas = object["oneOf"]?.arrayValue {
                    clauses.append(.exactlyOne(schemas.map {
                        MatchEvaluation(
                            value: evaluation.value,
                            schema: $0,
                            root: evaluation.root,
                            depth: childDepth
                        )
                    }))
                }
                if let child = object["not"] {
                    clauses.append(.negated(MatchEvaluation(
                        value: evaluation.value,
                        schema: child,
                        root: evaluation.root,
                        depth: childDepth
                    )))
                }
                if let condition = object["if"] {
                    clauses.append(.conditional(
                        value: evaluation.value,
                        condition: condition,
                        thenSchema: object["then"],
                        elseSchema: object["else"],
                        root: evaluation.root,
                        depth: childDepth
                    ))
                }

                if let array = evaluation.value.arrayValue {
                    if let minimum = object["minItems"].flatMap(nonnegativeInteger),
                       array.count < minimum {
                        results.append(false)
                        continue
                    }
                    if let maximum = object["maxItems"].flatMap(nonnegativeInteger),
                       array.count > maximum {
                        results.append(false)
                        continue
                    }
                    if object["uniqueItems"].flatMap(bool) == true {
                        let canonical = try array.map(canonicalJSON)
                        if Set(canonical).count != canonical.count {
                            results.append(false)
                            continue
                        }
                    }
                    let prefixes = object["prefixItems"]?.arrayValue ?? []
                    for (index, child) in prefixes.enumerated() where index < array.count {
                        clauses.append(.evaluate(MatchEvaluation(
                            value: array[index],
                            schema: child,
                            root: evaluation.root,
                            depth: childDepth
                        )))
                    }
                    if let items = object["items"] {
                        for arrayItem in array.dropFirst(prefixes.count) {
                            clauses.append(.evaluate(MatchEvaluation(
                                value: arrayItem,
                                schema: items,
                                root: evaluation.root,
                                depth: childDepth
                            )))
                        }
                    }
                    if let contains = object["contains"] {
                        let minimum = object["minContains"].flatMap(nonnegativeInteger) ?? 1
                        let maximum = object["maxContains"].flatMap(nonnegativeInteger) ?? Int.max
                        clauses.append(.countMatches(array.map {
                            MatchEvaluation(
                                value: $0,
                                schema: contains,
                                root: evaluation.root,
                                depth: childDepth
                            )
                        }, minimum: minimum, maximum: maximum))
                    }
                }
                if let dictionary = evaluation.value.objectValue {
                    if let minimum = object["minProperties"].flatMap(nonnegativeInteger),
                       dictionary.count < minimum {
                        results.append(false)
                        continue
                    }
                    if let maximum = object["maxProperties"].flatMap(nonnegativeInteger),
                       dictionary.count > maximum {
                        results.append(false)
                        continue
                    }
                    let properties = object["properties"]?.objectValue ?? [:]
                    let patterns = object["patternProperties"]?.objectValue ?? [:]
                    let required = Set(object["required"]?.arrayValue?.compactMap(\.stringValue) ?? [])
                    if !required.isSubset(of: Set(dictionary.keys)) {
                        results.append(false)
                        continue
                    }
                    var dependencyFailed = false
                    if let dependencies = object["dependentRequired"]?.objectValue {
                        for (key, dependency) in dependencies where dictionary[key] != nil {
                            let requiredKeys = Set(dependency.arrayValue?.compactMap(\.stringValue) ?? [])
                            if !requiredKeys.isSubset(of: Set(dictionary.keys)) {
                                dependencyFailed = true
                                break
                            }
                        }
                    }
                    if dependencyFailed {
                        results.append(false)
                        continue
                    }
                    for (key, dictionaryValue) in dictionary {
                        if let property = properties[key] {
                            clauses.append(.evaluate(MatchEvaluation(
                                value: dictionaryValue,
                                schema: property,
                                root: evaluation.root,
                                depth: childDepth
                            )))
                        }
                        var matchedPattern = false
                        for (pattern, child) in patterns where regex(pattern, matches: key) {
                            matchedPattern = true
                            clauses.append(.evaluate(MatchEvaluation(
                                value: dictionaryValue,
                                schema: child,
                                root: evaluation.root,
                                depth: childDepth
                            )))
                        }
                        if properties[key] == nil,
                           !matchedPattern,
                           let additional = object["additionalProperties"] {
                            clauses.append(.evaluate(MatchEvaluation(
                                value: dictionaryValue,
                                schema: additional,
                                root: evaluation.root,
                                depth: childDepth
                            )))
                        }
                        if let propertyNames = object["propertyNames"] {
                            clauses.append(.evaluate(MatchEvaluation(
                                value: .string(key),
                                schema: propertyNames,
                                root: evaluation.root,
                                depth: childDepth
                            )))
                        }
                    }
                }

                if clauses.isEmpty {
                    results.append(true)
                } else {
                    work.append(.combineAll(clauses.count))
                    work.append(contentsOf: clauses.reversed())
                }

            case .all(let evaluations):
                work.append(.combineAll(evaluations.count))
                work.append(contentsOf: evaluations.reversed().map(MatchWorkItem.evaluate))
            case .any(let evaluations):
                work.append(.combineAny(evaluations.count))
                work.append(contentsOf: evaluations.reversed().map(MatchWorkItem.evaluate))
            case .exactlyOne(let evaluations):
                work.append(.combineExactlyOne(evaluations.count))
                work.append(contentsOf: evaluations.reversed().map(MatchWorkItem.evaluate))
            case .negated(let evaluation):
                work.append(.invert)
                work.append(.evaluate(evaluation))
            case .conditional(let value, let condition, let thenSchema, let elseSchema, let root, let depth):
                work.append(.resolveConditional(
                    value: value,
                    thenSchema: thenSchema,
                    elseSchema: elseSchema,
                    root: root,
                    depth: depth
                ))
                work.append(.evaluate(MatchEvaluation(
                    value: value,
                    schema: condition,
                    root: root,
                    depth: depth
                )))
            case .countMatches(let evaluations, let minimum, let maximum):
                work.append(.combineCount(
                    evaluations.count,
                    minimum: minimum,
                    maximum: maximum
                ))
                work.append(contentsOf: evaluations.reversed().map(MatchWorkItem.evaluate))
            case .combineAll(let count):
                guard let values = removeLast(count, from: &results) else { return false }
                results.append(values.allSatisfy { $0 })
            case .combineAny(let count):
                guard let values = removeLast(count, from: &results) else { return false }
                results.append(values.contains(true))
            case .combineExactlyOne(let count):
                guard let values = removeLast(count, from: &results) else { return false }
                results.append(values.lazy.filter { $0 }.count == 1)
            case .combineCount(let count, let minimum, let maximum):
                guard let values = removeLast(count, from: &results) else { return false }
                let matched = values.lazy.filter { $0 }.count
                results.append(matched >= minimum && matched <= maximum)
            case .invert:
                guard let result = results.popLast() else { return false }
                results.append(!result)
            case .resolveConditional(let value, let thenSchema, let elseSchema, let root, let depth):
                guard let conditionMatched = results.popLast() else { return false }
                if conditionMatched, let thenSchema {
                    work.append(.evaluate(MatchEvaluation(
                        value: value,
                        schema: thenSchema,
                        root: root,
                        depth: depth
                    )))
                } else if !conditionMatched, let elseSchema {
                    work.append(.evaluate(MatchEvaluation(
                        value: value,
                        schema: elseSchema,
                        root: root,
                        depth: depth
                    )))
                } else {
                    results.append(true)
                }
            }
        }

        return results.count == 1 && results[0]
    }

    private func removeLast(_ count: Int, from results: inout [Bool]) -> [Bool]? {
        guard count >= 0, results.count >= count else { return nil }
        let start = results.count - count
        let values = Array(results[start...])
        results.removeSubrange(start...)
        return values
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

private struct IterativeStructuredJSONParser {
    private enum ParserError: Error {
        case invalidJSON
    }

    private enum ObjectExpectation {
        case keyOrEnd
        case key
        case colon
        case value
        case commaOrEnd
    }

    private enum ArrayExpectation {
        case valueOrEnd
        case value
        case commaOrEnd
    }

    private struct ObjectFrame {
        var values: [String: StructuredJSONValue] = [:]
        var pendingKey: String?
        var expectation: ObjectExpectation = .keyOrEnd
    }

    private struct ArrayFrame {
        var values: [StructuredJSONValue] = []
        var expectation: ArrayExpectation = .valueOrEnd
    }

    private enum ContainerFrame {
        case object(ObjectFrame)
        case array(ArrayFrame)
    }

    private let bytes: [UInt8]
    private let maximumNestingDepth: Int
    private var index = 0
    private var containers: [ContainerFrame] = []
    private var root: StructuredJSONValue?

    static func parse(
        _ text: String,
        maximumNestingDepth: Int
    ) throws -> StructuredJSONValue {
        var parser = IterativeStructuredJSONParser(
            bytes: Array(text.utf8),
            maximumNestingDepth: maximumNestingDepth
        )
        return try parser.parseDocument()
    }

    private mutating func parseDocument() throws -> StructuredJSONValue {
        while true {
            skipWhitespace()
            guard index < bytes.count else {
                break
            }
            switch bytes[index] {
            case UInt8(ascii: "{"):
                try beginContainer(.object(ObjectFrame()))
                index += 1
            case UInt8(ascii: "["):
                try beginContainer(.array(ArrayFrame()))
                index += 1
            case UInt8(ascii: "}"):
                index += 1
                try finishObject()
            case UInt8(ascii: "]"):
                index += 1
                try finishArray()
            case UInt8(ascii: ":"):
                index += 1
                try consumeColon()
            case UInt8(ascii: ","):
                index += 1
                try consumeComma()
            case UInt8(ascii: "\""):
                let string = try parseString()
                if !setObjectKeyIfExpected(string) {
                    try acceptValue(.string(string))
                }
            default:
                try acceptValue(parsePrimitive())
            }
        }

        guard containers.isEmpty, let root else {
            throw ParserError.invalidJSON
        }
        return root
    }

    private mutating func beginContainer(_ frame: ContainerFrame) throws {
        guard canAcceptValue(), containers.count < maximumNestingDepth else {
            throw ParserError.invalidJSON
        }
        containers.append(frame)
    }

    private mutating func finishObject() throws {
        guard let frame = containers.popLast(), case .object(let object) = frame else {
            throw ParserError.invalidJSON
        }
        guard object.expectation == .keyOrEnd || object.expectation == .commaOrEnd else {
            throw ParserError.invalidJSON
        }
        try acceptValue(.object(object.values))
    }

    private mutating func finishArray() throws {
        guard let frame = containers.popLast(), case .array(let array) = frame else {
            throw ParserError.invalidJSON
        }
        guard array.expectation == .valueOrEnd || array.expectation == .commaOrEnd else {
            throw ParserError.invalidJSON
        }
        try acceptValue(.array(array.values))
    }

    private mutating func consumeColon() throws {
        guard let frame = containers.popLast(), case .object(var object) = frame,
              object.expectation == .colon else {
            throw ParserError.invalidJSON
        }
        object.expectation = .value
        containers.append(.object(object))
    }

    private mutating func consumeComma() throws {
        guard let frame = containers.popLast() else {
            throw ParserError.invalidJSON
        }
        switch frame {
        case .object(var object):
            guard object.expectation == .commaOrEnd else {
                throw ParserError.invalidJSON
            }
            object.expectation = .key
            containers.append(.object(object))
        case .array(var array):
            guard array.expectation == .commaOrEnd else {
                throw ParserError.invalidJSON
            }
            array.expectation = .value
            containers.append(.array(array))
        }
    }

    private mutating func setObjectKeyIfExpected(_ key: String) -> Bool {
        guard let frame = containers.popLast() else {
            return false
        }
        guard case .object(var object) = frame,
              object.expectation == .keyOrEnd || object.expectation == .key else {
            containers.append(frame)
            return false
        }
        guard object.values[key] == nil else {
            containers.append(frame)
            return false
        }
        object.pendingKey = key
        object.expectation = .colon
        containers.append(.object(object))
        return true
    }

    private func canAcceptValue() -> Bool {
        guard let frame = containers.last else {
            return root == nil
        }
        switch frame {
        case .object(let object):
            return object.expectation == .value
        case .array(let array):
            return array.expectation == .valueOrEnd || array.expectation == .value
        }
    }

    private mutating func acceptValue(_ value: StructuredJSONValue) throws {
        guard let frame = containers.popLast() else {
            guard root == nil else {
                throw ParserError.invalidJSON
            }
            root = value
            return
        }
        switch frame {
        case .object(var object):
            guard object.expectation == .value, let key = object.pendingKey,
                  object.values[key] == nil else {
                throw ParserError.invalidJSON
            }
            object.values[key] = value
            object.pendingKey = nil
            object.expectation = .commaOrEnd
            containers.append(.object(object))
        case .array(var array):
            guard array.expectation == .valueOrEnd || array.expectation == .value else {
                throw ParserError.invalidJSON
            }
            array.values.append(value)
            array.expectation = .commaOrEnd
            containers.append(.array(array))
        }
    }

    private mutating func parseString() throws -> String {
        let start = index
        index += 1
        while index < bytes.count {
            switch bytes[index] {
            case UInt8(ascii: "\""):
                index += 1
                return try JSONDecoder().decode(
                    String.self,
                    from: Data(bytes[start..<index])
                )
            case UInt8(ascii: "\\"):
                index += 2
                guard index <= bytes.count else {
                    throw ParserError.invalidJSON
                }
            case 0x00...0x1F:
                throw ParserError.invalidJSON
            default:
                index += 1
            }
        }
        throw ParserError.invalidJSON
    }

    private mutating func parsePrimitive() throws -> StructuredJSONValue {
        let start = index
        while index < bytes.count, !Self.isTokenDelimiter(bytes[index]) {
            index += 1
        }
        guard start < index else {
            throw ParserError.invalidJSON
        }
        let token = bytes[start..<index]
        switch token.elementsEqual([UInt8]("true".utf8)) {
        case true:
            return .bool(true)
        case false:
            break
        }
        if token.elementsEqual([UInt8]("false".utf8)) {
            return .bool(false)
        }
        if token.elementsEqual([UInt8]("null".utf8)) {
            return .null
        }
        let number = try JSONDecoder().decode(Double.self, from: Data(token))
        guard number.isFinite else {
            throw ParserError.invalidJSON
        }
        return .number(number)
    }

    private mutating func skipWhitespace() {
        while index < bytes.count {
            switch bytes[index] {
            case UInt8(ascii: " "), UInt8(ascii: "\t"), UInt8(ascii: "\n"), UInt8(ascii: "\r"):
                index += 1
            default:
                return
            }
        }
    }

    private static func isTokenDelimiter(_ byte: UInt8) -> Bool {
        switch byte {
        case UInt8(ascii: ","), UInt8(ascii: "]"), UInt8(ascii: "}"),
             UInt8(ascii: " "), UInt8(ascii: "\t"), UInt8(ascii: "\n"), UInt8(ascii: "\r"):
            return true
        default:
            return false
        }
    }
}
