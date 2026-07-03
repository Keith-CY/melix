import MelixControlPlaneProtocol
import MelixWorkerProtocol

public extension Melix_Controlplane_V1_NativeAccelerationStatusSummary {
    static let currentSchemaVersion = "melix.native_acceleration.status.v1"

    static var unavailable: Self {
        var summary = Self()
        summary.schemaVersion = currentSchemaVersion
        summary.runtimeActive = false
        summary.status = "unavailable"
        summary.mode = ""
        summary.draftSupported = false
        summary.effectiveDepth = 0
        summary.requestGate = "not_requested"
        summary.runtimeScope = "none"
        summary.fallbackReason = "runtime_stats_unavailable"
        summary.autoregressiveFallback = true
        summary.samplingMatchesBaseline = false

        var forwardCounts = Melix_Controlplane_V1_NativeAccelerationForwardCountsSummary()
        forwardCounts.rounds = 0
        forwardCounts.acceptedTokens = 0
        forwardCounts.rejectedTokens = 0
        summary.forwardCounts = forwardCounts

        var timings = Melix_Controlplane_V1_NativeAccelerationTimingSummary()
        timings.draftProposeMs = 0
        timings.targetVerifyMs = 0
        summary.timings = timings

        var acceptanceByDepth = Melix_Controlplane_V1_NativeAccelerationAcceptanceByDepthSummary()
        acceptanceByDepth.effectiveDepth = 0
        acceptanceByDepth.acceptedTokens = 0
        acceptanceByDepth.rejectedTokens = 0
        acceptanceByDepth.acceptanceRate = 0
        acceptanceByDepth.rollbackRate = 0
        summary.acceptanceByDepth = acceptanceByDepth

        return summary
    }

    init(runtimeStats stats: Melix_Worker_V1_RuntimeStats) {
        self.init()
        schemaVersion = Self.currentSchemaVersion
        runtimeActive = stats.speculativeProbeRuntimeActive
        status = stats.speculativeProbeStatus
        mode = stats.speculativeProbeMode
        draftSupported = stats.speculativeProbeDraftSupported
        effectiveDepth = stats.speculativeProbeEffectiveDepth
        requestGate = stats.speculativeProbeRequestGate
        runtimeScope = stats.speculativeProbeRuntimeScope
        fallbackReason = stats.speculativeProbeFallbackReason
        autoregressiveFallback = stats.speculativeProbeAutoregressiveFallback
        samplingMatchesBaseline = stats.speculativeProbeSamplingMatchesBaseline

        var forwardCounts = Melix_Controlplane_V1_NativeAccelerationForwardCountsSummary()
        forwardCounts.rounds = stats.speculativeProbeRounds
        forwardCounts.acceptedTokens = stats.speculativeProbeAcceptedTokens
        forwardCounts.rejectedTokens = stats.speculativeProbeRejectedTokens
        self.forwardCounts = forwardCounts

        var timings = Melix_Controlplane_V1_NativeAccelerationTimingSummary()
        timings.draftProposeMs = stats.speculativeProbeDraftProposeMs
        timings.targetVerifyMs = stats.speculativeProbeTargetVerifyMs
        self.timings = timings

        var acceptanceByDepth = Melix_Controlplane_V1_NativeAccelerationAcceptanceByDepthSummary()
        acceptanceByDepth.effectiveDepth = stats.speculativeProbeEffectiveDepth
        acceptanceByDepth.acceptedTokens = stats.speculativeProbeAcceptedTokens
        acceptanceByDepth.rejectedTokens = stats.speculativeProbeRejectedTokens
        acceptanceByDepth.acceptanceRate = stats.speculativeProbeAcceptanceRate
        acceptanceByDepth.rollbackRate = stats.speculativeProbeRollbackRate
        self.acceptanceByDepth = acceptanceByDepth
    }
}
