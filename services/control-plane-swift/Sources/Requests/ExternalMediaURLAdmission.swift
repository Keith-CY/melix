import Foundation

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

    private static func isPrivateOrLoopbackHost(_ host: String) -> Bool {
        let normalized = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]")).lowercased()
        if normalized == "localhost" || normalized.hasSuffix(".localhost") {
            return true
        }
        if normalized.contains(":") {
            if normalized == "::1" || normalized.hasPrefix("fe80:")
                || normalized.hasPrefix("fc") || normalized.hasPrefix("fd")
            {
                return true
            }
        }
        let parts = normalized.split(separator: ".").compactMap { UInt8($0) }
        guard parts.count == 4 else {
            return false
        }
        if parts[0] == 10 || parts[0] == 127 {
            return true
        }
        if parts[0] == 169 && parts[1] == 254 {
            return true
        }
        if parts[0] == 172 && (16...31).contains(parts[1]) {
            return true
        }
        if parts[0] == 192 && parts[1] == 168 {
            return true
        }
        return false
    }
}
