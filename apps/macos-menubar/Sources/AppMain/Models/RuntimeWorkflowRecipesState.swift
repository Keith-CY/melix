import Foundation

public struct RuntimeWorkflowRecipeMetricState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let valueText: String

    public init(name: String, valueText: String) {
        self.id = name
        self.name = name
        self.valueText = valueText
    }
}

public struct RuntimeWorkflowRecipeSummaryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let version: String
    public let title: String
    public let tasks: [String]
    public let digest: String

    public init(id: String, version: String, title: String, tasks: [String], digest: String) {
        self.id = id
        self.version = version
        self.title = title
        self.tasks = tasks
        self.digest = digest
    }

    public var taskText: String {
        tasks.joined(separator: ", ")
    }
}

public struct RuntimeWorkflowRecipeCatalogState: Equatable, Sendable {
    public static let empty = RuntimeWorkflowRecipeCatalogState(schemaVersion: "", recipes: [], metrics: [])

    public let schemaVersion: String
    public let recipes: [RuntimeWorkflowRecipeSummaryState]
    public let metrics: [RuntimeWorkflowRecipeMetricState]
    public let availableTaskFilters: [String]

    public init(
        schemaVersion: String,
        recipes: [RuntimeWorkflowRecipeSummaryState],
        metrics: [RuntimeWorkflowRecipeMetricState]
    ) {
        self.schemaVersion = schemaVersion
        self.recipes = recipes
        self.metrics = metrics
        self.availableTaskFilters = Array(Set(recipes.flatMap(\.tasks))).sorted()
    }
}

public struct RuntimeWorkflowRecipeInputRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let valueType: String
    public let required: Bool
    public let defaultValueText: String
    public let uriKind: String

    public init(
        name: String,
        valueType: String,
        required: Bool,
        defaultValueText: String,
        uriKind: String
    ) {
        self.id = name
        self.name = name
        self.valueType = valueType
        self.required = required
        self.defaultValueText = defaultValueText
        self.uriKind = uriKind
    }

    public var requirementText: String {
        required ? "Required" : "Optional"
    }
}

public struct RuntimeWorkflowRecipeKeyValueRowState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let valueText: String

    public init(name: String, valueText: String) {
        self.id = name
        self.name = name
        self.valueText = valueText
    }
}

public struct RuntimeWorkflowRecipePipelineStepState: Identifiable, Equatable, Sendable {
    public let id: String
    public let command: String
    public let argumentSummaryText: String

    public init(id: String, command: String, argumentSummaryText: String) {
        self.id = id
        self.command = command
        self.argumentSummaryText = argumentSummaryText
    }
}

public struct RuntimeWorkflowRecipeDetailState: Identifiable, Equatable, Sendable {
    public let id: String
    public let schemaVersion: String
    public let version: String
    public let title: String
    public let description: String
    public let tasks: [String]
    public let digest: String
    public let inputRows: [RuntimeWorkflowRecipeInputRowState]
    public let preflightRows: [RuntimeWorkflowRecipeKeyValueRowState]
    public let pipelineSteps: [RuntimeWorkflowRecipePipelineStepState]
    public let outputRows: [RuntimeWorkflowRecipeKeyValueRowState]

    public init(
        id: String,
        schemaVersion: String,
        version: String,
        title: String,
        description: String,
        tasks: [String],
        digest: String,
        inputRows: [RuntimeWorkflowRecipeInputRowState],
        preflightRows: [RuntimeWorkflowRecipeKeyValueRowState],
        pipelineSteps: [RuntimeWorkflowRecipePipelineStepState],
        outputRows: [RuntimeWorkflowRecipeKeyValueRowState]
    ) {
        self.id = id
        self.schemaVersion = schemaVersion
        self.version = version
        self.title = title
        self.description = description
        self.tasks = tasks
        self.digest = digest
        self.inputRows = inputRows
        self.preflightRows = preflightRows
        self.pipelineSteps = pipelineSteps
        self.outputRows = outputRows
    }

    public var taskText: String {
        tasks.joined(separator: ", ")
    }
}

public struct RuntimeWorkflowURICandidateState: Identifiable, Equatable, Sendable {
    public let id: String
    public let kind: String
    public let sourceKind: String
    public let taskKind: String
    public let confidence: Double
    public let normalizedLocator: String
    public let repoID: String
    public let revision: String
    public let reasons: [String]
    public let warnings: [String]
    public let recommendedNextAction: String
    public let generatedCommandArguments: [String]

    public init(
        id: String,
        kind: String,
        sourceKind: String,
        taskKind: String,
        confidence: Double,
        normalizedLocator: String,
        repoID: String,
        revision: String,
        reasons: [String],
        warnings: [String],
        recommendedNextAction: String,
        generatedCommandArguments: [String]
    ) {
        self.id = id
        self.kind = kind
        self.sourceKind = sourceKind
        self.taskKind = taskKind
        self.confidence = confidence
        self.normalizedLocator = normalizedLocator
        self.repoID = repoID
        self.revision = revision
        self.reasons = reasons
        self.warnings = warnings
        self.recommendedNextAction = recommendedNextAction
        self.generatedCommandArguments = generatedCommandArguments
    }

