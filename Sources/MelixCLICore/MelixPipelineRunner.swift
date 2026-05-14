import Dispatch
import Foundation
import MelixControlPlaneCore

private enum MelixPipelineArgumentValue {
    static func isBoolean(_ value: Any) -> Bool {
        guard let number = value as? NSNumber else {
            return value is Bool
        }
        return CFGetTypeID(number) == CFBooleanGetTypeID()
    }

    static func booleanString(_ value: Any) -> String? {
        guard isBoolean(value) else {
            return nil
        }
        if let bool = value as? Bool {
            return bool ? "true" : "false"
        }
        return (value as? NSNumber)?.boolValue == true ? "true" : "false"
    }

    static func booleanValue(_ value: Any) -> Bool? {
        guard isBoolean(value) else {
            return nil
        }
        if let bool = value as? Bool {
            return bool
        }
        return (value as? NSNumber)?.boolValue
    }
}

extension MelixCLIRunner {
    public func runPipeline(_ options: PipelineRunOptions) async throws -> String {
        let totalStart = DispatchTime.now()
        let pipeline = try MelixPipelineDocument.load(from: options.filePath)
        let inputs = try pipeline.inputs.merging(MelixPipelineDocument.loadInputs(from: options.inputsPath)) { _, override in
            override
        }
        let pipelineHash = try MelixPipelineHash.hash(pipeline.rawObject)
        let inputsHash = try MelixPipelineHash.hash(inputs)
        let traceID = options.traceID.isEmpty ? UUID().uuidString : options.traceID
        let receiptRoot = receiptRootURL(
            pipelineName: pipeline.name,
            traceID: traceID,
            overridePath: options.receiptDir
        )
        let stepsRoot = receiptRoot.appendingPathComponent("steps", isDirectory: true)
        let summaryURL = receiptRoot.appendingPathComponent("run.json")
        let fileManager = FileManager.default
        try fileManager.createDirectory(at: stepsRoot, withIntermediateDirectories: true)

        var context = MelixPipelineContext(
            inputs: inputs,
            allowUnresolvedStepReferences: options.dryRun
        )
        var stepSummaries: [[String: Any]] = []
        var metrics: [String: Double] = [
            "melix.pipeline.resume_skipped_count": 0,
            "melix.pipeline.failed_step_count": 0,
        ]
        var resumeSkippedCount = 0
        var failedStepCount = 0
        var pipelineStatus = options.dryRun ? "planned" : "succeeded"
        var rerunFromStepReached = options.fromStepID.isEmpty

        if options.fromStepID.isEmpty == false,
           pipeline.steps.contains(where: { $0.id == options.fromStepID }) == false
        {
            let error = MelixCLIError.runtime("--from-step \(options.fromStepID) does not match any pipeline step.")
            failedStepCount = 1
            metrics["melix.pipeline.failed_step_count"] = Double(failedStepCount)
            metrics["melix.pipeline.total_ms"] = elapsedMilliseconds(since: totalStart)
            _ = try writeRunSummary(
                runSummary(
                    pipeline: pipeline,
                    traceID: traceID,
                    status: "failed",
                    receiptRoot: receiptRoot,
                    summaryURL: summaryURL,
                    pipelineHash: pipelineHash,
                    inputsHash: inputsHash,
                    stepSummaries: stepSummaries,
                    metrics: metrics,
                    error: error
                ),
                to: summaryURL,
                metrics: &metrics
            )
            throw error
        }

        let priorSummary = try loadOptionalJSONObject(from: summaryURL)
        if options.resume || options.fromStepID.isEmpty == false {
            try validateResumeSummary(
                priorSummary,
                pipelineHash: pipelineHash,
                inputsHash: inputsHash
            )
        }

        do {
            for (index, step) in pipeline.steps.enumerated() {
                let receiptURL = stepsRoot.appendingPathComponent(
                    "\(String(format: "%03d", index + 1))-\(sanitizePathComponent(step.id)).json"
                )
                let stepStart = DispatchTime.now()
                try MelixPipelineCommandBuilder.validateSupportedCommand(named: step.command)
                let shouldRun = try context.shouldRun(when: step.when)
                let resolvedArguments: [String: Any]
                let command: MelixCLICommand?
                let commandID: String
                if shouldRun {
                    let referenceStart = DispatchTime.now()
                    resolvedArguments = try context.resolveObject(step.args) as? [String: Any] ?? [:]
                    metrics["melix.pipeline.reference_resolve_ms", default: 0] += elapsedMilliseconds(since: referenceStart)
                    let builtCommand = try MelixPipelineCommandBuilder.command(
                        named: step.command,
                        args: resolvedArguments
                    )
                    command = builtCommand
                    commandID = MelixCLICommandCodec.commandID(for: builtCommand)
                } else {
                    resolvedArguments = step.args
                    command = nil
                    commandID = step.command
                }
                let metadata = try stepReceiptMetadata(
                    step: step,
                    index: index,
                    commandID: commandID,
                    pipelineHash: pipelineHash,
                    inputsHash: inputsHash,
                    resolvedArguments: resolvedArguments
                )

                if options.fromStepID.isEmpty == false && rerunFromStepReached == false {
                    if step.id == options.fromStepID {
                        rerunFromStepReached = true
                    } else if let receipt = try loadOptionalJSONObject(from: receiptURL) {
                        try validateStepReceipt(
                            receipt,
                            step: step,
                            expectedMetadata: metadata,
                            allowedStatuses: options.dryRun ? ["planned", "skipped", "succeeded"] : ["succeeded", "skipped"]
                        )
                        context.setStepEnvelope(normalizedResultEnvelope(receipt), for: step.id)
                        stepSummaries.append(
                            stepSummary(
                                step,
                                status: "loaded",
                                receiptURL: receiptURL,
                                envelope: receipt
                            )
                        )
                        continue
                    } else {
                        throw MelixCLIError.runtime("Missing prior receipt for step \(step.id) before --from-step \(options.fromStepID).")
                    }
                }

                if options.resume,
                   options.fromStepID.isEmpty,
                   let receipt = try loadOptionalJSONObject(from: receiptURL),
                   receipt["status"] as? String == "succeeded"
                {
                    try validateStepReceipt(
                        receipt,
                        step: step,
                        expectedMetadata: metadata,
                        allowedStatuses: ["succeeded"]
                    )
                    context.setStepEnvelope(normalizedResultEnvelope(receipt), for: step.id)
                    resumeSkippedCount += 1
                    metrics["melix.pipeline.resume_skipped_count"] = Double(resumeSkippedCount)
                    stepSummaries.append(
                        stepSummary(
                            step,
                            status: "skipped",
                            receiptURL: receiptURL,
                            envelope: receipt
                        )
                    )
                    continue
                }

                guard shouldRun else {
                    let envelope = attachStepMetadata(
                        metadata,
                        to: try MelixPipelineReceipt.outputEnvelope(
                            commandID: commandID,
                            traceID: traceID,
                            status: "skipped",
                            result: ["reason": "when condition evaluated to false"],
                            metrics: [:]
                        )
                    )
                    try writeJSONObject(envelope, to: receiptURL, metrics: &metrics)
                    context.setStepEnvelope(envelope, for: step.id)
                    metrics["melix.pipeline.step_ms.\(step.id)"] = elapsedMilliseconds(since: stepStart)
                    stepSummaries.append(stepSummary(step, status: "skipped", receiptURL: receiptURL, envelope: envelope))
                    continue
                }

                guard let command else {
                    throw MelixCLIError.runtime("Pipeline step \(step.id) could not build command \(step.command).")
                }

                var envelope: [String: Any]
                if options.dryRun {
                    let plannedArguments = Self.redactedPublicArguments(try MelixCLICommandCodec.arguments(for: command))
                    envelope = try MelixPipelineReceipt.outputEnvelope(
                        commandID: commandID,
                        traceID: traceID,
                        status: "planned",
                        result: [
                            "arguments": plannedArguments,
                            "command": step.command,
                        ],
                        metrics: [:]
                    )
                } else {
                    let output = try await run(
                        MelixCLIInvocation(
                            command: command,
                            outputFormat: .jsonV1,
                            traceID: traceID
                        )
                    )
                    guard let parsedEnvelope = MelixPipelineJSON.object(from: output) else {
                        throw MelixCLIError.runtime("Step \(step.id) did not return a JSON envelope.")
                    }
                    envelope = normalizedResultEnvelope(parsedEnvelope)
                    context.setStepEnvelope(envelope, for: step.id)
                    try MelixPipelineChecks.validate(step.checks, envelope: envelope, context: context)
                }
                envelope = attachStepMetadata(metadata, to: envelope)

                try writeJSONObject(envelope, to: receiptURL, metrics: &metrics)
                context.setStepEnvelope(envelope, for: step.id)
                metrics["melix.pipeline.step_ms.\(step.id)"] = elapsedMilliseconds(since: stepStart)
                stepSummaries.append(
                    stepSummary(
                        step,
                        status: envelope["status"] as? String ?? "succeeded",
                        receiptURL: receiptURL,
                        envelope: envelope
                    )
                )
            }
        } catch {
            let error = melixPipelineError(from: error)
            failedStepCount = 1
            metrics["melix.pipeline.failed_step_count"] = Double(failedStepCount)
            pipelineStatus = "failed"
            if stepSummaries.count < pipeline.steps.count {
                let failedStep = pipeline.steps[stepSummaries.count]
                let receiptURL = stepsRoot.appendingPathComponent(
                    "\(String(format: "%03d", stepSummaries.count + 1))-\(sanitizePathComponent(failedStep.id)).json"
                )
                let envelope = try MelixPipelineReceipt.errorEnvelope(
                    commandID: failedStep.command,
                    traceID: traceID,
                    error: error
                )
                try writeJSONObject(envelope, to: receiptURL, metrics: &metrics)
                stepSummaries.append(stepSummary(failedStep, status: "failed", receiptURL: receiptURL, envelope: envelope))
            }
            metrics["melix.pipeline.total_ms"] = elapsedMilliseconds(since: totalStart)
            _ = try writeRunSummary(
                runSummary(
                    pipeline: pipeline,
                    traceID: traceID,
                    status: pipelineStatus,
                    receiptRoot: receiptRoot,
                    summaryURL: summaryURL,
                    pipelineHash: pipelineHash,
                    inputsHash: inputsHash,
                    stepSummaries: stepSummaries,
                    metrics: metrics,
                    error: error
                ),
                to: summaryURL,
                metrics: &metrics
            )
            throw error
        }

        guard options.fromStepID.isEmpty || rerunFromStepReached else {
            throw MelixCLIError.runtime("--from-step \(options.fromStepID) does not match any pipeline step.")
        }

        metrics["melix.pipeline.resume_skipped_count"] = Double(resumeSkippedCount)
        metrics["melix.pipeline.failed_step_count"] = Double(failedStepCount)
        metrics["melix.pipeline.total_ms"] = elapsedMilliseconds(since: totalStart)
        let summary = try writeRunSummary(
            runSummary(
                pipeline: pipeline,
                traceID: traceID,
                status: pipelineStatus,
                receiptRoot: receiptRoot,
                summaryURL: summaryURL,
                pipelineHash: pipelineHash,
                inputsHash: inputsHash,
                stepSummaries: stepSummaries,
                metrics: metrics
            ),
            to: summaryURL,
            metrics: &metrics
        )
        return try MelixCLIJSON.prettyString(summary)
    }

