import Dispatch
import Foundation

private let defaultWorkflowRecipeRunRetentionLimit = 20

private struct MelixURIInspectionResult {
    let payload: [String: Any]
    let candidates: [[String: Any]]
    let metrics: [String: Double]
}

private struct MelixWorkflowRecipe: @unchecked Sendable {
    let id: String
    let version: String
    let title: String
    let description: String
    let tasks: [String]
    let inputs: [[String: Any]]
    let outputs: [String: Any]
    let plan: @Sendable ([String: String]) throws -> [[String: Any]]

    var payload: [String: Any] {
        let plannedSteps = (try? plan(defaultValues)) ?? []
        return [
            "schema_version": "melix.workflow_recipe.v1",
            "id": id,
            "version": version,
            "title": title,
            "description": description,
            "tasks": tasks,
            "inputs": inputs,
            "preflight": [
                "uri_inspection": inputs.contains { $0["uri_kind"] != nil },
                "pipeline_dry_run": true,
                "memory_fit": "delegated_to_existing_commands",
            ],
            "pipeline": [
                "schema_version": "melix.pipeline.v1",
                "steps": plannedSteps,
            ],
            "outputs": outputs,
            "provenance": [
                "source": "built_in",
                "governing_issue": "https://github.com/Keith-CY/melix/issues/636",
                "schema_version": "melix.workflow_recipe.v1",
            ],
        ]
    }

    var defaultValues: [String: String] {
        var values: [String: String] = [:]
        for input in inputs {
            guard let name = input["name"] as? String,
                  let defaultValue = input["default"] as? String
            else {
                continue
            }
            values[name] = defaultValue
        }
        return values
    }

    var digest: String {
        do {
            return try MelixRecipeHash.hash(payload)
        } catch {
            return ""
        }
    }
}

private enum MelixRecipeHash {
    static func hash(_ object: [String: Any]) throws -> String {
        let compatibleObject = try jsonCompatibleValue(object, context: "recipe payload")
        guard JSONSerialization.isValidJSONObject(compatibleObject) else {
            throw MelixCLIError.usage("Recipe payload contains values that cannot be serialized as JSON.")
        }
        let data = try JSONSerialization.data(withJSONObject: compatibleObject, options: [.sortedKeys])
        return data.reduce(UInt64(0xcbf29ce484222325)) { hash, byte in
            (hash ^ UInt64(byte)) &* 0x100000001b3
        }
        .hexString
    }

    static func hash(_ value: String) -> String {
        Data(value.utf8).reduce(UInt64(0xcbf29ce484222325)) { hash, byte in
            (hash ^ UInt64(byte)) &* 0x100000001b3
        }
        .hexString
    }

    private static func jsonCompatibleValue(_ value: Any, context: String) throws -> Any {
        switch value {
        case let dictionary as [String: Any]:
            var compatible: [String: Any] = [:]
            for (key, nestedValue) in dictionary {
                compatible[key] = try jsonCompatibleValue(nestedValue, context: "\(context).\(key)")
            }
            return compatible
        case let array as [Any]:
            return try array.enumerated().map { index, nestedValue in
                try jsonCompatibleValue(nestedValue, context: "\(context)[\(index)]")
            }
        case is NSNull, is String, is Bool, is Int, is Int64, is UInt, is UInt64, is Double, is Float:
            return value
        case let number as NSNumber:
            return number
        default:
            throw MelixCLIError.usage("Recipe payload field \(context) is not JSON-compatible.")
        }
    }
}

private extension UInt64 {
    var hexString: String {
        String(format: "%016llx", self)
    }
}

private enum MelixWorkflowRecipeCatalog {
    static let builtInRecipes: [MelixWorkflowRecipe] = [
        hfModelImportRecipe,
        localModelImportRecipe,
        hfEvalDatasetRecipe,
        loraLocalDatasetRecipe,
        benchmarkEvalSmokeRecipe,
        adapterCompareEvidenceRecipe,
    ]

    static func list(task: String = "") -> [MelixWorkflowRecipe] {
        let normalizedTask = task.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedTask.isEmpty == false else {
            return builtInRecipes
        }
        return builtInRecipes.filter { $0.tasks.contains(normalizedTask) }
    }

    static func recipe(id: String, version: String = "") throws -> MelixWorkflowRecipe {
        let normalizedID = id.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedVersion = version.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let recipe = builtInRecipes.first(where: {
            $0.id == normalizedID && (normalizedVersion.isEmpty || $0.version == normalizedVersion)
        }) else {
            throw MelixCLIError.runtime("Recipe \(id) was not found.")
        }
        return recipe
    }

    static func validate(_ recipe: MelixWorkflowRecipe) throws -> [String: Any] {
        let start = DispatchTime.now()
        var seenInputs = Set<String>()
        for input in recipe.inputs {
            guard let name = input["name"] as? String,
                  name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            else {
                throw MelixCLIError.usage("Recipe \(recipe.id) has an input without a name.")
            }
            guard seenInputs.insert(name).inserted else {
                throw MelixCLIError.usage("Recipe \(recipe.id) has duplicate input \(name).")
            }
        }
        _ = try MelixRecipeHash.hash(recipe.payload)
        let pipeline = try MelixRecipePlanner.plan(recipe: recipe, values: validationValues(for: recipe))
        try MelixRecipePlanner.validatePipelineCommands(pipeline)
        return [
            "schema_version": "melix.workflow_recipe.validation.v1",
            "recipe_id": recipe.id,
            "recipe_version": recipe.version,
            "valid": true,
            "recipe_digest": recipe.digest,
            "metrics": [
                "recipe.schema_validate_ms": elapsedMilliseconds(since: start),
            ],
        ]
    }

