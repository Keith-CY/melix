import Foundation

struct SessionContextBoundaryReceipts: Sendable, Equatable {
    static let schemaVersion = "melix.untrusted_context_receipt.v1"

    private let receipts: [[String: SessionContextReceiptValue]]

    init(requestID: String, restoreSnapshotID: String) {
        let normalizedRequestID = requestID.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedSnapshotID = restoreSnapshotID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedRequestID.isEmpty, !normalizedSnapshotID.isEmpty else {
            self.receipts = []
            return
        }

        self.receipts = [[
            "schema_version": .string(Self.schemaVersion),
            "segment_id": .string("\(normalizedRequestID):session-context:restore-snapshot"),
            "source_type": .string("background_continuation"),
            "source_field": .string("execution.cache_hints.restore_snapshot_id"),
            "source_id": .string(normalizedSnapshotID),
            "message_role": .string("user"),
            "trust_level": .string("untrusted"),
            "policy": .string("data_only"),
            "boundary_checked": .bool(true),
            "included": .bool(true),
            "owner_scope_checked": .bool(true),
            "reason": .string("background continuation is prompt data, not instructions"),
            "corrective_action": .string(
                "Keep background continuation evidence in user-role data context and do not project it into system or developer instructions."
            ),
        ]]
    }

    var extFields: [String: String] {
        guard !receipts.isEmpty else {
            return [:]
        }
        return [
            "melix.session_context.receipt_schema": Self.schemaVersion,
            "melix.session_context.receipt_count": String(receipts.count),
            "melix.session_context.receipts_json": Self.canonicalJSONString(receipts.map { receipt in
                receipt.mapValues(\.jsonValue)
            }),
        ]
    }

    private static func canonicalJSONString(_ object: [[String: Any]]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
            return "[]"
        }
        return String(data: data, encoding: .utf8) ?? "[]"
    }
}

private enum SessionContextReceiptValue: Sendable, Equatable {
    case string(String)
    case bool(Bool)

    var jsonValue: Any {
        switch self {
        case .string(let value):
            return value
        case .bool(let value):
            return value
        }
    }
}