    private func melixPipelineError(from error: Error) -> MelixCLIError {
        if let error = error as? MelixCLIError {
            return error
        }
        if let localized = error as? LocalizedError,
           let description = localized.errorDescription,
           description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        {
            return .runtime(description)
        }
        return .runtime(String(describing: error))
    }

    private static func redactedPublicArguments(_ arguments: [String]) -> [String] {
        var redacted: [String] = []
        redacted.reserveCapacity(arguments.count)
        var shouldRedactNext = false
        for argument in arguments {
            if shouldRedactNext {
                redacted.append("<redacted>")
                shouldRedactNext = false
                continue
            }
            if argument == "--hf-token" {
                redacted.append(argument)
                shouldRedactNext = true
                continue
            }
            if argument.hasPrefix("--hf-token=") {
                redacted.append("--hf-token=<redacted>")
                continue
            }
            redacted.append(argument)
        }
        return redacted
    }

    private func receiptRootURL(
        pipelineName: String,
        traceID: String,
        overridePath: String
    ) -> URL {
        if overridePath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false {
            return URL(fileURLWithPath: overridePath, isDirectory: true)
        }
        return MelixHome(environment: environment).rootURL
            .appendingPathComponent("pipelines", isDirectory: true)
            .appendingPathComponent(sanitizePathComponent(pipelineName), isDirectory: true)
            .appendingPathComponent(sanitizePathComponent(traceID), isDirectory: true)
    }

    private func validateResumeSummary(
        _ summary: [String: Any]?,
        pipelineHash: String,
        inputsHash: String
    ) throws {
        guard let summary else {
            throw MelixCLIError.runtime("Cannot resume pipeline because no prior summary manifest exists.")
        }
        guard summary["pipeline_hash"] as? String == pipelineHash,
              summary["inputs_hash"] as? String == inputsHash
        else {
            throw MelixCLIError.runtime("Pipeline resume metadata does not match the current pipeline or inputs.")
        }
    }

    private func stepSummary(
        _ step: MelixPipelineStep,
        status: String,
        receiptURL: URL,
        envelope: [String: Any]? = nil
    ) -> [String: Any] {
        var summary: [String: Any] = [
            "id": step.id,
            "command": step.command,
            "status": status,
            "receipt_path": receiptURL.path,
        ]
        let artifactPaths = envelope.map(artifactPaths(from:)) ?? []
        if artifactPaths.isEmpty == false {
            summary["artifact_paths"] = artifactPaths
        }
        if let metadata = envelope?["pipeline_step"] as? [String: Any] {
            summary["command_id"] = metadata["command_id"]
            summary["args_hash"] = metadata["args_hash"]
        }
        return summary
    }

    private func stepReceiptMetadata(
        step: MelixPipelineStep,
        index: Int,
        commandID: String,
        pipelineHash: String,
        inputsHash: String,
        resolvedArguments: [String: Any]
    ) throws -> [String: Any] {
        [
            "schema_version": "melix.pipeline.step.v1",
            "step_id": step.id,
            "step_index": index + 1,
            "command": step.command,
            "command_id": commandID,
            "args_hash": try MelixPipelineHash.hash(resolvedArguments),
            "pipeline_hash": pipelineHash,
            "inputs_hash": inputsHash,
        ]
    }

    private func attachStepMetadata(
        _ metadata: [String: Any],
        to envelope: [String: Any]
    ) -> [String: Any] {
        var envelope = envelope
        envelope["pipeline_step"] = metadata
        return envelope
    }

    private func validateStepReceipt(
        _ receipt: [String: Any],
        step: MelixPipelineStep,
        expectedMetadata: [String: Any],
        allowedStatuses: Set<String>
    ) throws {
        guard receipt["schema_version"] as? String == "melix.cli.output.v1" else {
            throw MelixCLIError.runtime("Pipeline receipt for step \(step.id) is not a successful JSON v1 output envelope.")
        }
        let status = receipt["status"] as? String ?? ""
        guard allowedStatuses.contains(status) else {
            throw MelixCLIError.runtime("Pipeline receipt for step \(step.id) is not reusable because status is \(status).")
        }
        guard MelixPipelineJSON.valuesEqual(receipt["command_id"], expectedMetadata["command_id"]) else {
            throw MelixCLIError.runtime("Pipeline receipt for step \(step.id) does not match the current command \(step.command).")
        }
        guard let metadata = receipt["pipeline_step"] as? [String: Any] else {
            throw MelixCLIError.runtime("Pipeline receipt for step \(step.id) is missing pipeline step metadata.")
        }
        for key in ["schema_version", "step_id", "step_index", "command", "command_id", "args_hash", "pipeline_hash", "inputs_hash"] {
            guard MelixPipelineJSON.valuesEqual(metadata[key], expectedMetadata[key]) else {
                throw MelixCLIError.runtime("Pipeline receipt for step \(step.id) does not match the current pipeline metadata.")
            }
        }
    }

