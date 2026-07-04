import Foundation

public struct NetworkFetchPolicyReceipt: Equatable, Sendable {
    public let schemaVersion: String
    public let surface: String
    public let routeScope: String
    public let action: String
    public let urlClass: String
    public let urlScheme: String
    public let hostClass: String
    public let resolvedIP: String
    public let resolvedIPClass: String
    public let redirectHopsChecked: Int
    public let blockedReason: String
    public let redactedURL: String
    public let rawURLIncluded: Bool
    public let fetchAttempted: Bool

    public init(
        schemaVersion: String = "melix.network_fetch_policy_receipt.v1",
        surface: String,
        routeScope: String,
        action: String,
        urlClass: String,
        urlScheme: String,
        hostClass: String,
        resolvedIP: String = "",
        resolvedIPClass: String = "",
        redirectHopsChecked: Int = 0,
        blockedReason: String = "",
        redactedURL: String,
        rawURLIncluded: Bool = false,
        fetchAttempted: Bool = false
    ) {
        self.schemaVersion = schemaVersion
        self.surface = surface
        self.routeScope = routeScope
        self.action = action
        self.urlClass = urlClass
        self.urlScheme = urlScheme
        self.hostClass = hostClass
        self.resolvedIP = resolvedIP
        self.resolvedIPClass = resolvedIPClass
        self.redirectHopsChecked = redirectHopsChecked
        self.blockedReason = blockedReason
        self.redactedURL = redactedURL
        self.rawURLIncluded = rawURLIncluded
        self.fetchAttempted = fetchAttempted
    }

    public var jsonObject: [String: Any] {
        [
            "schema_version": schemaVersion,
            "surface": surface,
            "route_scope": routeScope,
            "action": action,
            "url_class": urlClass,
            "url_scheme": urlScheme,
            "host_class": hostClass,
            "resolved_ip": resolvedIP,
            "resolved_ip_class": resolvedIPClass,
            "redirect_hops_checked": redirectHopsChecked,
            "blocked_reason": blockedReason,
            "redacted_url": redactedURL,
            "raw_url_included": rawURLIncluded,
            "fetch_attempted": fetchAttempted,
        ]
    }

    public func metadataFields(prefix: String) -> [String: String] {
        [
            "\(prefix).schema_version": schemaVersion,
            "\(prefix).surface": surface,
            "\(prefix).route_scope": routeScope,
            "\(prefix).action": action,
            "\(prefix).url_class": urlClass,
            "\(prefix).url_scheme": urlScheme,
            "\(prefix).host_class": hostClass,
            "\(prefix).resolved_ip": resolvedIP,
            "\(prefix).resolved_ip_class": resolvedIPClass,
            "\(prefix).redirect_hops_checked": String(redirectHopsChecked),
            "\(prefix).blocked_reason": blockedReason,
            "\(prefix).redacted_url": redactedURL,
            "\(prefix).raw_url_included": String(rawURLIncluded),
            "\(prefix).fetch_attempted": String(fetchAttempted),
        ]
    }
}

public struct PrivacyAuditCounter: Equatable, Sendable {
    public let schemaVersion: String
    public let surface: String
    public let routeScope: String
    public let blockedCount: Int
    public let redactedCount: Int
    public let passedCount: Int
    public let rawSensitiveSpanCount: Int

    public init(
        schemaVersion: String = "melix.privacy_audit_counter.v1",
        surface: String,
        routeScope: String,
        blockedCount: Int = 0,
        redactedCount: Int = 0,
        passedCount: Int = 0,
        rawSensitiveSpanCount: Int = 0
    ) {
        self.schemaVersion = schemaVersion
        self.surface = surface
        self.routeScope = routeScope
        self.blockedCount = blockedCount
        self.redactedCount = redactedCount
        self.passedCount = passedCount
        self.rawSensitiveSpanCount = rawSensitiveSpanCount
    }

    public var jsonObject: [String: Any] {
        [
            "schema_version": schemaVersion,
            "surface": surface,
            "route_scope": routeScope,
            "blocked_count": blockedCount,
            "redacted_count": redactedCount,
            "passed_count": passedCount,
            "raw_sensitive_span_count": rawSensitiveSpanCount,
        ]
    }

    public func metadataFields(prefix: String) -> [String: String] {
        [
            "\(prefix).schema_version": schemaVersion,
            "\(prefix).surface": surface,
            "\(prefix).route_scope": routeScope,
            "\(prefix).blocked_count": String(blockedCount),
            "\(prefix).redacted_count": String(redactedCount),
            "\(prefix).passed_count": String(passedCount),
            "\(prefix).raw_sensitive_span_count": String(rawSensitiveSpanCount),
        ]
    }
}

public struct ExternalMediaURLAdmissionReceipt: Equatable, Sendable {
    public let policy: String
    public let sourceKind: String
    public let scheme: String
    public let host: String
    public let reason: String

    public static func local(scheme: String) -> ExternalMediaURLAdmissionReceipt {
        ExternalMediaURLAdmissionReceipt(
            policy: "local_media_allowed",
            sourceKind: "local",
            scheme: scheme,
            host: "",
            reason: "local paths and file URLs stay inside local runtime handling"
        )
    }

    public func networkFetchPolicyReceipt(
        surface: String,
        routeScope: String
    ) -> NetworkFetchPolicyReceipt {
        if sourceKind == "local" {
            return NetworkFetchPolicyReceipt(
                surface: surface,
                routeScope: routeScope,
                action: "passed",
                urlClass: "local",
                urlScheme: scheme,
                hostClass: "local",
                redactedURL: "[LOCAL_PATH]"
            )
        }
        let hostClass = ExternalMediaURLAdmission.hostClass(for: host)
        return NetworkFetchPolicyReceipt(
            surface: surface,
            routeScope: routeScope,
            action: "passed",
            urlClass: hostClass == "public" ? "public" : hostClass,
            urlScheme: scheme,
            hostClass: hostClass,
            redactedURL: "\(scheme)://\(host)/[redacted]"
        )
    }
}