    private static func validationValues(for recipe: MelixWorkflowRecipe) -> [String: String] {
        var values = recipe.defaultValues
        for input in recipe.inputs {
            guard input["required"] as? Bool == true,
                  let name = input["name"] as? String,
                  (values[name] ?? "").isEmpty
            else {
                continue
            }
            values[name] = input["type"] as? String == "path" ? "/tmp/\(name)" : "sample-\(name)"
        }
        return values
    }

    private static let hfModelImportRecipe = MelixWorkflowRecipe(
        id: "import.hf-mlx-model",
        version: "1",
        title: "Import an MLX-compatible Hugging Face model",
        description: "Inspect fit, download a Hugging Face model, and rescan managed roots.",
        tasks: ["model_import"],
        inputs: [
            requiredInput("repo_id", type: "string", uriKind: "hf_model_repo"),
            optionalInput("revision", defaultValue: "main"),
            optionalInput("model_id"),
        ],
        outputs: [
            "managed_model_path": "from download_model step",
        ],
        plan: { values in
            [
                step(
                    "estimate_import",
                    command: "estimate.import",
                    args: [
                        "repo_id": try required("repo_id", in: values),
                        "target_kind": "import",
                    ]
                ),
                step(
                    "download_model",
                    command: "model.hub.download",
                    args: [
                        "repo_id": try required("repo_id", in: values),
                        "revision": value("revision", in: values, defaultValue: "main"),
                    ]
                ),
                step("rescan_roots", command: "model.roots.rescan"),
            ]
        }
    )

    private static let localModelImportRecipe = MelixWorkflowRecipe(
        id: "import.local-mlx-model",
        version: "1",
        title: "Import a local MLX model directory",
        description: "Import a local model directory into Melix managed storage and rescan roots.",
        tasks: ["model_import"],
        inputs: [
            requiredInput("path", type: "path", uriKind: "local_mlx_model_directory"),
            requiredInput("model_id"),
            optionalInput("model_kind", defaultValue: "text"),
            optionalInput("revision", defaultValue: "main"),
        ],
        outputs: [
            "managed_model_path": "from import_model step",
        ],
        plan: { values in
            [
                step(
                    "import_model",
                    command: "model.import",
                    args: [
                        "path": try required("path", in: values),
                        "model_id": try required("model_id", in: values),
                        "model_kind": value("model_kind", in: values, defaultValue: "text"),
                        "revision": value("revision", in: values, defaultValue: "main"),
                    ]
                ),
                step("rescan_roots", command: "model.roots.rescan"),
            ]
        }
    )

    private static let hfEvalDatasetRecipe = MelixWorkflowRecipe(
        id: "dataset.hf-eval",
        version: "1",
        title: "Prepare a Hugging Face evaluation dataset",
        description: "Download a Hugging Face dataset snapshot for evaluation workflows.",
        tasks: ["dataset_import", "eval"],
        inputs: [
            requiredInput("repo_id", type: "string", uriKind: "hf_dataset_repo"),
            optionalInput("revision", defaultValue: "main"),
        ],
        outputs: [
            "managed_dataset_path": "from download_dataset step",
        ],
        plan: { values in
            [
                step(
                    "download_dataset",
                    command: "dataset.hub.download",
                    args: [
                        "repo_id": try required("repo_id", in: values),
                        "revision": value("revision", in: values, defaultValue: "main"),
                    ]
                ),
            ]
        }
    )

    private static let loraLocalDatasetRecipe = MelixWorkflowRecipe(
        id: "train.lora.local-dataset",
        version: "1",
        title: "Train LoRA from a local dataset",
        description: "Train a LoRA or QLoRA adapter from a local dataset package.",
        tasks: ["train_lora"],
        inputs: [
            requiredInput("model_id"),
            requiredInput("dataset_uri", type: "path", uriKind: "local_dataset"),
            requiredInput("adapter_name"),
            optionalInput("training_mode", defaultValue: "lora"),
            optionalInput("target_repo"),
        ],
        outputs: [
            "adapter_manifest": "from train_lora step",
        ],
        plan: { values in
            [
                step(
                    "train_lora",
                    command: "lora.train",
                    args: [
                        "model_id": try required("model_id", in: values),
                        "dataset_uri": try required("dataset_uri", in: values),
                        "adapter_name": try required("adapter_name", in: values),
                        "training_mode": value("training_mode", in: values, defaultValue: "lora"),
                        "target_repo": values["target_repo"] ?? "",
                        "source_recipe_id": "train.lora.local-dataset",
                    ]
                ),
            ]
        }
    )

