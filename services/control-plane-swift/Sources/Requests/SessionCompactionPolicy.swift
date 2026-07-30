import Foundation
import MelixWorkerProtocol

public struct SessionCompactionRequestContext: Sendable, Equatable {
    public let sessionID: String
    public let modelID: String
    public let usableContextTokens: UInt32
    public let maxHistoryItems: UInt32
    public let warningWatermarkPercent: UInt32
    public let criticalWatermarkPercent: UInt32

    public init(
        sessionID: String,
        modelID: String,
        usableContextTokens: UInt32,
        maxHistoryItems: UInt32,
        warningWatermarkPercent: UInt32 = 65,
        criticalWatermarkPercent: UInt32 = 80
    ) {
        self.sessionID = sessionID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.modelID = modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.usableContextTokens = usableContextTokens
        self.maxHistoryItems = maxHistoryItems
        self.warningWatermarkPercent = warningWatermarkPercent
        self.criticalWatermarkPercent = criticalWatermarkPercent
    }

    func plan(
        requestID: String,
        messages: [NormalizedTextMessage]
    ) -> SessionCompactionPlan? {
        guard !sessionID.isEmpty, !modelID.isEmpty else {
            return nil
        }
        return SessionCompactionPolicy.plan(
            requestID: requestID,
            sessionID: sessionID,
            modelID: modelID,
            historyItems: Self.historyItems(for: messages),
            usableContextTokens: usableContextTokens,
            maxHistoryItems: maxHistoryItems,
            warningWatermarkPercent: warningWatermarkPercent,
            criticalWatermarkPercent: criticalWatermarkPercent
        )
    }

    private static func historyItems(
        for messages: [NormalizedTextMessage]
    ) -> [SessionHistoryItemEstimate] {
        messages.map { message in
            let estimatedTokens = estimatedTokens(for: message)
            return SessionHistoryItemEstimate(
                estimatedTokens: estimatedTokens == 0 ? 1 : estimatedTokens
            )
        }
    }

    private static func estimatedTokens(for message: NormalizedTextMessage) -> UInt32 {
        message.parts.reduce(tokenCount(in: message.name ?? "")) { partial, part in
            switch part.part {
            case .text(let text):
                return addingClamped(partial, tokenCount(in: text))
            case .imageUri, .imageBytes, .audioUri, .audioBytes:
                return addingClamped(partial, 256)
            case .videoUri, .videoBytes:
                return addingClamped(partial, 1_024)
            case nil:
                return partial
            }
        }
    }

    private static func tokenCount(in text: String) -> UInt32 {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return 0
        }
        var whitespaceEstimate = 0
        var isInsideWord = false
        for character in trimmed {
            if character.isWhitespace {
                isInsideWord = false
            } else if !isInsideWord {
                whitespaceEstimate += 1
                isInsideWord = true
            }
        }
        let byteEstimate = max(1, (trimmed.utf8.count + 3) / 4)
        return UInt32(min(Int(UInt32.max), max(whitespaceEstimate, byteEstimate)))
    }

    private static func addingClamped(_ lhs: UInt32, _ rhs: UInt32) -> UInt32 {
        let (value, overflow) = lhs.addingReportingOverflow(rhs)
        return overflow ? UInt32.max : value
    }
}

struct SessionHistoryItemEstimate: Sendable, Equatable {
    let estimatedTokens: UInt32
    let protectedGrounding: Bool

    init(estimatedTokens: UInt32, protectedGrounding: Bool = false) {
        self.estimatedTokens = estimatedTokens
        self.protectedGrounding = protectedGrounding
    }
}

enum SessionHistoryPolicy: String, Sendable, Equatable {
    case unlimited
    case boundedTail = "bounded_tail"
    case compactionRequired = "compaction_required"
}

struct SessionCompactionPlan: Sendable, Equatable {
    static let schemaVersion = "melix.session_compaction_policy_receipt.v1"

    let requestID: String
    let sessionID: String
    let modelID: String
    let historyPolicy: SessionHistoryPolicy
    let itemsBefore: Int
    let itemsAfter: Int
    let estimatedTokensBefore: UInt32
    let estimatedTokensAfter: UInt32
    let usableContextTokens: UInt32
    let maxHistoryItems: UInt32
    let protectedGroundingItemsBefore: Int
    let protectedGroundingItemsAfter: Int
    let protectedGroundingPreserved: Bool
    let watermarkState: String
    let tierApplied: String
    let compactionRequired: Bool

    var extFields: [String: String] {
        [
            "melix.session_compaction.receipt_schema": Self.schemaVersion,
            "melix.session_compaction.receipt_count": "1",
            "melix.session_compaction.receipts_json": Self.canonicalJSONString([receipt.mapValues(\.jsonValue)]),
        ]
    }

    private var receipt: [String: SessionCompactionReceiptValue] {
        [
            "schema_version": .string(Self.schemaVersion),
            "request_id": .string(requestID),
            "session_id": .string(sessionID),
            "model_id": .string(modelID),
            "history_policy": .string(historyPolicy.rawValue),
            "items_before": .int(itemsBefore),
            "items_after": .int(itemsAfter),
            "estimated_tokens_before": .uint32(estimatedTokensBefore),
            "estimated_tokens_after": .uint32(estimatedTokensAfter),
            "usable_context_tokens": .uint32(usableContextTokens),
            "max_history_items": .uint32(maxHistoryItems),
            "protected_grounding_items_before": .int(protectedGroundingItemsBefore),
            "protected_grounding_items_after": .int(protectedGroundingItemsAfter),
            "protected_grounding_preserved": .bool(protectedGroundingPreserved),
            "watermark_state": .string(watermarkState),
            "tier_applied": .string(tierApplied),
            "compaction_required": .bool(compactionRequired),
        ]
    }

