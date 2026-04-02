import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public struct LoraListOptions: Equatable, Sendable {
    public let modelID: String
    public let json: Bool

    public init(modelID: String = "", json: Bool = false) {
        self.modelID = modelID
        self.json = json
    }
}

public struct LoraTrainOptions: Equatable, Sendable {
    public let modelID: String
    public let datasetURI: String
    public let adapterName: String
    public let targetRepo: String
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String,
        datasetURI: String,
        adapterName: String,
        targetRepo: String = "",
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.datasetURI = datasetURI
        self.adapterName = adapterName
        self.targetRepo = targetRepo
        self.parameters = parameters
        self.json = json
    }
}

public struct LoraActivateOptions: Equatable, Sendable {
    public let modelID: String
    public let adapterPath: String
    public let derivedModelAlias: String
    public let json: Bool

    public init(
        modelID: String,
        adapterPath: String,
        derivedModelAlias: String = "",
        json: Bool = false
    ) {
        self.modelID = modelID
        self.adapterPath = adapterPath
        self.derivedModelAlias = derivedModelAlias
        self.json = json
    }
}

public struct BenchRunOptions: Equatable, Sendable {
    public let modelID: String
    public let suites: [String]
    public let parameters: [String: String]
    public let json: Bool

    public init(
        modelID: String,
        suites: [String] = [],
        parameters: [String: String] = [:],
        json: Bool = false
    ) {
        self.modelID = modelID
        self.suites = suites
        self.parameters = parameters
        self.json = json
    }
}

public enum MelixCLICommand: Equatable, Sendable {
    case loraList(LoraListOptions)
    case loraTrain(LoraTrainOptions)
    case loraActivate(LoraActivateOptions)
    case benchRun(BenchRunOptions)
}

public enum MelixCLIError: Error, LocalizedError, Equatable, Sendable {
    case usage(String)
    case missingValue(String)
    case missingRequired(String)

    public var errorDescription: String? {
        switch self {
        case .usage(let message):
            return message
        case .missingValue(let option):
            return "Missing value for \(option)."
        case .missingRequired(let message):
            return message
        }
    }
}

public enum MelixCLIParser {
    public static func parse(_ arguments: [String]) throws -> MelixCLICommand {
        guard let group = arguments.first else {
            throw MelixCLIError.usage(Self.usageText)
        }
        let tail = Array(arguments.dropFirst())
        switch group {
        case "lora":
            return try parseLora(tail)
        case "bench":
            return try parseBench(tail)
        default:
            throw MelixCLIError.usage(Self.usageText)
        }
    }

    public static let usageText = """
    Usage:
      melix lora list [--model-id MODEL_ID] [--json]
      melix lora train --model-id MODEL_ID --dataset-uri PATH --adapter-name NAME [--target-repo REPO] [--rank N] [--alpha N] [--dropout N] [--batch-size N] [--epochs N] [--learning-rate N] [--max-seq-length N] [--json]
      melix lora activate --model-id MODEL_ID --adapter-path PATH [--alias NAME] [--json]
      melix bench run --model-id MODEL_ID [--suite SUITE ...] [--sample-size N] [--batch-factor N] [--json]
    """

    private static func parseLora(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first else {
            throw MelixCLIError.usage(usageText)
        }
        let cursor = ArgumentCursor(arguments: Array(arguments.dropFirst()))
        switch action {
        case "list":
            let values = try cursor.parse()
            return .loraList(
                LoraListOptions(
                    modelID: values.single["--model-id"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        case "train":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix lora train.")
            }
            guard let datasetURI = values.single["--dataset-uri"], !datasetURI.isEmpty else {
                throw MelixCLIError.missingRequired("--dataset-uri is required for melix lora train.")
            }
            guard let adapterName = values.single["--adapter-name"], !adapterName.isEmpty else {
                throw MelixCLIError.missingRequired("--adapter-name is required for melix lora train.")
            }
            var parameters: [String: String] = [:]
            for option in ["--rank", "--alpha", "--dropout", "--batch-size", "--epochs", "--learning-rate", "--max-seq-length"] {
                if let value = values.single[option] {
                    parameters[normalizedParameterKey(option)] = value
                }
            }
            return .loraTrain(
                LoraTrainOptions(
                    modelID: modelID,
                    datasetURI: datasetURI,
                    adapterName: adapterName,
                    targetRepo: values.single["--target-repo"] ?? "",
                    parameters: parameters,
                    json: values.flags.contains("--json")
                )
            )
        case "activate":
            let values = try cursor.parse()
            guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
                throw MelixCLIError.missingRequired("--model-id is required for melix lora activate.")
            }
            guard let adapterPath = values.single["--adapter-path"], !adapterPath.isEmpty else {
                throw MelixCLIError.missingRequired("--adapter-path is required for melix lora activate.")
            }
            return .loraActivate(
                LoraActivateOptions(
                    modelID: modelID,
                    adapterPath: adapterPath,
                    derivedModelAlias: values.single["--alias"] ?? "",
                    json: values.flags.contains("--json")
                )
            )
        default:
            throw MelixCLIError.usage(usageText)
        }
    }

    private static func parseBench(_ arguments: [String]) throws -> MelixCLICommand {
        guard let action = arguments.first, action == "run" else {
            throw MelixCLIError.usage(usageText)
        }
        let values = try ArgumentCursor(arguments: Array(arguments.dropFirst())).parse()
        guard let modelID = values.single["--model-id"], !modelID.isEmpty else {
            throw MelixCLIError.missingRequired("--model-id is required for melix bench run.")
        }
        var parameters: [String: String] = [:]
        if let sampleSize = values.single["--sample-size"] {
            parameters["sample_size"] = sampleSize
        }
        if let batchFactor = values.single["--batch-factor"] {
            parameters["batch_factor"] = batchFactor
        }
        return .benchRun(
            BenchRunOptions(
                modelID: modelID,
                suites: values.multi["--suite"] ?? [],
                parameters: parameters,
                json: values.flags.contains("--json")
            )
        )
    }

    private static func normalizedParameterKey(_ option: String) -> String {
        option
            .replacingOccurrences(of: "--", with: "")
            .replacingOccurrences(of: "-", with: "_")
    }
}

private struct ParsedArguments {
    var single: [String: String] = [:]
    var multi: [String: [String]] = [:]
    var flags: Set<String> = []
}

private struct ArgumentCursor {
    let arguments: [String]