    private static let benchmarkEvalSmokeRecipe = MelixWorkflowRecipe(
        id: "benchmark.eval.smoke",
        version: "1",
        title: "Run benchmark and evaluation smoke evidence",
        description: "Run one small benchmark and one small evaluation against the same target.",
        tasks: ["benchmark", "eval"],
        inputs: [
            requiredInput("model_id"),
            optionalInput("bench_suite", defaultValue: "smoke"),
            optionalInput("eval_suite", defaultValue: "smoke"),
            optionalInput("dataset_id"),
            optionalInput("sample_size", defaultValue: "1"),
        ],
        outputs: [
            "benchmark_job": "from benchmark step",
            "evaluation_job": "from evaluation step",
        ],
        plan: { values in
            [
                step(
                    "benchmark",
                    command: "bench.run",
                    args: [
                        "model_id": try required("model_id", in: values),
                        "suite": [value("bench_suite", in: values, defaultValue: "smoke")],
                        "context_length": [1024],
                        "generation_length": 32,
                        "batch_size": [1],
                        "repeats": 1,
                        "sample_size": value("sample_size", in: values, defaultValue: "1"),
                        "source_recipe_id": "benchmark.eval.smoke",
                    ]
                ),
                step(
                    "evaluation",
                    command: "eval.run",
                    args: [
                        "model_id": try required("model_id", in: values),
                        "suite": [value("eval_suite", in: values, defaultValue: "smoke")],
                        "dataset_id": values["dataset_id"] ?? "",
                        "sample_size": value("sample_size", in: values, defaultValue: "1"),
                        "source_recipe_id": "benchmark.eval.smoke",
                    ]
                ),
            ]
        }
    )

    private static let adapterCompareEvidenceRecipe = MelixWorkflowRecipe(
        id: "adapter.compare.evidence",
        version: "1",
        title: "Compare base model and adapter evidence",
        description: "Run base-vs-adapter evaluation comparison without release-gate verdict enforcement.",
        tasks: ["eval_compare"],
        inputs: [
            requiredInput("model_id"),
            requiredInput("target_adapter"),
            optionalInput("suite", defaultValue: "smoke"),
            optionalInput("dataset_id"),
            optionalInput("sample_size", defaultValue: "1"),
        ],
        outputs: [
            "comparison_job": "from eval_compare step",
        ],
        plan: { values in
            [
                step(
                    "eval_compare",
                    command: "eval.compare",
                    args: [
                        "model_id": try required("model_id", in: values),
                        "target_adapter": [try required("target_adapter", in: values)],
                        "suite": [value("suite", in: values, defaultValue: "smoke")],
                        "dataset_id": values["dataset_id"] ?? "",
                        "sample_size": value("sample_size", in: values, defaultValue: "1"),
                        "source_recipe_id": "adapter.compare.evidence",
                    ]
                ),
            ]
        }
    )

    private static func requiredInput(_ name: String, type: String = "string", uriKind: String? = nil) -> [String: Any] {
        var input: [String: Any] = [
            "name": name,
            "type": type,
            "required": true,
        ]
        if let uriKind {
            input["uri_kind"] = uriKind
        }
        return input
    }

    private static func optionalInput(_ name: String, defaultValue: String = "") -> [String: Any] {
        var input: [String: Any] = [
            "name": name,
            "type": "string",
            "required": false,
        ]
        if defaultValue.isEmpty == false {
            input["default"] = defaultValue
        }
        return input
    }

    private static func step(_ id: String, command: String, args: [String: Any] = [:]) -> [String: Any] {
        [
            "id": id,
            "command": command,
            "args": args,
        ]
    }

    private static func required(_ key: String, in values: [String: String]) throws -> String {
        let value = value(key, in: values)
        guard value.isEmpty == false else {
            throw MelixCLIError.missingRequired("Recipe input \(key) is required.")
        }
        return value
    }

