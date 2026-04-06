import Foundation
import MelixControlPlaneProtocol

public struct GatewayAccessPolicy: Equatable, Sendable {
    public enum Mode: String, Equatable, Sendable {
        case none = "none"
        case bearerToken = "bearer_token"
        case apiKeys = "api_keys"

        init?(protoValue: Melix_Controlplane_V1_GatewayAccessMode) {
            switch protoValue {
            case .none:
                self = .none
            case .bearerToken:
                self = .bearerToken
            case .apiKeys:
                self = .apiKeys
            case .unspecified, .UNRECOGNIZED(_):
                return nil
            }
        }
    }

    public enum RequiredHeader: String, Equatable, Sendable {
        case none = "none"
        case authorizationBearer = "authorization-bearer"
        case xAPIKey = "x-api-key"

        var protoValue: Melix_Controlplane_V1_GatewayAuthHeader {
            switch self {
            case .none:
                return .none
            case .authorizationBearer:
                return .authorizationBearer
            case .xAPIKey:
                return .xApiKey
            }
        }
    }

    public struct KeyRecord: Equatable, Sendable {
        public let keyID: String
        public let label: String
        public let tokenHint: String
        let token: String

        public init(
            keyID: String,
            label: String,
            tokenHint: String,
            token: String
        ) {
            self.keyID = keyID
            self.label = label
            self.tokenHint = tokenHint
            self.token = token
        }
    }

    public enum AuthorizationOutcome: Equatable, Sendable {
        case localTrusted
        case authenticated(keyID: String, via: RequiredHeader)
    }

    public enum AuthorizationFailure: Error, Equatable, Sendable {
        case missingRequiredHeader(RequiredHeader)
        case invalidCredential(RequiredHeader)
        case disallowedHeader(RequiredHeader)
        case sharedAccessDisabled

        var statusCode: Int {
            switch self {
            case .missingRequiredHeader, .invalidCredential:
                return 401
            case .disallowedHeader, .sharedAccessDisabled:
                return 403
            }
        }

        var errorCode: String {
            switch self {
            case .missingRequiredHeader(.authorizationBearer):
                return "missing_authorization"
            case .missingRequiredHeader(.xAPIKey):
                return "missing_api_key"
            case .missingRequiredHeader(.none):
                return "missing_auth"
            case .invalidCredential(.authorizationBearer):
                return "invalid_authorization"
            case .invalidCredential(.xAPIKey):
                return "invalid_api_key"
            case .invalidCredential(.none):
                return "invalid_auth"
            case .disallowedHeader:
                return "auth_header_not_allowed"
            case .sharedAccessDisabled:
                return "shared_access_disabled"
            }
        }

        var message: String {
            switch self {
            case .missingRequiredHeader(.authorizationBearer):
                return "Authorization: Bearer credentials are required."
            case .missingRequiredHeader(.xAPIKey):
                return "x-api-key is required when shared access is enabled."
            case .missingRequiredHeader(.none):
                return "Authentication is required."
            case .invalidCredential(.authorizationBearer):
                return "The provided bearer token is invalid."
            case .invalidCredential(.xAPIKey):
                return "The provided x-api-key is invalid."
            case .invalidCredential(.none):
                return "The provided credentials are invalid."
            case .disallowedHeader(let requiredHeader):
                return "The supplied authentication header is not allowed. Use \(requiredHeader.displayName) instead."
            case .sharedAccessDisabled:
                return "Shared access is configured but currently disabled for this runtime."
            }
        }
    }

    public let mode: Mode
    public let sharedAccessEnabled: Bool
    public let keys: [KeyRecord]

    public init(
        mode: Mode = .none,
        sharedAccessEnabled: Bool = false,
        keys: [KeyRecord] = []
    ) {
        let sanitizedKeys = Self.sanitizedKeys(keys)
        switch mode {
        case .none:
            self.mode = .none
            self.sharedAccessEnabled = false
            self.keys = []
        case .bearerToken:
            guard let key = sanitizedKeys.first else {
                self.mode = .none
                self.sharedAccessEnabled = false
                self.keys = []
                return
            }
            self.mode = .bearerToken
            self.sharedAccessEnabled = false
            self.keys = [key]
        case .apiKeys:
            guard sanitizedKeys.isEmpty == false else {
                self.mode = .none
                self.sharedAccessEnabled = false
                self.keys = []
                return
            }
            self.mode = .apiKeys
            self.sharedAccessEnabled = sharedAccessEnabled
            self.keys = sanitizedKeys
        }
    }

    public static let localTrust = GatewayAccessPolicy()

