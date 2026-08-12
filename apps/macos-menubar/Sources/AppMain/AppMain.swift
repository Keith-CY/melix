import AppKit
import CoreFoundation
import Darwin
import Foundation
import MelixCLICore
import MelixControlPlaneCore

public enum MenuBarStartupSurface: String {
    case tray
    case console
    case commandCenter = "command-center"

    init(environmentValue: String?) {
        let normalized = environmentValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""
        self = MenuBarStartupSurface(rawValue: normalized) ?? .console
    }
}

public enum MenuBarPresentationMode: String, Equatable {
    case tray
    case dockAndTray = "dock-and-tray"

    init(environmentValue: String?) {
        let normalized = environmentValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""
        self = MenuBarPresentationMode(rawValue: normalized) ?? .tray
    }

    var activationPolicy: NSApplication.ActivationPolicy {
        switch self {
        case .tray:
            return .accessory
        case .dockAndTray:
            return .regular
        }
    }
}

public enum MenuBarTerminationMode: String, Equatable {
    case terminate
    case devDownScript = "dev-down-script"

    init(environmentValue: String?) {
        let normalized = environmentValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""
        self = MenuBarTerminationMode(rawValue: normalized) ?? .terminate
    }
}

@MainActor
public protocol StatusMenuInstalling: AnyObject {
    func install()
}

extension StatusMenu: StatusMenuInstalling {}

@MainActor
public protocol MenuBarApplicationLifecycle {
    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy)
    func setMainMenu(_ menu: NSMenu?)
    func run()
}

@MainActor
public protocol NSApplicationControlling {
    @discardableResult
    func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) -> Bool
    func setMainMenu(_ menu: NSMenu?)
    func run()
}

extension NSApplication: NSApplicationControlling {
    public func setMainMenu(_ menu: NSMenu?) {
        mainMenu = menu
    }
}

@MainActor
public struct LiveMenuBarApplication: MenuBarApplicationLifecycle {
    private let application: any NSApplicationControlling

    public init(application: any NSApplicationControlling = NSApplication.shared) {
        self.application = application
    }

    public func setActivationPolicy(_ activationPolicy: NSApplication.ActivationPolicy) {
        _ = application.setActivationPolicy(activationPolicy)
    }

    public func setMainMenu(_ menu: NSMenu?) {
        application.setMainMenu(menu)
    }

    public func run() {
        application.run()
    }
}

@MainActor
protocol Phase8WindowUIAcceptanceRunning {
    func run() async throws -> Phase8WindowUIAcceptanceResult
}

extension Phase8WindowUIAcceptanceRunner: Phase8WindowUIAcceptanceRunning {}

@MainActor
protocol AppScreenshotCaptureRunning {
    func run() async throws -> AppScreenshotCaptureManifest
}

extension AppScreenshotCaptureRunner: AppScreenshotCaptureRunning {}