    private static func value(_ key: String, in values: [String: String], defaultValue: String = "") -> String {
        (values[key] ?? defaultValue).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private enum MelixRecipePlanner {
    static func plan(recipe: MelixWorkflowRecipe, values: [String: String]) throws -> [String: Any] {
        let inputs = mergedInputs(recipe: recipe, values: values)
        let validationStart = DispatchTime.now()
        try validateRequiredInputs(recipe, values: inputs)
        let steps = try recipe.plan(inputs)
        let schemaValidateMS = elapsedMilliseconds(since: validationStart)
        let provenance = provenance(recipe: recipe, values: inputs)
        return [
            "schema_version": "melix.pipeline.v1",
            "name": recipe.id,
            "inputs": inputs.merging(provenance) { current, _ in current },
            "steps": steps,
            "metadata": [
                "source_recipe_id": recipe.id,
                "source_recipe_version": recipe.version,
                "source_recipe_digest": recipe.digest,
                "governing_issue": "https://github.com/Keith-CY/melix/issues/636",
                "recipe.schema_validate_ms": schemaValidateMS,
            ],
        ]
    }

    static func validatePipelineCommands(_ pipeline: [String: Any]) throws {
        guard pipeline["schema_version"] as? String == "melix.pipeline.v1" else {
            throw MelixCLIError.usage("Recipe plan must emit melix.pipeline.v1.")
        }
        guard let steps = pipeline["steps"] as? [[String: Any]],
              steps.isEmpty == false
        else {
            throw MelixCLIError.missingRequired("Recipe plan must emit at least one pipeline step.")
        }
        let supportedCommands = Set([
            "estimate.import",
            "model.import",
            "model.hub.download",
            "model.roots.rescan",
            "dataset.hub.download",
            "lora.train",
            "bench.run",
            "eval.run",
            "eval.compare",
        ])
        for step in steps {
            guard let command = step["command"] as? String,
                  supportedCommands.contains(command)
            else {
                throw MelixCLIError.usage("Recipe plan contains an unsupported pipeline command.")
            }
        }
    }

    static func writePipeline(_ pipeline: [String: Any], to outputPath: String) throws -> String {
        let expandedPath = (outputPath as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: expandedPath)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let data = try MelixCLIJSON.prettyData(pipeline)
        try data.write(to: url, options: .atomic)
        return url.path
    }

    private static func mergedInputs(recipe: MelixWorkflowRecipe, values: [String: String]) -> [String: String] {
        recipe.defaultValues.merging(values) { _, override in override }
    }

    private static func validateRequiredInputs(_ recipe: MelixWorkflowRecipe, values: [String: String]) throws {
        for input in recipe.inputs {
            guard input["required"] as? Bool == true,
                  let name = input["name"] as? String
            else {
                continue
            }
            guard (values[name] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
                throw MelixCLIError.missingRequired("Recipe input \(name) is required.")
            }
        }
    }

    private static func provenance(recipe: MelixWorkflowRecipe, values: [String: String]) -> [String: String] {
        var provenance = [
            "source_recipe_id": recipe.id,
            "source_recipe_version": recipe.version,
            "source_recipe_digest": recipe.digest,
        ]
        for key in ["uri", "source_uri", "repo_id", "path", "dataset_uri"] {
            guard let value = values[key], value.isEmpty == false else {
                continue
            }
            provenance["source_uri_digest"] = MelixRecipeHash.hash(value)
            break
        }
        return provenance
    }
}

private enum MelixURIResolver {
    static func inspect(_ uri: String) -> MelixURIInspectionResult {
        let start = DispatchTime.now()
        let normalizedURI = uri.trimmingCharacters(in: .whitespacesAndNewlines)
        let candidates = candidates(for: normalizedURI)
        let ambiguityCount = max(candidates.count - 1, 0)
        let metrics = [
            "uri.inspect_ms": elapsedMilliseconds(since: start),
            "uri.candidate_count": Double(candidates.count),
            "uri.ambiguity_count": Double(ambiguityCount),
        ]
        let payload: [String: Any] = [
            "schema_version": "melix.uri_inspection.v1",
            "original_uri": uri,
            "normalized_locator": normalizedURI,
            "candidate_count": candidates.count,
            "ambiguity_count": ambiguityCount,
            "candidates": candidates,
            "metrics": metrics,
        ]
        return MelixURIInspectionResult(payload: payload, candidates: candidates, metrics: metrics)
    }

    private static func candidates(for uri: String) -> [[String: Any]] {
        guard uri.isEmpty == false else {
            return []
        }
        if let hf = hfLocator(uri) {
            return [hfCandidate(hf)]
        }
        if isBareHuggingFaceRepo(uri) {
            return [
                candidate(
                    kind: "hf_model_repo",
                    confidence: 0.62,
                    taskKind: "model_import",
                    sourceKind: "huggingface",
                    revision: "main",
                    locator: "hf://model/\(uri)",
                    reasons: ["bare org/repo locator; prefer hf://model or hf://dataset for disambiguation"],
                    command: ["model", "hub", "download", "--repo-id", uri]
                ),
                candidate(
                    kind: "hf_dataset_repo",
                    confidence: 0.38,
                    taskKind: "dataset_import",
                    sourceKind: "huggingface",
                    revision: "main",
                    locator: "hf://dataset/\(uri)",
                    reasons: ["bare org/repo locator could also identify a Hugging Face dataset"],
                    command: ["dataset", "hub", "download", "--repo-id", uri]
                ),
            ]
        }
        return localCandidates(for: uri)
    }

    private static func hfLocator(_ uri: String) -> (kind: String, repoID: String, revision: String, locator: String)? {
        guard let components = URLComponents(string: uri) else {
            return nil
        }
        if components.scheme == "hf" {
            let kind: String
            let locatorPrefix: String
            switch components.host?.lowercased() {
            case "model":
                kind = "hf_model_repo"
                locatorPrefix = "hf://model"
            case "dataset":
                kind = "hf_dataset_repo"
                locatorPrefix = "hf://dataset"
            default:
                return nil
            }
            return hfLocator(kind: kind, locatorPrefix: locatorPrefix, pathComponents: hfPathComponents(components.path))
        }
        guard ["http", "https"].contains(components.scheme?.lowercased() ?? ""),
              components.host?.lowercased() == "huggingface.co"
        else {
            return nil
        }
        var pathComponents = hfPathComponents(components.path)
        var kind = "hf_model_repo"
        var locatorPrefix = "hf://model"
        if pathComponents.first == "datasets" {
            pathComponents.removeFirst()
            kind = "hf_dataset_repo"
            locatorPrefix = "hf://dataset"
        }
        return hfLocator(kind: kind, locatorPrefix: locatorPrefix, pathComponents: pathComponents)
    }

    private static func hfLocator(
        kind: String,
        locatorPrefix: String,
        pathComponents: [String]
    ) -> (kind: String, repoID: String, revision: String, locator: String)? {
        guard pathComponents.count >= 2 else {
            return nil
        }
        let second = pathComponents[1].split(separator: "@", maxSplits: 1, omittingEmptySubsequences: false)
        let repoName = second.first.map(String.init) ?? ""
        let repoID = "\(pathComponents[0])/\(repoName)"
        guard isBareHuggingFaceRepo(repoID) else {
            return nil
        }
        let revision: String
        if second.count > 1 {
            let explicitRevision = [String(second[1])] + Array(pathComponents.dropFirst(2))
            revision = explicitRevision.joined(separator: "/")
        } else {
            revision = revisionFromPathRemainder(Array(pathComponents.dropFirst(2))) ?? "main"
        }
        return (kind, repoID, revision, "\(locatorPrefix)/\(repoID)@\(revision)")
    }

    private static func hfPathComponents(_ path: String) -> [String] {
        path.split(separator: "/", omittingEmptySubsequences: true)
            .map(String.init)
            .map { $0.removingPercentEncoding ?? $0 }
    }

    private static func revisionFromPathRemainder(_ pathRemainder: [String]) -> String? {
        guard let marker = pathRemainder.first,
              ["tree", "blob", "resolve"].contains(marker),
              pathRemainder.count >= 2
        else {
            return nil
        }
        let revisionParts: ArraySlice<String>
        if pathRemainder.count >= 4,
           pathRemainder[1] == "refs"
        {
            revisionParts = pathRemainder[1...3]
        } else {
            revisionParts = pathRemainder[1...1]
        }
        let revision = revisionParts.joined(separator: "/")
        return revision.isEmpty ? nil : revision
    }

    private static func hfCandidate(_ hf: (kind: String, repoID: String, revision: String, locator: String)) -> [String: Any] {
        let isDataset = hf.kind == "hf_dataset_repo"
        return candidate(
            kind: hf.kind,
            confidence: 0.96,
            taskKind: isDataset ? "dataset_import" : "model_import",
            sourceKind: "huggingface",
            revision: hf.revision,
            locator: hf.locator,
            reasons: ["explicit Hugging Face \(isDataset ? "dataset" : "model") locator"],
            command: isDataset
                ? ["dataset", "hub", "download", "--repo-id", hf.repoID, "--revision", hf.revision]
                : ["model", "hub", "download", "--repo-id", hf.repoID, "--revision", hf.revision],
            extra: ["repo_id": hf.repoID]
        )
    }

    private static func localCandidates(for rawURI: String) -> [[String: Any]] {
        let path = (rawURI as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: path)
        let fileManager = FileManager.default
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
            return [
                candidate(
                    kind: "unknown",
                    confidence: 0.0,
                    taskKind: "inspect",
                    sourceKind: "local_path",
                    locator: url.path,
                    reasons: ["path does not exist"],
                    command: []
                ),
            ]
        }
        if isDirectory.boolValue {
            return localDirectoryCandidates(url)
        }
        return localFileCandidates(url)
    }

    private static func localDirectoryCandidates(_ url: URL) -> [[String: Any]] {
        var candidates: [[String: Any]] = []
        let fileManager = FileManager.default
        let hasConfig = fileManager.fileExists(atPath: url.appendingPathComponent("config.json").path)
        let hasModelWeights = directoryContainsFile(
            in: url,
            withExtensions: ["safetensors", "bin", "gguf"]
        )
        if hasConfig && hasModelWeights {
            candidates.append(candidate(
                kind: "local_mlx_model_directory",
                confidence: 0.90,
                taskKind: "model_import",
                sourceKind: "local_path",
                locator: url.path,
                reasons: ["directory contains config.json and model weight files"],
                command: ["model", "import", "--path", url.path],
                extra: ["resolved_path": url.path]
            ))
        }
        if ["samples.jsonl", "dataset.json", "manifest.json"].contains(where: {
            fileManager.fileExists(atPath: url.appendingPathComponent($0).path)
        }) {
            candidates.append(candidate(
                kind: "local_dataset_package",
                confidence: 0.72,
                taskKind: "train_lora",
                sourceKind: "local_path",
                locator: url.path,
                reasons: ["directory contains dataset package markers"],
                command: ["lora", "dataset", "inspect", "--dataset-uri", url.path],
                extra: ["resolved_path": url.path]
            ))
        }
        if ["train_lora.adapter.json", "adapter_config.json"].contains(where: {
            fileManager.fileExists(atPath: url.appendingPathComponent($0).path)
        }) {
            candidates.append(candidate(
                kind: "local_lora_adapter",
                confidence: 0.82,
                taskKind: "eval_compare",
                sourceKind: "local_path",
                locator: url.path,
                reasons: ["directory contains LoRA adapter metadata"],
                command: ["eval", "compare", "--target-adapter", url.path],
                extra: ["resolved_path": url.path]
            ))
        }
        return candidates.isEmpty ? [
            candidate(
                kind: "local_directory",
                confidence: 0.20,
                taskKind: "inspect",
                sourceKind: "local_path",
                locator: url.path,
                reasons: ["directory does not match a known Melix artifact shape"],
                command: [],
                extra: ["resolved_path": url.path]
            ),
        ] : candidates
    }

    private static func directoryContainsFile(in url: URL, withExtensions extensions: Set<String>) -> Bool {
        guard let enumerator = FileManager.default.enumerator(
            at: url,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles, .skipsSubdirectoryDescendants]
        ) else {
            return false
        }
        for case let childURL as URL in enumerator {
            guard extensions.contains(childURL.pathExtension.lowercased()) else {
                continue
            }
            let values = try? childURL.resourceValues(forKeys: [.isRegularFileKey])
            if values?.isRegularFile != false {
                return true
            }
        }
        return false
    }

