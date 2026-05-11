import Foundation

public struct MelixRuntimeSettingMetadata: Equatable, Sendable {
    public let key: String
    public let valueType: String
    public let environmentVariable: String
    public let summary: String

    public init(
        key: String,
        valueType: String,
        environmentVariable: String,
        summary: String
    ) {
        self.key = key
        self.valueType = valueType
        self.environmentVariable = environmentVariable
        self.summary = summary
    }
}

public enum MelixRuntimeDiscoveryContracts {
    public static let runtimeSettingsSchemaVersion = "melix.runtime_settings.effective.v1"
    public static let infoSchemaVersion = "melix.discovery.info.v1"
    public static let capabilitiesSchemaVersion = "melix.discovery.capabilities.v1"
    public static let instructionsSchemaVersion = "melix.discovery.instructions.v1"
    public static let schemaSchemaVersion = "melix.discovery.schema.v1"
    public static let configMetadataSchemaVersion = "melix.discovery.config_metadata.v1"

    public static let enabledFeatures: [String] = [
        "runtime_settings",
        "model_alias_discovery",
        "run_reports",
        "update_receipt",
        "local_http_discovery",
    ]

    public static let supportedTasks: [String] = [
        "text-generation",
        "embeddings",
        "rerank",
        "audio-transcription",
        "audio-speech",
        "image-generation",
        "image-edit",
        "evaluation",
        "benchmark",
    ]

    public static let runtimeSettingDefinitions: [MelixRuntimeSettingMetadata] = [
        .init(
            key: "model_cache_path",
            valueType: "string",
            environmentVariable: "MELIX_MODEL_CACHE_PATH",
            summary: "Directory for managed local model artifacts."
        ),
        .init(
            key: "dataset_cache_path",
            valueType: "string",
            environmentVariable: "MELIX_DATASET_CACHE_PATH",
            summary: "Directory for managed dataset snapshots and packages."
        ),
        .init(
            key: "artifact_path",
            valueType: "string",
            environmentVariable: "MELIX_ARTIFACT_PATH",
            summary: "Directory for generated benchmark, evaluation, and export artifacts."
        ),
        .init(
            key: "max_concurrent_jobs",
            valueType: "int",
            environmentVariable: "MELIX_MAX_CONCURRENT_JOBS",
            summary: "Maximum number of local runtime jobs Melix should schedule concurrently."
        ),
        .init(
            key: "memory_pressure_threshold",
            valueType: "double",
            environmentVariable: "MELIX_MEMORY_PRESSURE_THRESHOLD",
            summary: "Fraction of unified memory pressure at which Melix should become conservative."
        ),
        .init(
            key: "default_dtype",
            valueType: "string",
            environmentVariable: "MELIX_DEFAULT_DTYPE",
            summary: "Default tensor dtype used when a command does not specify one."
        ),
        .init(
            key: "default_quantization",
            valueType: "string",
            environmentVariable: "MELIX_DEFAULT_QUANTIZATION",
            summary: "Default quantization profile used for local model suggestions."
        ),
        .init(
            key: "benchmark_warmup",
            valueType: "int",
            environmentVariable: "MELIX_BENCHMARK_WARMUP",
            summary: "Default benchmark warmup iteration count."
        ),
        .init(
            key: "benchmark_repeats",
            valueType: "int",
            environmentVariable: "MELIX_BENCHMARK_REPEATS",
            summary: "Default benchmark repeat count."
        ),
        .init(
            key: "eval_sample_size",
            valueType: "int",
            environmentVariable: "MELIX_EVAL_SAMPLE_SIZE",
            summary: "Default evaluation sample size when a run does not override it."
        ),
        .init(
            key: "log_retention_days",
            valueType: "int",
            environmentVariable: "MELIX_LOG_RETENTION_DAYS",
            summary: "Number of days to retain local runtime logs."
        ),
        .init(
            key: "auto_cleanup_policy",
            valueType: "string",
            environmentVariable: "MELIX_AUTO_CLEANUP_POLICY",
            summary: "Default cleanup policy for local artifacts."
        ),
    ]