private enum MCPEnvironmentCredentialBoundary {
    // MCP_RESERVED_ENVIRONMENT_KEYS_BEGIN
    static let keyListEnvironmentKey = "MELIX_MCP_CREDENTIAL_ENV_KEYS"
    private static let configPathEnvironmentKey = "MELIX_MCP_CONFIG_PATH"
    private static let maximumSources = 256
    private static let maximumSourceIDBytes = 64
    private static let maximumCredentialReferences = 1_024
    private static let maximumCredentialKeyBytes = 255
    private static let maximumCredentialKeyListBytes = 32_768
    private static let maximumReferenceTargetBytes = 255
    private static let maximumReferenceTargetListBytes = 32_768
    private static let credentialHTTPHeaderPattern = try! NSRegularExpression(
        pattern: "(?:authorization|cookie|credential|password|private[_-]?key|secret|signature|token|api[_-]?key)",
        options: [.caseInsensitive]
    )
    private static let privateServiceEnvironmentKeys: Set<String> = [
        "MELIX_WORKER_SOCKET_PATH",
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH",
        "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH",
        "MELIX_COMPUTER_BROKER_SOCKET",
        "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID",
        "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID",
        "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID",
        "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_FD",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_BASE64",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64",
    ]
    private static let controlPlaneEnvironmentKeys: Set<String> = [
        "MELIX_ARTIFACT_PATH", "MELIX_AUTO_CLEANUP_POLICY",
        "MELIX_BENCHMARK_REPEATS", "MELIX_BENCHMARK_WARMUP",
        "MELIX_DATASET_CACHE_PATH", "MELIX_DEFAULT_DTYPE", "MELIX_DEFAULT_QUANTIZATION",
        "MELIX_DEV_EMBED_BACKEND_ID", "MELIX_DEV_EMBED_DIMENSIONS",
        "MELIX_DEV_EMBED_FAMILY_ID", "MELIX_DEV_EMBED_MODEL_PATH",
        "MELIX_DEV_EMBED_NORMALIZATION", "MELIX_DEV_EMBED_POOLING_MODE",
        "MELIX_DEV_IMAGE_FAMILY_ID", "MELIX_DEV_IMAGE_MODEL_PATH", "MELIX_DEV_IMAGE_TASK_KIND",
        "MELIX_DEV_RERANK_FAMILY_ID", "MELIX_DEV_RERANK_MODEL_PATH",
        "MELIX_DEV_TEXT_FAMILY_ID", "MELIX_DEV_TEXT_MODEL_PATH",
        "MELIX_EVAL_SAMPLE_SIZE", "MELIX_LOG_RETENTION_DAYS",
        "MELIX_MAX_CONCURRENT_JOBS", "MELIX_MEMORY_PRESSURE_THRESHOLD", "MELIX_MODEL_CACHE_PATH",
        "MELIX_ALLOWED_HOSTS", "MELIX_ALLOWED_ORIGINS",
        "MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS", "MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS",
        "MELIX_CONNECTION_RESUME_BUFFER_LIMIT", "MELIX_CONNECTION_RETRY_BACKOFF_SECONDS",
        "MELIX_CONNECTION_RETRY_LIMIT", "MELIX_DEV_RERANK_BACKEND_ID",
        "MELIX_DEV_RERANK_SCORING_MODE", "MELIX_DEV_RERANK_YES_NO_LABELS",
        "MELIX_GATEWAY_ACCELERATION_MODE", "MELIX_GATEWAY_ACCELERATION_PROFILE",
        "MELIX_GATEWAY_API_KEYS_JSON", "MELIX_GATEWAY_AUTH_MODE",
        "MELIX_GATEWAY_BEARER_TOKEN", "MELIX_GATEWAY_BEARER_TOKEN_HINT",
        "MELIX_GATEWAY_BEARER_TOKEN_ID", "MELIX_GATEWAY_BEARER_TOKEN_LABEL",
        "MELIX_GATEWAY_COMPLETION_BATCH_SIZE", "MELIX_GATEWAY_CONCURRENT_PROCESSING_ENABLED",
        "MELIX_GATEWAY_DEFAULT_MAX_TOKENS", "MELIX_GATEWAY_DEFAULT_TEMPERATURE",
        "MELIX_GATEWAY_DEFAULT_TOP_P", "MELIX_GATEWAY_DRAFT_MODEL_ID",
        "MELIX_GATEWAY_MAX_CONCURRENT_REQUESTS", "MELIX_GATEWAY_MAX_CONCURRENT_SEQUENCES",
        "MELIX_GATEWAY_MULTIMODAL_ROUTE_POLICY", "MELIX_GATEWAY_NUM_DRAFT_TOKENS",
        "MELIX_GATEWAY_PREFILL_BATCH_SIZE", "MELIX_GATEWAY_RATE_LIMIT_PER_MINUTE",
        "MELIX_GATEWAY_SHARED_ACCESS_ENABLED", "MELIX_GATEWAY_SPECULATIVE_ROUTE_POLICY",
        "MELIX_GATEWAY_STREAM_INTERVAL_TOKENS", "MELIX_GATEWAY_TIMEOUT_SECONDS",
        "MELIX_IMAGE_DEFAULT_EDIT_MODEL_ID", "MELIX_IMAGE_DEFAULT_GENERATE_MODEL_ID",
        "MELIX_IMAGE_DEFAULT_GUIDANCE", "MELIX_IMAGE_DEFAULT_NEGATIVE_PROMPT",
        "MELIX_IMAGE_DEFAULT_SIZE", "MELIX_IMAGE_DEFAULT_STEPS",
        "MELIX_IMAGE_DEFAULT_STRENGTH", "MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS",
        "MELIX_MCP_HIGH_RISK_ALLOWLIST", "MELIX_MODEL_IDLE_TIMEOUT_SECONDS",
        "MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS", "MELIX_PRIVACY_DETECTOR_MODE",
        "MELIX_ROUTE_SELECTION_RECEIPT_PATH",
    ]
    private static let swiftWorkerEnvironmentKeys: Set<String> = [
        "MELIX_DETERMINISTIC_VLM_DELAY_MS", "MELIX_DEV_OCR_MODEL_PATH",
        "MELIX_DEV_TEXT_MODEL_PATH", "MELIX_DEV_VLM_MODEL_PATH",
        "MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE", "MELIX_SWIFT_BASELINE_DECODE_PROBE",
        "MELIX_SWIFT_BATCH_DECODE_FORCE_MODEL_EVAL_PROBE", "MELIX_SWIFT_DFLASH_PROBE",
        "MELIX_SWIFT_DFLASH_PROBE_PATH", "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT",
        "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_COHORT_PENDING_WINDOW_MS",
        "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_PENDING_WINDOW_MS",
        "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT", "MELIX_SWIFT_TEXT_WORKER_FAMILY",
        "MELIX_SWIFT_TEXT_WORKER_ID", "MELIX_SWIFT_TEXT_WORKER_INITIAL_CACHE_BLOCKS",
        "MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES",
        "MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES",
        "MELIX_SWIFT_TEXT_WORKER_PREFILL_QUADRATIC_GUARD_TOKEN_THRESHOLD",
        "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES",
        "MELIX_SWIFT_TEXT_WORKER_RUNTIME_CACHE_FINGERPRINT", "MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION",
        "MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS", "MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE",
        "MELIX_SWIFT_VISION_PAYLOAD_RECEIPT_PATH", "MELIX_SWIFT_VISION_WORKER_BACKEND_MODE",
        "MELIX_SWIFT_VISION_WORKER_CACHE_ROOT", "MELIX_SWIFT_VISION_WORKER_DETERMINISTIC_DELAY_MS",
        "MELIX_SWIFT_VISION_WORKER_ID", "MELIX_SWIFT_VISION_WORKER_METRICS_PATH",
        "MELIX_SWIFT_VISION_WORKER_RUNTIME_CACHE_FINGERPRINT",
        "MELIX_SWIFT_VISION_WORKER_RUNTIME_VERSION", "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH",
        "MELIX_SWIFT_WORKER_FAMILY",
    ]
    private static let pythonWorkerEnvironmentKeys: Set<String> = [
        "MELIX_APP_PROCESS_PID",
        "MELIX_CLANG_MODULE_CACHE_PATH",
        "MELIX_COMPUTER_BROKER_CAPABILITY_FILE",
        "MELIX_COMPUTER_BROKER_DIR",
        "MELIX_COMPUTER_BROKER_PID",
        "MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE",
        "MELIX_COMPUTER_BROKER_PROTOCOL_VERSION",
        "MELIX_COMPUTER_BROKER_PUBLIC_KEY_BASE64",
        "MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE",
        "MELIX_COMPUTER_BROKER_RPC_TIMEOUT_MS",
        "MELIX_DETERMINISTIC_MULTIMODAL_DELAY_MS",
        "MELIX_DEV_SPEECH_MODEL_PATH",
        "MELIX_DEV_TEXT_ROUTE_KIND",
        "MELIX_DEV_TRANSCRIBE_MODEL_PATH",
        "MELIX_DEV_VLM_FAMILY_ID",
        "MELIX_ENABLE_TEST_CACHE_HOOKS",
        "MELIX_EVALUATION_PROBE_ANOMALY_LIMIT",
        "MELIX_EVALUATION_PROBE_SAMPLE_LIMIT",
        "MELIX_EVALUATION_PROBE_TOP_N",
        "MELIX_GIT_BRANCH",
        "MELIX_GIT_COMMIT",
        "MELIX_GIT_DIRTY",
        "MELIX_HOMEBREW_BIN_DIR",
        "MELIX_HTTP_READY_URL",
        "MELIX_LOGICAL_PRODUCT_IDENTITY",
        "MELIX_MLX_AUDIO_KOKORO_MODEL_PATH",
        "MELIX_MLX_AUDIO_PARAKEET_MODEL_PATH",
        "MELIX_MLX_AUDIO_QWEN3_TTS_MODEL_PATH",
        "MELIX_MLX_AUDIO_WHISPER_MODEL_PATH",
        "MELIX_PREFIX_CACHE_COLD_DIR",
        "MELIX_PREFIX_CACHE_COLD_MAX_BYTES",
        "MELIX_PROBE_MODE",
        "MELIX_PYTHON_WORKER_MODEL_LOAD_HEADROOM_BYTES",
        "MELIX_PYTHON_WORKER_PROCESS_MEMORY_BUDGET_BYTES",
        "MELIX_PYTHON_WORKER_STARTUP_T0_NS",
        "MELIX_RELEASE_OBSERVABILITY_OVERHEAD_ITERATIONS",
        "MELIX_RELEASE_OBSERVABILITY_OVERHEAD_SAMPLES",
        "MELIX_RUN_TOKEN",
        "MELIX_SOCKET_DIR",
        "MELIX_SWIFT_HOME",
        "MELIX_TEXT_NATIVE_MTP_PREFILL_STEP_SIZE",
        "MELIX_VLM_TEXT_BATCH_MAX_BATCH_SIZE",
        "MELIX_VLM_TEXT_BATCH_PREFILL_STEP_SIZE",
        "MELIX_WATCHDOG_COMPUTER_BROKER_PID",
        "MELIX_WATCHDOG_CONTROL_PLANE_PID",
        "MELIX_WATCHDOG_PYTHON_WORKER_PID",
        "MELIX_WATCHDOG_SWIFT_WORKER_PID",
    ]
    private static let controlPlaneSecretEnvironmentKeys: Set<String> = [
        "MELIX_API_KEY", "MELIX_HF_TOKEN", "MELIX_HUGGINGFACE_TOKEN",
        "MELIX_GATEWAY_API_KEYS_JSON", "MELIX_GATEWAY_AUTH_MODE",
        "MELIX_GATEWAY_BEARER_TOKEN", "MELIX_GATEWAY_BEARER_TOKEN_HINT",
        "MELIX_GATEWAY_BEARER_TOKEN_ID", "MELIX_GATEWAY_BEARER_TOKEN_LABEL",
        "MELIX_GATEWAY_SHARED_ACCESS_ENABLED", "MELIX_MCP_HIGH_RISK_ALLOWLIST",
    ]
    private static let stripOnlyEnvironmentKeys: Set<String> = [
        "MELIX_API_KEY", "MELIX_HF_TOKEN", "MELIX_HUGGINGFACE_TOKEN",
    ]
    private static let cliEnvironmentKeys: Set<String> = [
        "MELIX_BATCH_MODEL_DIR", "MELIX_BATCH_MODEL_INDEX", "MELIX_BATCH_MODEL_LIST",
        "MELIX_BATCH_MODEL_REPO_ID", "MELIX_BATCH_MODEL_TEMP_DIR", "MELIX_BATCH_PREFLIGHT",
        "MELIX_BATCH_RUN_ID", "MELIX_BENCH_BATCH_FACTOR", "MELIX_BENCH_BATCH_SIZE",
        "MELIX_BENCH_CONTEXT_LENGTH", "MELIX_BENCH_GENERATION_LENGTH", "MELIX_BENCH_REPEATS",
        "MELIX_BENCH_SAMPLE_SIZE", "MELIX_BENCH_SUITE", "MELIX_CONTINUE_ON_FAILURE",
        "MELIX_DOWNLOAD_ROOT", "MELIX_EVAL_BATCH_FACTOR", "MELIX_EVAL_DATASET_ID",
        "MELIX_EVAL_SAMPLE_SIZE", "MELIX_EVAL_SCORING_MODE", "MELIX_EVAL_SUITE",
        "MELIX_INSTALL_METHOD",
        "MELIX_JUDGE_MODEL", "MELIX_JUDGE_SERVER_ID", "MELIX_MAX_MODELS", "MELIX_MLX_LM",
        "MELIX_PROBE_MODE", "MELIX_PROJECT_ROOT", "MELIX_PUBLIC_CLI_PATH",
        "MELIX_RESTART_STACK_PER_MODEL", "MELIX_RUN_ID", "MELIX_RUN_TMP_ROOT",
        "MELIX_SERVICE_INSTANCE_NAME", "MELIX_START_INDEX", "MELIX_UPDATE_CHANNEL", "MELIX_UV",
    ]
    private static let reservedEnvironmentKeys: Set<String> = privateServiceEnvironmentKeys
        .union(controlPlaneEnvironmentKeys)
        .union(swiftWorkerEnvironmentKeys)
        .union(pythonWorkerEnvironmentKeys)
        .union(cliEnvironmentKeys)
        .union(stripOnlyEnvironmentKeys)
        .union([
        configPathEnvironmentKey,
        keyListEnvironmentKey,
        "MELIX_CONTROL_PLANE_SOCKET_PATH",
        "HOME",
        "PATH",
        "TMPDIR",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "DEVELOPER_DIR",
        "SDKROOT",
        "TOOLCHAINS",
        "PYTHONPATH",
        "UV_CACHE_DIR",
        "CLANG_MODULE_CACHE_PATH",
        "MELIX_REPO_ROOT",
        "MELIX_CLI",
        "MELIX_PUBLIC_CLI_PATH",
        "MELIX_HOME",
        "MELIX_RUNTIME_DIR",
        "MELIX_SERVICE_INSTANCE_NAME",
        "MELIX_MODEL_ROOTS",
        "MELIX_SWIFT_MLX_METALLIB_PATH",
        "MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE",
        "MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE",
        "MELIX_SWIFT_DFLASH_PROBE",
        "MELIX_SWIFT_DFLASH_PROBE_PATH",
        "MELIX_DEV_TEXT_MODEL_PATH",
        "MELIX_DEV_VLM_MODEL_PATH",
        "MELIX_MANAGED_MODEL_ROOT",
        "MELIX_AUDIO_RUNTIME_PACK_ROOT",
        "MELIX_MODEL_OPS_JOBS_ROOT",
        "MELIX_EVALUATION_JOBS_ROOT",
        "MELIX_GATEWAY_CONFIG_STORE_PATH",
        "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH",
        "MELIX_IMAGE_DEFAULTS_STORE_PATH",
        "MELIX_HTTP_HOST",
        "MELIX_HTTP_CONNECT_HOST",
        "MELIX_HTTP_PORT",
        "MELIX_BACKEND_MODE",
        "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE",
        "MELIX_PYTHON_BRIDGE_EXECUTABLE",
        "MELIX_MENU_BAR_STARTUP_SURFACE",
        "MELIX_MENU_BAR_PRESENTATION_MODE",
        "MELIX_MENU_BAR_TERMINATION_MODE",
        "MELIX_APP_BUNDLE_PATH",
        "MELIX_LOGICAL_PRODUCT_ID",
        "MELIX_PACKAGING_TARGET_ID",
        "MELIX_PACKAGING_KIND",
        "MELIX_PRODUCT_VERSION",
        "MELIX_UPDATE_CHANNEL_PATH",
        "MELIX_PRODUCT_MANIFEST_PATH",
        "MELIX_LOGS_DIR",
        "MELIX_CONTROL_PLANE_METRICS_PATH",
        "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH",
        "MELIX_PYTHON_WORKER_METRICS_PATH",
        "MELIX_ACTIVE_RUNTIME_PATH",
        "MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY",
        "PYTHONUNBUFFERED",
        "PYTHONPYCACHEPREFIX",
        "PYTHONNOUSERSITE",
        "PYTHONSAFEPATH",
        "MELIX_APP_SCREENSHOT_CAPTURE",
        "MELIX_APP_SCREENSHOT_APP_PATH",
        "MELIX_APP_SCREENSHOT_HEIGHT",
        "MELIX_APP_SCREENSHOT_OUTPUT_DIR",
        "MELIX_APP_SCREENSHOT_WIDTH",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_BENCH_SUITES",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_DATASET",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_SUITES",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_LOCAL_MODEL_PATH",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MATRIX_SUITES",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_SERVER_SESSION_ID",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TRAINING_FIXTURE",
        "MELIX_CONTROL_PLANE_PID",
        "MELIX_HTTP_READY",
        "MELIX_PYTHON_WORKER_PID",
        "MELIX_SWIFT_WORKER_PID",
    ])
    // MCP_RESERVED_ENVIRONMENT_KEYS_END

