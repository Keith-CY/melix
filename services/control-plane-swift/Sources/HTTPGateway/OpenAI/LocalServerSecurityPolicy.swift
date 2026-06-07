import Foundation

public struct LocalServerSecurityReceipt: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let bindHost: String
    public let allowedHosts: [String]
    public let allowedOrigins: [String]
    public let loopbackOnlyHostPolicy: Bool
    public let browserCorsPolicy: String

    public init(
        schemaVersion: String = "melix.local_server_security.v1",
        bindHost: String,
        allowedHosts: [String],
        allowedOrigins: [String],
        loopbackOnlyHostPolicy: Bool,
        browserCorsPolicy: String
    ) {
        self.schemaVersion = schemaVersion
        self.bindHost = bindHost
        self.allowedHosts = allowedHosts
        self.allowedOrigins = allowedOrigins
        self.loopbackOnlyHostPolicy = loopbackOnlyHostPolicy
        self.browserCorsPolicy = browserCorsPolicy
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case bindHost = "bind_host"
        case allowedHosts = "allowed_hosts"
        case allowedOrigins = "allowed_origins"
        case loopbackOnlyHostPolicy = "loopback_only_host_policy"
        case browserCorsPolicy = "browser_cors_policy"
    }

    public func jsonObject(encoder: JSONEncoder) throws -> [String: Any] {
        let data = try encoder.encode(self)
        let object = try JSONSerialization.jsonObject(with: data)
        return object as? [String: Any] ?? [:]
    }
}

public struct LocalServerSecurityPolicy: Equatable, Sendable {
    public struct CORS: Equatable, Sendable {
        public let origin: String

        public init(origin: String) {
            self.origin = origin
        }
    }

    public enum RejectionReason: Equatable, Sendable {
        case hostNotAllowed
        case originNotAllowed

        var errorCode: String {
            switch self {
            case .hostNotAllowed:
                return "host_not_allowed"
            case .originNotAllowed:
                return "origin_not_allowed"
            }
        }

        var message: String {
            switch self {
            case .hostNotAllowed:
                return "The request Host is not allowed by the local Melix server policy."
            case .originNotAllowed:
                return "The request Origin is not allowed by the local Melix server CORS policy."
            }
        }
    }

    public enum Admission: Equatable, Sendable {
        case accepted(cors: CORS?)
        case rejected(reason: RejectionReason, headerValue: String)
    }

    public let receipt: LocalServerSecurityReceipt

    private let allowedHostSet: Set<String>
    private let allowedOriginSet: Set<String>

    public init(
        bindHost: String,
        environment: [String: String]
    ) {
        let resolvedBindHost = Self.trimmed(bindHost).isEmpty ? "127.0.0.1" : Self.trimmed(bindHost)
        let explicitHosts = Self.normalizedList(environment["MELIX_ALLOWED_HOSTS"], normalize: Self.normalizedHostForAllowlist)
        let explicitOrigins = Self.normalizedList(
            environment["MELIX_ALLOWED_ORIGINS"],
            normalize: Self.normalizedAllowedOrigin
        )
        let defaultHosts = ["127.0.0.1", "[::1]", "::1", "localhost"]
        let bindHostEntry = Self.normalizedBindHostForAllowlist(resolvedBindHost)
        let allHosts = Self.orderedUnique(defaultHosts + (bindHostEntry.map { [$0] } ?? []) + explicitHosts)

        self.allowedHostSet = Set(allHosts.map { $0.lowercased() })
        self.allowedOriginSet = Set(explicitOrigins)
        self.receipt = LocalServerSecurityReceipt(
            bindHost: resolvedBindHost,
            allowedHosts: allHosts,
            allowedOrigins: explicitOrigins,
            loopbackOnlyHostPolicy: allHosts.allSatisfy(Self.isLoopbackAllowedHost),
            browserCorsPolicy: explicitOrigins.isEmpty ? "default_denied" : "explicit_allowlist"
        )
    }

    public func admit(headers: [String: String]) -> Admission {
        // In-process tests and server-to-server callers can bypass raw HTTP parsing.
        // Network HTTP/1.1 requests without Host are rejected by HTTPGatewayRequestParser.
        if let host = header(named: "host", in: headers) {
            guard !host.isEmpty, isAllowedHost(host) else {
                return .rejected(reason: .hostNotAllowed, headerValue: host)
            }
        }

        guard let origin = header(named: "origin", in: headers), !origin.isEmpty else {
            return .accepted(cors: nil)
        }
        let normalizedOrigin = origin.trimmingCharacters(in: .whitespacesAndNewlines)
        guard allowedOriginSet.contains(normalizedOrigin) else {
            return .rejected(reason: .originNotAllowed, headerValue: origin)
        }
        return .accepted(cors: CORS(origin: normalizedOrigin))
    }

    public static func varyHeader(includingOriginFrom existing: String?) -> String {
        guard let existing, !existing.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return "Origin"
        }
        let entries = existing
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        guard entries.contains(where: { $0.caseInsensitiveCompare("Origin") == .orderedSame }) == false else {
            return existing
        }
        return existing + ", Origin"
    }

    private func isAllowedHost(_ rawValue: String) -> Bool {
        guard let host = Self.normalizedHostForComparison(rawValue) else {
            return false
        }
        return allowedHostSet.contains(host.lowercased())
    }

    private func header(named expectedName: String, in headers: [String: String]) -> String? {
        headers.first { key, value in
            key.caseInsensitiveCompare(expectedName) == .orderedSame
        }?.value
    }

    private static func normalizedList(
        _ rawValue: String?,
        normalize: (String) -> String?
    ) -> [String] {
        orderedUnique(
            trimmed(rawValue)
                .split(separator: ",")
                .compactMap { normalize(String($0)) }
        )
    }

    private static func normalizedHostForAllowlist(_ rawValue: String) -> String? {
        normalizedHostForComparison(rawValue)
    }

    private static func normalizedBindHostForAllowlist(_ rawValue: String) -> String? {
        let host = normalizedHostForComparison(rawValue)
        guard host != "0.0.0.0", host != "::", host != "[::]" else {
            return nil
        }
        return host
    }

    private static func normalizedHostForComparison(_ rawValue: String) -> String? {
        let candidate = trimmed(rawValue)
        guard !candidate.isEmpty else {
            return nil
        }
        if candidate.hasPrefix("[") {
            guard let closeIndex = candidate.firstIndex(of: "]") else {
                return nil
            }
            return String(candidate[...closeIndex])
        }
        if candidate.filter({ $0 == ":" }).count > 1 {
            return candidate
        }
        return candidate
            .split(separator: ":", maxSplits: 1, omittingEmptySubsequences: true)
            .first
            .map(String.init)
    }

    private static func normalizedAllowedOrigin(_ rawValue: String) -> String? {
        let candidate = trimmed(rawValue)
        guard !candidate.isEmpty else {
            return nil
        }
        guard let components = URLComponents(string: candidate),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = components.host?.lowercased()
        else {
            return nil
        }
        if let port = components.port {
            return "\(scheme)://\(host):\(port)"
        }
        return "\(scheme)://\(host)"
    }

    private static func isLoopbackAllowedHost(_ value: String) -> Bool {
        switch value.lowercased() {
        case "127.0.0.1", "[::1]", "::1", "localhost":
            return true
        default:
            return false
        }
    }

    private static func orderedUnique(_ values: [String]) -> [String] {
        var seen: Set<String> = []
        var output: [String] = []
        for value in values {
            let key = value.lowercased()
            guard seen.insert(key).inserted else {
                continue
            }
            output.append(value)
        }
        return output
    }

    private static func trimmed(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
