import Foundation
import MelixCLICore

public actor MelixSubprocessCLIWorkflowRunner: MelixCLIWorkflowRunning {
    private let cliExecutablePath: String
    private let environment: [String: String]
    private let processExecutor: any MelixCLIProcessExecuting

    public init(
        cliExecutablePath: String,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        processExecutor: any MelixCLIProcessExecuting = LiveMelixCLIProcessExecutor()
    ) {
        self.cliExecutablePath = cliExecutablePath
        self.environment = environment
        self.processExecutor = processExecutor
    }

    public nonisolated var surface: MelixCLIWorkflowSurface {
        .subprocess
    }

    public func run(_ command: MelixCLICommand) async throws -> String {
        let arguments = try arguments(for: command)
        do {
            return try await processExecutor.run(
                executablePath: cliExecutablePath,
                arguments: arguments,
                environment: environment
            )
        } catch let error as MelixCLIProcessExecutionError {
            switch error {
            case .nonZeroExit(_, _, let exitCode, let stderr):
                throw MelixCLIWorkflowError.processFailed(
                    commandID: command.workflowCommandID,
                    surface: .subprocess,
                    exitCode: exitCode,
                    stderr: stderr
                )
            case .launchFailed(_, let reason), .invalidOutput(_, let reason):
                throw MelixCLIWorkflowError.processFailed(
                    commandID: command.workflowCommandID,
                    surface: .subprocess,
                    exitCode: 1,
                    stderr: reason
                )
            }
        }
    }

    private func arguments(for command: MelixCLICommand) throws -> [String] {
        switch command {
        case .modelHubDownload(let options):
            var arguments = ["model", "hub", "download", "--repo-id", options.repoID, "--revision", options.revision]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .modelImport(let options):
            var arguments = [
                "model",
                "import",
                "--path",
                options.path,
                "--model-id",
                options.modelID,
            ]
            appendOptionalValue(options.modelKind, option: "--model-kind", to: &arguments)
            appendOptionalValue(options.revision, option: "--revision", to: &arguments)
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .modelRootsAdd(let options):
            var arguments = ["model", "roots", "add", "--path", options.path]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .modelRootsRemove(let options):
            var arguments = ["model", "roots", "remove", "--path", options.path]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .modelRootsMove(let options):
            var arguments = ["model", "roots", "move", "--path", options.path, "--index", String(options.index)]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .modelRootsRescan(let options):
            var arguments = ["model", "roots", "rescan"]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .serverSessionCreate(let options):
            var arguments = [
                "server",
                "session",
                "create",
                "--title",
                options.title,
                "--model-id",
                options.modelID,
                "--host",
                options.host,
                "--port",
                String(options.port),
                "--rate-limit-per-minute",
                String(options.rateLimitPerMinute),
                "--timeout-seconds",
                String(options.timeoutSeconds),
            ]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .serverSessionUpdate(let options):
            var arguments = [
                "server",
                "session",
                "update",
                "--server-session-id",
                options.serverSessionID,
            ]
            appendOptionalValue(options.title, option: "--title", to: &arguments)
            appendOptionalValue(options.modelID, option: "--model-id", to: &arguments)
            appendOptionalValue(options.host, option: "--host", to: &arguments)
            appendPositiveInt(options.port, option: "--port", to: &arguments)
            appendPositiveInt(options.rateLimitPerMinute, option: "--rate-limit-per-minute", to: &arguments)
            appendPositiveInt(options.timeoutSeconds, option: "--timeout-seconds", to: &arguments)
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .serverSessionRemove(let options):
            var arguments = ["server", "session", "remove", "--server-session-id", options.serverSessionID]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .serverSessionSelect(let options):
            var arguments = ["server", "session", "select", "--server-session-id", options.serverSessionID]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .serverStart(let options):
            return serverControlArguments(command: "start", options: options)
        case .serverPause(let options):
            return serverControlArguments(command: "pause", options: options)
        case .serverResume(let options):
            return serverControlArguments(command: "resume", options: options)
        case .serverWake(let options):
            return serverControlArguments(command: "wake", options: options)
        case .serverStop(let options):
            return serverControlArguments(command: "stop", options: options)
        case .serverSetIdlePolicy(let options):
            var arguments = [
                "server",
                "set-idle-policy",
                "--server-session-id",
                options.serverSessionID,
                "--auto-sleep",
                options.autoSleepEnabled ? "true" : "false",
                "--light-sleep-after",
                String(options.lightSleepAfterSeconds),
                "--deep-sleep-after",
                String(options.deepSleepAfterSeconds),
            ]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .loraTrain(let options):
            var arguments = [
                "lora",
                "train",
                "--model-id",
                options.modelID,
                "--adapter-name",
                options.adapterName,
            ]
            if options.datasetSourceKind == "hf_dataset" {
                appendOptionalValue(options.datasetURI, option: "--hf-dataset-path", to: &arguments)
            } else {
                appendOptionalValue(options.datasetURI, option: "--dataset-uri", to: &arguments)
            }
            appendOptionalValue(options.targetRepo, option: "--target-repo", to: &arguments)
            appendOptionalValue(options.trainingMode, option: "--training-mode", to: &arguments)
            appendLoraTrainParameters(options.parameters, to: &arguments)
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .loraActivate(let options):
            var arguments = [
                "lora",
                "activate",
                "--model-id",
                options.modelID,
                "--adapter-path",
                options.adapterPath,
            ]
            appendOptionalValue(options.derivedModelAlias, option: "--alias", to: &arguments)
            appendOptionalValue(options.activationMode, option: "--activation-mode", to: &arguments)
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .chatRun(let options):
            var arguments = [
                "chat",
                "run",
                "--model-id",
                options.modelID,
                "--message",
                options.message,
            ]
            appendOptionalValue(options.systemPrompt, option: "--system", to: &arguments)
            appendOptionalValue(options.serverSessionID, option: "--server-session-id", to: &arguments)
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .benchRun(let options):
            var arguments = ["bench", "run"]
            appendTarget(modelID: options.modelID, hfRepoID: options.hfRepoID, to: &arguments)
            appendRepeated(options.suites, option: "--suite", to: &arguments)
            appendRepeated(options.contextLengths.map(String.init), option: "--context-length", to: &arguments)
            appendPositiveUInt32(options.generationLength, option: "--generation-length", to: &arguments)
            appendRepeated(options.batchSizes.map(String.init), option: "--batch-size", to: &arguments)
            appendPositiveUInt32(options.repeats, option: "--repeats", to: &arguments)
            appendOptionalValue(options.cacheProfile, option: "--cache-profile", to: &arguments)
            appendOptionalValue(options.reasoningMode, option: "--reasoning-mode", to: &arguments)
            appendOptionalValue(options.structuredOutputMode, option: "--structured-output-mode", to: &arguments)
            appendParameters(options.parameters, to: &arguments)
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .benchExportCSV(let options):
            var arguments = ["bench", "export-csv", "--job-id", options.jobID, "--output", options.outputPath]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .benchMatrixRun(let options):
            var arguments = ["bench", "matrix", "run"]
            appendTarget(modelID: options.modelID, hfRepoID: options.hfRepoID, to: &arguments)
            appendOptionalValue(options.taskKind, option: "--task-kind", to: &arguments)
            appendRepeated(options.suites, option: "--suite", to: &arguments)
            appendRepeated(options.contextLengths.map(String.init), option: "--context-length", to: &arguments)
            appendRepeated(options.generationLengths.map(String.init), option: "--generation-length", to: &arguments)
            appendRepeated(options.batchSizes.map(String.init), option: "--batch-size", to: &arguments)
            appendRepeated(options.cacheProfiles, option: "--cache-profile", to: &arguments)
            appendRepeated(options.reasoningModes, option: "--reasoning-mode", to: &arguments)
            appendRepeated(options.structuredOutputModes, option: "--structured-output-mode", to: &arguments)
            appendRepeated(options.concurrencyLevels.map(String.init), option: "--concurrency", to: &arguments)
            appendPositiveUInt32(options.repeats, option: "--repeats", to: &arguments)
            appendPositiveUInt32(options.requests, option: "--requests", to: &arguments)
            appendPositiveUInt32(options.durationSeconds, option: "--duration-seconds", to: &arguments)
            if options.allowLargeMatrix {
                arguments.append("--allow-large-matrix")
            }
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .benchMatrixExportSummaryCSV(let options):
            var arguments = [
                "bench",
                "matrix",
                "export-summary-csv",
                "--job-id",
                options.jobID,
                "--output",
                options.outputPath,
            ]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .benchMatrixExportRequestsCSV(let options):
            var arguments = [
                "bench",
                "matrix",
                "export-requests-csv",
                "--job-id",
                options.jobID,
                "--output",
                options.outputPath,
            ]
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .evalRun(let options):
            var arguments = ["eval", "run"]
            appendTarget(modelID: options.modelID, hfRepoID: options.hfRepoID, to: &arguments)
            appendRepeated(options.suites, option: "--suite", to: &arguments)
            appendOptionalValue(options.datasetID, option: "--dataset-id", to: &arguments)
            appendPositiveUInt32(options.sampleSize, option: "--sample-size", to: &arguments)
            appendParameters(options.parameters, to: &arguments)
            appendJSONFlag(options.json, to: &arguments)
            return arguments
        case .evalExportSummaryCSV(let options):
            return evalExportArguments(command: "export-summary-csv", options: options)
        case .evalExportSamplesCSV(let options):
            return evalExportArguments(command: "export-samples-csv", options: options)
        case .evalExportSamplesJSONL(let options):
            return evalExportArguments(command: "export-samples-jsonl", options: options)
        default:
            throw MelixCLIWorkflowError.unsupportedCommand(
                commandID: command.workflowCommandID,
                surface: .subprocess
            )
        }
    }

    private func serverControlArguments(
        command: String,
        options: ServerControlOptions
    ) -> [String] {
        var arguments = ["server", command, "--server-session-id", options.serverSessionID]
        appendJSONFlag(options.json, to: &arguments)
        return arguments
    }

    private func evalExportArguments(
        command: String,
        options: EvalExportOptions
    ) -> [String] {
        var arguments = ["eval", command, "--job-id", options.jobID, "--output", options.outputPath]
        appendJSONFlag(options.json, to: &arguments)
        return arguments
    }

    private func appendTarget(
        modelID: String,
        hfRepoID: String,
        to arguments: inout [String]
    ) {
        appendOptionalValue(modelID, option: "--model-id", to: &arguments)
        appendOptionalValue(hfRepoID, option: "--repo-id", to: &arguments)
    }

    private func appendParameters(
        _ parameters: [String: String],
        to arguments: inout [String]
    ) {
        for key in parameters.keys.sorted() {
            guard let value = parameters[key], value.isEmpty == false else {
                continue
            }
            arguments.append("--\(key.replacingOccurrences(of: "_", with: "-"))")
            arguments.append(value)
        }
    }

    private func appendLoraTrainParameters(
        _ parameters: [String: String],
        to arguments: inout [String]
    ) {
        let booleanFlags: Set<String> = [
            "response_only",
            "mask_prompt",
            "gradient_checkpointing",
        ]
        for key in parameters.keys.sorted() {
            guard let value = parameters[key], value.isEmpty == false else {
                continue
            }
            let option = "--\(key.replacingOccurrences(of: "_", with: "-"))"
            if booleanFlags.contains(key) {
                if value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "true" {
                    arguments.append(option)
                }
                continue
            }
            arguments.append(option)
            arguments.append(value)
        }
    }

    private func appendRepeated(
        _ values: [String],
        option: String,
        to arguments: inout [String]
    ) {
        for value in values where value.isEmpty == false {
            arguments.append(option)
            arguments.append(value)
        }
    }

    private func appendOptionalValue(
        _ value: String,
        option: String,
        to arguments: inout [String]
    ) {
        guard value.isEmpty == false else {
            return
        }
        arguments.append(option)
        arguments.append(value)
    }

    private func appendPositiveInt(
        _ value: Int,
        option: String,
        to arguments: inout [String]
    ) {
        guard value > 0 else {
            return
        }
        arguments.append(option)
        arguments.append(String(value))
    }

    private func appendPositiveUInt32(
        _ value: UInt32,
        option: String,
        to arguments: inout [String]
    ) {
        guard value > 0 else {
            return
        }
        arguments.append(option)
        arguments.append(String(value))
    }

    private func appendJSONFlag(
        _ enabled: Bool,
        to arguments: inout [String]
    ) {
        if enabled {
            arguments.append("--json")
        }
    }
}
