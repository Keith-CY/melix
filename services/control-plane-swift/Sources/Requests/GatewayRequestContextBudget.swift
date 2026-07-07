import Foundation

struct GatewayRequestContextBudget: Sendable, Equatable {
    static let contextSource = "control_plane_prompt_budget"
    static let promptTokensEstimateSource = "control_plane_heuristic_utf8_whitespace"

    let contextLength: UInt32
    let contextWindowTokens: UInt32
    let promptTokensEstimated: UInt32
    let outputCapTokens: UInt32
    let estimateSlackTokens: UInt32

    var metadata: [String: String] {
        [
            "melix.gateway.context_length": String(contextLength),
            "melix.gateway.requested_context": String(contextLength),
            "melix.gateway.context_source": Self.contextSource,
            "melix.gateway.context_window_tokens": String(contextWindowTokens),
            "melix.gateway.output_cap_tokens": String(outputCapTokens),
            "melix.gateway.prompt_tokens_estimated": String(promptTokensEstimated),
            "melix.gateway.prompt_tokens_estimate_source": Self.promptTokensEstimateSource,
            "melix.gateway.prompt_tokens_estimate_slack": String(estimateSlackTokens),
        ]
    }

    static func derive(
        contextWindowTokens: UInt32,
        outputCapTokens: UInt32,
        promptTokensEstimated: UInt32,
        estimateSlackTokens: UInt32
    ) -> GatewayRequestContextBudget? {
        guard contextWindowTokens > 0 else {
            return nil
        }
        let requested = addingClamped(
            addingClamped(promptTokensEstimated, outputCapTokens),
            estimateSlackTokens
        )
        let clamped = min(contextWindowTokens, requested)
        let contextLength = max(UInt32(1), clamped)
        return GatewayRequestContextBudget(
            contextLength: contextLength,
            contextWindowTokens: contextWindowTokens,
            promptTokensEstimated: promptTokensEstimated,
            outputCapTokens: outputCapTokens,
            estimateSlackTokens: estimateSlackTokens
        )
    }

    private static func addingClamped(_ lhs: UInt32, _ rhs: UInt32) -> UInt32 {
        let (value, overflow) = lhs.addingReportingOverflow(rhs)
        return overflow ? UInt32.max : value
    }
}
