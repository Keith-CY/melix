import Foundation
import MelixControlPlaneCore

public enum MelixRuntimeSettingsError: Error, Equatable, LocalizedError {
    case unknownKey(String)
    case invalidValue(key: String, expectedType: String, value: String)
    case invalidDocument(path: String)

    public var errorDescription: String? {
        switch self {
        case .unknownKey(let key):
            return "Unknown runtime setting key: \(key)."
        case let .invalidValue(key, expectedType, value):
            return "Invalid value for \(key). Expected \(expectedType), got \(value)."
        case .invalidDocument(let path):
            return "Runtime settings file must contain a JSON object: \(path)."
        }
    }
}

struct MelixRuntimeSettingsStore {
    private let melixHome: MelixHome
    private let environment: [String: String]
    private let fileManager: FileManager

    init(
        melixHome: MelixHome,
        environment: [String: String],
        fileManager: FileManager = .default
    ) {
        self.melixHome = melixHome
        self.environment = environment
        self.fileManager = fileManager
    }

    var projectSettingsFileURL: URL {
        projectRootURL()
            .appendingPathComponent(".melix", isDirectory: true)
            .appendingPathComponent("runtime_settings.json")
    }

    func effectiveSettings(overrides: [String: String] = [:]) throws -> [String: Any] {
        let startedAt = DispatchTime.now()
        let layout = MelixPathLayout(environment: environment)
        let userSettings = try loadSettingsDocument(at: melixHome.runtimeSettingsFileURL)
        let projectSettings = try loadSettingsDocument(at: projectSettingsFileURL)
        var settings: [String: Any] = [:]
        for definition in MelixRuntimeDiscoveryContracts.runtimeSettingDefinitions {
            let key = definition.key
            if let rawOverride = overrides[key] {
                settings[key] = [
                    "value": try coerce(rawOverride, definition: definition),
                    "source": "cli_flag",
                    "source_detail": "--override \(key)",
                ]
            } else if let rawEnvironmentValue = environment[definition.environmentVariable],
                      rawEnvironmentValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            {
                settings[key] = [
                    "value": try coerce(rawEnvironmentValue, definition: definition),
                    "source": "environment",
                    "source_detail": definition.environmentVariable,
                ]
            } else if let rawProjectValue = projectSettings[key] {
                settings[key] = [
                    "value": try coerce(rawProjectValue, definition: definition),
                    "source": "project_settings",
                    "source_detail": projectSettingsFileURL.path,
                ]
            } else if let rawUserValue = userSettings[key] {
                settings[key] = [
                    "value": try coerce(rawUserValue, definition: definition),
                    "source": "user_settings",
                    "source_detail": melixHome.runtimeSettingsFileURL.path,
                ]
            } else {
                settings[key] = [
                    "value": MelixRuntimeDiscoveryContracts.defaultRuntimeSettingValue(key: key, layout: layout),
                    "source": "default",
                    "source_detail": "builtin",
                ]
            }
        }
        return [
            "schema_version": MelixRuntimeDiscoveryContracts.runtimeSettingsSchemaVersion,
            "settings": settings,
            "sources": [
                "user_settings": melixHome.runtimeSettingsFileURL.path,
                "project_settings": projectSettingsFileURL.path,
            ],
            "metrics": [
                "settings_resolve_ms": NSNumber(value: elapsedMilliseconds(since: startedAt)),
            ],
        ]
    }

    func set(key rawKey: String, value rawValue: String) throws -> [String: Any] {
        let startedAt = DispatchTime.now()
        let key = rawKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let definition = try definition(for: key)
        let value = try coerce(rawValue, definition: definition)
        var document = try loadSettingsDocument(at: melixHome.runtimeSettingsFileURL)
        document[key] = value
        try writeSettingsDocument(document, to: melixHome.runtimeSettingsFileURL)
        return [
            "schema_version": "melix.runtime_settings.mutation.v1",
            "key": key,
            "value": value,
            "source": "user_settings",
            "source_detail": melixHome.runtimeSettingsFileURL.path,
            "metrics": [
                "settings_write_ms": NSNumber(value: elapsedMilliseconds(since: startedAt)),
            ],
        ]
    }

    func reset(key rawKey: String) throws -> [String: Any] {
        let startedAt = DispatchTime.now()
        let key = rawKey.trimmingCharacters(in: .whitespacesAndNewlines)
        _ = try definition(for: key)
        var document = try loadSettingsDocument(at: melixHome.runtimeSettingsFileURL)
        let removed = document.removeValue(forKey: key) != nil
        try writeSettingsDocument(document, to: melixHome.runtimeSettingsFileURL)
        return [
            "schema_version": "melix.runtime_settings.mutation.v1",
            "key": key,
            "removed": removed,
            "source": "user_settings",
            "source_detail": melixHome.runtimeSettingsFileURL.path,
            "metrics": [
                "settings_write_ms": NSNumber(value: elapsedMilliseconds(since: startedAt)),
            ],
        ]
    }

