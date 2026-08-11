import CoreFoundation
import Foundation

struct AgentApprovalPresentation: Sendable, Equatable {
    static let maximumPreviewBytes = 2_048
    static let maximumTargetCount = 6

    let operationKind: String
    let redactedArgumentsJSON: String
    let targetScopes: [String]
    let argumentsTruncated: Bool

    static func make(
        call: AgentToolCall,
        sessionID: String,
        branchID: String
    ) -> Self {
        guard
            let data = call.argumentsJSON.data(using: .utf8),
            data.count <= 64 * 1_024,
            let object = try? JSONSerialization.jsonObject(with: data),
            let arguments = object as? [String: Any]
        else {
            return Self(
                operationKind: AgentApprovalContextRegistry.policyProjection(
                    call: call,
                    sessionID: sessionID,
                    branchID: branchID,
                    arguments: [:]
                ).operationKind.rawValue,
                redactedArgumentsJSON: #"{"summary":"Arguments unavailable for bounded review."}"#,
                targetScopes: targetScopes(
                    call: call,
                    sessionID: sessionID,
                    branchID: branchID,
                    arguments: [:]
                ),
                argumentsTruncated: true
            )
        }

        var remainingNodes = 160
        var truncated = false
        let sanitized = sanitize(
            arguments,
            key: "",
            depth: 0,
            remainingNodes: &remainingNodes,
            truncated: &truncated
        )
        let preview: String
        if let sanitized,
           JSONSerialization.isValidJSONObject(sanitized),
           let encoded = try? JSONSerialization.data(
               withJSONObject: sanitized,
               options: [.sortedKeys]
           ),
           encoded.count <= maximumPreviewBytes,
           let value = String(data: encoded, encoding: .utf8) {
            preview = value
        } else {
            preview = #"{"summary":"Arguments exceeded the bounded redacted preview."}"#
            truncated = true
        }

        let projection = AgentApprovalContextRegistry.policyProjection(
            call: call,
            sessionID: sessionID,
            branchID: branchID,
            arguments: arguments
        )
        return Self(
            operationKind: projection.operationKind.rawValue,
            redactedArgumentsJSON: preview,
            targetScopes: targetScopes(
                projection: projection,
                arguments: arguments
            ),
            argumentsTruncated: truncated
        )
    }

