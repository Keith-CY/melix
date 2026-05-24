import Foundation

public enum OpenAIConformanceObservedStatus: String, Codable, Sendable, Equatable {
    case pass
    case fail
    case skipped
}

public struct OpenAIConformanceRow: Codable, Sendable, Equatable {
    public let field: String
    public let route: String
    public let expectedBehavior: String
    public let observedStatus: OpenAIConformanceObservedStatus
    public let observedReason: String

    public init(
        field: String,
        route: String,
        expectedBehavior: String,
        observedStatus: OpenAIConformanceObservedStatus,
        observedReason: String
    ) {
        self.field = field
        self.route = route
        self.expectedBehavior = expectedBehavior
        self.observedStatus = observedStatus
        self.observedReason = observedReason
    }

    enum CodingKeys: String, CodingKey {
        case field
        case route
        case expectedBehavior = "expected_behavior"
        case observedStatus = "observed_status"
        case observedReason = "observed_reason"
    }
}

public struct OpenAIConformanceReportSummary: Codable, Sendable, Equatable {
    public let total: Int
    public let passed: Int
    public let failed: Int
    public let skipped: Int
}

public struct OpenAIConformanceReport: Codable, Sendable, Equatable {
    public static let currentSchemaVersion = "melix.openai_conformance_report.v1"

    public let schemaVersion: String
    public let summary: OpenAIConformanceReportSummary
    public let rows: [OpenAIConformanceRow]

    public init(
        schemaVersion: String = Self.currentSchemaVersion,
        rows: [OpenAIConformanceRow]
    ) {
        var passed = 0
        var failed = 0
        var skipped = 0
        for row in rows {
            switch row.observedStatus {
            case .pass:
                passed += 1
            case .fail:
                failed += 1
            case .skipped:
                skipped += 1
            }
        }
        self.schemaVersion = schemaVersion
        self.rows = rows
        self.summary = OpenAIConformanceReportSummary(
            total: rows.count,
            passed: passed,
            failed: failed,
            skipped: skipped
        )
    }

    public func jsonData() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(self)
    }

    public func jsonString() throws -> String {
        String(decoding: try jsonData(), as: UTF8.self)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case summary
        case rows
    }
}
