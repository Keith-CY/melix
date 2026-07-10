import Foundation

struct SessionHistoryItemEstimate: Sendable, Equatable {
    let estimatedTokens: UInt32
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
        let retainedItems = retainedTailItems(historyItems, maxHistoryItems: maxHistoryItems)
        let itemsAfter = retainedItems.count
        let estimatedTokensAfter = sumEstimatedTokens(retainedItems)
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

    private static func retainedTailItems(
        _ historyItems: [SessionHistoryItemEstimate],
        maxHistoryItems: UInt32
    ) -> [SessionHistoryItemEstimate] {
        guard maxHistoryItems != 0 else {
            return historyItems
        }
        let limit = min(Int(maxHistoryItems), historyItems.count)
        return Array(historyItems.suffix(limit))
    }

    private static func sumEstimatedTokens(_ historyItems: [SessionHistoryItemEstimate]) -> UInt32 {
        historyItems.reduce(UInt32(0)) { total, item in
            let (value, overflow) = total.addingReportingOverflow(item.estimatedTokens)
            return overflow ? UInt32.max : value
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