    func validate() -> [String: Any] {
        let startedAt = DispatchTime.now()
        var errors: [[String: Any]] = []
        for url in [melixHome.runtimeSettingsFileURL, projectSettingsFileURL] {
            do {
                let document = try loadSettingsDocument(at: url)
                for (key, value) in document {
                    do {
                        let definition = try definition(for: key)
                        _ = try coerce(value, definition: definition)
                    } catch {
                        errors.append([
                            "path": url.path,
                            "key": key,
                            "message": String(describing: error),
                        ])
                    }
                }
            } catch {
                errors.append([
                    "path": url.path,
                    "message": String(describing: error),
                ])
            }
        }
        return [
            "schema_version": "melix.runtime_settings.validation.v1",
            "valid": errors.isEmpty,
            "errors": errors,
            "metrics": [
                "settings_validate_ms": NSNumber(value: elapsedMilliseconds(since: startedAt)),
            ],
        ]
    }

    private func projectRootURL() -> URL {
        URL(fileURLWithPath: projectRootPath(), isDirectory: true)
    }

    private func projectRootPath() -> String {
        if let explicit = environment["MELIX_PROJECT_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           explicit.isEmpty == false
        {
            return (explicit as NSString).expandingTildeInPath
        }
        return fileManager.currentDirectoryPath
    }

    private func loadSettingsDocument(at url: URL) throws -> [String: Any] {
        guard fileManager.fileExists(atPath: url.path) else {
            return [:]
        }
        let data = try Data(contentsOf: url)
        let decoded = try JSONSerialization.jsonObject(with: data)
        guard let object = decoded as? [String: Any] else {
            throw MelixRuntimeSettingsError.invalidDocument(path: url.path)
        }
        return object
    }

    private func writeSettingsDocument(_ document: [String: Any], to url: URL) throws {
        let data = try JSONSerialization.data(withJSONObject: document, options: [.prettyPrinted, .sortedKeys])
        try melixHome.writeAtomically(data, to: url)
    }

    private func definition(for key: String) throws -> MelixRuntimeSettingMetadata {
        guard let definition = MelixRuntimeDiscoveryContracts.runtimeSettingDefinitions.first(where: { $0.key == key }) else {
            throw MelixRuntimeSettingsError.unknownKey(key)
        }
        return definition
    }

    private func coerce(_ rawValue: Any, definition: MelixRuntimeSettingMetadata) throws -> Any {
        switch definition.valueType {
        case "int":
            if let number = rawValue as? NSNumber {
                let doubleValue = number.doubleValue
                guard doubleValue.isFinite, doubleValue.rounded(.towardZero) == doubleValue else {
                    break
                }
                return NSNumber(value: number.intValue)
            }
            if let value = rawValue as? Int {
                return NSNumber(value: value)
            }
            if let string = rawValue as? String, let parsed = Int(string) {
                return NSNumber(value: parsed)
            }
        case "double":
            if let number = rawValue as? NSNumber {
                return NSNumber(value: number.doubleValue)
            }
            if let value = rawValue as? Double {
                return NSNumber(value: value)
            }
            if let string = rawValue as? String, let parsed = Double(string) {
                return NSNumber(value: parsed)
            }
        case "string":
            if let string = rawValue as? String {
                return string
            }
            if let number = rawValue as? NSNumber {
                return number.stringValue
            }
        default:
            break
        }
        throw MelixRuntimeSettingsError.invalidValue(
            key: definition.key,
            expectedType: definition.valueType,
            value: String(describing: rawValue)
        )
    }
}

struct MelixRuntimeDiscoveryBuilder {
    private let environment: [String: String]
    private let melixHome: MelixHome
    private let layout: MelixPathLayout

    init(environment: [String: String]) {
        self.environment = environment
        self.melixHome = MelixHome(environment: environment)
        self.layout = MelixPathLayout(environment: environment)
    }

    func infoPayload() -> [String: Any] {
        let startedAt = DispatchTime.now()
        return [
            "schema_version": MelixRuntimeDiscoveryContracts.infoSchemaVersion,
            "version": installedVersion(),
            "features": MelixRuntimeDiscoveryContracts.enabledFeatures,
            "supported_tasks": MelixRuntimeDiscoveryContracts.supportedTasks,
            "links": MelixRuntimeDiscoveryContracts.discoveryLinks(),
            "schema": MelixRuntimeDiscoveryContracts.schemaPayload(repoRootPath: repoRootPath()),
            "local_paths": localPathsPayload(),
            "update": updateReceipt(),
            "metrics": [
                "discovery_build_ms": NSNumber(value: elapsedMilliseconds(since: startedAt)),
            ],
        ]
    }

