import Foundation

public struct PrivacyDetectorReceipt: Equatable, Sendable {
    public let schemaVersion: String
    public let surface: String
    public let routeScope: String
    public let detectorID: String
    public let policyID: String
    public let policyMode: String
    public let action: String
    public let categories: [String]
    public let matchCount: Int
    public let redactedSpanCount: Int
    public let blockedReason: String
    public let confidenceSource: String
    public let rawSensitiveSpanCount: Int
    public let rawTextIncluded: Bool

    public init(
        schemaVersion: String = "melix.privacy_detector_receipt.v1",
        surface: String,
        routeScope: String,
        detectorID: String = "melix.pattern_detector.v1",
        policyID: String = "melix.default_privacy_policy.v1",
        policyMode: String,
        action: String,
        categories: [String] = [],
        matchCount: Int = 0,
        redactedSpanCount: Int = 0,
        blockedReason: String = "",
        confidenceSource: String = "deterministic_pattern",
        rawSensitiveSpanCount: Int = 0,
        rawTextIncluded: Bool = false
    ) {
        self.schemaVersion = schemaVersion
        self.surface = surface
        self.routeScope = routeScope
        self.detectorID = detectorID
        self.policyID = policyID
        self.policyMode = policyMode
        self.action = action
        self.categories = categories
        self.matchCount = matchCount
        self.redactedSpanCount = redactedSpanCount
        self.blockedReason = blockedReason
        self.confidenceSource = confidenceSource
        self.rawSensitiveSpanCount = rawSensitiveSpanCount
        self.rawTextIncluded = rawTextIncluded
    }

    public var jsonObject: [String: Any] {
        [
            "schema_version": schemaVersion,
            "surface": surface,
            "route_scope": routeScope,
            "detector_id": detectorID,
            "policy_id": policyID,
            "policy_mode": policyMode,
            "action": action,
            "categories": categories,
            "match_count": matchCount,
            "redacted_span_count": redactedSpanCount,
            "blocked_reason": blockedReason,
            "confidence_source": confidenceSource,
            "raw_sensitive_span_count": rawSensitiveSpanCount,
            "raw_text_included": rawTextIncluded,
        ]
    }

    public func metadataFields(prefix: String) -> [String: String] {
        [
            "\(prefix).schema_version": schemaVersion,
            "\(prefix).surface": surface,
            "\(prefix).route_scope": routeScope,
            "\(prefix).detector_id": detectorID,
            "\(prefix).policy_id": policyID,
            "\(prefix).policy_mode": policyMode,
            "\(prefix).action": action,
            "\(prefix).categories": categories.joined(separator: ","),
            "\(prefix).match_count": String(matchCount),
            "\(prefix).redacted_span_count": String(redactedSpanCount),
            "\(prefix).blocked_reason": blockedReason,
            "\(prefix).confidence_source": confidenceSource,
            "\(prefix).raw_sensitive_span_count": String(rawSensitiveSpanCount),
            "\(prefix).raw_text_included": String(rawTextIncluded),
        ]
    }
}

public struct PatternPrivacyDetectionResult: Equatable, Sendable {
    public let redactedTexts: [String]
    public let receipt: PrivacyDetectorReceipt
    public let auditCounter: PrivacyAuditCounter
}