    private static func localFileCandidates(_ url: URL) -> [[String: Any]] {
        let ext = url.pathExtension.lowercased()
        if ["jsonl", "csv", "parquet"].contains(ext) {
            return [
                candidate(
                    kind: "local_dataset_file",
                    confidence: 0.88,
                    taskKind: "train_lora",
                    sourceKind: "local_path",
                    locator: url.path,
                    reasons: ["file extension \(ext) is supported by dataset workflows"],
                    command: ["lora", "dataset", "inspect", "--dataset-uri", url.path],
                    extra: ["resolved_path": url.path, "dataset_kind": ext]
                ),
            ]
        }
        if url.lastPathComponent == "train_lora.adapter.json" || url.lastPathComponent.hasSuffix(".adapter.json") {
            return [
                candidate(
                    kind: "local_lora_adapter_manifest",
                    confidence: 0.92,
                    taskKind: "eval_compare",
                    sourceKind: "local_path",
                    locator: url.path,
                    reasons: ["file name matches a Melix LoRA adapter manifest"],
                    command: ["eval", "compare", "--target-adapter", url.path],
                    extra: ["resolved_path": url.path]
                ),
            ]
        }
        if ext == "gguf" {
            return [
                candidate(
                    kind: "gguf_model_file",
                    confidence: 0.70,
                    taskKind: "inspect",
                    sourceKind: "local_path",
                    locator: url.path,
                    reasons: ["GGUF files are inspectable but are not a supported direct import target in this slice"],
                    command: [],
                    extra: ["resolved_path": url.path, "supported_import": false]
                ),
            ]
        }
        return [
            candidate(
                kind: "local_file",
                confidence: 0.10,
                taskKind: "inspect",
                sourceKind: "local_path",
                locator: url.path,
                reasons: ["file does not match a known Melix artifact shape"],
                command: [],
                extra: ["resolved_path": url.path]
            ),
        ]
    }