    public static func defaultRuntimeSettingValue(
        key: String,
        layout: MelixPathLayout
    ) -> Any {
        switch key {
        case "model_cache_path":
            return layout.managedModelRootURL.path
        case "dataset_cache_path":
            return layout.rootURL.appendingPathComponent("datasets", isDirectory: true).path
        case "artifact_path":
            return layout.rootURL.appendingPathComponent("artifacts", isDirectory: true).path
        case "max_concurrent_jobs":
            return NSNumber(value: 2)
        case "memory_pressure_threshold":
            return NSNumber(value: 0.80)
        case "default_dtype":
            return "float16"
        case "default_quantization":
            return "4bit"
        case "benchmark_warmup":
            return NSNumber(value: 1)
        case "benchmark_repeats":
            return NSNumber(value: 3)
        case "eval_sample_size":
            return NSNumber(value: 20)
        case "log_retention_days":
            return NSNumber(value: 14)
        case "auto_cleanup_policy":
            return "manual"
        default:
            return ""
        }
    }

    public static func runtimeSettingsMetadata(layout: MelixPathLayout) -> [[String: Any]] {
        runtimeSettingDefinitions.map { definition in
            [
                "key": definition.key,
                "type": definition.valueType,
                "default": defaultRuntimeSettingValue(key: definition.key, layout: layout),
                "environment_variable": definition.environmentVariable,
                "summary": definition.summary,
            ]
        }
    }

    public static func discoveryLinks(baseURL: String = "") -> [String: String] {
        let prefix = baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let base = prefix.isEmpty ? "" : "/\(prefix)"
        return [
            "well_known": "\(base)/.well-known/melix.json",
            "capabilities": "\(base)/api/capabilities",
            "instructions": "\(base)/api/instructions",
            "config_metadata": "\(base)/api/config-metadata",
        ]
    }

    public static func instructionsPayload() -> [String: Any] {
        [
            "schema_version": instructionsSchemaVersion,
            "areas": [
                [
                    "id": "settings",
                    "title": "Runtime settings",
                    "commands": [
                        "melix settings show --json",
                        "melix settings set <key> <value>",
                        "melix settings validate",
                        "melix settings reset <key>",
                    ],
                ],
                [
                    "id": "discovery",
                    "title": "Machine-readable discovery",
                    "commands": [
                        "melix info --json",
                        "melix capabilities --json",
                        "melix instructions --json",
                        "melix schema --json",
                        "melix config metadata --json",
                    ],
                ],
                [
                    "id": "models",
                    "title": "Model targets",
                    "commands": [
                        "melix model list --json",
                        "melix capabilities --json --model-query <model>",
                    ],
                ],
                [
                    "id": "updates",
                    "title": "Local update receipt",
                    "commands": [
                        "melix info --json",
                    ],
                ],
            ],
        ]
    }

    public static func schemaPayload(repoRootPath: String) -> [String: Any] {
        [
            "schema_version": schemaSchemaVersion,
            "schemas": [
                [
                    "id": "protocol",
                    "path": URL(fileURLWithPath: repoRootPath)
                        .appendingPathComponent("packages/protocol/schema", isDirectory: true)
                        .path,
                ],
                [
                    "id": "plans",
                    "path": URL(fileURLWithPath: repoRootPath)
                        .appendingPathComponent("docs/plans", isDirectory: true)
                        .path,
                ],
            ],
        ]
    }

    public static func configMetadataPayload(layout: MelixPathLayout) -> [String: Any] {
        [
            "schema_version": configMetadataSchemaVersion,
            "settings": runtimeSettingsMetadata(layout: layout),
        ]
    }