    public init?(apply command: Melix_Controlplane_V1_ApplyGatewayAccess) {
        guard Self.trimmed(command.serverSessionID).isEmpty == false else {
            return nil
        }
        guard let mode = Mode(protoValue: command.mode) else {
            return nil
        }

        switch mode {
        case .none:
            self = .localTrust
        case .bearerToken, .apiKeys:
            guard command.hasPrimaryKey else {
                return nil
            }
            let key = Self.keyRecord(from: command.primaryKey)
            guard let key else {
                return nil
            }
            self = GatewayAccessPolicy(
                mode: mode,
                sharedAccessEnabled: mode == .apiKeys ? command.sharedAccessEnabled : false,
                keys: [key]
            )
        }
    }

    public var requiredHeader: RequiredHeader {
        switch mode {
        case .none:
            return .none
        case .bearerToken:
            return .authorizationBearer
        case .apiKeys:
            return .xAPIKey
        }
    }

    public var sharedAccessReady: Bool {
        mode == .apiKeys && keys.isEmpty == false
    }

    public var supportsPersistentSessions: Bool {
        switch mode {
        case .none:
            return false
        case .bearerToken:
            return keys.isEmpty == false
        case .apiKeys:
            return sharedAccessEnabled && keys.isEmpty == false
        }
    }

    public var acceptedAPIKeyCount: Int {
        mode == .apiKeys ? keys.count : 0
    }

    public func containsKey(id keyID: String) -> Bool {
        keys.contains(where: { $0.keyID == keyID })
    }

    public var metricModeCode: Double {
        switch mode {
        case .none:
            return 0
        case .bearerToken:
            return 1
        case .apiKeys:
            return 2
        }
    }

    public var summary: Melix_Controlplane_V1_GatewayAccessSummary {
        var summary = Melix_Controlplane_V1_GatewayAccessSummary()
        summary.mode = protoMode
        summary.sharedAccessEnabled = sharedAccessEnabled
        summary.sharedAccessReady = sharedAccessReady
        summary.requiredHeader = requiredHeader.protoValue
        summary.acceptedApiKeyCount = UInt32(acceptedAPIKeyCount)
        summary.keys = keys.map { key in
            var summary = Melix_Controlplane_V1_GatewayAccessKeySummary()
            summary.keyID = key.keyID
            summary.label = key.label
            summary.tokenHint = key.tokenHint
            return summary
        }
        return summary
    }

    public func authorize(headers: [String: String]) -> Result<AuthorizationOutcome, AuthorizationFailure> {
        switch mode {
        case .none:
            return .success(.localTrusted)
        case .bearerToken:
            if Self.hasNonEmptyHeader(named: "x-api-key", in: headers) {
                return .failure(.disallowedHeader(.authorizationBearer))
            }

            guard let headerValue = Self.header(named: "authorization", in: headers) else {
                return .failure(.missingRequiredHeader(.authorizationBearer))
            }
            guard let token = Self.bearerToken(from: headerValue), matches(token: token) else {
                return .failure(.invalidCredential(.authorizationBearer))
            }
            return .success(.authenticated(keyID: keys[0].keyID, via: .authorizationBearer))
        case .apiKeys:
            let authorizationHeader = Self.header(named: "authorization", in: headers)
            let apiKeyHeader = Self.header(named: "x-api-key", in: headers)
            guard sharedAccessEnabled else {
                if authorizationHeader != nil || apiKeyHeader != nil {
                    return .failure(.sharedAccessDisabled)
                }
                return .success(.localTrusted)
            }
            if let apiKeyHeader {
                guard matches(token: apiKeyHeader) else {
                    return .failure(.invalidCredential(.xAPIKey))
                }
                let keyID = keys.first(where: { $0.token == apiKeyHeader })?.keyID ?? ""
                return .success(.authenticated(keyID: keyID, via: .xAPIKey))
            }
            if let authorizationHeader {
                guard let token = Self.bearerToken(from: authorizationHeader), matches(token: token) else {
                    return .failure(.invalidCredential(.authorizationBearer))
                }
                let keyID = keys.first(where: { $0.token == token })?.keyID ?? ""
                return .success(.authenticated(keyID: keyID, via: .authorizationBearer))
            }
            return .failure(.missingRequiredHeader(.xAPIKey))
        }
    }

    public static func load(environment: [String: String]) -> GatewayAccessPolicy {
        let mode = Mode(rawValue: normalized(environment["MELIX_GATEWAY_AUTH_MODE"])) ?? .none
        switch mode {
        case .none:
            return .localTrust
        case .bearerToken:
            let token = trimmed(environment["MELIX_GATEWAY_BEARER_TOKEN"])
            guard token.isEmpty == false else {
                return .localTrust
            }
            let keyID = nonEmpty(environment["MELIX_GATEWAY_BEARER_TOKEN_ID"]) ?? "bearer-token"
            let label = nonEmpty(environment["MELIX_GATEWAY_BEARER_TOKEN_LABEL"]) ?? "Primary Bearer Token"
            let tokenHint = nonEmpty(environment["MELIX_GATEWAY_BEARER_TOKEN_HINT"]) ?? keyID
            return GatewayAccessPolicy(
                mode: .bearerToken,
                keys: [
                    KeyRecord(
                        keyID: keyID,
                        label: label,
                        tokenHint: tokenHint,
                        token: token
                    ),
                ]
            )
        case .apiKeys:
            let sharedAccessEnabled = parseBool(environment["MELIX_GATEWAY_SHARED_ACCESS_ENABLED"])
            let keys = parseKeyRecords(json: environment["MELIX_GATEWAY_API_KEYS_JSON"])
            return GatewayAccessPolicy(
                mode: .apiKeys,
                sharedAccessEnabled: sharedAccessEnabled,
                keys: keys
            )
        }
    }