    private func artifactPaths(from envelope: [String: Any]) -> [String] {
        var paths: [String] = []
        if let artifacts = envelope["artifacts"] as? [[String: Any]] {
            for artifact in artifacts {
                appendArtifactPath(artifact["path"], to: &paths)
            }
        }
        if let result = envelope["result"] {
            collectArtifactPaths(from: result, into: &paths)
        }
        return paths
    }

    private func collectArtifactPaths(from value: Any, into paths: inout [String]) {
        if let object = value as? [String: Any] {
            for key in ["artifact_path", "bundle_path", "managed_model_path", "output_path", "report_path"] {
                appendArtifactPath(object[key], to: &paths)
            }
            for nested in object.values {
                collectArtifactPaths(from: nested, into: &paths)
            }
            return
        }
        if let array = value as? [Any] {
            for item in array {
                collectArtifactPaths(from: item, into: &paths)
            }
        }
    }

    private func appendArtifactPath(_ value: Any?, to paths: inout [String]) {
        guard let path = value as? String,
              path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false,
              paths.contains(path) == false
        else {
            return
        }
        paths.append(path)
    }

    private func normalizedResultEnvelope(_ envelope: [String: Any]) -> [String: Any] {
        guard var result = envelope["result"] as? [String: Any],
              (result["output_path"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false
        else {
            return envelope
        }
        for alias in ["artifact_path", "bundle_path", "managed_model_path", "report_path"] {
            guard let outputPath = result[alias] as? String,
                  outputPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            else {
                continue
            }
            result["output_path"] = outputPath
            var normalized = envelope
            normalized["result"] = result
            return normalized
        }
        return envelope
    }

    private func runSummary(
        pipeline: MelixPipelineDocument,
        traceID: String,
        status: String,
        receiptRoot: URL,
        summaryURL: URL,
        pipelineHash: String,
        inputsHash: String,
        stepSummaries: [[String: Any]],
        metrics: [String: Double],
        error: MelixCLIError? = nil
    ) -> [String: Any] {
        var summary: [String: Any] = [
            "schema_version": "melix.pipeline.run.v1",
            "name": pipeline.name,
            "trace_id": traceID,
            "status": status,
            "receipt_dir": receiptRoot.path,
            "summary_path": summaryURL.path,
            "pipeline_hash": pipelineHash,
            "inputs_hash": inputsHash,
            "steps": stepSummaries,
            "metrics": metrics,
        ]
        if let error {
            summary["error"] = [
                "code": MelixCLIJSONEnvelope.code(for: error),
                "message": error.errorDescription ?? "\(error)",
            ]
        }
        return summary
    }

    private func writeRunSummary(
        _ summary: [String: Any],
        to url: URL,
        metrics: inout [String: Double]
    ) throws -> [String: Any] {
        let receiptWriteMS = metrics["melix.pipeline.receipt_write_ms", default: 0]
        let placeholder = MelixCLIJSONMetricPatch.makePlaceholder(metricName: "melix.pipeline.receipt_write_ms")
        var provisionalMetrics = metrics.reduce(into: [String: Any]()) { partial, item in
            partial[item.key] = item.value
        }
        provisionalMetrics["melix.pipeline.receipt_write_ms"] = placeholder.token
        var provisional = summary
        provisional["metrics"] = provisionalMetrics
        let start = DispatchTime.now()
        let data = try JSONSerialization.data(withJSONObject: provisional, options: [.prettyPrinted, .sortedKeys])
        let placeholderRange = try MelixCLIJSONMetricPatch.placeholderRange(in: data, placeholder: placeholder)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: url, options: .atomic)
        metrics["melix.pipeline.receipt_write_ms"] = receiptWriteMS + elapsedMilliseconds(since: start)

        let replacementData = try MelixCLIJSONMetricPatch.paddedLiteralData(
            for: metrics["melix.pipeline.receipt_write_ms", default: 0],
            byteCount: placeholderRange.count
        )
        let handle = try FileHandle(forUpdating: url)
        defer { try? handle.close() }
        try handle.seek(toOffset: UInt64(placeholderRange.lowerBound))
        try handle.write(contentsOf: replacementData)

        var persisted = summary
        persisted["metrics"] = metrics
        return persisted
    }

    private func writeJSONObject(
        _ object: [String: Any],
        to url: URL,
        metrics: inout [String: Double]
    ) throws {
        let start = DispatchTime.now()
        let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: url, options: .atomic)
        metrics["melix.pipeline.receipt_write_ms", default: 0] += elapsedMilliseconds(since: start)
    }
}

private struct MelixPipelineDocument {
    let name: String
    let inputs: [String: Any]
    let steps: [MelixPipelineStep]
    let rawObject: [String: Any]

    static func load(from path: String) throws -> MelixPipelineDocument {
        guard path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            throw MelixCLIError.missingRequired("--file is required for melix pipeline run.")
        }
        let data: Data
        do {
            data = try Data(contentsOf: URL(fileURLWithPath: path))
        } catch {
            throw MelixCLIError.runtime("Failed to read pipeline file \(path): \((error as NSError).localizedDescription)")
        }
        let jsonObject: Any
        do {
            jsonObject = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.usage("Pipeline file is not valid JSON: \((error as NSError).localizedDescription)")
        }
        guard let object = jsonObject as? [String: Any] else {
            throw MelixCLIError.usage("Pipeline file must be a JSON object.")
        }
        guard object["schema_version"] as? String == "melix.pipeline.v1" else {
            throw MelixCLIError.usage("Pipeline schema_version must be melix.pipeline.v1.")
        }
        guard let name = object["name"] as? String,
              name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        else {
            throw MelixCLIError.missingRequired("Pipeline name is required.")
        }
        let inputs: [String: Any]
        if let rawInputs = object["inputs"] {
            guard let inputObject = rawInputs as? [String: Any] else {
                throw MelixCLIError.usage("Pipeline inputs must be a JSON object.")
            }
            inputs = inputObject
        } else {
            inputs = [:]
        }
        guard let stepObjects = object["steps"] as? [[String: Any]],
              stepObjects.isEmpty == false
        else {
            throw MelixCLIError.missingRequired("Pipeline steps must contain at least one step.")
        }
        let steps = try stepObjects.map(MelixPipelineStep.init(object:))
        let duplicateIDs = Dictionary(grouping: steps.map(\.id), by: { $0 }).filter { $0.value.count > 1 }.keys
        guard duplicateIDs.isEmpty else {
            throw MelixCLIError.usage("Pipeline step IDs must be unique: \(duplicateIDs.sorted().joined(separator: ", ")).")
        }
        return MelixPipelineDocument(name: name, inputs: inputs, steps: steps, rawObject: object)
    }

    static func loadInputs(from path: String) throws -> [String: Any] {
        guard path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            return [:]
        }
        let data: Data
        do {
            data = try Data(contentsOf: URL(fileURLWithPath: path))
        } catch {
            throw MelixCLIError.runtime("Failed to read pipeline inputs file \(path): \((error as NSError).localizedDescription)")
        }
        let jsonObject: Any
        do {
            jsonObject = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw MelixCLIError.usage("Pipeline inputs file is not valid JSON: \((error as NSError).localizedDescription)")
        }
        guard let object = jsonObject as? [String: Any] else {
            throw MelixCLIError.usage("Pipeline inputs file must be a JSON object.")
        }
        return object
    }
}

private struct MelixPipelineStep {
    let id: String
    let command: String
    let args: [String: Any]
    let when: [String: Any]?
    let checks: [String: Any]?

