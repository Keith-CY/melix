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
    public let modelFamily: String?
    public let parserMode: String?
    public let tagDialect: String?
    public let requestedParser: String?
    public let resolvedParser: String?
    public let parserFallbackMode: String?
    public let parserRefusalReason: String?

    public init(
        field: String,
        route: String,
        expectedBehavior: String,
        observedStatus: OpenAIConformanceObservedStatus,
        observedReason: String,
        modelFamily: String? = nil,
        parserMode: String? = nil,
        tagDialect: String? = nil,
        requestedParser: String? = nil,
        resolvedParser: String? = nil,
        parserFallbackMode: String? = nil,
        parserRefusalReason: String? = nil
    ) {
        self.field = field
        self.route = route
        self.expectedBehavior = expectedBehavior
        self.observedStatus = observedStatus
        self.observedReason = observedReason
        self.modelFamily = modelFamily
        self.parserMode = parserMode
        self.tagDialect = tagDialect
        self.requestedParser = requestedParser
        self.resolvedParser = resolvedParser
        self.parserFallbackMode = parserFallbackMode
        self.parserRefusalReason = parserRefusalReason
    }

    enum CodingKeys: String, CodingKey {
        case field
        case route
        case expectedBehavior = "expected_behavior"
        case observedStatus = "observed_status"
        case observedReason = "observed_reason"
        case modelFamily = "model_family"
        case parserMode = "parser_mode"
        case tagDialect = "tag_dialect"
        case requestedParser = "requested_parser"
        case resolvedParser = "resolved_parser"
        case parserFallbackMode = "parser_fallback_mode"
        case parserRefusalReason = "parser_refusal_reason"
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
