import Foundation

public enum RuntimeBatchRunValidationSeverity: String, Equatable, Sendable {
    case info
    case warning
    case error
}

public struct RuntimeBatchRunValidationMessageState: Identifiable, Equatable, Sendable {
    public let id: String
    public let severity: RuntimeBatchRunValidationSeverity
    public let field: String
    public let message: String

    public init(id: String, severity: RuntimeBatchRunValidationSeverity, field: String, message: String) {
        self.id = id
        self.severity = severity
        self.field = field
        self.message = message
    }
}

public struct RuntimeBatchRunModelInputState: Identifiable, Equatable, Sendable {
    public let id: String
    public let index: String
    public let repoID: String
    public let sourceLine: Int

    public init(index: String, repoID: String, sourceLine: Int) {
        self.id = "\(index):\(repoID)"
        self.index = index
        self.repoID = repoID
        self.sourceLine = sourceLine
    }
}

public struct RuntimeBatchRunConfigEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let value: String
    public let sourceLine: Int

    public init(key: String, value: String, sourceLine: Int) {
        self.id = "\(sourceLine):\(key)"
        self.key = key
        self.value = value
        self.sourceLine = sourceLine
    }
}

enum RuntimeBatchRunSetupParser {
    private static let supportedConfigKeys: Set<String> = [
        "bench_batch_factor",
        "bench_batch_size",
        "bench_context_length",
        "bench_generation_length",
        "bench_repeats",
        "bench_sample_size",
        "bench_suite",
        "continue_on_failure",
        "eval_batch_factor",
        "eval_dataset_id",
        "eval_sample_size",
        "eval_scoring_mode",
        "eval_suite",
        "judge_model",
        "judge_remote_server_id",
        "max_models",
        "melix_cli",
        "melix_home",
        "model_list",
        "output_root",
        "preflight",
        "restart_stack_per_model",
        "runtime_dir",
        "run_id",
        "service_instance_name",
        "start_index",
        "temp_root",
        "http_port",
    ]
    private static let secretKeySubstrings = ["api_key", "token", "secret", "password"]

    static func modelInputs(from text: String) -> [RuntimeBatchRunModelInputState] {
        var inputs: [RuntimeBatchRunModelInputState] = []
        var autoIndex = 1
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.isEmpty == false, line.hasPrefix("#") == false else {
                continue
            }

            let index: String
            let repoID: String
            if let separator = line.firstIndex(of: "|") {
                index = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
                repoID = line[line.index(after: separator)...].trimmingCharacters(in: .whitespacesAndNewlines)
            } else {
                index = String(format: "%02d", autoIndex)
                repoID = line
            }

            if index.isEmpty == false, repoID.isEmpty == false {
                inputs.append(RuntimeBatchRunModelInputState(index: index, repoID: repoID, sourceLine: lineNumber))
            }
            autoIndex += 1
        }
        return inputs
    }

    static func configEntries(from text: String) -> [RuntimeBatchRunConfigEntryState] {
        var entries: [RuntimeBatchRunConfigEntryState] = []
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            guard let parsed = parsedConfigLine(rawLine, lineNumber: lineNumber) else {
                continue
            }
            guard supportedConfigKeys.contains(parsed.key), embedsRawSecret(parsed.key) == false else {
                continue
            }
            entries.append(RuntimeBatchRunConfigEntryState(key: parsed.key, value: parsed.value, sourceLine: lineNumber))
        }
        return entries
    }

    static func validationMessages(modelsText: String, configText: String) -> [RuntimeBatchRunValidationMessageState] {
        var messages: [RuntimeBatchRunValidationMessageState] = []
        let modelInputs = modelInputs(from: modelsText)
        if modelInputs.isEmpty {
            messages.append(
                RuntimeBatchRunValidationMessageState(
                    id: "models-empty",
                    severity: .error,
                    field: "Model List",
                    message: "Add at least one model repository."
                )
            )
        }

        messages.append(contentsOf: modelValidationMessages(from: modelsText))
        messages.append(contentsOf: configValidationMessages(from: configText))
        return messages
    }

    static func canRequestPreflight(modelsText: String, configText: String) -> Bool {
        validationMessages(modelsText: modelsText, configText: configText).contains { $0.severity == .error } == false
    }

    static func summaryText(modelsText: String, configText: String) -> String {
        let modelCount = modelInputs(from: modelsText).count
        let configCount = configEntries(from: configText).count
        return "\(modelCount) \(modelCount == 1 ? "model" : "models") • \(configCount) config values"
    }

    private static func modelValidationMessages(from text: String) -> [RuntimeBatchRunValidationMessageState] {
        var messages: [RuntimeBatchRunValidationMessageState] = []
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.isEmpty == false, line.hasPrefix("#") == false else {
                continue
            }
            if let separator = line.firstIndex(of: "|") {
                let index = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
                let repoID = line[line.index(after: separator)...].trimmingCharacters(in: .whitespacesAndNewlines)
                if index.isEmpty || repoID.isEmpty {
                    messages.append(
                        RuntimeBatchRunValidationMessageState(
                            id: "models-line-\(lineNumber)",
                            severity: .error,
                            field: "Model List",
                            message: "Invalid model list line \(lineNumber); expected index | repo-id."
                        )
                    )
                }
            }
        }
        return messages
    }

    private static func configValidationMessages(from text: String) -> [RuntimeBatchRunValidationMessageState] {
        var messages: [RuntimeBatchRunValidationMessageState] = []
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let lineNumber = offset + 1
            var line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.isEmpty == false, line.hasPrefix("#") == false else {
                continue
            }
            if let comment = line.firstIndex(of: "#") {
                line = line[..<comment].trimmingCharacters(in: .whitespacesAndNewlines)
            }
            guard let separator = line.firstIndex(of: ":") else {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-line-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Invalid batch config line \(lineNumber); expected key: value."
                    )
                )
                continue
            }
            let key = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
            if key.isEmpty {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-line-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Invalid batch config line \(lineNumber); key is empty."
                    )
                )
                continue
            }
            let keyString = String(key)
            if embedsRawSecret(keyString) {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-secret-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Unsupported batch config key '\(keyString)' at line \(lineNumber); use stored credential ids instead of raw secrets."
                    )
                )
            } else if supportedConfigKeys.contains(keyString) == false {
                messages.append(
                    RuntimeBatchRunValidationMessageState(
                        id: "config-unsupported-\(lineNumber)",
                        severity: .error,
                        field: "Config",
                        message: "Unsupported batch config key '\(keyString)' at line \(lineNumber)."
                    )
                )
            }
        }
        return messages
    }

    private static func parsedConfigLine(
        _ rawLine: Substring,
        lineNumber: Int
    ) -> (key: String, value: String, sourceLine: Int)? {
        var line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard line.isEmpty == false, line.hasPrefix("#") == false else {
            return nil
        }
        if let comment = line.firstIndex(of: "#") {
            line = line[..<comment].trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard let separator = line.firstIndex(of: ":") else {
            return nil
        }
        let key = line[..<separator].trimmingCharacters(in: .whitespacesAndNewlines)
        let value = line[line.index(after: separator)...]
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
        guard key.isEmpty == false else {
            return nil
        }
        return (String(key), value, lineNumber)
    }

    private static func embedsRawSecret(_ key: String) -> Bool {
        let lowered = key.lowercased()
        return secretKeySubstrings.contains { lowered.contains($0) }
    }
}