    init(object: [String: Any]) throws {
        guard let id = object["id"] as? String,
              id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        else {
            throw MelixCLIError.missingRequired("Pipeline step id is required.")
        }
        guard let command = object["command"] as? String,
              command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        else {
            throw MelixCLIError.missingRequired("Pipeline step \(id) command is required.")
        }
        self.id = id
        self.command = command
        if let rawArgs = object["args"] {
            guard let args = rawArgs as? [String: Any] else {
                throw MelixCLIError.usage("Pipeline step \(id) args must be a JSON object.")
            }
            self.args = args
        } else {
            self.args = [:]
        }
        if let rawWhen = object["when"] {
            guard let when = rawWhen as? [String: Any] else {
                throw MelixCLIError.usage("Pipeline step \(id) when must be a JSON object.")
            }
            self.when = when
        } else {
            self.when = nil
        }
        if let rawChecks = object["checks"] {
            guard let checks = rawChecks as? [String: Any] else {
                throw MelixCLIError.usage("Pipeline step \(id) checks must be a JSON object.")
            }
            try MelixPipelineChecks.validateSchema(checks, stepID: id)
            self.checks = checks
        } else {
            self.checks = nil
        }
    }
}

private struct MelixPipelineContext {
    let inputs: [String: Any]
    let allowUnresolvedStepReferences: Bool
    private var stepEnvelopes: [String: [String: Any]] = [:]

    init(
        inputs: [String: Any],
        allowUnresolvedStepReferences: Bool = false
    ) {
        self.inputs = inputs
        self.allowUnresolvedStepReferences = allowUnresolvedStepReferences
    }

    mutating func setStepEnvelope(_ envelope: [String: Any], for stepID: String) {
        stepEnvelopes[stepID] = envelope
    }

    func shouldRun(when: [String: Any]?) throws -> Bool {
        guard let when else {
            return true
        }
        guard let inputName = when["input"] as? String,
              let expected = when["equals"]
        else {
            throw MelixCLIError.usage("Pipeline when clauses support only {\"input\":\"name\",\"equals\":value}.")
        }
        let actual = inputs[inputName]
        return MelixPipelineJSON.valuesEqual(actual, expected)
    }

    func resolveObject(_ value: Any) throws -> Any {
        if let string = value as? String {
            return try resolveString(string)
        }
        if let array = value as? [Any] {
            return try array.map { try resolveObject($0) }
        }
        if let object = value as? [String: Any] {
            var resolved: [String: Any] = [:]
            for (key, item) in object {
                resolved[key] = try resolveObject(item)
            }
            return resolved
        }
        return value
    }

    func resolveString(_ value: String) throws -> Any {
        let matches = MelixPipelineReference.matches(in: value)
        guard matches.isEmpty == false else {
            return value
        }
        if matches.count == 1,
           matches[0].fullRange.lowerBound == value.startIndex,
           matches[0].fullRange.upperBound == value.endIndex
        {
            return try valueAtReference(matches[0].expression)
        }
        var rendered = value
        for match in matches.reversed() {
            let replacement = try stringValue(valueAtReference(match.expression))
            rendered.replaceSubrange(match.fullRange, with: replacement)
        }
        return rendered
    }

    func valueAtReference(_ expression: String) throws -> Any {
        if expression.hasPrefix("inputs.") {
            let path = String(expression.dropFirst("inputs.".count))
            return try value(at: path.components(separatedBy: "."), in: inputs, reference: expression)
        }
        if expression.hasPrefix("steps.") {
            let remainder = String(expression.dropFirst("steps.".count))
            let pieces = remainder.components(separatedBy: ".")
            guard let stepID = pieces.first, stepID.isEmpty == false else {
                throw MelixCLIError.usage("Invalid pipeline reference ${\(expression)}.")
            }
            guard let envelope = stepEnvelopes[stepID] else {
                if allowUnresolvedStepReferences {
                    return "${\(expression)}"
                }
                throw MelixCLIError.runtime("Pipeline reference ${\(expression)} points to missing step \(stepID).")
            }
            do {
                return try value(at: Array(pieces.dropFirst()), in: envelope, reference: expression)
            } catch {
                if allowUnresolvedStepReferences {
                    return "${\(expression)}"
                }
                throw error
            }
        }
        throw MelixCLIError.usage("Unsupported pipeline reference ${\(expression)}.")
    }

    private func value(at path: [String], in object: Any, reference: String) throws -> Any {
        guard path.isEmpty == false else {
            return object
        }
        var current: Any = object
        for part in path {
            if let dictionary = current as? [String: Any],
               let next = dictionary[part]
            {
                current = next
                continue
            }
            if let array = current as? [Any],
               let index = Int(part),
               array.indices.contains(index)
            {
                current = array[index]
                continue
            }
            throw MelixCLIError.runtime("Pipeline reference ${\(reference)} could not be resolved.")
        }
        return current
    }

    private func stringValue(_ value: Any) throws -> String {
        if let string = value as? String {
            return string
        }
        if let bool = MelixPipelineArgumentValue.booleanString(value) {
            return bool
        }
        if let number = value as? NSNumber {
            return number.stringValue
        }
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }
}

private enum MelixPipelineCommandBuilder {
    static func validateSupportedCommand(named name: String) throws {
        guard supportedCommandNames.contains(name) else {
            throw MelixCLIError.usage("Unsupported pipeline command \(name).")
        }
    }