    private static let appEnvironmentKeys: Set<String> = Set([
        "MELIX_PUBLIC_CLI_PATH",
        "MELIX_APP_SCREENSHOT_CAPTURE",
        "MELIX_APP_SCREENSHOT_APP_PATH",
        "MELIX_APP_SCREENSHOT_HEIGHT",
        "MELIX_APP_SCREENSHOT_OUTPUT_DIR",
        "MELIX_APP_SCREENSHOT_WIDTH",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_BENCH_SUITES",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_DATASET",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_SUITES",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_LOCAL_MODEL_PATH",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MATRIX_SUITES",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_SERVER_SESSION_ID",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP",
        "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TRAINING_FIXTURE",
        "MELIX_DEV_RERANK_BACKEND_ID",
        "MELIX_DEV_RERANK_SCORING_MODE",
        "MELIX_DEV_RERANK_YES_NO_LABELS",
        "MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS",
        "MELIX_CONTROL_PLANE_PID",
        "MELIX_MENU_BAR_TERMINATION_MODE",
        "MELIX_PYTHON_WORKER_PID",
        "MELIX_SWIFT_WORKER_PID",
    ]).union(cliEnvironmentKeys)

    enum BoundaryError: Error {
        case invalidConfiguration
    }

    static func sanitizedEnvironment(
        _ environment: [String: String],
        fileManager: FileManager = .default
    ) throws -> [String: String] {
        var sanitized = environment.filter { key, _ in
            reservedEnvironmentKeys.contains(key)
                && privateServiceEnvironmentKeys.contains(key) == false
                && (
                    controlPlaneEnvironmentKeys.contains(key) == false
                        || appEnvironmentKeys.contains(key)
                )
                && (
                    swiftWorkerEnvironmentKeys.contains(key) == false
                        || appEnvironmentKeys.contains(key)
                )
                && pythonWorkerEnvironmentKeys.contains(key) == false
                && stripOnlyEnvironmentKeys.contains(key) == false
        }
        let credentialKeys = try credentialEnvironmentKeys(
            environment: environment,
            fileManager: fileManager
        )
        for key in privateServiceEnvironmentKeys.union(credentialKeys) {
            sanitized.removeValue(forKey: key)
        }
        if let explicitPath = environment[configPathEnvironmentKey]?
            .trimmingCharacters(in: .whitespacesAndNewlines), explicitPath.isEmpty == false
        {
            sanitized[configPathEnvironmentKey] = expandedFileURL(
                path: explicitPath,
                environment: environment,
                fileManager: fileManager
            ).standardizedFileURL.path
        }
        sanitized.removeValue(forKey: keyListEnvironmentKey)
        return sanitized
    }