    public static func modelAliasDiscoveryPayload(query rawQuery: String) -> [String: Any] {
        let query = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.isEmpty == false else {
            return [
                "query": query,
                "status": "not_requested",
                "suggestions": [],
                "families": aliasFamiliesPayload(),
            ]
        }
        if isLocalModelPath(query) {
            return [
                "query": query,
                "status": "local_path_passthrough",
                "suggestions": [],
                "families": aliasFamiliesPayload(),
            ]
        }
        if isFullModelID(query) {
            return [
                "query": query,
                "status": "valid_full_model_id",
                "suggestions": [],
                "families": aliasFamiliesPayload(),
            ]
        }

        let normalizedQuery = normalizedAliasToken(query)
        let suggestions = modelAliasRecords()
            .filter { record in
                record.normalizedTokens.contains(normalizedQuery)
                    || record.normalizedModelID.contains(normalizedQuery)
            }
            .map(\.payload)
        return [
            "query": query,
            "status": suggestions.isEmpty ? "no_match" : "suggested",
            "suggestions": suggestions,
            "families": aliasFamiliesPayload(),
        ]
    }

    private static func modelAliasRecords() -> [ModelAliasRecord] {
        [
            ModelAliasRecord(
                family: "qwen3.5",
                modelID: "mlx-community/Qwen3.5-9B-MLX-4bit",
                aliases: [
                    "qwen35_9b_mlx_4bit",
                    "qwen3.5-9b-mlx-4bit",
                    "qwen-3.5-9b-4bit",
                ],
                quantization: "4bit"
            ),
            ModelAliasRecord(
                family: "qwen3.5",
                modelID: "mlx-community/Qwen3.5-9B-MLX-8bit",
                aliases: [
                    "qwen35_9b_mlx_8bit",
                    "qwen3.5-9b-mlx-8bit",
                    "qwen-3.5-9b-8bit",
                ],
                quantization: "8bit"
            ),
            ModelAliasRecord(
                family: "qwen3.5",
                modelID: "mlx-community/Qwen3.5-26B-MLX-4bit",
                aliases: [
                    "qwen35_26b_mlx_4bit",
                    "qwen3.5-26b-mlx-4bit",
                    "qwen-3.5-26b-4bit",
                ],
                quantization: "4bit"
            ),
        ]
    }

    private static func aliasFamiliesPayload() -> [[String: Any]] {
        let records = modelAliasRecords()
        let grouped = Dictionary(grouping: records, by: \.family)
        return grouped.keys.sorted().map { family in
            [
                "family": family,
                "model_ids": (grouped[family] ?? []).map(\.modelID).sorted(),
            ]
        }
    }

    private static func isLocalModelPath(_ query: String) -> Bool {
        query.hasPrefix("/")
            || query.hasPrefix("~/")
            || query.hasPrefix("./")
            || query.hasPrefix("../")
            || query.hasPrefix("file://")
    }

    private static func isFullModelID(_ query: String) -> Bool {
        let parts = query.split(separator: "/", omittingEmptySubsequences: true)
        return parts.count == 2
            && parts.allSatisfy { $0.isEmpty == false }
            && query.contains(" ") == false
    }

    private static func normalizedAliasToken(_ value: String) -> String {
        value
            .lowercased()
            .unicodeScalars
            .filter { CharacterSet.alphanumerics.contains($0) }
            .map(String.init)
            .joined()
    }

    private struct ModelAliasRecord {
        let family: String
        let modelID: String
        let aliases: [String]
        let quantization: String

        var normalizedModelID: String {
            MelixRuntimeDiscoveryContracts.normalizedAliasToken(modelID)
        }

        var normalizedTokens: Set<String> {
            Set(aliases.map(MelixRuntimeDiscoveryContracts.normalizedAliasToken))
        }

        var payload: [String: Any] {
            [
                "family": family,
                "model_id": modelID,
                "aliases": aliases,
                "quantization": quantization,
            ]
        }
    }
}
