import Foundation

struct AgentApprovalPolicyProjection: Sendable, Equatable {
    let operationKind: AgentApprovalOperationKind
    let workspaceScope: String?
    let appBundleID: String?
    let networkHost: String?
}

public actor AgentApprovalContextRegistry: AgentApprovalContextProviding {
    private struct RunScope: Sendable, Equatable {
        let sessionID: String
        let branchID: String
    }

    private var scopes: [String: RunScope] = [:]

    public init() {}

    public func register(
        runID: String,
        sessionID: String,
        branchID: String
    ) {
        let normalizedRunID = Self.nonempty(runID)
        let normalizedSessionID = Self.nonempty(sessionID)
        guard let normalizedRunID, let normalizedSessionID else {
            return
        }
        scopes[normalizedRunID] = RunScope(
            sessionID: normalizedSessionID,
            branchID: branchID.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
        )
    }

    public func unregister(runID: String) {
        guard let runID = Self.nonempty(runID) else {
            return
        }
        scopes.removeValue(forKey: runID)
    }

    public func context(
        for call: AgentToolCall,
        runID: String
    ) -> AgentApprovalPolicyContext? {
        guard
            let scope = scopes[runID],
            let sourceID = Self.nonempty(call.sourceID),
            let toolName = Self.nonempty(call.toolName),
            Self.nonempty(call.schemaDigest) != nil,
            let riskClass = AgentApprovalRiskClass.fromRuntimeValue(
                call.riskClass
            )
        else {
            return nil
        }

        let arguments = Self.arguments(from: call.argumentsJSON)
        let projection = Self.policyProjection(
            call: call,
            sessionID: scope.sessionID,
            branchID: scope.branchID,
            arguments: arguments
        )
        return AgentApprovalPolicyContext(
            sourceID: sourceID,
            toolName: toolName,
            riskClass: riskClass,
            operationKind: projection.operationKind,
            workspaceScope: projection.workspaceScope,
            appBundleID: projection.appBundleID,
            networkHost: projection.networkHost,
            toolKnown: true,
            schemaState: .current
        )
    }

    static func policyProjection(
        call: AgentToolCall,
        sessionID: String,
        branchID: String,
        arguments: [String: Any]
    ) -> AgentApprovalPolicyProjection {
        let sourceID = nonempty(call.sourceID) ?? ""
        let toolName = nonempty(call.toolName) ?? ""
        return AgentApprovalPolicyProjection(
            operationKind: operationKind(
                sourceID: sourceID,
                toolName: toolName,
                arguments: arguments
            ),
            workspaceScope: policyScope(
                sessionID: sessionID,
                branchID: branchID
            ),
            appBundleID: appBundleID(
                sourceID: sourceID,
                toolName: toolName,
                arguments: arguments
            ),
            networkHost: networkHost(
                toolName: toolName,
                arguments: arguments
            )
        )
    }

    private static func operationKind(
        sourceID: String,
        toolName: String,
        arguments: [String: Any]
    ) -> AgentApprovalOperationKind {
        if sourceID == "builtin" {
            if toolName == "workspace_file" {
                switch string(arguments["operation"])?.lowercased() {
                case "read":
                    return .read
                case "write", "edit":
                    return .write
                default:
                    return .unknown
                }
            }
            return .read
        }
        if sourceID == "computer", toolName == "computer_use" {
            switch string(arguments["operation"])?.lowercased() {
            case "get_permissions", "open_session", "capture_frame",
                 "close_session":
                return .read
            case "press_element":
                return .write
            default:
                return .unknown
            }
        }
        return .unknown
    }

    private static func policyScope(
        sessionID: String,
        branchID: String
    ) -> String? {
        guard let sessionID = nonempty(sessionID) else {
            return nil
        }
        guard let branchID = nonempty(branchID) else {
            return "session:\(sessionID)"
        }
        return "session:\(sessionID)/branch:\(branchID)"
    }

    private static func appBundleID(
        sourceID: String,
        toolName: String,
        arguments: [String: Any]
    ) -> String? {
        guard sourceID == "computer", toolName == "computer_use" else {
            return nil
        }
        if let target = arguments["target"] as? [String: Any] {
            return nonempty(string(target["bundle_id"]))
        }
        if let targets = arguments["allowed_targets"] as? [[String: Any]],
           targets.count == 1 {
            return nonempty(string(targets[0]["bundle_id"]))
        }
        return nil
    }

    private static func networkHost(
        toolName: String,
        arguments: [String: Any]
    ) -> String? {
        guard toolName == "visit",
              let rawURL = nonempty(string(arguments["url"])),
              let host = URLComponents(string: rawURL)?.host
        else {
            return nil
        }
        return host.lowercased()
    }

    private static func arguments(from rawJSON: String) -> [String: Any] {
        guard
            let data = rawJSON.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data),
            let arguments = object as? [String: Any]
        else {
            return [:]
        }
        return arguments
    }

    private static func string(_ value: Any?) -> String? {
        value as? String
    }

    private static func nonempty(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(
            in: .whitespacesAndNewlines
        ) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }
}