    static func credentialEnvironmentKeys(
        environment: [String: String],
        fileManager: FileManager = .default
    ) throws -> Set<String> {
        var keys = Set<String>()
        var referenceCount = 0
        var encodedReferenceTargetBytes = 0
        var httpHeaderCount = 0
        var encodedHTTPHeaderBytes = 0
        var sourceIDs = Set<String>()
        if let rawKeyList = environment[keyListEnvironmentKey] {
            let listedKeys = rawKeyList.split(separator: ",", omittingEmptySubsequences: true)
            guard listedKeys.count <= maximumCredentialReferences else {
                throw BoundaryError.invalidConfiguration
            }
            for rawKey in listedKeys {
                let key = String(rawKey)
                try insertCredentialKey(key, into: &keys)
            }
        }

        let explicitPath = environment[configPathEnvironmentKey]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let configURL: URL
        let configIsRequired: Bool
        if let explicitPath, explicitPath.isEmpty == false {
            guard
                explicitPath.utf8.count <= 4_096,
                explicitPath.contains("\0") == false,
                explicitPath.hasPrefix("/") || explicitPath == "~" || explicitPath.hasPrefix("~/")
            else {
                throw BoundaryError.invalidConfiguration
            }
            configURL = expandedFileURL(
                path: explicitPath,
                environment: environment,
                fileManager: fileManager
            )
            configIsRequired = true
        } else if let melixHome = environment["MELIX_HOME"]?
            .trimmingCharacters(in: .whitespacesAndNewlines), melixHome.isEmpty == false
        {
            configURL = expandedFileURL(
                path: melixHome,
                environment: environment,
                fileManager: fileManager
            )
                .appendingPathComponent("config/mcp-tools.json")
            configIsRequired = false
        } else {
            let homeDirectory: URL
            if let home = environment["HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines),
               home.hasPrefix("/")
            {
                homeDirectory = URL(fileURLWithPath: home)
            } else {
                homeDirectory = fileManager.homeDirectoryForCurrentUser
            }
            configURL = homeDirectory.appendingPathComponent(".melix/config/mcp-tools.json")
            configIsRequired = false
        }

        guard fileManager.fileExists(atPath: configURL.path) else {
            if configIsRequired {
                throw BoundaryError.invalidConfiguration
            }
            return keys
        }
        let encodedPayload: Data
        do {
            encodedPayload = try MCPToolCatalog.boundedConfigurationData(
                atPath: configURL.path
            )
        } catch {
            throw BoundaryError.invalidConfiguration
        }
        guard MCPToolCatalog.configurationDataPassesPreflight(encodedPayload) else {
            throw BoundaryError.invalidConfiguration
        }
        let payload: Any
        do {
            payload = try JSONSerialization.jsonObject(with: encodedPayload)
        } catch {
            throw BoundaryError.invalidConfiguration
        }
        guard
            let document = payload as? [String: Any],
            let sources = document["sources"] as? [Any],
            sources.count <= maximumSources
        else {
            throw BoundaryError.invalidConfiguration
        }
        if let parserMode = document["default_parser_mode"], !(parserMode is String) {
            throw BoundaryError.invalidConfiguration
        }
        for rawSource in sources {
            guard let source = rawSource as? [String: Any] else {
                throw BoundaryError.invalidConfiguration
            }
            guard let rawSourceID = source["source_id"] as? String else {
                throw BoundaryError.invalidConfiguration
            }
            let sourceID = rawSourceID
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            try validateSourceID(sourceID)
            guard sourceIDs.insert(sourceID).inserted else {
                throw BoundaryError.invalidConfiguration
            }
            if let enabled = source["enabled"], !isJSONBoolean(enabled) {
                throw BoundaryError.invalidConfiguration
            }
            for fieldName in ["namespaces", "redaction_terms"] {
                if let rawValues = source[fieldName] {
                    guard
                        let values = rawValues as? [Any],
                        values.allSatisfy({ $0 is String })
                    else {
                        throw BoundaryError.invalidConfiguration
                    }
                }
            }
            try validateUnsignedInteger(
                source["request_timeout_ms"],
                maximum: UInt64(UInt32.max)
            )
            try validateUnsignedInteger(
                source["connect_timeout_ms"],
                maximum: UInt64(UInt32.max)
            )
            try validateUnsignedInteger(
                source["max_result_bytes"],
                maximum: UInt64.max
            )
            if let revision = source["configuration_revision"], !(revision is String) {
                throw BoundaryError.invalidConfiguration
            }
            guard let rawTransport = source["transport"] else {
                continue
            }
            guard let transport = rawTransport as? [String: Any] else {
                throw BoundaryError.invalidConfiguration
            }
            guard let transportKind = transport["kind"] as? String else {
                throw BoundaryError.invalidConfiguration
            }
            switch transportKind {
            case "stdio":
                guard
                    transport["url"] == nil,
                    transport["headers"] == nil,
                    transport["header_environment_references"] == nil
                else {
                    throw BoundaryError.invalidConfiguration
                }
                guard
                    let command = transport["command"] as? String,
                    command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false,
                    command.contains("\0") == false,
                    let arguments = (transport["arguments"] ?? [Any]()) as? [Any],
                    arguments.allSatisfy({ $0 is String }),
                    (transport["working_directory"] ?? "") is String,
                    ((transport["working_directory"] as? String) ?? "").isEmpty
                        || ((transport["working_directory"] as? String) ?? "").hasPrefix("/")
                else {
                    throw BoundaryError.invalidConfiguration
                }
            case "streamable_http":
                guard
                    transport["command"] == nil,
                    transport["arguments"] == nil,
                    transport["working_directory"] == nil,
                    transport["environment_references"] == nil
                else {
                    throw BoundaryError.invalidConfiguration
                }
                guard
                    let url = transport["url"] as? String,
                    url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false,
                    let components = URLComponents(string: url),
                    let scheme = components.scheme?.lowercased(),
                    scheme == "http" || scheme == "https",
                    let encodedHost = components.host?.lowercased()
                else {
                    throw BoundaryError.invalidConfiguration
                }
                let host = encodedHost.hasPrefix("[") && encodedHost.hasSuffix("]")
                    ? String(encodedHost.dropFirst().dropLast())
                    : encodedHost
                guard
                    host.isEmpty == false,
                    components.user == nil,
                    components.password == nil,
                    components.fragment == nil,
                    url.contains("#") == false,
                    scheme != "http" || ["localhost", "127.0.0.1", "::1"].contains(host)
                else {
                    throw BoundaryError.invalidConfiguration
                }
            default:
                throw BoundaryError.invalidConfiguration
            }
            let rawHeaders = transport["headers"] ?? [String: String]()
            guard let headers = rawHeaders as? [String: Any] else {
                throw BoundaryError.invalidConfiguration
            }
            var sourceHTTPHeaderNames = Set<String>()
            for (headerName, rawHeaderValue) in headers {
                guard rawHeaderValue is String else {
                    throw BoundaryError.invalidConfiguration
                }
                try validateHTTPHeaderName(headerName)
                guard isCredentialHTTPHeaderName(headerName) == false else {
                    throw BoundaryError.invalidConfiguration
                }
                guard sourceHTTPHeaderNames.insert(headerName.lowercased()).inserted else {
                    throw BoundaryError.invalidConfiguration
                }
                httpHeaderCount += 1
                encodedHTTPHeaderBytes += headerName.utf8.count
                if httpHeaderCount > 1 {
                    encodedHTTPHeaderBytes += 1
                }
                guard
                    httpHeaderCount <= maximumCredentialReferences,
                    encodedHTTPHeaderBytes <= maximumReferenceTargetListBytes
                else {
                    throw BoundaryError.invalidConfiguration
                }
            }
            let referenceFieldNames = transportKind == "stdio"
                ? ["environment_references"]
                : ["header_environment_references"]
            for fieldName in referenceFieldNames {
                let rawReferences = transport[fieldName] ?? [String: String]()
                guard let references = rawReferences as? [String: Any] else {
                    throw BoundaryError.invalidConfiguration
                }
                for (childKey, rawSourceKey) in references {
                    guard let sourceKey = rawSourceKey as? String else {
                        throw BoundaryError.invalidConfiguration
                    }
                    if fieldName == "environment_references" {
                        try validateEnvironmentKey(childKey)
                    } else {
                        try validateHTTPHeaderName(childKey)
                        guard sourceHTTPHeaderNames.insert(childKey.lowercased()).inserted else {
                            throw BoundaryError.invalidConfiguration
                        }
                        httpHeaderCount += 1
                        encodedHTTPHeaderBytes += childKey.utf8.count
                        if httpHeaderCount > 1 {
                            encodedHTTPHeaderBytes += 1
                        }
                        guard
                            httpHeaderCount <= maximumCredentialReferences,
                            encodedHTTPHeaderBytes <= maximumReferenceTargetListBytes
                        else {
                            throw BoundaryError.invalidConfiguration
                        }
                    }
                    referenceCount += 1
                    encodedReferenceTargetBytes += childKey.utf8.count
                    if referenceCount > 1 {
                        encodedReferenceTargetBytes += 1
                    }
                    guard
                        referenceCount <= maximumCredentialReferences,
                        encodedReferenceTargetBytes <= maximumReferenceTargetListBytes
                    else {
                        throw BoundaryError.invalidConfiguration
                    }
                    try insertCredentialKey(sourceKey, into: &keys)
                }
            }
        }
        return keys
    }

    private static func validateCredentialKey(_ key: String) throws {
        try validateEnvironmentKey(key)
        guard
            key.utf8.count <= maximumCredentialKeyBytes,
            reservedEnvironmentKeys.contains(key) == false
        else {
            throw BoundaryError.invalidConfiguration
        }
    }

    private static func insertCredentialKey(
        _ key: String,
        into keys: inout Set<String>
    ) throws {
        try validateCredentialKey(key)
        keys.insert(key)
        let encodedBytes = keys.reduce(0) { $0 + $1.utf8.count }
            + max(0, keys.count - 1)
        guard
            keys.count <= maximumCredentialReferences,
            encodedBytes <= maximumCredentialKeyListBytes
        else {
            throw BoundaryError.invalidConfiguration
        }
    }

    private static func expandedFileURL(
        path: String,
        environment: [String: String],
        fileManager: FileManager
    ) -> URL {
        guard path == "~" || path.hasPrefix("~/") else {
            return URL(fileURLWithPath: path)
        }
        let homeDirectory: URL
        if let home = environment["HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           home.hasPrefix("/")
        {
            homeDirectory = URL(fileURLWithPath: home)
        } else {
            homeDirectory = fileManager.homeDirectoryForCurrentUser
        }
        guard path != "~" else {
            return homeDirectory
        }
        return homeDirectory.appendingPathComponent(String(path.dropFirst(2)))
    }

    private static func validateEnvironmentKey(_ key: String) throws {
        let scalars = key.unicodeScalars
        guard
            key.utf8.count <= maximumReferenceTargetBytes,
            let first = scalars.first,
            isUppercaseASCII(first) || first == "_"
        else {
            throw BoundaryError.invalidConfiguration
        }
        guard scalars.dropFirst().allSatisfy({ scalar in
            isUppercaseASCII(scalar) || (48...57).contains(Int(scalar.value)) || scalar == "_"
        }) else {
            throw BoundaryError.invalidConfiguration
        }
    }

    private static func validateSourceID(_ sourceID: String) throws {
        let scalars = sourceID.unicodeScalars
        guard
            sourceID.utf8.count <= maximumSourceIDBytes,
            let first = scalars.first,
            (97...122).contains(Int(first.value)) || (48...57).contains(Int(first.value)),
            scalars.dropFirst().allSatisfy({ scalar in
                (97...122).contains(Int(scalar.value))
                    || (48...57).contains(Int(scalar.value))
                    || scalar == "_"
                    || scalar == "-"
            })
        else {
            throw BoundaryError.invalidConfiguration
        }
    }

    private static func validateUnsignedInteger(
        _ rawValue: Any?,
        maximum: UInt64
    ) throws {
        guard let rawValue else {
            return
        }
        guard
            let number = rawValue as? NSNumber,
            CFGetTypeID(number) != CFBooleanGetTypeID(),
            let value = UInt64(number.stringValue),
            value <= maximum
        else {
            throw BoundaryError.invalidConfiguration
        }
    }

    private static func isJSONBoolean(_ rawValue: Any) -> Bool {
        guard let number = rawValue as? NSNumber else {
            return false
        }
        return CFGetTypeID(number) == CFBooleanGetTypeID()
    }

    private static func isCredentialHTTPHeaderName(_ name: String) -> Bool {
        credentialHTTPHeaderPattern.firstMatch(
            in: name,
            range: NSRange(name.startIndex..<name.endIndex, in: name)
        ) != nil
    }

    private static func validateHTTPHeaderName(_ name: String) throws {
        let punctuation = Set("!#$%&'*+-.^_`|~".unicodeScalars)
        guard
            name.isEmpty == false,
            name.utf8.count <= maximumReferenceTargetBytes,
            name.unicodeScalars.allSatisfy({ scalar in
                isUppercaseASCII(scalar)
                    || (97...122).contains(Int(scalar.value))
                    || (48...57).contains(Int(scalar.value))
                    || punctuation.contains(scalar)
            })
        else {
            throw BoundaryError.invalidConfiguration
        }
    }

    private static func isUppercaseASCII(_ scalar: UnicodeScalar) -> Bool {
        (65...90).contains(Int(scalar.value))
    }
}

@MainActor
public final class MenuBarTerminationCoordinator: NSObject {
    private let mode: MenuBarTerminationMode
    private let repoRoot: String
    private let runtimeDirectory: String?
    private let workerProcessIDs: [pid_t]
    private let terminateApplication: @MainActor @Sendable () -> Void
    private let terminateWorkerProcess: @MainActor @Sendable (pid_t) -> Void
    private let launchDevDownScript: @MainActor @Sendable (String, String?) -> Void
    private var isTerminationRequested = false

    public init(
        mode: MenuBarTerminationMode,
        repoRoot: String,
        runtimeDirectory: String?,
        workerProcessIDs: [pid_t]? = nil,
        terminateApplication: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) },
        terminateWorkerProcess: @escaping @MainActor @Sendable (pid_t) -> Void = { pid in
            _ = Darwin.kill(pid, SIGTERM)
        },
        launchDevDownScript: (@MainActor @Sendable (String, String?) -> Void)? = nil
    ) {
        self.mode = mode
        self.repoRoot = repoRoot
        self.runtimeDirectory = runtimeDirectory
        self.workerProcessIDs = workerProcessIDs ?? MenuBarTerminationCoordinator.bundledWorkerProcessIDs()
        self.terminateApplication = terminateApplication
        self.terminateWorkerProcess = terminateWorkerProcess
        self.launchDevDownScript = launchDevDownScript ?? { repoRoot, runtimeDirectory in
            MenuBarTerminationCoordinator.launchDevDownProcess(
                repoRoot: repoRoot,
                runtimeDirectory: runtimeDirectory
            )
        }
    }