    private var protoMode: Melix_Controlplane_V1_GatewayAccessMode {
        switch mode {
        case .none:
            return .none
        case .bearerToken:
            return .bearerToken
        case .apiKeys:
            return .apiKeys
        }
    }

    private func matches(token: String) -> Bool {
        keys.contains(where: { $0.token == token })
    }

    private static func sanitizedKeys(_ keys: [KeyRecord]) -> [KeyRecord] {
        var seenIDs = Set<String>()
        var seenTokens = Set<String>()
        var sanitized: [KeyRecord] = []

        for key in keys {
            guard let normalized = normalizedKeyRecord(key) else {
                continue
            }
            guard seenIDs.insert(normalized.keyID).inserted else {
                continue
            }
            guard seenTokens.insert(normalized.token).inserted else {
                continue
            }

            sanitized.append(normalized)
        }

        return sanitized
    }

    private static func parseKeyRecords(json: String?) -> [KeyRecord] {
        guard let json = nonEmpty(json), let data = json.data(using: .utf8) else {
            return []
        }
        guard let values = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            return []
        }
        return values.compactMap { value in
            guard let token = value["token"] as? String else {
                return nil
            }
            let keyID = (value["id"] as? String) ?? (value["key_id"] as? String) ?? ""
            let label = (value["label"] as? String) ?? keyID
            let tokenHint = (value["token_hint"] as? String) ?? (value["hint"] as? String) ?? keyID
            return KeyRecord(
                keyID: keyID,
                label: label,
                tokenHint: tokenHint,
                token: token
            )
        }
    }

    private static func parseBool(_ value: String?) -> Bool {
        switch normalized(value) {
        case "1", "true", "yes", "on":
            return true
        default:
            return false
        }
    }

    private static func bearerToken(from headerValue: String) -> String? {
        let trimmedValue = trimmed(headerValue)
        guard trimmedValue.lowercased().hasPrefix("bearer ") else {
            return nil
        }
        let token = trimmed(String(trimmedValue.dropFirst("Bearer ".count)))
        return token.isEmpty ? nil : token
    }

    private static func header(named name: String, in headers: [String: String]) -> String? {
        let loweredName = name.lowercased()
        guard
            let value = headers.first(where: { $0.key.lowercased() == loweredName })?.value,
            trimmed(value).isEmpty == false
        else {
            return nil
        }
        return trimmed(value)
    }

    private static func hasNonEmptyHeader(named name: String, in headers: [String: String]) -> Bool {
        header(named: name, in: headers) != nil
    }

    private static func normalized(_ value: String?) -> String {
        trimmed(value).lowercased()
    }

    private static func nonEmpty(_ value: String?) -> String? {
        let trimmedValue = trimmed(value)
        return trimmedValue.isEmpty ? nil : trimmedValue
    }

    private static func trimmed(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private static func keyRecord(
        from record: Melix_Controlplane_V1_GatewayAccessKeyRecord
    ) -> KeyRecord? {
        normalizedKeyRecord(
            KeyRecord(
                keyID: record.keyID,
                label: record.label,
                tokenHint: record.tokenHint,
                token: record.token
            )
        )
    }

    private static func normalizedKeyRecord(_ key: KeyRecord) -> KeyRecord? {
        let keyID = nonEmpty(key.keyID) ?? ""
        let token = trimmed(key.token)
        guard keyID.isEmpty == false, token.isEmpty == false else {
            return nil
        }
        guard containsSecret(keyID, token: token) == false else {
            return nil
        }
        return KeyRecord(
            keyID: keyID,
            label: secretSafeLabel(fallbackKeyID: keyID),
            tokenHint: secretSafeTokenHint(fallbackKeyID: keyID),
            token: token
        )
    }

    private static func containsSecret(_ value: String, token: String) -> Bool {
        trimmed(value).contains(token)
    }

    private static func secretSafeLabel(fallbackKeyID: String) -> String {
        fallbackKeyID
    }

    private static func secretSafeTokenHint(fallbackKeyID: String) -> String {
        fallbackKeyID
    }
}

private extension GatewayAccessPolicy.RequiredHeader {
    var displayName: String {
        switch self {
        case .none:
            return "no authentication"
        case .authorizationBearer:
            return "Authorization: Bearer"
        case .xAPIKey:
            return "x-api-key"
        }
    }
}
