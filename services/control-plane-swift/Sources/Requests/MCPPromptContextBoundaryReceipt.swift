import CryptoKit
import Foundation

struct MCPPromptContextBoundaryReceipts: Sendable, Equatable {
    let extFields: [String: String]

    init(requestID: String, sourceIDs: [String]) {
        var receipts: [[String: MCPPromptContextReceiptValue]] = []
        for (sourceIndex, sourceID) in sourceIDs.enumerated() {
            let normalizedSourceID = sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !normalizedSourceID.isEmpty else {
                continue
            }
            let redactedSourceID = Self.redactedSourceID(normalizedSourceID)
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

    private static func redactedSourceID(_ sourceID: String) -> String {
        guard isPublicSourceID(sourceID) else {
            return "mcp-source:\(sha256Hex(sourceID).prefix(12))"
        }
        return sourceID
    }

    private static func isPublicSourceID(_ sourceID: String) -> Bool {
        guard sourceID.count <= 96 else {
            return false
        }
        return sourceID.allSatisfy { character in
            character.isASCII
                && (character.isLetter || character.isNumber || character == "." || character == "_" || character == "-")
        }
    }

    private static func sha256Hex(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
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