    func parse() throws -> ParsedArguments {
        var result = ParsedArguments()
        var index = 0
        while index < arguments.count {
            let token = arguments[index]
            if token == "--json" {
                result.flags.insert(token)
                index += 1
                continue
            }
            guard token.hasPrefix("--") else {
                throw MelixCLIError.usage(MelixCLIParser.usageText)
            }
            let valueIndex = index + 1
            guard valueIndex < arguments.count else {
                throw MelixCLIError.missingValue(token)
            }
            let value = arguments[valueIndex]
            if token == "--suite" {
                result.multi[token, default: []].append(value)
            } else {
                result.single[token] = value
            }
            index += 2
        }
        return result
    }
}

public actor MelixCLIRunner {
    private let client: any ControlPlaneXPCClient

    public init(client: any ControlPlaneXPCClient = LocalControlPlaneXPCClient()) {
        self.client = client
    }

    public func run(_ command: MelixCLICommand) async throws -> String {
        switch command {
        case .loraList(let options):
            let modelID = try await resolveModelID(preferred: options.modelID)
            let result = try await client.runModelOperation(
                modelID: modelID,
                operation: "registry_snapshot",
                outputDir: "",
                quantProfileID: "",
                weightQuant: "",
                kvQuant: "",
                ext: [:]
            )
            return options.json ? result.manifestJson : renderRegistrySnapshot(result.manifestJson)
        case .loraTrain(let options):
            var ext = options.parameters
            ext["adapter_name"] = options.adapterName
            ext["dataset_uri"] = options.datasetURI
            if !options.targetRepo.isEmpty {
                ext["target_repo"] = options.targetRepo
            }
            let result = try await client.runModelOperation(
                modelID: options.modelID,
                operation: "train_lora",
                outputDir: "",
                quantProfileID: "",
                weightQuant: "",
                kvQuant: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .loraActivate(let options):
            var ext = ["artifact_path": options.adapterPath]
            if !options.derivedModelAlias.isEmpty {
                ext["derived_model_alias"] = options.derivedModelAlias
            }
            let result = try await client.runModelOperation(
                modelID: options.modelID,
                operation: "activate_adapter",
                outputDir: "",
                quantProfileID: "",
                weightQuant: "",
                kvQuant: "",
                ext: ext
            )
            return options.json ? result.manifestJson : result.outputPath
        case .benchRun(let options):
            _ = try await client.loadModel(modelID: options.modelID)
            let result = try await client.runBench(
                ControlPlaneBenchRequest(
                    modelID: options.modelID,
                    suites: options.suites,
                    parameters: options.parameters
                )
            )
            if options.json {
                return try prettyJSON(
                    [
                        "report_path": result.reportPath,
                        "report_markdown": result.reportMarkdown,
                        "metrics": result.metrics,
                    ]
                )
            }
            return result.reportMarkdown.isEmpty ? result.reportPath : result.reportMarkdown
        }
    }

    private func resolveModelID(preferred: String) async throws -> String {
        if !preferred.isEmpty {
            return preferred
        }
        let snapshot = try await client.serverSnapshot()
        if let model = snapshot.models.first(where: { $0.kind == "text" }) ?? snapshot.models.first {
            return model.modelID
        }
        throw MelixCLIError.missingRequired("No model is available in the current server snapshot.")
    }

    private func renderRegistrySnapshot(_ manifestJSON: String) -> String {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let adapters = payload["adapters"] as? [[String: Any]]
        else {
            return manifestJSON
        }
        if adapters.isEmpty {
            return "No adapters found.\n"
        }
        let lines = adapters.map { adapter in
            let name = (adapter["adapter_name"] as? String) ?? "adapter"
            let status = (adapter["status"] as? String) ?? "unknown"
            let sourceModel = (adapter["source_model"] as? String) ?? ""
            return "\(name)\t\(status)\t\(sourceModel)"
        }
        return (["adapter\tstatus\tsource_model"] + lines).joined(separator: "\n") + "\n"
    }

    private func prettyJSON(_ payload: [String: Any]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        return String(decoding: data, as: UTF8.self) + "\n"
    }
}
