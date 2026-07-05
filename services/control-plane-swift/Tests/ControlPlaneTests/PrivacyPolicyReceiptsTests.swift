import Testing

@testable import MelixControlPlaneCore

struct PrivacyPolicyReceiptsTests {
    @Test("pattern privacy detector preserves statement separators after unquoted assignments")
    func patternPrivacyDetectorPreservesStatementSeparatorsAfterUnquotedAssignments() {
        let result = PatternPrivacyDetector.detect(
            textSegments: ["Use API_KEY=abc,def;ghi before sending."],
            surface: "local_proxy_text_request",
            routeScope: "chat_completions",
            policyMode: "redact"
        )

        #expect(result.redactedTexts == ["Use [REDACTED_SECRET];ghi before sending."])
        #expect(result.receipt.matchCount == 1)
        #expect(result.receipt.categories == ["secret"])
    }

    @Test("pattern privacy detector redacts uppercase standalone Hugging Face tokens")
    func patternPrivacyDetectorRedactsUppercaseStandaloneHuggingFaceTokens() {
        let result = PatternPrivacyDetector.detect(
            textSegments: ["Use token HF_ABCDEF123456."],
            surface: "local_proxy_text_request",
            routeScope: "chat_completions",
            policyMode: "redact"
        )

        #expect(result.redactedTexts == ["Use token [REDACTED_SECRET]."])
        #expect(result.receipt.matchCount == 1)
        #expect(result.receipt.categories == ["secret"])
    }

    @Test("pattern privacy detector detect mode audits matches without enforcement")
    func patternPrivacyDetectorDetectModeAuditsMatchesWithoutEnforcement() {
        let result = PatternPrivacyDetector.detect(
            textSegments: ["Email alice@example.test and use token hf_ABCDEF123456."],
            surface: "local_proxy_text_request",
            routeScope: "chat_completions",
            policyMode: "detect"
        )

        #expect(result.redactedTexts == ["Email [REDACTED_EMAIL] and use token [REDACTED_SECRET]."])
        #expect(result.receipt.policyMode == "detect")
        #expect(result.receipt.action == "detected")
        #expect(result.receipt.categories == ["email", "secret"])
        #expect(result.receipt.matchCount == 2)
        #expect(result.receipt.redactedSpanCount == 0)
        #expect(result.auditCounter.blockedCount == 0)
        #expect(result.auditCounter.redactedCount == 0)
        #expect(result.auditCounter.passedCount == 1)
    }
}