public enum ExternalMediaURLAdmissionError: Error, Equatable {
    case malformedURL(String)
    case unsupportedScheme(String)
    case missingHost
    case privateHost(String)

    public var operatorMessage: String {
        switch self {
        case .malformedURL:
            return "External media URL is invalid."
        case let .unsupportedScheme(scheme):
            return "Unsupported external media URL scheme: \(scheme)."
        case .missingHost:
            return "External media URL requires a host."
        case let .privateHost(host):
            return "External media URL host is not allowed: \(host)."
        }
    }

    public var refusalReason: String {
        switch self {
        case .malformedURL:
            return "malformed_url"
        case .unsupportedScheme:
            return "unsupported_scheme"
        case .missingHost:
            return "missing_host"
        case .privateHost:
            return "private_or_loopback_host"
        }
    }

    public func networkFetchPolicyReceipt(
        rawURL: String,
        surface: String,
        routeScope: String
    ) -> NetworkFetchPolicyReceipt {
        let trimmed = rawURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let components = URLComponents(string: trimmed)
        let scheme = components?.scheme?.lowercased() ?? ""
        let host: String
        let hostClass: String
        switch self {
        case .privateHost(let privateHost):
            host = privateHost.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            hostClass = ExternalMediaURLAdmission.hostClass(for: host)
        case .missingHost:
            host = ""
            hostClass = "missing"
        case .malformedURL:
            host = ""
            hostClass = "invalid"
        case .unsupportedScheme:
            host = components?.host?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
            hostClass = host.isEmpty ? "missing" : ExternalMediaURLAdmission.hostClass(for: host)
        }
        let redactedURL: String
        if hostClass == "loopback" || hostClass == "link_local" || hostClass == "private" {
            redactedURL = "\(scheme.isEmpty ? "https" : scheme)://[REDACTED_PRIVATE_HOST]/[redacted]"
        } else {
            redactedURL = "[REDACTED_URL]"
        }
        return NetworkFetchPolicyReceipt(
            surface: surface,
            routeScope: routeScope,
            action: "blocked",
            urlClass: hostClass,
            urlScheme: scheme,
            hostClass: hostClass,
            blockedReason: refusalReason,
            redactedURL: redactedURL
        )
    }
}

public enum ExternalMediaURLAdmission {
    public static func validate(
        _ rawURL: String,
        mediaKind: String
    ) throws -> ExternalMediaURLAdmissionReceipt {
        let trimmed = rawURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw ExternalMediaURLAdmissionError.malformedURL(mediaKind)
        }

        guard let components = URLComponents(string: trimmed) else {
            throw ExternalMediaURLAdmissionError.malformedURL(mediaKind)
        }
        let scheme = components.scheme?.lowercased() ?? ""

        if scheme.isEmpty {
            return .local(scheme: "path")
        }
        if scheme == "file" {
            return .local(scheme: "file")
        }
        guard scheme == "https" else {
            throw ExternalMediaURLAdmissionError.unsupportedScheme(scheme)
        }
        guard let host = components.host?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !host.isEmpty
        else {
            throw ExternalMediaURLAdmissionError.missingHost
        }
        guard !isPrivateOrLoopbackHost(host) else {
            throw ExternalMediaURLAdmissionError.privateHost(host)
        }

        return ExternalMediaURLAdmissionReceipt(
            policy: "external_https_public_only",
            sourceKind: "remote",
            scheme: scheme,
            host: host,
            reason: "accepted_https_public_host_without_fetch"
        )
    }

    static func hostClass(for host: String) -> String {
        let normalized = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]")).lowercased()
        if normalized == "localhost" || normalized.hasSuffix(".localhost") {
            return "loopback"
        }
        if normalized.contains(":") {
            if let ipv4Tail = ipv4TailFromIPv6Literal(normalized) {
                return hostClass(for: ipv4Tail)
            }
            if normalized == "::1" {
                return "loopback"
            }
            if normalized.hasPrefix("fe80:") {
                return "link_local"
            }
            if normalized.hasPrefix("fc") || normalized.hasPrefix("fd") {
                return "private"
            }
        }
        let parts = normalized.split(separator: ".").compactMap { UInt8($0) }
        guard parts.count == 4 else {
            return "public"
        }
        if parts[0] == 10 || parts[0] == 127 {
            return parts[0] == 127 ? "loopback" : "private"
        }
        if parts[0] == 169 && parts[1] == 254 {
            return "link_local"
        }
        if parts[0] == 172 && (16...31).contains(parts[1]) {
            return "private"
        }
        if parts[0] == 192 && parts[1] == 168 {
            return "private"
        }
        return "public"
    }

    private static func ipv4TailFromIPv6Literal(_ normalized: String) -> String? {
        let tail: Substring
        if normalized.hasPrefix("::ffff:") {
            tail = normalized.dropFirst("::ffff:".count)
        } else if normalized.hasPrefix("::") {
            tail = normalized.dropFirst("::".count)
        } else {
            return nil
        }
        return tail.contains(".") ? String(tail) : nil
    }

    private static func isPrivateOrLoopbackHost(_ host: String) -> Bool {
        let hostClass = hostClass(for: host)
        return hostClass == "loopback" || hostClass == "link_local" || hostClass == "private"
    }
}
