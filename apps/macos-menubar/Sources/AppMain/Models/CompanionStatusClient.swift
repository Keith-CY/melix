import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public enum CompanionStatusPhase: String, Codable, Equatable, Sendable {
    case idle
    case loading
    case loaded
    case failed
}

public struct CompanionStatusLogEntryState: Codable, Equatable, Sendable {
    public let eventType: String
    public let source: String
    public let jobID: String
    public let requestID: String
    public let modelID: String
    public let operation: String
    public let state: String
    public let lane: String
    public let workerID: String
    public let progressStage: String
    public let updatedAtUnixMS: Int64
    public let failureCode: String
    public let redactionSummary: String

    public init(
        eventType: String,
        source: String,
        jobID: String,
        requestID: String,
        modelID: String,
        operation: String,
        state: String,
        lane: String,
        workerID: String,
        progressStage: String,
        updatedAtUnixMS: Int64,
        failureCode: String,
        redactionSummary: String
    ) {
        self.eventType = eventType
        self.source = source
        self.jobID = jobID
        self.requestID = requestID
        self.modelID = modelID
        self.operation = operation
        self.state = state
        self.lane = lane
        self.workerID = workerID
        self.progressStage = progressStage
        self.updatedAtUnixMS = updatedAtUnixMS
        self.failureCode = failureCode
        self.redactionSummary = redactionSummary
    }
}

public struct CompanionStatusLogTailState: Codable, Equatable, Sendable {
    public let source: String
    public let visible: Int
    public let total: Int
    public let entries: [CompanionStatusLogEntryState]

    public init(
        source: String = "image_jobs",
        visible: Int = 0,
        total: Int = 0,
        entries: [CompanionStatusLogEntryState] = []
    ) {
        self.source = source
        self.visible = visible
        self.total = total
        self.entries = entries
    }
}

public struct CompanionStatusSnapshot: Codable, Equatable, Sendable {
    public let status: String
    public let readOnly: Bool
    public let authorizationScope: String
    public let logTail: CompanionStatusLogTailState
    public let redactionLogs: String

    public init(
        status: String,
        readOnly: Bool,
        authorizationScope: String,
        logTail: CompanionStatusLogTailState,
        redactionLogs: String
    ) {
        self.status = status
        self.readOnly = readOnly
        self.authorizationScope = authorizationScope
        self.logTail = logTail
        self.redactionLogs = redactionLogs
    }
}

public struct CompanionStatusState: Equatable, Sendable, CustomStringConvertible {
    public var phase: CompanionStatusPhase
    public var status: String
    public var readOnly: Bool
    public var authorizationScope: String
    public var logTail: CompanionStatusLogTailState
    public var redactionLogs: String
    public var lastError: String?

    public init(
        phase: CompanionStatusPhase = .idle,
        status: String = "",
        readOnly: Bool = false,
        authorizationScope: String = "",
        logTail: CompanionStatusLogTailState = CompanionStatusLogTailState(),
        redactionLogs: String = "",
        lastError: String? = nil
    ) {
        self.phase = phase
        self.status = status
        self.readOnly = readOnly
        self.authorizationScope = authorizationScope
        self.logTail = logTail
        self.redactionLogs = redactionLogs
        self.lastError = lastError
    }

    public var description: String {
        "CompanionStatusState(phase: \(phase.rawValue), status: \(status), readOnly: \(readOnly), authorizationScope: \(authorizationScope), logTail: \(logTail), redactionLogs: \(redactionLogs), lastError: \(String(describing: lastError)))"
    }

    public static func loaded(from snapshot: CompanionStatusSnapshot) -> CompanionStatusState {
        CompanionStatusState(
            phase: .loaded,
            status: snapshot.status,
            readOnly: snapshot.readOnly,
            authorizationScope: snapshot.authorizationScope,
            logTail: snapshot.logTail,
            redactionLogs: snapshot.redactionLogs
        )
    }

    public static func failed(_ message: String) -> CompanionStatusState {
        CompanionStatusState(phase: .failed, lastError: message)
    }
}

public protocol CompanionStatusClient: Sendable {
    func refreshStatus(
        statusURL: URL,
        resumeHeader: String,
        sessionToken: String
    ) async throws -> CompanionStatusSnapshot
}

public protocol CompanionStatusHTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionCompanionStatusHTTPTransport: CompanionStatusHTTPTransport {
    public init() {}

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw CompanionStatusClientError.invalidResponse("Companion status response was not HTTP.")
        }
        return (data, httpResponse)
    }
}