    public var confidenceText: String {
        let percent = confidence * 100
        if percent.isFinite, percent.rounded(.towardZero) == percent {
            return "\(Int(percent))%"
        }
        return "\(String(format: "%.1f", percent))%"
    }

    public var reasonText: String {
        reasons.joined(separator: "; ")
    }

    public var warningText: String {
        warnings.joined(separator: "; ")
    }

    public var generatedCommandText: String {
        generatedCommandArguments.isEmpty
            ? recommendedNextAction
            : generatedCommandArguments.joined(separator: " ")
    }
}

public struct RuntimeWorkflowURIInspectionState: Equatable, Sendable {
    public let schemaVersion: String
    public let originalURI: String
    public let normalizedLocator: String
    public let candidateCount: Int
    public let ambiguityCount: Int
    public let candidates: [RuntimeWorkflowURICandidateState]
    public let metrics: [RuntimeWorkflowRecipeMetricState]

    public init(
        schemaVersion: String,
        originalURI: String,
        normalizedLocator: String,
        candidateCount: Int,
        ambiguityCount: Int,
        candidates: [RuntimeWorkflowURICandidateState],
        metrics: [RuntimeWorkflowRecipeMetricState]
    ) {
        self.schemaVersion = schemaVersion
        self.originalURI = originalURI
        self.normalizedLocator = normalizedLocator
        self.candidateCount = candidateCount
        self.ambiguityCount = ambiguityCount
        self.candidates = candidates
        self.metrics = metrics
    }

    public var summaryText: String {
        "\(candidateCount) \(candidateCount == 1 ? "candidate" : "candidates"), \(ambiguityCount) ambiguous"
    }
}

public enum RuntimeWorkflowRecipesPayloadDecoder {
    public static func decodeCatalog(_ output: String) throws -> RuntimeWorkflowRecipeCatalogState {
        try decodeCatalog(Data(output.utf8))
    }

    public static func decodeCatalog(_ data: Data) throws -> RuntimeWorkflowRecipeCatalogState {
        let payload = try jsonObject(from: data, message: "Workflow recipe catalog payload must be a JSON object.")
        let recipes = (payload["recipes"] as? [[String: Any]] ?? []).map { recipe in
            RuntimeWorkflowRecipeSummaryState(
                id: stringText(for: recipe["id"]),
                version: stringText(for: recipe["version"]),
                title: stringText(for: recipe["title"]),
                tasks: stringArray(for: recipe["tasks"]),
                digest: stringText(for: recipe["recipe_digest"])
            )
        }
        return RuntimeWorkflowRecipeCatalogState(
            schemaVersion: stringText(for: payload["schema_version"]),
            recipes: recipes,
            metrics: metricRows(from: payload["metrics"])
        )
    }

    public static func decodeDetail(_ output: String) throws -> RuntimeWorkflowRecipeDetailState {
        try decodeDetail(Data(output.utf8))
    }

    public static func decodeDetail(_ data: Data) throws -> RuntimeWorkflowRecipeDetailState {
        let payload = try jsonObject(from: data, message: "Workflow recipe detail payload must be a JSON object.")
        let pipeline = payload["pipeline"] as? [String: Any] ?? [:]
        return RuntimeWorkflowRecipeDetailState(
            id: stringText(for: payload["id"]),
            schemaVersion: stringText(for: payload["schema_version"]),
            version: stringText(for: payload["version"]),
            title: stringText(for: payload["title"]),
            description: stringText(for: payload["description"]),
            tasks: stringArray(for: payload["tasks"]),
            digest: stringText(for: payload["recipe_digest"]),
            inputRows: inputRows(from: payload["inputs"]),
            preflightRows: keyValueRows(from: payload["preflight"]),
            pipelineSteps: pipelineSteps(from: pipeline["steps"]),
            outputRows: keyValueRows(from: payload["outputs"])
        )
    }

    public static func decodeURIInspection(_ output: String) throws -> RuntimeWorkflowURIInspectionState {
        try decodeURIInspection(Data(output.utf8))
    }

