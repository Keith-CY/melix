import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public enum CompanionPairingPhase: String, Codable, Equatable, Sendable {
    case idle
    case issuing
    case active
    case revoking
    case failed
}

public struct CompanionPairingDescriptor: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let statusURL: String
    public let resumeHeader: String
    public let tokenTransport: String
    public let allowedRoutes: [String]
    public let forbiddenCapabilities: [String]
    public let expiresAtUnixMS: Int64

    public init(
        schemaVersion: String,
        statusURL: String,
        resumeHeader: String,
        tokenTransport: String,
        allowedRoutes: [String],
        forbiddenCapabilities: [String],
        expiresAtUnixMS: Int64
    ) {
        self.schemaVersion = schemaVersion
        self.statusURL = statusURL
        self.resumeHeader = resumeHeader
        self.tokenTransport = tokenTransport
        self.allowedRoutes = allowedRoutes
        self.forbiddenCapabilities = forbiddenCapabilities
        self.expiresAtUnixMS = expiresAtUnixMS
    }
}

public struct CompanionPairingIssueResult: Equatable, Sendable {
    public let sessionID: String
    public let scope: String
    public let rememberMe: Bool
    public let expiresAtUnixMS: Int64
    public let resumeHeader: String
    public let resumeToken: String
    public let pairing: CompanionPairingDescriptor

    public init(
        sessionID: String,
        scope: String,
        rememberMe: Bool,
        expiresAtUnixMS: Int64,
        resumeHeader: String,
        resumeToken: String,
        pairing: CompanionPairingDescriptor
    ) {
        self.sessionID = sessionID
        self.scope = scope
        self.rememberMe = rememberMe
        self.expiresAtUnixMS = expiresAtUnixMS
        self.resumeHeader = resumeHeader
        self.resumeToken = resumeToken
        self.pairing = pairing
    }
}

public struct CompanionPairingState: Equatable, Sendable, CustomStringConvertible {
    public var phase: CompanionPairingPhase
    public var sessionID: String
    public var scope: String
    public var statusURL: String
    public var resumeHeader: String
    public var tokenTransport: String
    public var allowedRoutes: [String]
    public var forbiddenCapabilities: [String]
    public var expiresAtUnixMS: Int64
    public var lastError: String?

    public init(
        phase: CompanionPairingPhase = .idle,
        sessionID: String = "",
        scope: String = "",
        statusURL: String = "",
        resumeHeader: String = "",
        tokenTransport: String = "",
        allowedRoutes: [String] = [],
        forbiddenCapabilities: [String] = [],
        expiresAtUnixMS: Int64 = 0,
        lastError: String? = nil
    ) {
        self.phase = phase
        self.sessionID = sessionID
        self.scope = scope
        self.statusURL = statusURL
        self.resumeHeader = resumeHeader
        self.tokenTransport = tokenTransport
        self.allowedRoutes = allowedRoutes
        self.forbiddenCapabilities = forbiddenCapabilities
        self.expiresAtUnixMS = expiresAtUnixMS
        self.lastError = lastError
    }

    public var copyBundleAvailable: Bool {
        phase == .active && sessionID.isEmpty == false && statusURL.isEmpty == false
    }

    public var description: String {
        "CompanionPairingState(phase: \(phase.rawValue), sessionID: \(sessionID), scope: \(scope), statusURL: \(statusURL), resumeHeader: \(resumeHeader), tokenTransport: \(tokenTransport), allowedRoutes: \(allowedRoutes), forbiddenCapabilities: \(forbiddenCapabilities), expiresAtUnixMS: \(expiresAtUnixMS), lastError: \(String(describing: lastError)))"
    }

    static func active(from result: CompanionPairingIssueResult) -> CompanionPairingState {
        CompanionPairingState(
            phase: .active,
            sessionID: result.sessionID,
            scope: result.scope,
            statusURL: result.pairing.statusURL,
            resumeHeader: result.resumeHeader,
            tokenTransport: result.pairing.tokenTransport,
            allowedRoutes: result.pairing.allowedRoutes,
            forbiddenCapabilities: result.pairing.forbiddenCapabilities,
            expiresAtUnixMS: result.expiresAtUnixMS,
            lastError: nil
        )
    }

    static func failed(_ message: String) -> CompanionPairingState {
        CompanionPairingState(phase: .failed, lastError: message)
    }
}

public protocol CompanionPairingClient: Sendable {
    func issuePairing(baseURL: URL, apiKey: String) async throws -> CompanionPairingIssueResult
    func revokePairing(baseURL: URL, sessionToken: String) async throws
}

public protocol CompanionPairingHTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionCompanionPairingHTTPTransport: CompanionPairingHTTPTransport {
    public init() {}

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw CompanionPairingClientError.invalidResponse("Companion pairing response was not HTTP.")
        }
        return (data, httpResponse)
    }
}