    private static func canonicalJSONString(_ object: [[String: Any]]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
            return "[]"
        }
        return String(data: data, encoding: .utf8) ?? "[]"
    }
}

struct SessionCompactionPolicy {
    static func plan(
        requestID: String,
        sessionID: String,
        modelID: String,
        historyItems: [SessionHistoryItemEstimate],
        usableContextTokens: UInt32,
        maxHistoryItems: UInt32,
        warningWatermarkPercent: UInt32 = 65,
        criticalWatermarkPercent: UInt32 = 80
    ) -> SessionCompactionPlan {
        let itemsBefore = historyItems.count
        let estimatedTokensBefore = sumEstimatedTokens(historyItems)
        let protectedGroundingItemsBefore = countProtectedGroundingItems(historyItems)
        let retainedItems = retainedPolicyItems(historyItems, maxHistoryItems: maxHistoryItems)
        let itemsAfter = retainedItems.count
        let estimatedTokensAfter = sumEstimatedTokens(retainedItems)
        let protectedGroundingItemsAfter = countProtectedGroundingItems(retainedItems)
        // Planner-only retention keeps protected grounding by construction. Future
        // summarization paths must update this if grounding can be transformed or dropped.
        let protectedGroundingPreserved = protectedGroundingItemsBefore == protectedGroundingItemsAfter
        let overBudget = usableContextTokens == 0
            ? estimatedTokensAfter > 0
            : estimatedTokensAfter > usableContextTokens

        let historyPolicy: SessionHistoryPolicy
        let tierApplied: String
        let compactionRequired: Bool
        if overBudget {
            historyPolicy = .compactionRequired
            tierApplied = "requires_compaction"
            compactionRequired = true
        } else if maxHistoryItems != 0, itemsAfter < itemsBefore {
            historyPolicy = .boundedTail
            tierApplied = "drop_tail_history"
            compactionRequired = false
        } else {
            historyPolicy = .unlimited
            tierApplied = "none"
            compactionRequired = false
        }

        return SessionCompactionPlan(
            requestID: requestID.trimmingCharacters(in: .whitespacesAndNewlines),
            sessionID: sessionID.trimmingCharacters(in: .whitespacesAndNewlines),
            modelID: modelID.trimmingCharacters(in: .whitespacesAndNewlines),
            historyPolicy: historyPolicy,
            itemsBefore: itemsBefore,
            itemsAfter: itemsAfter,
            estimatedTokensBefore: estimatedTokensBefore,
            estimatedTokensAfter: estimatedTokensAfter,
            usableContextTokens: usableContextTokens,
            maxHistoryItems: maxHistoryItems,
            protectedGroundingItemsBefore: protectedGroundingItemsBefore,
            protectedGroundingItemsAfter: protectedGroundingItemsAfter,
            protectedGroundingPreserved: protectedGroundingPreserved,
            watermarkState: watermarkState(
                estimatedTokensAfter: estimatedTokensAfter,
                usableContextTokens: usableContextTokens,
                warningWatermarkPercent: warningWatermarkPercent,
                criticalWatermarkPercent: criticalWatermarkPercent
            ),
            tierApplied: tierApplied,
            compactionRequired: compactionRequired
        )
    }

    private static func retainedPolicyItems(
        _ historyItems: [SessionHistoryItemEstimate],
        maxHistoryItems: UInt32
    ) -> [SessionHistoryItemEstimate] {
        guard maxHistoryItems != 0 else {
            return historyItems
        }
        // maxHistoryItems bounds ordinary tail history; protected grounding can exceed it.
        let limit = min(Int(clamping: maxHistoryItems), historyItems.count)
        let tailStartIndex = historyItems.count - limit
        return historyItems.enumerated().compactMap { index, item in
            guard item.protectedGrounding || index >= tailStartIndex else {
                return nil
            }
            return item
        }
    }

    private static func sumEstimatedTokens(_ historyItems: [SessionHistoryItemEstimate]) -> UInt32 {
        historyItems.reduce(UInt32(0)) { total, item in
            let (value, overflow) = total.addingReportingOverflow(item.estimatedTokens)
            return overflow ? UInt32.max : value
        }
    }

    private static func countProtectedGroundingItems(_ historyItems: [SessionHistoryItemEstimate]) -> Int {
        historyItems.reduce(0) { count, item in
            item.protectedGrounding ? count + 1 : count
        }
    }

    private static func watermarkState(
        estimatedTokensAfter: UInt32,
        usableContextTokens: UInt32,
        warningWatermarkPercent: UInt32,
        criticalWatermarkPercent: UInt32
    ) -> String {
        guard usableContextTokens > 0 else {
            return estimatedTokensAfter > 0 ? "overflow" : "within_budget"
        }
        if estimatedTokensAfter > usableContextTokens {
            return "overflow"
        }

        let used = UInt64(estimatedTokensAfter) * 100
        let budget = UInt64(usableContextTokens)
        if used >= budget * UInt64(criticalWatermarkPercent) {
            return "critical"
        }
        if used >= budget * UInt64(warningWatermarkPercent) {
            return "warning"
        }
        return "within_budget"
    }
}

private enum SessionCompactionReceiptValue: Sendable, Equatable {
    case string(String)
    case bool(Bool)
    case int(Int)
    case uint32(UInt32)

    var jsonValue: Any {
        switch self {
        case .string(let value):
            return value
        case .bool(let value):
            return value
        case .int(let value):
            return value
        case .uint32(let value):
            return Int(value)
        }
    }
}