    private static func candidate(
        kind: String,
        confidence: Double,
        taskKind: String,
        sourceKind: String,
        revision: String = "",
        locator: String,
        reasons: [String],
        command: [String],
        extra: [String: Any] = [:]
    ) -> [String: Any] {
        var payload: [String: Any] = [
            "kind": kind,
            "confidence": confidence,
            "task_kind": taskKind,
            "source_kind": sourceKind,
            "normalized_locator": locator,
            "reasons": reasons,
            "recommended_next_action": command.isEmpty ? "inspect_only" : command.joined(separator: " "),
            "generated_command_arguments": command,
            "warnings": [],
        ]
        if revision.isEmpty == false {
            payload["revision"] = revision
        }
        for (key, value) in extra {
            payload[key] = value
        }
        return payload
    }

    private static func splitRevision(_ value: String) -> (repoID: String, revision: String) {
        let trimmed = value.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let parts = trimmed.split(separator: "@", maxSplits: 1, omittingEmptySubsequences: false)
        let repoID = parts.first.map(String.init) ?? ""
        let revision = parts.count > 1 ? String(parts[1]) : "main"
        return (repoID, revision.isEmpty ? "main" : revision)
    }

    private static func isBareHuggingFaceRepo(_ value: String) -> Bool {
        let parts = value.split(separator: "/", omittingEmptySubsequences: false)
        return parts.count == 2
            && parts.allSatisfy { part in
                part.isEmpty == false && part.allSatisfy { character in
                    character.isLetter || character.isNumber || ["-", "_", "."].contains(character)
                }
            }
    }
}

extension MelixCLIRunner {
    public func runURIInspect(_ options: URIInspectOptions) throws -> String {
        let inspection = MelixURIResolver.inspect(options.uri)
        if options.json {
            return try prettyWorkflowJSON(inspection.payload)
        }
        return renderURIInspection(inspection.payload)
    }

    public func runURIImport(_ options: URIImportOptions) async throws -> String {
        let inspection = MelixURIResolver.inspect(options.uri)
        let importableCandidates = inspection.candidates.filter { candidate in
            isURIImportableKind(candidate["kind"] as? String ?? "")
        }
        guard let candidate = importableCandidates.first,
              importableCandidates.count == 1
        else {
            let status = importableCandidates.isEmpty ? "unresolved" : "ambiguous"
            let payload: [String: Any] = [
                "schema_version": "melix.uri_import.v1",
                "status": status,
                "inspection": inspection.payload,
                "importable_candidate_count": importableCandidates.count,
            ]
            let message = importableCandidates.isEmpty
                ? "URI import did not resolve an importable candidate. Run melix uri inspect first.\n"
                : "URI import is ambiguous. Run melix uri inspect first.\n"
            return options.json ? try prettyWorkflowJSON(payload) : message
        }
        guard let kind = candidate["kind"] as? String else {
            throw MelixCLIError.runtime("URI inspection did not produce a candidate kind.")
        }
        let command = try commandForURIImport(kind: kind, candidate: candidate, options: options)
        let payload: [String: Any] = [
            "schema_version": "melix.uri_import.v1",
            "status": options.dryRun ? "planned" : "executed",
            "candidate": candidate,
            "command_id": MelixCLICommandCodec.commandID(for: command),
            "arguments": try MelixCLICommandCodec.arguments(for: command),
            "metrics": inspection.metrics,
        ]
        guard options.dryRun else {
            let output = try await run(command)
            if options.json {
                var executedPayload = payload
                executedPayload["result"] = MelixCLIJSON.jsonValue(from: output)
                return try prettyWorkflowJSON(executedPayload)
            }
            return output
        }
        if options.json {
            return try prettyWorkflowJSON(payload)
        }
        return (payload["arguments"] as? [String] ?? []).joined(separator: " ") + "\n"
    }

    public func runRecipesList(_ options: RecipeListOptions) throws -> String {
        let start = DispatchTime.now()
        let recipes = MelixWorkflowRecipeCatalog.list(task: options.task)
        let payload: [String: Any] = [
            "schema_version": "melix.workflow_recipe_catalog.v1",
            "recipes": recipes.map(summaryPayload),
            "metrics": [
                "recipe.lookup_ms": elapsedMilliseconds(since: start),
            ],
        ]
        return options.json ? try prettyWorkflowJSON(payload) : renderRecipeList(recipes)
    }

