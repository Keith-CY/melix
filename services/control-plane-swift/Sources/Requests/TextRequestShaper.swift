import Foundation

public struct TextRequestShaper: Sendable {
    private struct PresetDefaults: Sendable {
        let temperature: Double?
        let topP: Double?
        let maxTokens: UInt32?
        let saveBoundarySnapshot: Bool?
        let cachePolicy: String?
    }

    private struct WorkflowDefaults: Sendable {
        let lane: String
        let priority: Int32
        let latencySensitive: Bool
        let latencyClass: String
        let admissionPolicy: String
        let cachePolicy: String?
        let saveBoundarySnapshot: Bool?
    }

    private let presets: [String: PresetDefaults]
    private let workflows: [TextWorkflowKind: WorkflowDefaults]

    public init(
        presets: [String: (temperature: Double?, topP: Double?, maxTokens: UInt32?, saveBoundarySnapshot: Bool?, cachePolicy: String?)] = [
            "deep_reasoning": (0.2, 0.95, 512, true, "reasoning-deep"),
            "concise": (0.4, 1.0, 128, nil, nil),
        ],
        workflows: [TextWorkflowKind: (lane: String, priority: Int32, latencySensitive: Bool, latencyClass: String, admissionPolicy: String, cachePolicy: String?, saveBoundarySnapshot: Bool?)] = [
            .interactive: (
                lane: "text.decode.interactive",
                priority: 100,
                latencySensitive: true,
                latencyClass: "interactive",
                admissionPolicy: "workflow.interactive",
                cachePolicy: nil,
                saveBoundarySnapshot: nil
            ),
            .toolFollowup: (
                lane: "text.prefill.hot",
                priority: 120,
                latencySensitive: true,
                latencyClass: "interactive",
                admissionPolicy: "workflow.tool_followup",
                cachePolicy: "session-hot",
                saveBoundarySnapshot: true
            ),
            .backgroundAnalysis: (
                lane: "text.prefill.background",
                priority: 40,
                latencySensitive: false,
                latencyClass: "background",
                admissionPolicy: "workflow.background_analysis",
                cachePolicy: "background-prefill",
                saveBoundarySnapshot: false
            ),
        ]
    ) {
        self.presets = presets.mapValues { value in
            PresetDefaults(
                temperature: value.temperature,
                topP: value.topP,
                maxTokens: value.maxTokens,
                saveBoundarySnapshot: value.saveBoundarySnapshot,
                cachePolicy: value.cachePolicy
            )
        }
        self.workflows = workflows.mapValues { value in
            WorkflowDefaults(
                lane: value.lane,
                priority: value.priority,
                latencySensitive: value.latencySensitive,
                latencyClass: value.latencyClass,
                admissionPolicy: value.admissionPolicy,
                cachePolicy: value.cachePolicy,
                saveBoundarySnapshot: value.saveBoundarySnapshot
            )
        }
    }

    public func shape(_ request: NormalizedTextRequest) -> ShapedTextRequest {
        let preset = request.presetID.flatMap { presets[$0] }
        let workflowKind = request.workflow ?? .interactive
        let workflow = workflows[workflowKind] ?? workflows[.interactive]!
        let resolvedSessionID = request.sessionID?.nilIfEmpty
        let resolvedBranchID = request.branchID?.nilIfEmpty ?? (resolvedSessionID == nil ? nil : "branch-main")

        let temperature = request.temperature
            ?? preset?.temperature
            ?? 0.7
        let topP = request.topP
            ?? preset?.topP
            ?? 1.0
        let maxTokens = request.maxTokens
            ?? preset?.maxTokens
            ?? 256
        let saveBoundarySnapshot = request.saveBoundarySnapshot
            ?? preset?.saveBoundarySnapshot
            ?? workflow.saveBoundarySnapshot
            ?? (resolvedSessionID != nil)
        let cachePolicy = workflow.cachePolicy
            ?? preset?.cachePolicy
            ?? (resolvedSessionID == nil ? nil : "session-reuse")

        return ShapedTextRequest(
            endpoint: request.endpoint,
            model: request.model,
            messages: request.messages,
            stream: request.stream,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            sessionID: resolvedSessionID,
            branchID: resolvedBranchID,
            parentRequestID: request.parentRequestID?.nilIfEmpty,
            restoreSnapshotID: request.restoreSnapshotID?.nilIfEmpty,
            saveBoundarySnapshot: saveBoundarySnapshot,
            presetID: request.presetID?.nilIfEmpty,
            workflow: request.workflow,
            workflowRunID: request.workflowRunID?.nilIfEmpty,
            workflowNodeID: request.workflowNodeID?.nilIfEmpty,
            latencyClass: workflow.latencyClass,
            lane: workflow.lane,
            priority: workflow.priority,
            latencySensitive: workflow.latencySensitive,
            admissionPolicy: workflow.admissionPolicy,
            cachePolicy: cachePolicy
        )
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
