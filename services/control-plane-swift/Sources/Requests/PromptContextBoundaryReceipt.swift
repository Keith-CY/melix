import Foundation
import MelixWorkerProtocol

struct PromptContextBoundaryReceipts: Sendable, Equatable {
    static let schemaVersion = "melix.untrusted_context_receipt.v1"

    private let receipts: [[String: PromptContextReceiptValue]]

    init(requestID: String, messages: [NormalizedTextMessage]) {
        var receipts: [[String: PromptContextReceiptValue]] = []
        for (messageIndex, message) in messages.enumerated() where Self.isUntrustedMessageRole(message.role) {
            for (partIndex, part) in message.parts.enumerated() {
                guard let sourceField = Self.sourceField(for: part, messageIndex: messageIndex, partIndex: partIndex) else {
                    continue
                }
                var receipt: [String: PromptContextReceiptValue] = [
                    "schema_version": .string(Self.schemaVersion),
                    "segment_id": .string("\(requestID):message-\(messageIndex):part-\(partIndex)"),
                    "source_type": .string(Self.sourceType(for: message)),
                    "source_field": .string(sourceField),
                    "message_role": .string(message.role),
                    "trust_level": .string("untrusted"),
                    "policy": .string("data_only"),
                    "boundary_checked": .bool(true),
                    "included": .bool(true),
                    "owner_scope_checked": .bool(false),
                    "reason": .string("chat message content is prompt data, not instructions"),
                    "corrective_action": .string(
                        "Keep this message part in its original role and do not promote it into system or developer instructions."
                    ),
                ]
                if let sourceID = message.name {
                    receipt["source_id"] = .string(sourceID)
                }
                receipts.append(receipt)
            }
        }
        self.receipts = receipts
    }

    var extFields: [String: String] {
        guard !receipts.isEmpty else {
            return [:]
        }
        return [
            "melix.prompt_context.receipt_schema": Self.schemaVersion,
            "melix.prompt_context.receipt_count": String(receipts.count),
            "melix.prompt_context.receipts_json": Self.canonicalJSONString(receipts.map { receipt in
                receipt.mapValues(\.jsonValue)
            }),
        ]
    }

    private static func isUntrustedMessageRole(_ role: String) -> Bool {
        let normalizedRole = role.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return !normalizedRole.isEmpty && normalizedRole != "system" && normalizedRole != "developer"
    }

    private static func sourceType(for message: NormalizedTextMessage) -> String {
        let normalizedRole = message.role.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedRole == "tool" {
            return "tool_output"
        }

        guard let name = message.name else {
            return "chat_prompt_message"
        }
        let normalizedName = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if hasAnyPrefix(
            normalizedName,
            ["retrieved_document", "retrieved-doc", "document", "doc", "rag", "rag_document", "knowledge"]
        ) {
            return "retrieved_document"
        }
        if hasAnyPrefix(normalizedName, ["skill", "agent_skill"]) {
            return "skill"
        }
        if hasAnyPrefix(normalizedName, ["memory", "retrieved_memory", "pinned_memory"]) {
            return "memory"
        }
        if hasAnyPrefix(normalizedName, ["background_continuation", "background-continuation", "background_job", "background-job"]) {
            return "background_continuation"
        }
        return "chat_prompt_message"
    }

    private static func hasAnyPrefix(_ value: String, _ prefixes: [String]) -> Bool {
        prefixes.contains { prefix in
            value == prefix || value.hasPrefix("\(prefix):") || value.hasPrefix("\(prefix).")
        }
    }

    private static func sourceField(
        for part: Melix_Worker_V1_MessagePart,
        messageIndex: Int,
        partIndex: Int
    ) -> String? {
        switch part.part {
        case .text(let value)?:
            guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return "messages[\(messageIndex)].parts[\(partIndex)].text"
        case .imageUri(let value)?:
            guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return "messages[\(messageIndex)].parts[\(partIndex)].image_uri"
        case .imageBytes(let value)?:
            guard !value.isEmpty else {
                return nil
            }
            return "messages[\(messageIndex)].parts[\(partIndex)].image_bytes"
        case .audioUri(let value)?:
            guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return "messages[\(messageIndex)].parts[\(partIndex)].audio_uri"
        case .audioBytes(let value)?:
            guard !value.isEmpty else {
                return nil
            }
            return "messages[\(messageIndex)].parts[\(partIndex)].audio_bytes"
        case .videoUri(let value)?:
            guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return "messages[\(messageIndex)].parts[\(partIndex)].video_uri"
        case .videoBytes(let value)?:
            guard !value.isEmpty else {
                return nil
            }
            return "messages[\(messageIndex)].parts[\(partIndex)].video_bytes"
        case nil:
            return nil
        }
    }

    private static func canonicalJSONString(_ object: [[String: Any]]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
            return "[]"
        }
        return String(data: data, encoding: .utf8) ?? "[]"
    }
}

private enum PromptContextReceiptValue: Sendable, Equatable {
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