    public func runRecipesShow(_ options: RecipeShowOptions) throws -> String {
        let start = DispatchTime.now()
        let recipe = try MelixWorkflowRecipeCatalog.recipe(id: options.recipeID, version: options.version)
        var payload = recipe.payload
        payload["recipe_digest"] = recipe.digest
        payload["metrics"] = [
            "recipe.lookup_ms": elapsedMilliseconds(since: start),
        ]
        return options.json ? try prettyWorkflowJSON(payload) : renderRecipeShow(recipe)
    }

    public func runRecipesValidate(_ options: RecipeValidateOptions) throws -> String {
        let recipe = try MelixWorkflowRecipeCatalog.recipe(id: options.target)
        let payload = try MelixWorkflowRecipeCatalog.validate(recipe)
        return options.json ? try prettyWorkflowJSON(payload) : "Recipe \(recipe.id) is valid.\n"
    }

    public func runRecipesPlan(_ options: RecipePlanOptions) throws -> String {
        let startedAt = DispatchTime.now()
        let lookupStart = DispatchTime.now()
        let recipe = try MelixWorkflowRecipeCatalog.recipe(id: options.recipeID, version: options.version)
        let lookupMS = elapsedMilliseconds(since: lookupStart)
        let plan = try MelixRecipePlanner.plan(recipe: recipe, values: options.values)
        try MelixRecipePlanner.validatePipelineCommands(plan)
        var artifacts: [[String: Any]] = []
        if options.outputPath.isEmpty == false {
            let writtenPath = try MelixRecipePlanner.writePipeline(plan, to: options.outputPath)
            artifacts.append(["kind": "pipeline", "path": writtenPath])
        }
        let payload: [String: Any] = [
            "schema_version": "melix.workflow_recipe_plan.v1",
            "recipe_id": recipe.id,
            "recipe_version": recipe.version,
            "recipe_digest": recipe.digest,
            "pipeline": plan,
            "artifacts": artifacts,
            "metrics": [
                "recipe.lookup_ms": lookupMS,
                "recipe.schema_validate_ms": (plan["metadata"] as? [String: Any])?["recipe.schema_validate_ms"] ?? 0,
                "recipe.plan_ms": elapsedMilliseconds(since: startedAt),
            ],
        ]
        return options.json ? try prettyWorkflowJSON(payload) : try MelixCLIJSON.prettyString(plan)
    }

    public func runRecipesApply(_ options: RecipeApplyOptions) async throws -> String {
        let startedAt = DispatchTime.now()
        let recipe = try MelixWorkflowRecipeCatalog.recipe(id: options.recipeID, version: options.version)
        let plan = try MelixRecipePlanner.plan(recipe: recipe, values: options.values)
        try MelixRecipePlanner.validatePipelineCommands(plan)
        let runRoot = MelixHome(environment: environment).rootURL
            .appendingPathComponent("workflow-recipes", isDirectory: true)
            .appendingPathComponent(sanitizeRecipePathComponent(recipe.id), isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: runRoot, withIntermediateDirectories: true)
        let retainedRuns = try pruneRecipeRuns(
            under: runRoot.deletingLastPathComponent(),
            keeping: runRoot,
            limit: defaultWorkflowRecipeRunRetentionLimit
        )
        let pipelineURL = runRoot.appendingPathComponent("pipeline.json")
        _ = try MelixRecipePlanner.writePipeline(plan, to: pipelineURL.path)
        let receiptURL = runRoot.appendingPathComponent("receipts", isDirectory: true)
        let output = try await runPipeline(
            PipelineRunOptions(
                filePath: pipelineURL.path,
                receiptDir: receiptURL.path,
                resume: options.resume,
                fromStepID: options.fromStepID,
                dryRun: options.dryRun
            )
        )
        if options.json {
            var payload = MelixCLIJSON.jsonValue(from: output) as? [String: Any] ?? ["pipeline_output": output]
            payload["recipe"] = [
                "id": recipe.id,
                "version": recipe.version,
                "digest": recipe.digest,
                "retention_limit": defaultWorkflowRecipeRunRetentionLimit,
                "run_root": runRoot.path,
            ]
            payload["metrics"] = (payload["metrics"] as? [String: Any] ?? [:]).merging([
                "recipe.apply_start_ms": elapsedMilliseconds(since: startedAt),
                "recipe.apply_retained_runs": retainedRuns,
            ]) { current, _ in current }
            return try prettyWorkflowJSON(payload)
        }
        return output
    }

    public func runRecipesInit(_ options: RecipeInitOptions) throws -> String {
        let inspection = MelixURIResolver.inspect(options.sourceURI)
        let recipeID = try recommendedRecipeID(task: options.task, inspection: inspection)
        let recipe = try MelixWorkflowRecipeCatalog.recipe(id: recipeID)
        var payload = recipe.payload
        payload["provenance"] = [
            "source": "generated_from_uri",
            "source_uri_digest": MelixRecipeHash.hash(options.sourceURI),
            "inspection": inspection.payload,
        ]
        if options.outputPath.isEmpty == false {
            _ = try MelixRecipePlanner.writePipeline(payload, to: options.outputPath)
        }
        return options.json ? try prettyWorkflowJSON(payload) : renderRecipeShow(recipe)
    }