public struct LiveCompanionPairingClient: CompanionPairingClient {
    private let transport: any CompanionPairingHTTPTransport

    public init(
        transport: any CompanionPairingHTTPTransport = URLSessionCompanionPairingHTTPTransport()
    ) {
        self.transport = transport
    }

    public func issuePairing(baseURL: URL, apiKey: String) async throws -> CompanionPairingIssueResult {
        let url = baseURL
            .appendingPathComponent("v1")
            .appendingPathComponent("melix")
            .appendingPathComponent("auth")
            .appendingPathComponent("session")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        request.httpBody = try JSONEncoder().encode(CompanionPairingIssueRequest())

        let (data, response) = try await transport.data(for: request)
        try validateHTTPResponse(data: data, response: response)
        let payload = try JSONDecoder().decode(CompanionPairingIssueResponse.self, from: data)
        return try payload.result()
    }

    public func revokePairing(baseURL: URL, sessionToken: String) async throws {
        let url = baseURL
            .appendingPathComponent("v1")
            .appendingPathComponent("melix")
            .appendingPathComponent("auth")
            .appendingPathComponent("session")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue(sessionToken, forHTTPHeaderField: "x-melix-session")

        let (data, response) = try await transport.data(for: request)
        try validateHTTPResponse(data: data, response: response)
    }

    private func validateHTTPResponse(data: Data, response: HTTPURLResponse) throws {
        guard (200..<300).contains(response.statusCode) else {
            let message = String(decoding: data, as: UTF8.self)
            throw CompanionPairingClientError.httpStatus(response.statusCode, message)
        }
    }
}

public enum CompanionPairingClientError: Error, CustomStringConvertible, Equatable {
    case invalidResponse(String)
    case invalidPayload(String)
    case httpStatus(Int, String)

    public var description: String {
        switch self {
        case .invalidResponse(let message):
            return message
        case .invalidPayload(let message):
            return message
        case .httpStatus(let statusCode, let message):
            return "Companion pairing HTTP \(statusCode): \(message)"
        }
    }
}

private struct CompanionPairingIssueRequest: Encodable {
    let rememberMe = true
    let scope = "companion_read_only"

    enum CodingKeys: String, CodingKey {
        case rememberMe = "remember_me"
        case scope
    }
}

private struct CompanionPairingIssueResponse: Decodable {
    let session: Session
    let resume: Resume
    let pairing: Pairing?

    struct Session: Decodable {
        let sessionID: String
        let scope: String
        let rememberMe: Bool
        let expiresAtUnixMS: Int64

        enum CodingKeys: String, CodingKey {
            case sessionID = "session_id"
            case scope
            case rememberMe = "remember_me"
            case expiresAtUnixMS = "expires_at_unix_ms"
        }
    }

    struct Resume: Decodable {
        let header: String
        let token: String
    }

    struct Pairing: Decodable {
        let schemaVersion: String
        let statusURL: String
        let resumeHeader: String
        let tokenTransport: String
        let allowedRoutes: [Route]
        let forbiddenCapabilities: [String]
        let expiresAtUnixMS: Int64

        enum CodingKeys: String, CodingKey {
            case schemaVersion = "schema_version"
            case statusURL = "status_url"
            case resumeHeader = "resume_header"
            case tokenTransport = "token_transport"
            case allowedRoutes = "allowed_routes"
            case forbiddenCapabilities = "forbidden_capabilities"
            case expiresAtUnixMS = "expires_at_unix_ms"
        }

        struct Route: Decodable {
            let method: String
            let path: String

            var displayText: String {
                let normalizedMethod = method.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
                let normalizedPath = path.trimmingCharacters(in: .whitespacesAndNewlines)
                guard normalizedMethod.isEmpty == false else {
                    return normalizedPath
                }
                guard normalizedPath.isEmpty == false else {
                    return normalizedMethod
                }
                return "\(normalizedMethod) \(normalizedPath)"
            }
        }

        func descriptor() -> CompanionPairingDescriptor {
            CompanionPairingDescriptor(
                schemaVersion: schemaVersion,
                statusURL: statusURL,
                resumeHeader: resumeHeader,
                tokenTransport: tokenTransport,
                allowedRoutes: allowedRoutes.map(\.displayText),
                forbiddenCapabilities: forbiddenCapabilities,
                expiresAtUnixMS: expiresAtUnixMS
            )
        }
    }

    func result() throws -> CompanionPairingIssueResult {
        guard let pairing else {
            throw CompanionPairingClientError.invalidPayload("Companion pairing response did not include a pairing descriptor.")
        }
        return CompanionPairingIssueResult(
            sessionID: session.sessionID,
            scope: session.scope,
            rememberMe: session.rememberMe,
            expiresAtUnixMS: session.expiresAtUnixMS,
            resumeHeader: resume.header,
            resumeToken: resume.token,
            pairing: pairing.descriptor()
        )
    }
}