    public static func decodeURIInspection(_ data: Data) throws -> RuntimeWorkflowURIInspectionState {
        let payload = try jsonObject(from: data, message: "Workflow recipe URI inspection payload must be a JSON object.")
        let candidates = (payload["candidates"] as? [[String: Any]] ?? []).enumerated().map { index, candidate in
            RuntimeWorkflowURICandidateState(
                id: [
                    stringText(for: candidate["kind"]),
                    stringText(for: candidate["normalized_locator"]),
                    String(index),
                ].joined(separator: "|"),
                kind: stringText(for: candidate["kind"]),
                sourceKind: stringText(for: candidate["source_kind"]),
                taskKind: stringText(for: candidate["task_kind"]),
                confidence: doubleValue(for: candidate["confidence"]),
                normalizedLocator: stringText(for: candidate["normalized_locator"]),
                repoID: stringText(for: candidate["repo_id"]),
                revision: stringText(for: candidate["revision"]),
                reasons: stringArray(for: candidate["reasons"]),
                warnings: stringArray(for: candidate["warnings"]),
                recommendedNextAction: stringText(for: candidate["recommended_next_action"]),
                generatedCommandArguments: stringArray(for: candidate["generated_command_arguments"])
            )
        }
        return RuntimeWorkflowURIInspectionState(
            schemaVersion: stringText(for: payload["schema_version"]),
            originalURI: stringText(for: payload["original_uri"]),
            normalizedLocator: stringText(for: payload["normalized_locator"]),
            candidateCount: intValue(for: payload["candidate_count"], fallback: candidates.count),
            ambiguityCount: intValue(for: payload["ambiguity_count"], fallback: max(candidates.count - 1, 0)),
            candidates: candidates,
            metrics: metricRows(from: payload["metrics"])
        )
    }

    private static func jsonObject(from data: Data, message: String) throws -> [String: Any] {
        let decoded = try JSONSerialization.jsonObject(with: data)
        guard let payload = decoded as? [String: Any] else {
            throw dataCorrupted(message)
        }
        return payload
    }

    private static func inputRows(from value: Any?) -> [RuntimeWorkflowRecipeInputRowState] {
        (value as? [[String: Any]] ?? []).map { input in
            RuntimeWorkflowRecipeInputRowState(
                name: stringText(for: input["name"]),
                valueType: stringText(for: input["type"]),
                required: (input["required"] as? Bool) ?? false,
                defaultValueText: stringText(for: input["default"]),
                uriKind: stringText(for: input["uri_kind"])
            )
        }
    }

    private static func pipelineSteps(from value: Any?) -> [RuntimeWorkflowRecipePipelineStepState] {
        (value as? [[String: Any]] ?? []).map { step in
            RuntimeWorkflowRecipePipelineStepState(
                id: stringText(for: step["id"]),
                command: stringText(for: step["command"]),
                argumentSummaryText: argumentSummary(from: step["args"])
            )
        }
    }

    private static func keyValueRows(from value: Any?) -> [RuntimeWorkflowRecipeKeyValueRowState] {
        let object = value as? [String: Any] ?? [:]
        return object.keys.sorted().map { key in
            RuntimeWorkflowRecipeKeyValueRowState(name: key, valueText: displayText(for: object[key] ?? NSNull()))
        }
    }

    private static func metricRows(from value: Any?) -> [RuntimeWorkflowRecipeMetricState] {
        let object = value as? [String: Any] ?? [:]
        return object.keys.sorted().map { key in
            RuntimeWorkflowRecipeMetricState(name: key, valueText: displayText(for: object[key] ?? NSNull()))
        }
    }

    private static func stringArray(for value: Any?) -> [String] {
        (value as? [Any] ?? []).map { stringText(for: $0) }.filter { $0.isEmpty == false }
    }

    private static func stringText(for value: Any?) -> String {
        guard let value else {
            return ""
        }
        if value is NSNull {
            return ""
        }
        if let string = value as? String {
            return string
        }
        return displayText(for: value)
    }

    private static func intValue(for value: Any?, fallback: Int) -> Int {
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let string = value as? String, let int = Int(string) {
            return int
        }
        return fallback
    }

    private static func doubleValue(for value: Any?) -> Double {
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let string = value as? String, let double = Double(string) {
            return double
        }
        return 0
    }

    private static func argumentSummary(from value: Any?) -> String {
        guard let object = value as? [String: Any], object.isEmpty == false else {
            return ""
        }
        return object.keys.sorted().map { key in
            "\(key)=\(displayText(for: object[key] ?? NSNull()))"
        }
        .joined(separator: ", ")
    }

    private static func displayText(for value: Any) -> String {
        if value is NSNull {
            return "null"
        }
        if let string = value as? String {
            return string
        }
        if let bool = value as? Bool {
            return bool ? "true" : "false"
        }
        if let number = value as? NSNumber {
            let doubleValue = number.doubleValue
            if doubleValue.isFinite, doubleValue.rounded(.towardZero) == doubleValue {
                return String(number.int64Value)
            }
            return String(doubleValue)
        }
        if JSONSerialization.isValidJSONObject(value),
           let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
           let string = String(data: data, encoding: .utf8)
        {
            return string
        }
        return String(describing: value)
    }

    private static func dataCorrupted(_ message: String) -> DecodingError {
        DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: message))
    }
}