public struct LiveCompanionStatusClient: CompanionStatusClient {
    private let transport: any CompanionStatusHTTPTransport

    public init(
        transport: any CompanionStatusHTTPTransport = URLSessionCompanionStatusHTTPTransport()
    ) {
        self.transport = transport
    }

    public func refreshStatus(
        statusURL: URL,
        resumeHeader: String,
        sessionToken: String
    ) async throws -> CompanionStatusSnapshot {
        var request = URLRequest(url: statusURL)
        request.httpMethod = "GET"
        request.setValue(sessionToken, forHTTPHeaderField: resumeHeader)

        let (data, response) = try await transport.data(for: request)
        try validateHTTPResponse(data: data, response: response)
        let payload = try JSONDecoder().decode(CompanionStatusResponsePayload.self, from: data)
        return payload.snapshot()
    }

    private func validateHTTPResponse(data: Data, response: HTTPURLResponse) throws {
        guard (200..<300).contains(response.statusCode) else {
            let message = String(decoding: data, as: UTF8.self)
            throw CompanionStatusClientError.httpStatus(response.statusCode, message)
        }
    }
}

public enum CompanionStatusClientError: Error, CustomStringConvertible, Equatable {
    case invalidResponse(String)
    case httpStatus(Int, String)

    public var description: String {
        switch self {
        case .invalidResponse(let message):
            return message
        case .httpStatus(let statusCode, let message):
            return "Companion status HTTP \(statusCode): \(message)"
        }
    }
}

private struct CompanionStatusResponsePayload: Decodable {
    let readOnly: Bool
    let status: String
    let authorization: Authorization
    let logs: Logs
    let redaction: Redaction

    struct Authorization: Decodable {
        let scope: String
    }

    struct Logs: Decodable {
        let source: String
        let visible: Int
        let total: Int
        let entries: [Entry]
    }

    struct Entry: Decodable {
        let eventType: String
        let source: String
        let jobID: String
        let requestID: String
        let modelID: String
        let operation: String
        let state: String
        let lane: String
        let workerID: String
        let progressStage: String
        let updatedAtUnixMS: Int64
        let failureCode: String
        let redaction: EntryRedaction

        enum CodingKeys: String, CodingKey {
            case eventType = "event_type"
            case source
            case jobID = "job_id"
            case requestID = "request_id"
            case modelID = "model_id"
            case operation
            case state
            case lane
            case workerID = "worker_id"
            case progressStage = "progress_stage"
            case updatedAtUnixMS = "updated_at_unix_ms"
            case failureCode = "failure_code"
            case redaction
        }

        func asState() -> CompanionStatusLogEntryState {
            CompanionStatusLogEntryState(
                eventType: eventType,
                source: source,
                jobID: jobID,
                requestID: requestID,
                modelID: modelID,
                operation: operation,
                state: state,
                lane: lane,
                workerID: workerID,
                progressStage: progressStage,
                updatedAtUnixMS: updatedAtUnixMS,
                failureCode: failureCode,
                redactionSummary: redaction.summary
            )
        }
    }

    struct EntryRedaction: Decodable {
        let rawLogLine: String
        let rawPrompt: String
        let requestBody: String
        let artifactURIs: String
        let localPaths: String
        let errorMessage: String

        enum CodingKeys: String, CodingKey {
            case rawLogLine = "raw_log_line"
            case rawPrompt = "raw_prompt"
            case requestBody = "request_body"
            case artifactURIs = "artifact_uris"
            case localPaths = "local_paths"
            case errorMessage = "error_message"
        }

        var summary: String {
            [
                "raw log line \(rawLogLine)",
                "raw prompt \(rawPrompt)",
                "request body \(requestBody)",
                "artifact URIs \(artifactURIs)",
                "local paths \(localPaths)",
                "error message \(errorMessage)",
            ].joined(separator: "; ")
        }
    }

    struct Redaction: Decodable {
        let logs: String
    }

    enum CodingKeys: String, CodingKey {
        case readOnly = "read_only"
        case status
        case authorization
        case logs
        case redaction
    }

    func snapshot() -> CompanionStatusSnapshot {
        CompanionStatusSnapshot(
            status: status,
            readOnly: readOnly,
            authorizationScope: authorization.scope,
            logTail: CompanionStatusLogTailState(
                source: logs.source,
                visible: logs.visible,
                total: logs.total,
                entries: logs.entries.map { $0.asState() }
            ),
            redactionLogs: redaction.logs
        )
    }
}