    func capabilitiesPayload(modelQuery: String = "") -> [String: Any] {
        [
            "schema_version": MelixRuntimeDiscoveryContracts.capabilitiesSchemaVersion,
            "features": MelixRuntimeDiscoveryContracts.enabledFeatures,
            "supported_tasks": MelixRuntimeDiscoveryContracts.supportedTasks,
            "model_alias_discovery": MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: modelQuery),
        ]
    }

    func instructionsPayload() -> [String: Any] {
        MelixRuntimeDiscoveryContracts.instructionsPayload()
    }

    func schemaPayload() -> [String: Any] {
        MelixRuntimeDiscoveryContracts.schemaPayload(repoRootPath: repoRootPath())
    }

    func configMetadataPayload() -> [String: Any] {
        MelixRuntimeDiscoveryContracts.configMetadataPayload(layout: layout)
    }

    private func projectRootPath() -> String {
        if let explicit = environment["MELIX_PROJECT_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           explicit.isEmpty == false
        {
            return (explicit as NSString).expandingTildeInPath
        }
        return FileManager.default.currentDirectoryPath
    }

    private func localPathsPayload() -> [String: Any] {
        [
            "melix_home": melixHome.rootURL.path,
            "runtime_settings": melixHome.runtimeSettingsFileURL.path,
            "project_settings": URL(fileURLWithPath: projectRootPath())
                .appendingPathComponent(".melix", isDirectory: true)
                .appendingPathComponent("runtime_settings.json")
                .path,
            "managed_models": melixHome.managedModelRootURL.path,
            "logs": melixHome.logsDirectoryURL.path,
            "runtime": melixHome.runtimeDirectoryURL.path,
        ]
    }

    private func updateReceipt() -> [String: Any] {
        let channelPath = environment["MELIX_UPDATE_CHANNEL_PATH"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let channel = environment["MELIX_UPDATE_CHANNEL"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "stable"
        let installed = installedVersion()
        guard channelPath.isEmpty == false else {
            return unavailableUpdateReceipt(installedVersion: installed, channel: channel)
        }
        guard
            let data = try? Data(contentsOf: URL(fileURLWithPath: channelPath)),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return unavailableUpdateReceipt(installedVersion: installed, channel: channel)
        }
        let latest = object["latest_known_version"] as? String ?? object["latest_version"] as? String ?? ""
        return [
            "installed_version": installed,
            "latest_known_version": latest,
            "update_available": latest.isEmpty ? false : latest != installed,
            "update_channel": object["update_channel"] as? String ?? channel,
            "install_method": installMethod(),
            "suggested_update_command": suggestedUpdateCommand(),
            "checked": true,
            "status": "ok",
        ]
    }

    private func unavailableUpdateReceipt(installedVersion: String, channel: String) -> [String: Any] {
        [
            "installed_version": installedVersion,
            "latest_known_version": "",
            "update_available": false,
            "update_channel": channel,
            "install_method": installMethod(),
            "suggested_update_command": suggestedUpdateCommand(),
            "checked": false,
            "status": "unavailable",
        ]
    }

    private func installedVersion() -> String {
        MelixRuntimeDiscoveryContracts.installedVersion(repoRootPath: repoRootPath())
    }

    private func installMethod() -> String {
        let explicit = environment["MELIX_INSTALL_METHOD"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if explicit.isEmpty == false {
            return explicit
        }
        if FileManager.default.fileExists(atPath: URL(fileURLWithPath: repoRootPath()).appendingPathComponent(".git").path) {
            return "source_checkout"
        }
        return "unknown"
    }

    private func suggestedUpdateCommand() -> [String] {
        installMethod() == "source_checkout" ? ["git", "pull", "--ff-only"] : []
    }

    private func repoRootPath() -> String {
        if let explicit = environment["MELIX_REPO_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines), explicit.isEmpty == false {
            return explicit
        }
        let candidates = [
            FileManager.default.currentDirectoryPath,
        ]
        for candidate in candidates where candidate.isEmpty == false {
            var url = URL(fileURLWithPath: candidate, isDirectory: true)
            for _ in 0..<8 {
                if FileManager.default.fileExists(atPath: url.appendingPathComponent("Package.swift").path),
                   FileManager.default.fileExists(atPath: url.appendingPathComponent("packages/protocol/schema").path)
                {
                    return url.path
                }
                let parent = url.deletingLastPathComponent()
                guard parent.path != url.path else {
                    break
                }
                url = parent
            }
        }
        return FileManager.default.currentDirectoryPath
    }
}
