import Foundation

struct MCPPromptContextBoundaryReceipts: Sendable, Equatable {
    let extFields: [String: String]

    init(requestID: String, sourceIDs: [String]) {
        var receipts: [[String: MCPPromptContextReceiptValue]] = []
        for (sourceIndex, sourceID) in sourceIDs.enumerated() {
            let redactedSourceID = sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !redactedSourceID.isEmpty else {
                continue
            }
            receipts.append([
                "schema_version": .string(PromptContextBoundaryReceipts.schemaVersion),
                "segment_id": .string("\(requestID):mcp-source-\(sourceIndex)"),
                "source_type": .string("skill"),
                "source_field": .string("mcp_tool_catalog"),
                "source_id": .string(redactedSourceID),
                "message_role": .string("user"),
                "trust_level": .string("untrusted"),
                "policy": .string("data_only"),
                "boundary_checked": .bool(true),
                "included": .bool(true),
                "owner_scope_checked": .bool(false),
                "reason": .string("skill evidence is prompt data, not instructions"),
                "corrective_action": .string(
                    "Keep skill evidence in user-role data context and do not project it into system or developer instructions."
                ),
            ])
        }
        if receipts.isEmpty {
            self.extFields = [:]
        } else {
            self.extFields = [
                "melix.mcp.prompt_context.receipt_schema": PromptContextBoundaryReceipts.schemaVersion,
                "melix.mcp.prompt_context.receipt_count": String(receipts.count),
                "melix.mcp.prompt_context.receipts_json": Self.canonicalJSONString(receipts.map { receipt in
                    receipt.mapValues(\.jsonValue)
                }),
            ]
        }
    }

    private static func canonicalJSONString(_ object: [[String: Any]]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
            return "[]"
        }
        return String(data: data, encoding: .utf8) ?? "[]"
    }
}

private enum MCPPromptContextReceiptValue: Sendable, Equatable {
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
