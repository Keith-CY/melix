import Testing

@testable import MelixControlPlaneCore

struct PrivacyPolicyReceiptsTests {
    @Test("pattern privacy detector redacts unquoted assignment values through punctuation")
    func patternPrivacyDetectorRedactsUnquotedAssignmentValuesThroughPunctuation() {
        let result = PatternPrivacyDetector.detect(
            textSegments: ["Use API_KEY=abc,def;ghi before sending."],
            surface: "local_proxy_text_request",
            routeScope: "chat_completions",
            policyMode: "redact"
        )

        #expect(result.redactedTexts == ["Use [REDACTED_SECRET] before sending."])
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
}