public enum PatternPrivacyDetector {
    public static func detect(
        textSegments: [String],
        surface: String,
        routeScope: String,
        policyMode: String
    ) -> PatternPrivacyDetectionResult {
        let normalizedMode = normalizedPolicyMode(policyMode)
        var redactedTexts: [String] = []
        var categories = Set<String>()
        var matchCount = 0

        for text in textSegments {
            let matches = privacyPatternMatches(in: text)
            for match in matches {
                categories.insert(match.category)
            }
            matchCount += matches.count
            redactedTexts.append(redactedText(for: text, matches: matches))
        }

        let action: String
        let redactedSpanCount: Int
        let blockedReason: String
        if matchCount == 0 {
            action = "passed"
            redactedSpanCount = 0
            blockedReason = ""
        } else if normalizedMode == "block" {
            action = "blocked"
            redactedSpanCount = 0
            blockedReason = "pattern_match_blocked"
        } else if normalizedMode == "detect" {
            // Redacted text is still computed above to keep scan behavior shared,
            // but detect mode reports a non-mutating action so callers must not
            // apply replacement text.
            action = "detected"
            redactedSpanCount = 0
            blockedReason = ""
        } else {
            action = "redacted"
            redactedSpanCount = matchCount
            blockedReason = ""
        }

        let receipt = PrivacyDetectorReceipt(
            surface: surface,
            routeScope: routeScope,
            policyMode: normalizedMode,
            action: action,
            categories: categories.sorted(),
            matchCount: matchCount,
            redactedSpanCount: redactedSpanCount,
            blockedReason: blockedReason
        )
        let counter = PrivacyAuditCounter(
            surface: surface,
            routeScope: routeScope,
            blockedCount: action == "blocked" ? 1 : 0,
            redactedCount: action == "redacted" ? 1 : 0,
            passedCount: action == "passed" || action == "detected" ? 1 : 0
        )
        return PatternPrivacyDetectionResult(
            redactedTexts: redactedTexts,
            receipt: receipt,
            auditCounter: counter
        )
    }

    private static func normalizedPolicyMode(_ value: String) -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return switch normalized {
        case "block", "detect":
            normalized
        default:
            "redact"
        }
    }

    private struct PatternMatch {
        let range: NSRange
        let category: String
        let placeholder: String
    }

    private static let privacyPatterns: [(category: String, placeholder: String, regex: NSRegularExpression)] = [
        (
            "secret",
            "[REDACTED_SECRET]",
            try! NSRegularExpression(
                pattern: #"\b[A-Za-z0-9_]*(?:HF_TOKEN|HUGGINGFACE_HUB_TOKEN|MELIX_HF_TOKEN|MELIX_HUGGINGFACE_TOKEN|MELIX_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|API_KEY|ACCESS_TOKEN|AUTH_TOKEN|BEARER_TOKEN|SECRET_KEY|CLIENT_SECRET|PASSWORD)\s*=\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s;]+)"#,
                options: [.caseInsensitive]
            )
        ),
        (
            "secret",
            "[REDACTED_SECRET]",
            try! NSRegularExpression(
                pattern: #"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"#,
                options: [.caseInsensitive]
            )
        ),
        (
            "secret",
            "[REDACTED_SECRET]",
            try! NSRegularExpression(
                pattern: #"\bhf_[A-Za-z0-9][A-Za-z0-9_\-=]{5,}"#,
                options: [.caseInsensitive]
            )
        ),
        (
            "email",
            "[REDACTED_EMAIL]",
            try! NSRegularExpression(
                pattern: #"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\b"#
            )
        ),
    ]

    private static func privacyPatternMatches(in text: String) -> [PatternMatch] {
        let nsText = text as NSString
        let fullRange = NSRange(location: 0, length: nsText.length)
        var accepted: [PatternMatch] = []
        for pattern in privacyPatterns {
            let matches = pattern.regex.matches(in: text, range: fullRange)
            for match in matches {
                guard match.range.length > 0 else {
                    continue
                }
                let candidate = PatternMatch(
                    range: match.range,
                    category: pattern.category,
                    placeholder: pattern.placeholder
                )
                guard !accepted.contains(where: { rangesOverlap($0.range, candidate.range) }) else {
                    continue
                }
                accepted.append(candidate)
            }
        }
        return accepted.sorted { lhs, rhs in
            lhs.range.location < rhs.range.location
        }
    }

    private static func redactedText(for text: String, matches: [PatternMatch]) -> String {
        guard !matches.isEmpty else {
            return text
        }
        let redacted = NSMutableString(string: text)
        for match in matches.sorted(by: { $0.range.location > $1.range.location }) {
            redacted.replaceCharacters(in: match.range, with: match.placeholder)
        }
        return redacted as String
    }

    private static func rangesOverlap(_ lhs: NSRange, _ rhs: NSRange) -> Bool {
        lhs.location < rhs.location + rhs.length && rhs.location < lhs.location + lhs.length
    }
}