    private static func sanitize(
        _ value: Any,
        key: String,
        depth: Int,
        remainingNodes: inout Int,
        truncated: inout Bool
    ) -> Any? {
        guard depth <= 5, remainingNodes > 0 else {
            truncated = true
            return "[TRUNCATED]"
        }
        remainingNodes -= 1

        if isSensitiveKey(key) {
            return "[REDACTED]"
        }
        if let dictionary = value as? [String: Any] {
            var output: [String: Any] = [:]
            let keys = dictionary.keys.sorted()
            if keys.count > 32 {
                truncated = true
            }
            for childKey in keys.prefix(32) {
                if let child = sanitize(
                    dictionary[childKey]!,
                    key: childKey,
                    depth: depth + 1,
                    remainingNodes: &remainingNodes,
                    truncated: &truncated
                ) {
                    output[childKey] = child
                }
            }
            return output
        }
        if let array = value as? [Any] {
            if array.count > 8 {
                truncated = true
            }
            return array.prefix(8).compactMap {
                sanitize(
                    $0,
                    key: key,
                    depth: depth + 1,
                    remainingNodes: &remainingNodes,
                    truncated: &truncated
                )
            }
        }
        if let string = value as? String {
            return sanitizedString(string, key: key, truncated: &truncated)
        }
        if let number = value as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return number.boolValue
            }
            return number
        }
        if value is NSNull {
            return NSNull()
        }
        truncated = true
        return "[UNSUPPORTED]"
    }

    private static func sanitizedString(
        _ raw: String,
        key: String,
        truncated: inout Bool
    ) -> String {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if isSensitiveKey(key) || looksLikeOpaqueSecret(value) {
            return "[REDACTED]"
        }
        if let url = URLComponents(string: value),
           let scheme = url.scheme,
           let host = url.host,
           !scheme.isEmpty,
           !host.isEmpty {
            var safe = URLComponents()
            safe.scheme = scheme.lowercased()
            safe.host = host.lowercased()
            safe.port = url.port
            safe.path = url.path
            return bounded(safe.string ?? "\(scheme)://\(host)", truncated: &truncated)
        }
        return bounded(value, truncated: &truncated)
    }

    private static func bounded(
        _ value: String,
        truncated: inout Bool
    ) -> String {
        guard value.count > 180 else {
            return value
        }
        truncated = true
        return String(value.prefix(177)) + "…"
    }

    private static func isSensitiveKey(_ raw: String) -> Bool {
        let key = raw.lowercased().replacingOccurrences(of: "-", with: "_")
        return [
            "authorization", "password", "passwd", "secret", "token",
            "api_key", "apikey", "credential", "cookie", "session_key",
            "private_key", "payment", "card", "cvv", "cvc", "otp",
        ].contains { key.contains($0) }
    }

    private static func looksLikeOpaqueSecret(_ value: String) -> Bool {
        guard value.count >= 40, value.rangeOfCharacter(from: .whitespaces) == nil else {
            return false
        }
        let scalarSet = Set(value.unicodeScalars.map(\.value))
        let alphanumericCount = value.unicodeScalars.filter {
            CharacterSet.alphanumerics.contains($0)
        }.count
        return scalarSet.count >= 12
            && Double(alphanumericCount) / Double(max(value.unicodeScalars.count, 1)) > 0.8
    }

    private static func targetScopes(
        call: AgentToolCall,
        sessionID: String,
        branchID: String,
        arguments: [String: Any]
    ) -> [String] {
        let projection = AgentApprovalContextRegistry.policyProjection(
            call: call,
            sessionID: sessionID,
            branchID: branchID,
            arguments: arguments
        )
        return targetScopes(
            projection: projection,
            arguments: arguments
        )
    }

    private static func targetScopes(
        projection: AgentApprovalPolicyProjection,
        arguments: [String: Any]
    ) -> [String] {
        var scopes: [String] = []

        func append(_ value: String?) {
            guard let value,
                  !value.isEmpty,
                  !scopes.contains(value),
                  scopes.count < maximumTargetCount
            else {
                return
            }
            scopes.append(String(value.prefix(180)))
        }

        append(projection.workspaceScope.map { "policy: \($0)" })
        append(projection.appBundleID.map { "policy: app:\($0)" })
        append(projection.networkHost.map { "policy: host:\($0)" })
        for key in ["path", "file", "directory", "workspace"] {
            if let raw = string(arguments[key]) {
                append("call target: path:\(boundedPath(raw))")
            }
        }
        if let target = arguments["target"] as? [String: Any] {
            append(string(target["window_title"]).map {
                "call target: window:\($0)"
            })
        }
        if let targets = arguments["allowed_targets"] as? [[String: Any]] {
            for target in targets.prefix(2) {
                append(string(target["window_title"]).map {
                    "call target: window:\($0)"
                })
            }
        }
        if let command = string(arguments["command"]) {
            append(command.split(whereSeparator: \.isWhitespace).first.map {
                "call target: executable:\($0)"
            })
        }
        return Array(scopes.prefix(maximumTargetCount))
    }

    private static func boundedPath(_ raw: String) -> String {
        let components = URL(fileURLWithPath: raw).standardizedFileURL.pathComponents
        guard components.count > 3 else {
            return raw
        }
        return "…/" + components.suffix(3).joined(separator: "/")
    }

    private static func string(_ value: Any?) -> String? {
        guard let value = value as? String else {
            return nil
        }
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? nil : normalized
    }
}