    @objc
    public func handleQuitMenuItem(_ sender: Any?) {
        _ = sender
        requestTermination()
    }

    public func requestTermination() {
        guard isTerminationRequested == false else {
            return
        }

        isTerminationRequested = true
        for workerProcessID in workerProcessIDs {
            terminateWorkerProcess(workerProcessID)
        }
        if mode == .devDownScript {
            launchDevDownScript(repoRoot, runtimeDirectory)
        }
        terminateApplication()
    }

    static func bundledWorkerProcessIDs(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> [pid_t] {
        var seenProcessIDs = Set<pid_t>()
        return [
            "MELIX_CONTROL_PLANE_PID",
            "MELIX_SWIFT_WORKER_PID",
            "MELIX_PYTHON_WORKER_PID",
        ].compactMap { key in
            guard
                let rawValue = environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines),
                let processID = pid_t(rawValue),
                processID > 0,
                seenProcessIDs.insert(processID).inserted
            else {
                return nil
            }

            return processID
        }
    }

    static func launchDevDownProcess(repoRoot: String, runtimeDirectory: String?) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [
            "-c",
            """
import os, subprocess, sys
script_path = sys.argv[1]
runtime_dir = sys.argv[2] if len(sys.argv) > 2 else ""
env = os.environ.copy()
if runtime_dir:
    env["MELIX_RUNTIME_DIR"] = runtime_dir
subprocess.Popen(
    ["/bin/bash", script_path],
    env=env,
    start_new_session=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
""",
            URL(fileURLWithPath: repoRoot)
                .appendingPathComponent("scripts/dev_down.sh")
                .path,
            runtimeDirectory ?? "",
        ]
        try? process.run()
    }
}

