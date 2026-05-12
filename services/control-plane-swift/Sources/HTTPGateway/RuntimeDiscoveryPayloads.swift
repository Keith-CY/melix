import Foundation
import MelixControlPlaneProtocol

struct HTTPRuntimeDiscoveryPayloads {
    let environment: [String: String]
    let runtimeBinding: GatewayRuntimeBinding

    private var layout: MelixPathLayout {
        MelixPathLayout(environment: environment)
    }

    func wellKnownPayload() -> [String: Any] {
        [
            "schema_version": MelixRuntimeDiscoveryContracts.infoSchemaVersion,
            "version": MelixRuntimeDiscoveryContracts.installedVersion(repoRootPath: repoRootPath()),
            "features": MelixRuntimeDiscoveryContracts.enabledFeatures,
            "supported_tasks": MelixRuntimeDiscoveryContracts.supportedTasks,
            "links": MelixRuntimeDiscoveryContracts.discoveryLinks(),
            "local_paths": localPathsPayload(),
            "runtime": [
                "host": runtimeBinding.host,
                "port": NSNumber(value: runtimeBinding.port),
                "active_server_session_id": runtimeBinding.activeServerSessionID,
            ],
        ]
    }

    func capabilitiesPayload(models: [Melix_Controlplane_V1_ModelSummary]) -> [String: Any] {
        [
            "schema_version": MelixRuntimeDiscoveryContracts.capabilitiesSchemaVersion,
            "features": MelixRuntimeDiscoveryContracts.enabledFeatures,
            "supported_tasks": MelixRuntimeDiscoveryContracts.supportedTasks,
            "models": models.map(modelPayload),
            "model_alias_discovery": MelixRuntimeDiscoveryContracts.modelAliasDiscoveryPayload(query: ""),
        ]
    }

    func instructionsPayload() -> [String: Any] {
        MelixRuntimeDiscoveryContracts.instructionsPayload()
    }

    func configMetadataPayload() -> [String: Any] {
        MelixRuntimeDiscoveryContracts.configMetadataPayload(layout: layout)
    }

    private func localPathsPayload() -> [String: Any] {
        [
            "melix_home": layout.rootURL.path,
            "runtime_settings": layout.rootURL.appendingPathComponent("runtime_settings.json").path,
            "managed_models": layout.managedModelRootURL.path,
            "logs": layout.logsDirectoryURL.path,
            "runtime": layout.runtimeDirectoryURL.path,
        ]
    }

    private func repoRootPath() -> String {
        if let explicit = environment["MELIX_REPO_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           explicit.isEmpty == false
        {
            return explicit
        }
        var url = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true)
        for _ in 0..<8 {
            if FileManager.default.fileExists(atPath: url.appendingPathComponent("pyproject.toml").path) {
                return url.path
            }
            let parent = url.deletingLastPathComponent()
            guard parent.path != url.path else {
                break
            }
            url = parent
        }
        return FileManager.default.currentDirectoryPath
    }

    private func modelPayload(_ model: Melix_Controlplane_V1_ModelSummary) -> [String: Any] {
        [
            "model_id": model.modelID,
            "kind": model.kind,
            "state": model.state.discoveryString,
            "hf_repo_id": model.settings.ext["melix.hf_repo_id"] ?? "",
        ]
    }
}

private extension Melix_Controlplane_V1_ModelState {
    var discoveryString: String {
        switch self {
        case .modelWarm:
            return "warm"
        case .modelPinned:
            return "pinned"
        case .modelUnloaded:
            return "unloaded"
        case .modelLoading:
            return "loading"
        case .modelDiscovered:
            return "discovered"
        case .modelFailed:
            return "failed"
        case .modelEvicting:
            return "evicting"
        default:
            return "unknown"
        }
    }
}