    private func commandForURIImport(
        kind: String,
        candidate: [String: Any],
        options: URIImportOptions
    ) throws -> MelixCLICommand {
        switch kind {
        case "hf_model_repo":
            return .modelHubDownload(
                .init(
                    repoID: try requiredCandidateString("repo_id", candidate),
                    revision: options.revision.isEmpty ? (candidate["revision"] as? String ?? "main") : options.revision,
                    json: options.json
                )
            )
        case "hf_dataset_repo":
            return .datasetHubDownload(
                .init(
                    repoID: try requiredCandidateString("repo_id", candidate),
                    revision: options.revision.isEmpty ? (candidate["revision"] as? String ?? "main") : options.revision,
                    json: options.json
                )
            )
        case "local_mlx_model_directory":
            guard options.modelID.isEmpty == false else {
                throw MelixCLIError.missingRequired("--model-id is required to import a local model URI.")
            }
            return .modelImport(
                .init(
                    path: try requiredCandidateString("resolved_path", candidate),
                    modelID: options.modelID,
                    revision: options.revision,
                    json: options.json
                )
            )
        default:
            throw MelixCLIError.runtime("URI kind \(kind) is not importable by melix uri import.")
        }
    }

    private func requiredCandidateString(_ key: String, _ candidate: [String: Any]) throws -> String {
        guard let value = candidate[key] as? String,
              value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        else {
            throw MelixCLIError.runtime("URI candidate did not include \(key).")
        }
        return value
    }

    private func isURIImportableKind(_ kind: String) -> Bool {
        ["hf_model_repo", "hf_dataset_repo", "local_mlx_model_directory"].contains(kind)
    }

    private func summaryPayload(_ recipe: MelixWorkflowRecipe) -> [String: Any] {
        [
            "id": recipe.id,
            "version": recipe.version,
            "title": recipe.title,
            "tasks": recipe.tasks,
            "recipe_digest": recipe.digest,
        ]
    }

    private func renderURIInspection(_ payload: [String: Any]) -> String {
        guard let candidates = payload["candidates"] as? [[String: Any]],
              candidates.isEmpty == false
        else {
            return "No candidates found.\n"
        }
        var lines = ["kind\ttask_kind\tconfidence\tnormalized_locator"]
        for candidate in candidates {
            lines.append([
                candidate["kind"] as? String ?? "",
                candidate["task_kind"] as? String ?? "",
                "\(candidate["confidence"] ?? "")",
                candidate["normalized_locator"] as? String ?? "",
            ].joined(separator: "\t"))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private func renderRecipeList(_ recipes: [MelixWorkflowRecipe]) -> String {
        guard recipes.isEmpty == false else {
            return "No recipes found.\n"
        }
        var lines = ["id\tversion\ttasks\ttitle"]
        for recipe in recipes {
            lines.append([recipe.id, recipe.version, recipe.tasks.joined(separator: ","), recipe.title].joined(separator: "\t"))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private func renderRecipeShow(_ recipe: MelixWorkflowRecipe) -> String {
        "id=\(recipe.id)\nversion=\(recipe.version)\ntasks=\(recipe.tasks.joined(separator: ","))\ntitle=\(recipe.title)\n"
    }

    private func recommendedRecipeID(task: String, inspection: MelixURIInspectionResult) throws -> String {
        if task == "import",
           let firstKind = inspection.candidates.first?["kind"] as? String
        {
            if firstKind == "hf_model_repo" {
                return "import.hf-mlx-model"
            }
            if firstKind == "local_mlx_model_directory" {
                return "import.local-mlx-model"
            }
        }
        if task == "eval" {
            return "dataset.hf-eval"
        }
        guard let recipeID = MelixWorkflowRecipeCatalog.list(task: task).first?.id else {
            throw MelixCLIError.runtime("No workflow recipe matches task \(task).")
        }
        return recipeID
    }

    private func pruneRecipeRuns(under recipeRoot: URL, keeping currentRunRoot: URL, limit: Int) throws -> Int {
        guard limit > 0 else {
            return 0
        }
        let fileManager = FileManager.default
        guard let children = try? fileManager.contentsOfDirectory(
            at: recipeRoot,
            includingPropertiesForKeys: [.creationDateKey, .contentModificationDateKey, .isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else {
            return 1
        }
        let currentRunPath = currentRunRoot.standardizedFileURL.path
        let runDirectories = children.compactMap { url -> (url: URL, date: Date)? in
            guard url.standardizedFileURL.path != currentRunPath,
                  UUID(uuidString: url.lastPathComponent) != nil
            else {
                return nil
            }
            let values = try? url.resourceValues(forKeys: [.creationDateKey, .contentModificationDateKey, .isDirectoryKey])
            guard values?.isDirectory == true else {
                return nil
            }
            return (url, values?.creationDate ?? values?.contentModificationDate ?? .distantPast)
        }
        let removable = runDirectories
            .sorted { left, right in
                if left.date == right.date {
                    return left.url.lastPathComponent < right.url.lastPathComponent
                }
                return left.date > right.date
            }
            .dropFirst(max(limit - 1, 0))
        for run in removable {
            try? fileManager.removeItem(at: run.url)
        }
        return min(runDirectories.count + 1, limit)
    }

    private func prettyWorkflowJSON(_ payload: [String: Any]) throws -> String {
        try MelixCLIJSON.prettyString(payload)
    }

    private func sanitizeRecipePathComponent(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        let sanitized = String(value.unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" })
            .trimmingCharacters(in: CharacterSet(charactersIn: "-."))
        return sanitized.isEmpty ? "recipe" : sanitized
    }
}