enum MenuBarApplicationMenuBuilder {
    @MainActor
    static func makeMainMenu(
        target: AnyObject,
        action: Selector,
        updateTarget: AnyObject? = nil,
        updateAction: Selector? = nil,
        updateEnabled: Bool = false
    ) -> NSMenu {
        let mainMenu = NSMenu(title: MelixBranding.productName)
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu(title: MelixBranding.productName)
        if let updateTarget, let updateAction {
            let updateItem = NSMenuItem(
                title: "Check for Updates…",
                action: updateAction,
                keyEquivalent: ""
            )
            updateItem.target = updateTarget
            updateItem.isEnabled = updateEnabled
            appMenu.addItem(updateItem)
            appMenu.addItem(.separator())
        }
        let quitItem = NSMenuItem(title: "Quit Melix", action: action, keyEquivalent: "q")
        quitItem.target = target
        quitItem.keyEquivalentModifierMask = [.command]
        appMenu.addItem(quitItem)
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        let editMenuItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(NSMenuItem(title: "Undo", action: Selector(("undo:")), keyEquivalent: "z"))
        let redoItem = NSMenuItem(title: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        redoItem.keyEquivalentModifierMask = [.command, .shift]
        editMenu.addItem(redoItem)
        editMenu.addItem(.separator())
        editMenu.addItem(NSMenuItem(title: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x"))
        editMenu.addItem(NSMenuItem(title: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c"))
        editMenu.addItem(NSMenuItem(title: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v"))
        editMenu.addItem(NSMenuItem(title: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a"))
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)

        return mainMenu
    }
}

@MainActor
public final class MelixMenuBarBootstrap {
    let viewModel: RuntimeViewModel
    let cliWorkflowRunner: (any MelixCLIWorkflowRunning)?
    private let startupSurface: MenuBarStartupSurface
    private let desktopFoundationPresenter: any DesktopFoundationPresenting
    private let commandCenterPresenter: any DesktopFoundationPresenting
    private let statusMenu: any StatusMenuInstalling

    public init(
        client: any ControlPlaneXPCClient,
        startupSurface: MenuBarStartupSurface = .console,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore(),
        melixHome: MelixHome = MelixHome(),
        operatorSessionStore: (any OperatorSessionStoring)? = nil,
        cliWorkflowRunner: (any MelixCLIWorkflowRunning)? = nil,
        operatorCommandRunner: MelixCLIRunner? = nil,
        serverSessionAPIKeyStore: (any ServerSessionAPIKeyStoring)? = nil,
        remoteServerStore: (any RemoteServerStoring)? = nil,
        evaluationPromptStore: (any EvaluationPromptStoring)? = nil,
        loraTrainingJobStore: (any LoraTrainingJobStoring)? = nil,
        huggingFaceTokenStore: (any HuggingFaceTokenStoring)? = nil,
        desktopFoundationPresenterFactory: @MainActor @escaping (
            RuntimeViewModel,
            MenuBarMetricsStore
        ) -> any DesktopFoundationPresenting = { viewModel, metrics in
            DesktopFoundationPresenter(viewModel: viewModel, metrics: metrics)
        },
        commandCenterPresenterFactory: @MainActor @escaping (
            RuntimeViewModel,
            MenuBarMetricsStore
        ) -> any DesktopFoundationPresenting = { viewModel, metrics in
            CommandCenterPresenter(viewModel: viewModel, metrics: metrics)
        },
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) },
        statusMenuFactory: @MainActor @escaping (
            RuntimeViewModel,
            @escaping @MainActor @Sendable () -> Void,
            @escaping @MainActor @Sendable () -> Void
        ) -> any StatusMenuInstalling = { viewModel, openConsole, terminationHandler in
            StatusMenu(
                viewModel: viewModel,
                openConsoleHandler: openConsole,
                terminationHandler: terminationHandler
            )
        }
    ) {
        let resolvedOperatorSessionStore = operatorSessionStore ?? OperatorSessionStore(melixHome: melixHome)
        let resolvedOperatorCommandRunner = operatorCommandRunner ?? (
            cliWorkflowRunner == nil
                ? MelixCLIRunner(
                    client: client,
                    operatorSessionStore: MelixOperatorSessionStore(melixHome: melixHome)
                )
                : nil
        )
        let resolvedServerSessionAPIKeyStore = serverSessionAPIKeyStore ?? ServerSessionAPIKeyStore(melixHome: melixHome)
        let resolvedRemoteServerStore = remoteServerStore ?? RemoteServerStore(melixHome: melixHome)
        let resolvedEvaluationPromptStore = evaluationPromptStore ?? EvaluationPromptStore(melixHome: melixHome)
        let resolvedLoraTrainingJobStore = loraTrainingJobStore ?? LoraTrainingJobStore(melixHome: melixHome)
        let resolvedHuggingFaceTokenStore = huggingFaceTokenStore ?? HuggingFaceTokenStore(melixHome: melixHome)
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: resolvedOperatorSessionStore,
            cliWorkflowRunner: cliWorkflowRunner,
            operatorCommandRunner: resolvedOperatorCommandRunner,
            serverSessionAPIKeyStore: resolvedServerSessionAPIKeyStore,
            remoteServerStore: resolvedRemoteServerStore,
            evaluationPromptStore: resolvedEvaluationPromptStore,
            loraTrainingJobStore: resolvedLoraTrainingJobStore,
            huggingFaceTokenStore: resolvedHuggingFaceTokenStore
        )
        let desktopFoundationPresenter = desktopFoundationPresenterFactory(viewModel, metrics)
        let commandCenterPresenter = commandCenterPresenterFactory(viewModel, metrics)
        viewModel.openCommandCenterAction = {
            commandCenterPresenter.show()
        }
        self.viewModel = viewModel
        self.cliWorkflowRunner = cliWorkflowRunner
        self.startupSurface = startupSurface
        self.desktopFoundationPresenter = desktopFoundationPresenter
        self.commandCenterPresenter = commandCenterPresenter
        self.statusMenu = statusMenuFactory(viewModel, {
            desktopFoundationPresenter.show()
        }, terminationHandler)
    }

    public func start() {
        statusMenu.install()
        switch startupSurface {
        case .tray:
            break
        case .console:
            desktopFoundationPresenter.show()
        case .commandCenter:
            commandCenterPresenter.show()
        }
        Task {
            await viewModel.start()
        }
    }

    static func live(
        environment: MenuBarBootstrapEnvironment,
        cliProcessExecutor: any MelixCLIProcessExecuting = LiveMelixCLIProcessExecutor(),
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) }
    ) -> MelixMenuBarBootstrap {
        let processEnvironment: [String: String]
        let credentialBoundaryAccepted: Bool
        do {
            processEnvironment = try environment.cliEnvironment(base: ProcessInfo.processInfo.environment)
            credentialBoundaryAccepted = true
        } catch {
            processEnvironment = environment.minimumProductEnvironment()
            credentialBoundaryAccepted = false
        }
        let daemonService = ControlPlaneIPCExecutionClient(
            socketPath: environment.controlPlaneSocketPath
        )
        let localClient = LocalControlPlaneXPCClient(service: daemonService)
        let melixHome = MelixHome(environment: processEnvironment)
        let cliWorkflowRunner = credentialBoundaryAccepted
            ? MelixSubprocessCLIWorkflowRunner(
                cliExecutablePath: environment.cliExecutablePath,
                environment: processEnvironment,
                processExecutor: cliProcessExecutor
            )
            : nil
        return MelixMenuBarBootstrap(
            client: localClient,
            startupSurface: environment.startupSurface,
            melixHome: melixHome,
            operatorSessionStore: OperatorSessionStore(melixHome: melixHome),
            cliWorkflowRunner: cliWorkflowRunner,
            serverSessionAPIKeyStore: ServerSessionAPIKeyStore(melixHome: melixHome),
            remoteServerStore: RemoteServerStore(melixHome: melixHome),
            evaluationPromptStore: EvaluationPromptStore(melixHome: melixHome),
            loraTrainingJobStore: LoraTrainingJobStore(melixHome: melixHome),
            terminationHandler: terminationHandler
        )
    }

    public static func live(
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) }
    ) -> MelixMenuBarBootstrap {
        live(
            environment: MenuBarBootstrapEnvironment(environment: ProcessInfo.processInfo.environment),
            terminationHandler: terminationHandler
        )
    }

    static func liveCLIRunnerBaseCommand(
        environment: [String: String],
        repoRoot: String
    ) -> [String] {
        if let publicCLIPath = environment["MELIX_PUBLIC_CLI_PATH"]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           publicCLIPath.isEmpty == false {
            return [publicCLIPath]
        }
        return [
            "/usr/bin/env",
            "swift",
            "run",
            "--package-path",
            repoRoot,
            "melix",
        ]
    }

    private static func liveCLIRunner(
        client: any ControlPlaneXPCClient,
        melixHome: MelixHome,
        repoRoot: String,
        environment: [String: String]
    ) -> MelixCLIRunner {
        let executor = MelixCLIProcessExecutor(
            baseCommand: liveCLIRunnerBaseCommand(environment: environment, repoRoot: repoRoot),
            environment: environment,
            workingDirectory: repoRoot
        )
        return MelixCLIRunner(
            client: client,
            environment: environment,
            operatorSessionStore: MelixOperatorSessionStore(melixHome: melixHome),
            commandExecutor: executor.run
        )
    }
}

struct MenuBarBootstrapEnvironment {
    let repoRoot: String
    let cliExecutablePath: String
    let controlPlaneSocketPath: String
    let startupSurface: MenuBarStartupSurface
    let presentationMode: MenuBarPresentationMode
    let terminationMode: MenuBarTerminationMode
    let runtimeDirectory: String?

    init(environment: [String: String]) {
        if let repoRoot = environment["MELIX_REPO_ROOT"], !repoRoot.isEmpty {
            self.repoRoot = repoRoot
        } else {
            self.repoRoot = MenuBarBootstrapEnvironment.inferRepoRoot()
        }
        self.cliExecutablePath = environment["MELIX_CLI"] ?? MenuBarBootstrapEnvironment.inferCLIExecutablePath(
            repoRoot: self.repoRoot
        )
        self.controlPlaneSocketPath =
            environment["MELIX_CONTROL_PLANE_SOCKET_PATH"] ?? "/tmp/melix-controlplane.sock"
        self.startupSurface = MenuBarStartupSurface(
            environmentValue: environment["MELIX_MENU_BAR_STARTUP_SURFACE"]
        )
        self.presentationMode = MenuBarPresentationMode(
            environmentValue: environment["MELIX_MENU_BAR_PRESENTATION_MODE"]
        )
        self.terminationMode = MenuBarTerminationMode(
            environmentValue: environment["MELIX_MENU_BAR_TERMINATION_MODE"]
        )
        self.runtimeDirectory =
            environment["MELIX_RUNTIME_DIR"]
            ?? URL(fileURLWithPath: self.controlPlaneSocketPath).deletingLastPathComponent().path
    }

