import Foundation

public struct RuntimeWorkspacePreflightCheckState: Identifiable, Equatable, Sendable {
    public let id: String
    public let code: String
    public let status: String
    public let title: String
    public let detail: String
    public let recoveryHint: String
    public let items: [[String: String]]

    public init(
        code: String,
        status: String,
        title: String,
        detail: String,
        recoveryHint: String,
        items: [[String: String]]
    ) {
        self.id = code
        self.code = code
        self.status = status
        self.title = title
        self.detail = detail
        self.recoveryHint = recoveryHint
        self.items = items
    }

    public var isBlocking: Bool {
        let normalized = status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "error" || normalized == "blocked"
    }
}

public struct RuntimeWorkspacePreflightReceiptState: Equatable, Sendable {
    public let schemaVersion: String
    public let status: String
    public let projectID: String
    public let manifestPath: String
    public let workspaceManifestSchemaVersion: String
    public let checks: [RuntimeWorkspacePreflightCheckState]
    public let metrics: [String: Double]

    public init(
        schemaVersion: String,
        status: String,
        projectID: String,
        manifestPath: String,
        workspaceManifestSchemaVersion: String,
        checks: [RuntimeWorkspacePreflightCheckState],
        metrics: [String: Double]
    ) {
        self.schemaVersion = schemaVersion
        self.status = status
        self.projectID = projectID
        self.manifestPath = manifestPath
        self.workspaceManifestSchemaVersion = workspaceManifestSchemaVersion
        self.checks = checks
        self.metrics = metrics
    }

    public var blockingChecks: [RuntimeWorkspacePreflightCheckState] {
        checks.filter(\.isBlocking)
    }

    public var statusSummary: String {
        let normalized = status.trimmingCharacters(in: .whitespacesAndNewlines)
        let blockerCount = blockingChecks.count
        guard blockerCount > 0 else {
            return normalized.isEmpty ? "ready" : normalized
        }
        return "\(normalized.isEmpty ? "blocked" : normalized): \(blockerCount) issue\(blockerCount == 1 ? "" : "s")"
    }
}

public enum RuntimeWorkspacePreflightReceiptDecoder {
    public static func decode(_ output: String) throws -> RuntimeWorkspacePreflightReceiptState {
        try decode(Data(output.utf8))
    }

    public static func decode(_ data: Data) throws -> RuntimeWorkspacePreflightReceiptState {
        let payload = try JSONDecoder().decode(RuntimeWorkspacePreflightReceiptPayload.self, from: data)
        return payload.state()
    }
}

private struct RuntimeWorkspacePreflightReceiptPayload: Decodable {
    let schemaVersion: String
    let status: String
    let projectID: String
    let manifestPath: String
    let workspaceManifestSchemaVersion: String
    let checks: [RuntimeWorkspacePreflightCheckPayload]
    let metrics: [String: Double]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case projectID = "project_id"
        case manifestPath = "manifest_path"
        case workspaceManifestSchemaVersion = "workspace_manifest_schema_version"
        case checks
        case metrics
    }

    func state() -> RuntimeWorkspacePreflightReceiptState {
        RuntimeWorkspacePreflightReceiptState(
            schemaVersion: schemaVersion,
            status: status,
            projectID: projectID,
            manifestPath: manifestPath,
            workspaceManifestSchemaVersion: workspaceManifestSchemaVersion,
            checks: checks.map { $0.state() },
            metrics: metrics
        )
    }
}

private struct RuntimeWorkspacePreflightCheckPayload: Decodable {
    let code: String
    let status: String
    let title: String
    let detail: String
    let recoveryHint: String
    let items: [[String: String]]

    enum CodingKeys: String, CodingKey {
        case code
        case status
        case title
        case detail
        case recoveryHint = "recovery_hint"
        case items
    }

    func state() -> RuntimeWorkspacePreflightCheckState {
        RuntimeWorkspacePreflightCheckState(
            code: code,
            status: status,
            title: title,
            detail: detail,
            recoveryHint: recoveryHint,
            items: items
        )
    }
}