    static func command(named name: String, args: [String: Any]) throws -> MelixCLICommand {
        try validateSupportedCommand(named: name)
        switch name {
        case "estimate.import":
            return .estimateImport(
                EstimateImportOptions(
                    repoID: try requiredString("repo_id", args),
                    targetKind: string("target_kind", args) ?? "import",
                    targetInputs: parameters(args, excluding: [
                        "repo_id",
                        "target_kind",
                    ])
                )
            )
        case "convert":
            return .convert(
                ConvertOptions(
                    modelID: try requiredString("model_id", args),
                    outputDir: string("output_dir", args) ?? "",
                    targetFormat: string("target_format", args) ?? "melix_model_bundle"
                )
            )
        case "quantize":
            return .quantize(
                QuantizeOptions(
                    modelID: try requiredString("model_id", args),
                    outputDir: string("output_dir", args) ?? "",
                    quantProfileID: string("quant_profile_id", args) ?? "",
                    weightQuant: string("weight_quant", args) ?? "",
                    kvQuant: string("kv_quant", args) ?? "",
                    quantizationMode: try quantizationMode(args),
                    sourceArtifactKind: try sourceArtifactKind(args),
                    sourceArtifactPath: string("source_artifact_path", args) ?? "",
                    quantizationBackend: try quantizationBackend(args),
                    mlxLMQBits: try mlxLMIntegerString("mlx_lm_q_bits", args),
                    mlxLMQGroupSize: try mlxLMIntegerString("mlx_lm_q_group_size", args),
                    mlxLMQMode: try mlxLMQMode(args),
                    calibrationDatasetURI: string("calibration_dataset_uri", args) ?? "",
                    qualityDelta: string("quality_delta", args) ?? "",
                    latencyDelta: string("latency_delta", args) ?? "",
                    localInferenceSmokeMode: try localInferenceSmokeMode(args),
                    localInferenceSmokePrompt: string("local_inference_smoke_prompt", args) ?? ""
                )
            )
        case "upload":
            return .upload(
                UploadOptions(
                    modelID: try requiredString("model_id", args),
                    outputDir: string("output_dir", args) ?? "",
                    targetRepo: try requiredString("target_repo", args),
                    artifactPath: string("artifact_path", args) ?? "",
                    artifactKind: string("artifact_kind", args) ?? "",
                    artifactManifestPath: string("artifact_manifest_path", args) ?? "",
                    publishBackend: string("publish_backend", args) ?? "",
                    localPublishRoot: string("local_publish_root", args) ?? ""
                )
            )
        case "model.import":
            return .modelImport(
                ModelImportOptions(
                    path: try requiredString("path", args),
                    modelID: try requiredString("model_id", args),
                    modelKind: string("model_kind", args) ?? "text",
                    revision: string("revision", args) ?? "main"
                )
            )
        case "model.hub.download":
            return .modelHubDownload(
                ModelHubDownloadOptions(
                    repoID: try requiredString("repo_id", args),
                    revision: string("revision", args) ?? "main",
                    hfToken: string("hf_token", args) ?? ""
                )
            )
        case "model.inspect":
            return .modelInspect(
                ModelInspectOptions(
                    modelID: try requiredString("model_id", args)
                )
            )
        case "model.roots.rescan":
            return .modelRootsRescan(ModelRootsRescanOptions())
        case "dataset.hub.download":
            return .datasetHubDownload(
                DatasetHubDownloadOptions(
                    repoID: try requiredString("repo_id", args),
                    revision: string("revision", args) ?? "main",
                    hfToken: string("hf_token", args) ?? ""
                )
            )
        case "server.session.update":
            return .serverSessionUpdate(
                ServerSessionUpdateOptions(
                    serverSessionID: string("server_session_id", args) ?? ServerSessionRuntimeStore.defaultServerSessionID,
                    title: string("title", args) ?? "",
                    defaultModelID: string("default_model_id", args) ?? "",
                    servedModelIDs: try firstStringArray(["served_model_ids"], args),
                    host: string("host", args) ?? "",
                    port: try int("port", args) ?? 0,
                    rateLimitPerMinute: try int("rate_limit_per_minute", args) ?? 0,
                    timeoutSeconds: try int("timeout_seconds", args) ?? 0,
                    modelIdleTimeoutSeconds: try int("model_idle_timeout_seconds", args) ?? 0,
                    accelerationMode: string("acceleration_mode", args) ?? "",
                    draftModelID: string("draft_model_id", args) ?? "",
                    numDraftTokens: try int("num_draft_tokens", args) ?? 0
                )
            )
        case "server.session.select":
            return .serverSessionSelect(
                ServerSessionIDOptions(
                    serverSessionID: string("server_session_id", args) ?? ServerSessionRuntimeStore.defaultServerSessionID
                )
            )
        case "server.start":
            return .serverStart(
                ServerControlOptions(
                    serverSessionID: string("server_session_id", args) ?? ServerSessionRuntimeStore.defaultServerSessionID
                )
            )
        case "chat.run":
            return .chatRun(
                ChatRunOptions(
                    modelID: try requiredString("model_id", args),
                    message: try requiredString("message", args),
                    systemPrompt: string("system", args) ?? string("system_prompt", args) ?? "",
                    serverSessionID: string("server_session_id", args) ?? ServerSessionRuntimeStore.defaultServerSessionID
                )
            )
        case "lora.train":
            return .loraTrain(
                LoraTrainOptions(
                    modelID: try requiredString("model_id", args),
                    datasetSourceKind: datasetSourceKind(args),
                    datasetURI: try datasetURI(args),
                    adapterName: try requiredString("adapter_name", args),
                    targetRepo: string("target_repo", args) ?? "",
                    trainingMode: string("training_mode", args) ?? "",
                    parameters: parameters(args, excluding: [
                        "model_id",
                        "dataset_uri",
                        "hf_dataset_path",
                        "adapter_name",
                        "target_repo",
                        "training_mode",
                    ])
                )
            )
        case "alignment.train":
            return .alignmentTrain(
                AlignmentTrainOptions(
                    modelID: try requiredString("model_id", args),
                    datasetSourceKind: datasetSourceKind(args),
                    datasetURI: try datasetURI(args),
                    adapterName: try requiredString("adapter_name", args),
                    targetRepo: string("target_repo", args) ?? "",
                    algorithm: try alignmentAlgorithm(args),
                    parameters: parameters(args, excluding: [
                        "model_id",
                        "dataset_uri",
                        "hf_dataset_path",
                        "dataset_source_kind",
                        "adapter_name",
                        "target_repo",
                        "algorithm",
                        "alignment_algorithm",
                        "training_mode",
                    ])
                )
            )
        case "lora.activate":
            return .loraActivate(
                LoraActivateOptions(
                    modelID: try requiredString("model_id", args),
                    adapterPath: try requiredString("adapter_path", args),
                    derivedModelAlias: string("derived_model_alias", args) ?? string("alias", args) ?? "",
                    activationMode: string("activation_mode", args) ?? ""
                )
            )
        case "lora.publish":
            return try .loraPublish(loraPublishOptions(args))
        case "bench.run":
            return .benchRun(
                BenchRunOptions(
                    modelID: string("model_id", args) ?? "",
                    hfRepoID: string("repo_id", args) ?? "",
                    suites: try firstStringArray(["suites", "suite"], args),
                    contextLengths: try firstUInt32Array(["context_lengths", "context_length"], args),
                    generationLength: try uint32("generation_length", args) ?? 0,
                    batchSizes: try firstUInt32Array(["batch_sizes", "batch_size"], args),
                    repeats: try uint32("repeats", args) ?? 1,
                    cacheProfile: string("cache_profile", args) ?? "",
                    reasoningMode: string("reasoning_mode", args) ?? "",
                    structuredOutputMode: string("structured_output_mode", args) ?? "",
                    parameters: parameters(args, excluding: [
                        "model_id",
                        "repo_id",
                        "suites",
                        "suite",
                        "context_lengths",
                        "context_length",
                        "generation_length",
                        "batch_sizes",
                        "batch_size",
                        "repeats",
                        "cache_profile",
                        "reasoning_mode",
                        "structured_output_mode",
                    ])
                )
            )
        case "bench.matrix.run":
            return .benchMatrixRun(
                BenchMatrixRunOptions(
                    modelID: string("model_id", args) ?? "",
                    hfRepoID: string("repo_id", args) ?? "",
                    taskKind: string("task_kind", args) ?? "",
                    suites: try firstStringArray(["suites", "suite"], args),
                    contextLengths: try firstUInt32Array(["context_lengths", "context_length"], args),
                    generationLengths: try firstUInt32Array(["generation_lengths", "generation_length"], args),
                    batchSizes: try firstUInt32Array(["batch_sizes", "batch_size"], args),
                    cacheProfiles: try firstStringArray(["cache_profiles", "cache_profile"], args),
                    reasoningModes: try firstStringArray(["reasoning_modes", "reasoning_mode"], args),
                    structuredOutputModes: try firstStringArray(["structured_output_modes", "structured_output_mode"], args),
                    concurrencyLevels: try firstUInt32Array(["concurrency_levels", "concurrency"], args),
                    repeats: try uint32("repeats", args) ?? 1,
                    requests: try uint32("requests", args) ?? 0,
                    durationSeconds: try uint32("duration_seconds", args) ?? 0,
                    allowLargeMatrix: try bool("allow_large_matrix", args) ?? false
                )
            )
        case "bench.export-csv":
            return .benchExportCSV(BenchExportCSVOptions(jobID: try requiredString("job_id", args), outputPath: try requiredString("output", args)))
        case "bench.matrix.export-summary-csv":
            return .benchMatrixExportSummaryCSV(BenchExportCSVOptions(jobID: try requiredString("job_id", args), outputPath: try requiredString("output", args)))
        case "bench.matrix.export-requests-csv":
            return .benchMatrixExportRequestsCSV(BenchExportCSVOptions(jobID: try requiredString("job_id", args), outputPath: try requiredString("output", args)))
        case "eval.run":
            return .evalRun(
                EvalRunOptions(
                    modelID: string("model_id", args) ?? "",
                    hfRepoID: string("repo_id", args) ?? "",
                    suites: try firstStringArray(["suites", "suite"], args),
                    datasetID: string("dataset_id", args) ?? "",
                    sampleSize: try uint32("sample_size", args) ?? 0,
                    source: evaluationSource(args),
                    fieldMapping: evaluationFieldMapping(args),
                    profile: try evaluationProfile(args),
                    parameters: parameters(args, excluding: [
                        "model_id",
                        "repo_id",
                        "suites",
                        "suite",
                        "dataset_id",
                        "sample_size",
                        "source_csv",
                        "source_jsonl",
                        "hf_dataset_path",
                        "hf_dataset_name",
                        "hf_dataset_revision",
                        "hf_dataset_split",
                        "field_system_path",
                        "field_input_text_path",
                        "field_target_path",
                        "field_sample_id_path",
                        "profile_type",
                        "result_kind",
                        "extraction_mode",
                        "threshold",
                        "output_schema_json",
                        "ignored_paths",
                        "eval_prompt",
                        "eval_prompt_file",
                        "eval_prompt_id",
                        "eval_prompt_revision",
                    ]),
                    evalPromptID: string("eval_prompt_id", args) ?? "",
                    evalPromptRevisionID: string("eval_prompt_revision", args) ?? "",
                    evalPrompt: string("eval_prompt", args) ?? "",
                    evalPromptFile: string("eval_prompt_file", args) ?? ""
                )
            )
        case "eval.compare":
            return .evalCompare(
                EvalCompareOptions(
                    modelID: string("model_id", args) ?? "",
                    hfRepoID: string("repo_id", args) ?? "",
                    targetModelIDs: try firstStringArray(["target_model_ids", "target_model_id"], args),
                    targetAdapterManifestPaths: try firstStringArray(["target_adapters", "target_adapter"], args),
                    suites: try firstStringArray(["suites", "suite"], args),
                    datasetID: string("dataset_id", args) ?? "",
                    sampleSize: try uint32("sample_size", args) ?? 0,
                    source: evaluationSource(args),
                    fieldMapping: evaluationFieldMapping(args),
                    profile: try evaluationProfile(args),
                    parameters: parameters(args, excluding: [
                        "model_id",
                        "repo_id",
                        "target_model_ids",
                        "target_model_id",
                        "target_adapters",
                        "target_adapter",
                        "suites",
                        "suite",
                        "dataset_id",
                        "sample_size",
                    ])
                )
            )
        case "eval.export-summary-csv":
            return .evalExportSummaryCSV(EvalExportOptions(jobID: try requiredString("job_id", args), outputPath: try requiredString("output", args)))
        case "eval.export-samples-csv":
            return .evalExportSamplesCSV(EvalExportOptions(jobID: try requiredString("job_id", args), outputPath: try requiredString("output", args)))
        case "eval.export-samples-jsonl":
            return .evalExportSamplesJSONL(EvalExportOptions(jobID: try requiredString("job_id", args), outputPath: try requiredString("output", args)))
        default:
            throw MelixCLIError.usage("Unsupported pipeline command \(name).")
        }
    }