    static func inferRepoRoot(anchorPath: String = #filePath) -> String {
        let anchorURL = URL(fileURLWithPath: anchorPath).deletingLastPathComponent()
        if let repoRoot = locateRepoRoot(startingAt: anchorURL) {
            return repoRoot.path
        }
        return FileManager.default.currentDirectoryPath
    }

    private static func locateRepoRoot(startingAt startURL: URL) -> URL? {
        var candidate = startURL
        while true {
            let agentsPath = candidate.appendingPathComponent("AGENTS.md").path
            let gitPath = candidate.appendingPathComponent(".git").path
            if FileManager.default.fileExists(atPath: agentsPath)
                || FileManager.default.fileExists(atPath: gitPath)
            {
                return candidate
            }
            let parent = candidate.deletingLastPathComponent()
            if parent.path == candidate.path {
                return nil
            }
            candidate = parent
        }
    }

    private static func inferCLIExecutablePath(repoRoot: String) -> String {
        let repoURL = URL(fileURLWithPath: repoRoot)
        let candidates = [
            repoURL.appendingPathComponent(".build/arm64-apple-macosx/debug/melix").path,
            repoURL.appendingPathComponent(".build/arm64-apple-macosx/release/melix").path,
            repoURL.appendingPathComponent(".build/debug/melix").path,
            repoURL.appendingPathComponent(".build/release/melix").path,
            "melix",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) } ?? candidates[0]
    }

    func cliEnvironment(base: [String: String]) throws -> [String: String] {
        productEnvironment(
            base: try MCPEnvironmentCredentialBoundary.sanitizedEnvironment(base)
        )
    }

    func minimumProductEnvironment() -> [String: String] {
        productEnvironment(base: [:])
    }

    private func productEnvironment(base: [String: String]) -> [String: String] {
        var merged = base
        merged["MELIX_REPO_ROOT"] = repoRoot
        merged["MELIX_CONTROL_PLANE_SOCKET_PATH"] = controlPlaneSocketPath
        if let runtimeDirectory, runtimeDirectory.isEmpty == false {
            merged["MELIX_RUNTIME_DIR"] = runtimeDirectory
        }
        let melixHome = MelixHome(environment: merged)
        func isMissingOrEmpty(_ key: String) -> Bool {
            merged[key]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false
        }
        if isMissingOrEmpty("MELIX_HOME") {
            merged["MELIX_HOME"] = melixHome.rootURL.path
        }
        if isMissingOrEmpty("MELIX_MANAGED_MODEL_ROOT") {
            merged["MELIX_MANAGED_MODEL_ROOT"] = melixHome.managedModelRootURL.path
        }
        if isMissingOrEmpty("MELIX_AUDIO_RUNTIME_PACK_ROOT") {
            merged["MELIX_AUDIO_RUNTIME_PACK_ROOT"] = melixHome.audioRuntimePackRootURL.path
        }
        if isMissingOrEmpty("MELIX_MODEL_OPS_JOBS_ROOT") {
            merged["MELIX_MODEL_OPS_JOBS_ROOT"] = melixHome.modelOpsJobsRootURL.path
        }
        if isMissingOrEmpty("MELIX_EVALUATION_JOBS_ROOT") {
            merged["MELIX_EVALUATION_JOBS_ROOT"] = melixHome.evaluationJobsRootURL.path
        }
        if isMissingOrEmpty("MELIX_GATEWAY_CONFIG_STORE_PATH") {
            merged["MELIX_GATEWAY_CONFIG_STORE_PATH"] = melixHome.configDirectoryURL
                .appendingPathComponent("gateway-config.json")
                .path
        }
        if isMissingOrEmpty("MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH") {
            merged["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"] = melixHome.configDirectoryURL
                .appendingPathComponent("gateway-serving-defaults.json")
                .path
        }
        if isMissingOrEmpty("MELIX_IMAGE_DEFAULTS_STORE_PATH") {
            merged["MELIX_IMAGE_DEFAULTS_STORE_PATH"] = melixHome.configDirectoryURL
                .appendingPathComponent("image-defaults.json")
                .path
        }
        return merged
    }
}

@MainActor
enum MelixMenuBarLauncher {
    static func launch(
        application: any MenuBarApplicationLifecycle,
        presentationMode: MenuBarPresentationMode,
        terminationCoordinator: MenuBarTerminationCoordinator = MenuBarTerminationCoordinator(
            mode: .terminate,
            repoRoot: FileManager.default.currentDirectoryPath,
            runtimeDirectory: nil
        ),
        softwareUpdates: SoftwareUpdateController = .shared,
        bootstrapFactory: (@escaping @MainActor @Sendable () -> Void) -> MelixMenuBarBootstrap,
        retain: (MelixMenuBarBootstrap) -> Void
    ) {
        softwareUpdates.start()
        application.setActivationPolicy(presentationMode.activationPolicy)
        application.setMainMenu(
            MenuBarApplicationMenuBuilder.makeMainMenu(
                target: terminationCoordinator,
                action: #selector(MenuBarTerminationCoordinator.handleQuitMenuItem(_:)),
                updateTarget: softwareUpdates,
                updateAction: #selector(SoftwareUpdateController.checkForUpdates(_:)),
                updateEnabled: softwareUpdates.canCheckForUpdates
            )
        )

        let bootstrap = bootstrapFactory {
            terminationCoordinator.requestTermination()
        }
        retain(bootstrap)
        bootstrap.start()

        application.run()
    }
}

@main
@MainActor
enum MelixMenuBarApp {
    private static var retainedBootstrap: MelixMenuBarBootstrap?
    private static var retainedTerminationCoordinator: MenuBarTerminationCoordinator?

    static func requestPermissionRestart() {
        retainedTerminationCoordinator?.requestTermination()
    }

    static func launchLive(
        application: any MenuBarApplicationLifecycle = LiveMenuBarApplication(),
        bootstrapFactory: ((@escaping @MainActor @Sendable () -> Void) -> MelixMenuBarBootstrap)? = nil,
        presentationMode: MenuBarPresentationMode = MenuBarBootstrapEnvironment(
            environment: ProcessInfo.processInfo.environment
        ).presentationMode
    ) {
        let environment = MenuBarBootstrapEnvironment(environment: ProcessInfo.processInfo.environment)
        let terminationCoordinator = MenuBarTerminationCoordinator(
            mode: environment.terminationMode,
            repoRoot: environment.repoRoot,
            runtimeDirectory: environment.runtimeDirectory
        )
        retainedTerminationCoordinator = terminationCoordinator

        MelixMenuBarLauncher.launch(
            application: application,
            presentationMode: presentationMode,
            terminationCoordinator: terminationCoordinator,
            bootstrapFactory: bootstrapFactory ?? { terminationHandler in
                MelixMenuBarBootstrap.live(
                    environment: environment,
                    terminationHandler: terminationHandler
                )
            },
            retain: { retainedBootstrap = $0 }
        )
    }

    static func main() {
        main(environment: ProcessInfo.processInfo.environment)
    }

    static func main(
        environment: [String: String],
        launchLiveHandler: @escaping @MainActor () -> Void = defaultMainLaunchLiveHandler,
        phase8WindowUIAcceptanceHandler: @escaping @MainActor ([String: String]) -> Void = defaultMainPhase8WindowUIAcceptanceHandler,
        appScreenshotCaptureHandler: @escaping @MainActor ([String: String]) -> Void = defaultMainAppScreenshotCaptureHandler,
        credentialBoundaryFailureHandler: @escaping @MainActor () -> Void = defaultCredentialBoundaryFailureHandler
    ) {
        guard let sanitizedEnvironment = try? MCPEnvironmentCredentialBoundary.sanitizedEnvironment(environment) else {
            credentialBoundaryFailureHandler()
            return
        }
        for key in environment.keys where sanitizedEnvironment[key] == nil {
            unsetenv(key)
        }
        if sanitizedEnvironment["MELIX_APP_SCREENSHOT_CAPTURE"] == "1" {
            appScreenshotCaptureHandler(sanitizedEnvironment)
            return
        }
        if sanitizedEnvironment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE"] == "1" {
            phase8WindowUIAcceptanceHandler(sanitizedEnvironment)
            return
        }
        launchLiveHandler()
    }

    static func runPhase8WindowUIAcceptance(
        environment: [String: String],
        application: any MenuBarApplicationLifecycle = LiveMenuBarApplication(),
        bootstrapFactory: @escaping @MainActor ([String: String]) -> MelixMenuBarBootstrap = makePhase8WindowUIAcceptanceBootstrap,
        acceptanceRunnerFactory: @escaping @MainActor (
            MelixMenuBarBootstrap,
            [String: String]
        ) throws -> any Phase8WindowUIAcceptanceRunning = makePhase8WindowUIAcceptanceRunner,
        writeStandardOutput: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardOutput,
        writeStandardError: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardError,
        flushHandler: @escaping @MainActor () -> Void = flushPhase8WindowUIAcceptanceIO,
        exitHandler: @escaping @MainActor (Int32) -> Void = exitPhase8WindowUIAcceptance,
        operationScheduler: @escaping @MainActor (@escaping @MainActor @Sendable () async -> Void) -> Void = schedulePhase8WindowUIAcceptanceOperation,
        runLoopRunner: @escaping @MainActor () -> Void = runPhase8WindowUIAcceptanceLoop
    ) {
        application.setActivationPolicy(.accessory)
        operationScheduler {
            let exitCode = await executePhase8WindowUIAcceptance(
                environment: environment,
                bootstrapFactory: bootstrapFactory,
                acceptanceRunnerFactory: acceptanceRunnerFactory,
                writeStandardOutput: writeStandardOutput,
                writeStandardError: writeStandardError
            )
            flushHandler()
            exitHandler(exitCode)
        }

        runLoopRunner()
    }

    static func runAppScreenshotCapture(
        environment: [String: String],
        application: any MenuBarApplicationLifecycle = LiveMenuBarApplication(),
        runnerFactory: @escaping @MainActor ([String: String]) throws -> any AppScreenshotCaptureRunning = makeAppScreenshotCaptureRunner,
        writeStandardOutput: @escaping @MainActor (Data) -> Void = writeAppScreenshotCaptureStandardOutput,
        writeStandardError: @escaping @MainActor (Data) -> Void = writeAppScreenshotCaptureStandardError,
        flushHandler: @escaping @MainActor () -> Void = flushAppScreenshotCaptureIO,
        exitHandler: @escaping @MainActor (Int32) -> Void = exitAppScreenshotCapture,
        operationScheduler: @escaping @MainActor (@escaping @MainActor @Sendable () async -> Void) -> Void = scheduleAppScreenshotCaptureOperation,
        runLoopRunner: @escaping @MainActor () -> Void = runAppScreenshotCaptureLoop
    ) {
        application.setActivationPolicy(.accessory)
        operationScheduler {
            let exitCode = await executeAppScreenshotCapture(
                environment: environment,
                runnerFactory: runnerFactory,
                writeStandardOutput: writeStandardOutput,
                writeStandardError: writeStandardError
            )
            flushHandler()
            exitHandler(exitCode)
        }

        runLoopRunner()
    }

    static func executePhase8WindowUIAcceptance(
        environment: [String: String],
        bootstrapFactory: @escaping @MainActor ([String: String]) -> MelixMenuBarBootstrap = makePhase8WindowUIAcceptanceBootstrap,
        acceptanceRunnerFactory: @escaping @MainActor (
            MelixMenuBarBootstrap,
            [String: String]
        ) throws -> any Phase8WindowUIAcceptanceRunning = makePhase8WindowUIAcceptanceRunner,
        writeStandardOutput: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardOutput,
        writeStandardError: @escaping @MainActor (Data) -> Void = writePhase8WindowUIAcceptanceStandardError
    ) async -> Int32 {
        do {
            let bootstrap = bootstrapFactory(environment)
            let runner = try acceptanceRunnerFactory(bootstrap, environment)
            let result = try await runner.run()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            encoder.keyEncodingStrategy = .convertToSnakeCase
            let data = try encoder.encode(result)
            writeStandardOutput(data)
            writeStandardOutput(Data("\n".utf8))
            return 0
        } catch {
            let message = error.localizedDescription + "\n"
            writeStandardError(Data(message.utf8))
            return 1
        }
    }

    static func executeAppScreenshotCapture(
        environment: [String: String],
        runnerFactory: @escaping @MainActor ([String: String]) throws -> any AppScreenshotCaptureRunning = makeAppScreenshotCaptureRunner,
        writeStandardOutput: @escaping @MainActor (Data) -> Void = writeAppScreenshotCaptureStandardOutput,
        writeStandardError: @escaping @MainActor (Data) -> Void = writeAppScreenshotCaptureStandardError
    ) async -> Int32 {
        do {
            let runner = try runnerFactory(environment)
            let result = try await runner.run()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            encoder.keyEncodingStrategy = .convertToSnakeCase
            let data = try encoder.encode(result)
            writeStandardOutput(data)
            writeStandardOutput(Data("\n".utf8))
            return 0
        } catch {
            let message = error.localizedDescription + "\n"
            writeStandardError(Data(message.utf8))
            return 1
        }
    }

    private static func defaultMainLaunchLiveHandler() { launchLive() }

    private static func defaultMainPhase8WindowUIAcceptanceHandler(environment: [String: String]) {
        runPhase8WindowUIAcceptance(environment: environment)
    }

    private static func defaultMainAppScreenshotCaptureHandler(environment: [String: String]) {
        runAppScreenshotCapture(environment: environment)
    }

    private static func defaultCredentialBoundaryFailureHandler() {
        FileHandle.standardError.write(
            Data("Melix refused to launch because the active MCP configuration is invalid.\n".utf8)
        )
    }

    private static func makePhase8WindowUIAcceptanceBootstrap(
        environment: [String: String]
    ) -> MelixMenuBarBootstrap {
        let bootstrapEnvironment = MenuBarBootstrapEnvironment(environment: environment)
        return MelixMenuBarBootstrap.live(environment: bootstrapEnvironment)
    }

    private static func writePhase8WindowUIAcceptanceStandardOutput(_ data: Data) {
        FileHandle.standardOutput.write(data)
    }

    private static func writePhase8WindowUIAcceptanceStandardError(_ data: Data) {
        FileHandle.standardError.write(data)
    }

    private static func flushPhase8WindowUIAcceptanceIO() {
        fflush(nil)
    }

    private static func exitPhase8WindowUIAcceptance(_ exitCode: Int32) { Darwin.exit(exitCode) }

    private static func schedulePhase8WindowUIAcceptanceOperation(
        _ operation: @escaping @MainActor @Sendable () async -> Void
    ) {
        Task { @MainActor in
            await operation()
        }
    }

    private static func runPhase8WindowUIAcceptanceLoop() { RunLoop.main.run() }

    private static func makePhase8WindowUIAcceptanceRunner(
        bootstrap: MelixMenuBarBootstrap,
        environment: [String: String]
    ) throws -> any Phase8WindowUIAcceptanceRunning {
        guard let cliWorkflowRunner = bootstrap.cliWorkflowRunner else {
            throw Phase8WindowUIAcceptanceError.missingCLIWorkflowRunner
        }

        return try Phase8WindowUIAcceptanceRunner(
            viewModel: bootstrap.viewModel,
            cliWorkflowRunner: cliWorkflowRunner,
            config: .init(environment: environment)
        )
    }

    private static func makeAppScreenshotCaptureRunner(
        environment: [String: String]
    ) throws -> any AppScreenshotCaptureRunning {
        AppScreenshotCaptureRunner(config: .init(environment: environment))
    }

    private static func writeAppScreenshotCaptureStandardOutput(_ data: Data) {
        FileHandle.standardOutput.write(data)
    }

    private static func writeAppScreenshotCaptureStandardError(_ data: Data) {
        FileHandle.standardError.write(data)
    }

    private static func flushAppScreenshotCaptureIO() {
        fflush(nil)
    }

    private static func exitAppScreenshotCapture(_ exitCode: Int32) { Darwin.exit(exitCode) }

    private static func scheduleAppScreenshotCaptureOperation(
        _ operation: @escaping @MainActor @Sendable () async -> Void
    ) {
        Task { @MainActor in
            await operation()
        }
    }

    private static func runAppScreenshotCaptureLoop() { RunLoop.main.run() }
}