    private static let supportedCommandNames: Set<String> = [
        "estimate.import",
        "convert",
        "quantize",
        "upload",
        "model.import",
        "model.hub.download",
        "model.inspect",
        "model.roots.rescan",
        "dataset.hub.download",
        "server.session.update",
        "server.session.select",
        "server.start",
        "chat.run",
        "lora.train",
        "alignment.train",
        "lora.activate",
        "lora.publish",
        "bench.run",
        "bench.matrix.run",
        "bench.export-csv",
        "bench.matrix.export-summary-csv",
        "bench.matrix.export-requests-csv",
        "eval.run",
        "eval.compare",
        "eval.export-summary-csv",
        "eval.export-samples-csv",
        "eval.export-samples-jsonl",
    ]

    private static func alignmentAlgorithm(_ args: [String: Any]) throws -> String {
        let algorithm = (string("algorithm", args) ?? string("alignment_algorithm", args) ?? string("training_mode", args) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard algorithm.isEmpty == false else {
            throw MelixCLIError.missingRequired("Pipeline command argument algorithm is required.")
        }
        guard ["dpo", "orpo", "cpo", "grpo", "rlhf"].contains(algorithm) else {
            throw MelixCLIError.usage("Pipeline command argument algorithm must be one of: dpo, orpo, cpo, grpo, rlhf.")
        }
        return algorithm
    }

    private static func quantizationMode(_ args: [String: Any]) throws -> String {
        let mode = (string("quantization_mode", args) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard mode.isEmpty || MelixQuantizationAllowedValues.quantizationModes.contains(mode) else {
            throw MelixCLIError.usage(
                "Pipeline command argument quantization_mode must be one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.quantizationModes))."
            )
        }
        return mode
    }

    private static func sourceArtifactKind(_ args: [String: Any]) throws -> String {
        let kind = (string("source_artifact_kind", args) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard kind.isEmpty || MelixQuantizationAllowedValues.sourceArtifactKinds.contains(kind) else {
            throw MelixCLIError.usage(
                "Pipeline command argument source_artifact_kind must be one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.sourceArtifactKinds))."
            )
        }
        return kind
    }

    private static func quantizationBackend(_ args: [String: Any]) throws -> String {
        let backend = (string("quantization_backend", args) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard backend.isEmpty || MelixQuantizationAllowedValues.quantizationBackends.contains(backend) else {
            throw MelixCLIError.usage(
                "Pipeline command argument quantization_backend must be one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.quantizationBackends))."
            )
        }
        return backend
    }

    private static func mlxLMQMode(_ args: [String: Any]) throws -> String {
        let mode = (string("mlx_lm_q_mode", args) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard mode.isEmpty || MelixQuantizationAllowedValues.mlxLMQModes.contains(mode) else {
            throw MelixCLIError.usage(
                "Pipeline command argument mlx_lm_q_mode must be one of: \(MelixQuantizationAllowedValues.renderedList(MelixQuantizationAllowedValues.mlxLMQModes))."
            )
        }
        return mode
    }

    private static func mlxLMIntegerString(_ key: String, _ args: [String: Any]) throws -> String {
        let value = (string(key, args) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.isEmpty || Int(value) != nil else {
            throw MelixCLIError.usage("Pipeline command argument \(key) must be an integer.")
        }
        return value
    }

    private static func localInferenceSmokeMode(_ args: [String: Any]) throws -> String {
        let mode = (string("local_inference_smoke_mode", args) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard mode.isEmpty || ["structural", "runtime_generate"].contains(mode) else {
            throw MelixCLIError.usage("Pipeline command argument local_inference_smoke_mode must be one of: structural, runtime_generate.")
        }
        return mode
    }

    private static func loraPublishOptions(_ args: [String: Any]) throws -> LoraPublishOptions {
        let modelID = try requiredString("model_id", args)
        let targetRepo = try requiredString("target_repo", args)
        let exportKind = try loraPublishExportKind(args)
        let adapterPath = (string("adapter_path", args) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let mergedModelPath = (string("merged_model_path", args) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let manifestPath = (string("manifest_path", args) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let artifactPath = (string("artifact_path", args) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let selectedCount = [adapterPath, mergedModelPath, manifestPath, artifactPath]
            .filter { $0.isEmpty == false }
            .count
        guard selectedCount == 1 else {
            throw MelixCLIError.missingRequired(
                "Exactly one of adapter_path, merged_model_path, manifest_path, or artifact_path is required for pipeline command lora.publish."
            )
        }

        if adapterPath.isEmpty == false {
            if exportKind == .mergedExport {
                throw MelixCLIError.usage("Pipeline command argument export_kind merged is incompatible with adapter_path.")
            }
            return LoraPublishOptions(
                modelID: modelID,
                targetRepo: targetRepo,
                exportKind: .adapterExport,
                artifactPath: adapterPath,
                artifactManifestPath: adapterPath,
                publishBackend: string("publish_backend", args) ?? "",
                localPublishRoot: string("local_publish_root", args) ?? ""
            )
        }
        if mergedModelPath.isEmpty == false {
            if exportKind == .adapterExport {
                throw MelixCLIError.usage("Pipeline command argument export_kind adapter is incompatible with merged_model_path.")
            }
            return LoraPublishOptions(
                modelID: modelID,
                targetRepo: targetRepo,
                exportKind: .mergedExport,
                artifactPath: mergedModelPath,
                publishBackend: string("publish_backend", args) ?? "",
                localPublishRoot: string("local_publish_root", args) ?? ""
            )
        }
        if manifestPath.isEmpty == false {
            return LoraPublishOptions(
                modelID: modelID,
                targetRepo: targetRepo,
                exportKind: exportKind,
                artifactPath: manifestPath,
                artifactManifestPath: manifestPath,
                publishBackend: string("publish_backend", args) ?? "",
                localPublishRoot: string("local_publish_root", args) ?? ""
            )
        }
        guard let exportKind else {
            throw MelixCLIError.missingRequired(
                "Pipeline command argument export_kind is required when lora.publish uses artifact_path."
            )
        }
        return LoraPublishOptions(
            modelID: modelID,
            targetRepo: targetRepo,
            exportKind: exportKind,
            artifactPath: artifactPath,
            artifactManifestPath: (string("artifact_manifest_path", args) ?? artifactPath)
                .trimmingCharacters(in: .whitespacesAndNewlines),
            publishBackend: string("publish_backend", args) ?? "",
            localPublishRoot: string("local_publish_root", args) ?? ""
        )
    }

    private static func loraPublishExportKind(_ args: [String: Any]) throws -> LoraPublishExportKind? {
        let rawKind = (string("export_kind", args) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard rawKind.isEmpty == false else {
            return nil
        }
        switch rawKind {
        case "adapter", "adapter_export":
            return .adapterExport
        case "merged", "merged_export":
            return .mergedExport
        default:
            throw MelixCLIError.usage("Pipeline command argument export_kind must be one of: adapter, merged.")
        }
    }

    private static func requiredString(_ key: String, _ args: [String: Any]) throws -> String {
        guard let value = string(key, args), value.isEmpty == false else {
            throw MelixCLIError.missingRequired("Pipeline command argument \(key) is required.")
        }
        return value
    }

    private static func string(_ key: String, _ args: [String: Any]) -> String? {
        guard let value = args[key] else {
            return nil
        }
        if let string = value as? String {
            return string
        }
        if let bool = MelixPipelineArgumentValue.booleanString(value) {
            return bool
        }
        if let number = value as? NSNumber {
            return number.stringValue
        }
        return nil
    }

    private static func int(_ key: String, _ args: [String: Any]) throws -> Int? {
        guard let value = args[key] else {
            return nil
        }
        if MelixPipelineArgumentValue.isBoolean(value) {
            throw MelixCLIError.usage("Pipeline command argument \(key) must be an integer.")
        }
        if let int = value as? Int {
            return int
        }
        if let number = value as? NSNumber,
           number.doubleValue.rounded(.towardZero) == number.doubleValue
        {
            return number.intValue
        }
        if let string = value as? String {
            guard let int = Int(string) else {
                throw MelixCLIError.usage("Pipeline command argument \(key) must be an integer.")
            }
            return int
        }
        throw MelixCLIError.usage("Pipeline command argument \(key) must be an integer.")
    }

    private static func uint32(_ key: String, _ args: [String: Any]) throws -> UInt32? {
        guard let int = try int(key, args) else {
            return nil
        }
        guard int >= 0, int <= Int(UInt32.max) else {
            throw MelixCLIError.usage("Pipeline command argument \(key) must be an unsigned integer.")
        }
        return UInt32(int)
    }

    private static func bool(_ key: String, _ args: [String: Any]) throws -> Bool? {
        guard let value = args[key] else {
            return nil
        }
        if let bool = value as? Bool {
            return bool
        }
        if let number = value as? NSNumber {
            if number.intValue == 0 {
                return false
            }
            if number.intValue == 1 {
                return true
            }
            throw MelixCLIError.usage("Pipeline command argument \(key) must be a boolean.")
        }
        if let string = value as? String {
            switch string.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "true", "yes", "1":
                return true
            case "false", "no", "0":
                return false
            default:
                throw MelixCLIError.usage("Pipeline command argument \(key) must be a boolean.")
            }
        }
        throw MelixCLIError.usage("Pipeline command argument \(key) must be a boolean.")
    }

    private static func firstStringArray(_ keys: [String], _ args: [String: Any]) throws -> [String] {
        for key in keys where args[key] != nil {
            return try stringArray(key, args) ?? []
        }
        return []
    }

    private static func firstUInt32Array(_ keys: [String], _ args: [String: Any]) throws -> [UInt32] {
        for key in keys where args[key] != nil {
            return try uint32Array(key, args) ?? []
        }
        return []
    }

    private static func stringArray(_ key: String, _ args: [String: Any]) throws -> [String]? {
        guard let value = args[key] else {
            return nil
        }
        if let array = value as? [String] {
            return array
        }
        if let array = value as? [Any] {
            return try array.map { item in
                if let string = item as? String {
                    return string
                }
                if let number = item as? NSNumber {
                    return number.stringValue
                }
                throw MelixCLIError.usage("Pipeline command argument \(key) must be an array of strings.")
            }
        }
        if let string = value as? String {
            return string.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        }
        throw MelixCLIError.usage("Pipeline command argument \(key) must be an array of strings.")
    }

    private static func uint32Array(_ key: String, _ args: [String: Any]) throws -> [UInt32]? {
        guard let value = args[key] else {
            return nil
        }
        let rawItems: [Any]
        if let array = value as? [Any] {
            rawItems = array
        } else if let string = value as? String {
            rawItems = string.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        } else {
            throw MelixCLIError.usage("Pipeline command argument \(key) must be an array of unsigned integers.")
        }
        return try rawItems.map { item in
            if MelixPipelineArgumentValue.isBoolean(item) {
                throw MelixCLIError.usage("Pipeline command argument \(key) must be an array of unsigned integers.")
            }
            if let int = item as? Int,
               int >= 0,
               int <= Int(UInt32.max)
            {
                return UInt32(int)
            }
            if let number = item as? NSNumber,
               number.doubleValue.rounded(.towardZero) == number.doubleValue,
               number.doubleValue >= 0,
               number.doubleValue <= Double(UInt32.max)
            {
                return UInt32(number.uint32Value)
            }
            if let string = item as? String,
               let value = UInt32(string)
            {
                return value
            }
            throw MelixCLIError.usage("Pipeline command argument \(key) must be an array of unsigned integers.")
        }
    }

    private static func parameters(_ args: [String: Any], excluding excluded: Set<String>) -> [String: String] {
        var result: [String: String] = [:]
        for (key, value) in args where excluded.contains(key) == false {
            if let string = value as? String {
                result[key] = string
            } else if let bool = MelixPipelineArgumentValue.booleanString(value) {
                result[key] = bool
            } else if let number = value as? NSNumber {
                result[key] = number.stringValue
            }
        }
        return result
    }

    private static func datasetSourceKind(_ args: [String: Any]) -> String {
        if args["hf_dataset_path"] != nil {
            return "huggingface"
        }
        return string("dataset_source_kind", args) ?? "local_package"
    }

    private static func datasetURI(_ args: [String: Any]) throws -> String {
        if let hfDatasetPath = string("hf_dataset_path", args), hfDatasetPath.isEmpty == false {
            return hfDatasetPath
        }
        return try requiredString("dataset_uri", args)
    }

    private static func evaluationSource(_ args: [String: Any]) -> ControlPlaneEvaluationRequest.Source {
        if let sourceCSV = string("source_csv", args), sourceCSV.isEmpty == false {
            return .localCSV(path: sourceCSV)
        }
        if let sourceJSONL = string("source_jsonl", args), sourceJSONL.isEmpty == false {
            return .localJSONL(path: sourceJSONL)
        }
        if let datasetPath = string("hf_dataset_path", args), datasetPath.isEmpty == false {
            return .huggingFaceDataset(
                datasetPath: datasetPath,
                datasetName: string("hf_dataset_name", args) ?? "",
                datasetRevision: string("hf_dataset_revision", args) ?? "main",
                split: string("hf_dataset_split", args) ?? "train"
            )
        }
        return .builtinPackage
    }

    private static func evaluationFieldMapping(_ args: [String: Any]) -> ControlPlaneEvaluationRequest.FieldMapping {
        ControlPlaneEvaluationRequest.FieldMapping(
            systemPath: string("field_system_path", args) ?? "",
            inputTextPath: string("field_input_text_path", args) ?? "",
            targetPath: string("field_target_path", args) ?? "",
            sampleIDPath: string("field_sample_id_path", args) ?? ""
        )
    }

    private static func evaluationProfile(_ args: [String: Any]) throws -> ControlPlaneEvaluationRequest.Profile {
        ControlPlaneEvaluationRequest.Profile(
            profileType: string("profile_type", args) ?? "final_result",
            resultKind: string("result_kind", args) ?? "text",
            extractionMode: string("extraction_mode", args) ?? "heuristic_final",
            scoringMode: string("scoring_mode", args) ?? "",
            threshold: Double(string("threshold", args) ?? "") ?? 1.0,
            outputSchemaJSON: string("output_schema_json", args) ?? "",
            ignoredPaths: try stringArray("ignored_paths", args) ?? []
        )
    }
}

private enum MelixPipelineChecks {
    static func validateSchema(_ checks: [String: Any], stepID: String) throws {
        if let rawFields = checks["required_result_fields"],
           rawFields as? [String] == nil
        {
            throw MelixCLIError.usage("Pipeline step \(stepID) checks.required_result_fields must be an array of strings.")
        }
        if let rawEquals = checks["equals"],
           rawEquals as? [String: Any] == nil
        {
            throw MelixCLIError.usage("Pipeline step \(stepID) checks.equals must be a JSON object.")
        }
        if let rawArtifactPaths = checks["artifact_path_exists"],
           rawArtifactPaths as? [String] == nil
        {
            throw MelixCLIError.usage("Pipeline step \(stepID) checks.artifact_path_exists must be an array of strings.")
        }
    }

    static func validate(
        _ checks: [String: Any]?,
        envelope: [String: Any],
        context: MelixPipelineContext
    ) throws {
        guard let checks else {
            return
        }
        if let fields = checks["required_result_fields"] as? [String] {
            for field in fields {
                _ = try MelixPipelineJSON.value(at: ["result"] + field.components(separatedBy: "."), in: envelope)
            }
        }
        if let equals = checks["equals"] as? [String: Any] {
            for (path, expected) in equals {
                let actual = try MelixPipelineJSON.value(at: path.components(separatedBy: "."), in: envelope)
                let resolvedExpected = try context.resolveObject(expected)
                guard MelixPipelineJSON.valuesEqual(actual, resolvedExpected) else {
                    throw MelixCLIError.runtime("Pipeline check failed for \(path).")
                }
            }
        }
        if let artifactPaths = checks["artifact_path_exists"] as? [String] {
            for artifactPath in artifactPaths {
                let resolved = try context.resolveString(artifactPath)
                guard let path = resolved as? String,
                      FileManager.default.fileExists(atPath: path)
                else {
                    throw MelixCLIError.runtime("Pipeline artifact check failed for \(artifactPath).")
                }
            }
        }
    }
}

private enum MelixPipelineReceipt {
    static func outputEnvelope(
        commandID: String,
        traceID: String,
        status: String,
        result: [String: Any],
        metrics: [String: Double]
    ) throws -> [String: Any] {
        let text = try MelixCLIJSONEnvelope.outputEnvelopeString(
            commandID: commandID,
            traceID: traceID,
            result: result,
            metrics: metrics,
            status: status
        )
        return MelixPipelineJSON.object(from: text) ?? [:]
    }

    static func errorEnvelope(
        commandID: String,
        traceID: String,
        error: MelixCLIError
    ) throws -> [String: Any] {
        let text = try MelixCLIJSONEnvelope.errorEnvelopeString(
            commandID: commandID,
            traceID: traceID,
            error: error
        )
        return MelixPipelineJSON.object(from: text) ?? [:]
    }
}

private enum MelixPipelineJSON {
    static func object(from text: String) -> [String: Any]? {
        guard let data = text.data(using: .utf8) else {
            return nil
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    static func value(at path: [String], in object: Any) throws -> Any {
        var current = object
        for part in path {
            if let dictionary = current as? [String: Any],
               let next = dictionary[part]
            {
                current = next
                continue
            }
            if let array = current as? [Any],
               let index = Int(part),
               array.indices.contains(index)
            {
                current = array[index]
                continue
            }
            throw MelixCLIError.runtime("Missing pipeline value at \(path.joined(separator: ".")).")
        }
        return current
    }

    static func valuesEqual(_ lhs: Any?, _ rhs: Any?) -> Bool {
        switch (lhs, rhs) {
        case (_ as NSNull, _ as NSNull):
            return true
        case let (left as String, right as String):
            return left == right
        case let (left as [Any], right as [Any]):
            guard left.count == right.count else {
                return false
            }
            return zip(left, right).allSatisfy { valuesEqual($0, $1) }
        case let (left as [String: Any], right as [String: Any]):
            guard left.count == right.count else {
                return false
            }
            for (key, leftValue) in left {
                guard right.keys.contains(key),
                      valuesEqual(leftValue, right[key])
                else {
                    return false
                }
            }
            return true
        case let (left?, right?):
            if let leftBool = MelixPipelineArgumentValue.booleanValue(left),
               let rightBool = MelixPipelineArgumentValue.booleanValue(right)
            {
                return leftBool == rightBool
            }
            if MelixPipelineArgumentValue.isBoolean(left) || MelixPipelineArgumentValue.isBoolean(right) {
                return false
            }
            guard let leftNumber = left as? NSNumber,
                  let rightNumber = right as? NSNumber
            else {
                return false
            }
            return leftNumber == rightNumber
        case (nil, nil):
            return true
        default:
            return false
        }
    }
}

private enum MelixPipelineReference {
    struct Match {
        let fullRange: Range<String.Index>
        let expression: String
    }

    static func matches(in value: String) -> [Match] {
        var matches: [Match] = []
        var searchStart = value.startIndex
        while let openRange = value.range(of: "${", range: searchStart..<value.endIndex),
              let closeIndex = value[openRange.upperBound...].firstIndex(of: "}")
        {
            let expression = String(value[openRange.upperBound..<closeIndex])
            let fullRange = openRange.lowerBound..<value.index(after: closeIndex)
            matches.append(Match(fullRange: fullRange, expression: expression))
            searchStart = value.index(after: closeIndex)
        }
        return matches
    }
}

private enum MelixPipelineHash {
    static func hash(_ value: Any) throws -> String {
        let normalized = normalize(value)
        let data = try JSONSerialization.data(withJSONObject: normalized, options: [.sortedKeys])
        return fnv1a64Hex(data)
    }

    private static func normalize(_ value: Any) -> Any {
        if let dictionary = value as? [String: Any] {
            var normalized: [String: Any] = [:]
            for key in dictionary.keys.sorted() {
                if let item = dictionary[key] {
                    normalized[key] = normalize(item)
                }
            }
            return normalized
        }
        if let array = value as? [Any] {
            return array.map(normalize)
        }
        return value
    }

    private static func fnv1a64Hex(_ data: Data) -> String {
        var hash: UInt64 = 0xcbf29ce484222325
        for byte in data {
            hash ^= UInt64(byte)
            hash = hash &* 0x100000001b3
        }
        return String(format: "%016llx", hash)
    }
}

private func loadOptionalJSONObject(from url: URL) throws -> [String: Any]? {
    guard FileManager.default.fileExists(atPath: url.path) else {
        return nil
    }
    let data = try Data(contentsOf: url)
    return try JSONSerialization.jsonObject(with: data) as? [String: Any]
}

private func sanitizePathComponent(_ value: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
    let scalars = value.unicodeScalars.map { scalar -> Character in
        allowed.contains(scalar) ? Character(scalar) : "-"
    }
    let sanitized = String(scalars).trimmingCharacters(in: CharacterSet(charactersIn: "-."))
    return sanitized.isEmpty ? "pipeline" : sanitized
}
