import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public struct AccelerationReceiptValidation: Sendable, Equatable {
    public let ok: Bool
    public let receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt
    public let profileReceipt: ServingProfileAdmissionReceipt
    public let unsupportedReason: Melix_Controlplane_V1_UnsupportedCapabilityReason
    public let message: String
    public let recoveryHint: String
}

public struct ServingProfileAdmissionReceipt: Sendable, Equatable {
    public let requestedProfile: String
    public let effectiveProfile: String
    public let profileMode: String
    public let proofMatrixID: String
    public let verificationStatus: String
    public let profileAdmissionStatus: String
    public let fallbackReason: String
    public let recoveryHint: String

    public var isAdmitted: Bool {
        profileAdmissionStatus == "admitted"
    }
}

public struct ResolvedAccelerationConfig: Sendable, Equatable {
    public static let schemaVersion = "melix.resolved_acceleration_config.v1"

    public let method: String
    public let requestedMethod: String
    public let sidecarModel: String
    public let numSpeculativeTokens: UInt32
    public let profile: String
    public let conflictingFlags: [String]
    public let controllerScope: String
    public let disabledReason: String
}

public struct ServingMemoryAdmissionReceipt: Sendable, Equatable {
    public static let schemaVersion = "melix.serving_memory_admission.v1"

    public let requestedContext: UInt32
    public let effectiveContext: UInt32
    public let requestedBatch: UInt32
    public let effectiveBatch: UInt32
    public let memoryHeadroomBytes: UInt64
    public let estimatedActiveBytes: UInt64
    public let memoryTelemetrySource: String
    public let admissionReason: String
    public let fitsMemory: Bool
}

public enum ModelCapabilityReceipts {
    public static let schemaVersion = "melix.model_capability_receipt.v1"
    private static let defaultServingContextCap: UInt32 = 8_192
    private static let minimumServingContext: UInt32 = 2_048
    private static let defaultServingMemoryHeadroomBytes: UInt64 = 2_147_483_648
    private static let defaultServingBytesPerToken: UInt64 = 262_144

    public static func receipt(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ModelCapabilityReceipt {
        if model.hasCapabilityReceipt {
            return model.capabilityReceipt
        }

        var receipt = Melix_Controlplane_V1_ModelCapabilityReceipt()
        receipt.schemaVersion = schemaVersion
        receipt.tasks = taskReceipts(for: model)
        receipt.acceleration = accelerationReceipt(for: model)
        return receipt
    }

    public static func withReceipt(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ModelSummary {
        var updated = model
        var source = model
        source.clearCapabilityReceipt()
        updated.capabilityReceipt = receipt(for: source)
        return updated
    }

    public static func accelerationReceipt(
        for model: Melix_Controlplane_V1_ModelSummary,
        requestedMode: Melix_Controlplane_V1_AccelerationMode? = nil,
        draftModelID: String = ""
    ) -> Melix_Controlplane_V1_AccelerationCapabilityReceipt {
        var receipt = Melix_Controlplane_V1_AccelerationCapabilityReceipt()
        let requested = normalizedAccelerationMode(
            requestedMode ?? defaultAccelerationMode(for: model)
        )
        let supportedModes = supportedAccelerationModes(for: model)
        let draftIDs = parsedList(model.settings.ext["melix.acceleration.valid_draft_model_ids"])
        let speculativeHead = speculativeHeadReceipt(for: model)

        receipt.requestedAccelerationMode = requested
        receipt.resolvedAccelerationMode = supportedModes.contains(requested) ? requested : .baseline
        receipt.supportedModes = supportedModes
        receipt.targetCapability = targetCapability(for: model)
        receipt.drafterCapability = drafterCapability(for: model)
        receipt.validDraftModelIds = draftIDs
        receipt.speculativeHead = speculativeHead
        receipt.provenance = provenance(for: model)
        receipt.metadata = accelerationMetadata(for: model)

        switch requested {
        case .baseline:
            receipt.state = .capabilitySupported
            receipt.unsupportedReason = .unsupportedReasonNone
            receipt.resolvedAccelerationMode = .baseline
            receipt.recoveryHint = ""
        case .speculativeDecode:
            let validation = validateSpeculativeDecode(
                draftModelID: draftModelID,
                supportedModes: supportedModes,
                draftIDs: draftIDs,
                targetCapability: receipt.targetCapability,
                drafterCapability: receipt.drafterCapability,
                speculativeHead: speculativeHead
            )
            receipt.state = validation.state
            receipt.unsupportedReason = validation.unsupportedReason
            receipt.recoveryHint = validation.recoveryHint
            receipt.resolvedAccelerationMode = validation.state == .capabilitySupported
                ? .speculativeDecode
                : .baseline
            if !draftModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                receipt.draftCompatibility = [
                    draftCompatibilityReceipt(
                        draftModelID: draftModelID,
                        state: validation.state,
                        unsupportedReason: validation.unsupportedReason,
                        recoveryHint: validation.recoveryHint,
                        model: model
                    ),
                ]
            } else {
                receipt.draftCompatibility = draftIDs.map {
                    draftCompatibilityReceipt(
                        draftModelID: $0,
                        state: .capabilitySupported,
                        unsupportedReason: .unsupportedReasonNone,
                        recoveryHint: "",
                        model: model
                    )
                }
            }
        default:
            if supportedModes.contains(requested) {
                receipt.state = .capabilitySupported
                receipt.unsupportedReason = .unsupportedReasonNone
                receipt.resolvedAccelerationMode = requested
                receipt.recoveryHint = ""
            } else {
                receipt.state = .capabilityUnsupported
                receipt.unsupportedReason = .unsupportedReasonUnsupportedMode
                receipt.resolvedAccelerationMode = .baseline
                receipt.recoveryHint = "Use baseline mode or configure an explicit supported acceleration receipt for this model."
            }
        }

        return receipt
    }

    public static func validateAcceleration(
        model: Melix_Controlplane_V1_ModelSummary,
        requestedMode: Melix_Controlplane_V1_AccelerationMode,
        draftModelID: String,
        requestedProfileID: String? = nil
    ) -> AccelerationReceiptValidation {
        let receipt = accelerationReceipt(
            for: model,
            requestedMode: requestedMode,
            draftModelID: draftModelID
        )
        let profileReceipt = profileAdmissionReceipt(
            for: model,
            requestedMode: requestedMode,
            requestedProfileID: requestedProfileID
        )
        guard receipt.state == .capabilitySupported else {
            let reason = receipt.unsupportedReason == .unspecified
                ? .unsupportedReasonUnsupportedMode
                : receipt.unsupportedReason
            return AccelerationReceiptValidation(
                ok: false,
                receipt: receipt,
                profileReceipt: profileReceipt,
                unsupportedReason: reason,
                message: refusalMessage(reason: reason, receipt: receipt, draftModelID: draftModelID),
                recoveryHint: receipt.recoveryHint
            )
        }
        guard profileReceipt.isAdmitted else {
            return AccelerationReceiptValidation(
                ok: false,
                receipt: receipt,
                profileReceipt: profileReceipt,
                unsupportedReason: .unsupportedReasonExperimentalUnverified,
                message: "Serving profile \(profileReceipt.requestedProfile) requires a passing proof matrix row before optimized admission.",
                recoveryHint: profileReceipt.recoveryHint
            )
        }
        return AccelerationReceiptValidation(
            ok: true,
            receipt: receipt,
            profileReceipt: profileReceipt,
            unsupportedReason: .unsupportedReasonNone,
            message: "",
            recoveryHint: ""
        )
    }

    public static func profileAdmissionReceipt(
        for model: Melix_Controlplane_V1_ModelSummary,
        requestedMode: Melix_Controlplane_V1_AccelerationMode,
        requestedProfileID: String? = nil
    ) -> ServingProfileAdmissionReceipt {
        let normalizedProfileID = ServingAccelerationProfiles.normalizeProfileID(requestedProfileID)
            ?? ServingAccelerationProfiles.normalizeProfileID(model.settings.accelerationProfileID)
            ?? ServingAccelerationProfiles.defaultProfileID
        let profile = ServingAccelerationProfiles.profile(id: normalizedProfileID)
        let ext = model.settings.ext
        let requestedMode = normalizedAccelerationMode(requestedMode)
        let profileMode = ext["melix.acceleration.profile.profile_mode"]?.nilIfEmpty
            ?? (requestedMode == .baseline && profile.accelerationMode == .baseline ? "default" : "optimized")
        let proofMatrixID = ext["melix.acceleration.profile.proof_matrix_id"]?.nilIfEmpty ?? ""
        let explicitVerificationStatus = ext["melix.acceleration.profile.verification_status"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
            .nilIfEmpty
        let requiresProof = profileMode != "default" || requestedMode != .baseline || profile.accelerationMode != .baseline

        guard requiresProof else {
            return ServingProfileAdmissionReceipt(
                requestedProfile: normalizedProfileID,
                effectiveProfile: normalizedProfileID,
                profileMode: profileMode,
                proofMatrixID: proofMatrixID,
                verificationStatus: "not_required",
                profileAdmissionStatus: "admitted",
                fallbackReason: "",
                recoveryHint: ""
            )
        }

        let verificationStatus = explicitVerificationStatus ?? (proofMatrixID.isEmpty ? "missing" : "failed")
        guard !proofMatrixID.isEmpty, verificationStatus == "passed" else {
            let fallbackReason = verificationStatus == "missing"
                ? "experimental_unverified"
                : "verification_failed"
            return ServingProfileAdmissionReceipt(
                requestedProfile: normalizedProfileID,
                effectiveProfile: ServingAccelerationProfiles.defaultProfileID,
                profileMode: profileMode,
                proofMatrixID: proofMatrixID,
                verificationStatus: verificationStatus,
                profileAdmissionStatus: verificationStatus == "missing" ? "experimental_unverified" : "refused",
                fallbackReason: fallbackReason,
                recoveryHint: "Attach a passing proof matrix row before enabling this profile."
            )
        }

        return ServingProfileAdmissionReceipt(
            requestedProfile: normalizedProfileID,
            effectiveProfile: normalizedProfileID,
            profileMode: profileMode,
            proofMatrixID: proofMatrixID,
            verificationStatus: "passed",
            profileAdmissionStatus: "admitted",
            fallbackReason: "",
            recoveryHint: ""
        )
    }

    public static func discoveryPayload(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String: Any] {
        let receipt = receipt(for: model)
        return [
            "schema_version": receipt.schemaVersion,
            "tasks": receipt.tasks.map(taskPayload),
            "acceleration": accelerationPayload(receipt.acceleration),
        ]
    }

    public static func accelerationAuditMetadata(
        _ receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt,
        profileReceipt: ServingProfileAdmissionReceipt? = nil,
        model: Melix_Controlplane_V1_ModelSummary? = nil
    ) -> [String: String] {
        var metadata = [
            "melix.capability.receipt_schema": schemaVersion,
            "melix.acceleration.requested_acceleration_mode": accelerationModeIdentifier(receipt.requestedAccelerationMode),
            "melix.acceleration.resolved_acceleration_mode": accelerationModeIdentifier(receipt.resolvedAccelerationMode),
            "melix.acceleration.supported_modes": receipt.supportedModes.map(accelerationModeIdentifier).joined(separator: ","),
            "melix.acceleration.target_capability": receipt.targetCapability,
            "melix.acceleration.drafter_capability": receipt.drafterCapability,
            "melix.acceleration.unsupported_reason": unsupportedReasonIdentifier(receipt.unsupportedReason),
            "melix.acceleration.state": supportStateIdentifier(receipt.state),
        ]
        if !receipt.validDraftModelIds.isEmpty {
            metadata["melix.acceleration.valid_draft_model_ids"] = receipt.validDraftModelIds.joined(separator: ",")
        }
        if !receipt.recoveryHint.isEmpty {
            metadata["melix.acceleration.recovery_hint"] = receipt.recoveryHint
        }
        if let profileReceipt {
            metadata.merge(profileAdmissionAuditMetadata(profileReceipt), uniquingKeysWith: { _, newValue in newValue })
        }
        if let model {
            metadata.merge(
                servingCapabilityAuditMetadata(
                    receipt,
                    profileReceipt: profileReceipt,
                    model: model
                ),
                uniquingKeysWith: { _, newValue in newValue }
            )
        }
        return metadata
    }

    public static func servingCapabilityAuditMetadata(
        _ receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt,
        profileReceipt: ServingProfileAdmissionReceipt?,
        model: Melix_Controlplane_V1_ModelSummary
    ) -> [String: String] {
        let capabilities = servingCapabilities(for: model)
        let inputModalities = servingInputModalities(for: model)
        let outputModalities = servingOutputModalities(for: capabilities)
        let unsupportedReason = unsupportedReasonIdentifier(receipt.unsupportedReason)
        return [
            "melix.serving.capability.schema_version": "melix.serving_capability_receipt.v1",
            "melix.serving.capability.capabilities": capabilities.joined(separator: ","),
            "melix.serving.capability.input_modalities": inputModalities.joined(separator: ","),
            "melix.serving.capability.output_modalities": outputModalities.joined(separator: ","),
            "melix.serving.capability.acceleration_profile": servingCapabilityAccelerationProfile(profileReceipt),
            "melix.serving.capability.requested_mode": accelerationModeIdentifier(receipt.requestedAccelerationMode),
            "melix.serving.capability.resolved_mode": accelerationModeIdentifier(receipt.resolvedAccelerationMode),
            "melix.serving.capability.optional_dependency_source": "not_required",
            "melix.serving.capability.unsupported_reason": unsupportedReason,
            "melix.serving.capability.ignored_flags": servingCapabilityIgnoredFlags(receipt, profileReceipt: profileReceipt).joined(separator: ","),
            "melix.serving.capability.fallback_policy": servingCapabilityFallbackPolicy(receipt, profileReceipt: profileReceipt),
        ]
    }

    public static func profileAdmissionAuditMetadata(
        _ receipt: ServingProfileAdmissionReceipt
    ) -> [String: String] {
        [
            "melix.acceleration.profile.requested_profile": receipt.requestedProfile,
            "melix.acceleration.profile.effective_profile": receipt.effectiveProfile,
            "melix.acceleration.profile.profile_mode": receipt.profileMode,
            "melix.acceleration.profile.proof_matrix_id": receipt.proofMatrixID,
            "melix.acceleration.profile.verification_status": receipt.verificationStatus,
            "melix.acceleration.profile.profile_admission_status": receipt.profileAdmissionStatus,
            "melix.acceleration.profile.fallback_reason": receipt.fallbackReason,
            "melix.acceleration.profile.recovery_hint": receipt.recoveryHint,
        ]
    }

    public static func resolvedAccelerationConfig(
        for acceleration: Melix_Worker_V1_AccelerationPolicy,
        executionMetadata: [String: String],
        validation: AccelerationReceiptValidation
    ) -> ResolvedAccelerationConfig {
        let disabledReason = resolvedAccelerationDisabledReason(
            validation: validation,
            executionMetadata: executionMetadata
        )
        let conflictingFlags = resolvedAccelerationConflictingFlags(
            receipt: validation.receipt,
            profileReceipt: validation.profileReceipt,
            executionMetadata: executionMetadata
        )
        let requestedMethod = resolvedAccelerationRequestedMethod(
            receipt: validation.receipt,
            conflictingFlags: conflictingFlags
        )
        let disabled = disabledReason != "none"
        let method = disabled
            ? "baseline"
            : accelerationModeIdentifier(validation.receipt.resolvedAccelerationMode)
        let sidecarModel = method == "speculative_decode"
            ? acceleration.draftModelID.trimmingCharacters(in: .whitespacesAndNewlines)
            : ""
        let numSpeculativeTokens = method == "speculative_decode"
            ? acceleration.numDraftTokens
            : 0
        return ResolvedAccelerationConfig(
            method: method,
            requestedMethod: requestedMethod,
            sidecarModel: sidecarModel,
            numSpeculativeTokens: numSpeculativeTokens,
            profile: servingCapabilityAccelerationProfile(validation.profileReceipt),
            conflictingFlags: conflictingFlags,
            controllerScope: method == "speculative_decode" ? "request" : "none",
            disabledReason: disabledReason
        )
    }

    public static func resolvedAccelerationConfigAuditMetadata(
        _ config: ResolvedAccelerationConfig
    ) -> [String: String] {
        [
            "melix.serving.acceleration_config.schema_version": ResolvedAccelerationConfig.schemaVersion,
            "melix.serving.acceleration_config.method": config.method,
            "melix.serving.acceleration_config.requested_method": config.requestedMethod,
            "melix.serving.acceleration_config.sidecar_model": config.sidecarModel,
            "melix.serving.acceleration_config.num_speculative_tokens": String(config.numSpeculativeTokens),
            "melix.serving.acceleration_config.profile": config.profile,
            "melix.serving.acceleration_config.conflicting_flags": config.conflictingFlags.joined(separator: ","),
            "melix.serving.acceleration_config.controller_scope": config.controllerScope,
            "melix.serving.acceleration_config.disabled_reason": config.disabledReason,
        ]
    }

    public static func servingMemoryAdmissionReceipt(
        for model: Melix_Controlplane_V1_ModelSummary,
        requestedContext explicitRequestedContext: UInt32? = nil,
        requestedBatch: UInt32,
        detectedMemoryBytes: UInt64? = nil
    ) -> ServingMemoryAdmissionReceipt {
        let requestedBatch = max(requestedBatch, 1)
        let modelContext = model.maxContext > 0 ? model.maxContext : defaultServingContextCap
        let explicitContext = explicitRequestedContext.flatMap { $0 > 0 ? $0 : nil }
        let requestedContext = explicitContext ?? modelContext
        let cappedContext = min(requestedContext, defaultServingContextCap)
        var effectiveContext = explicitContext ?? cappedContext
        var effectiveBatch = requestedBatch
        let memoryTelemetrySource = detectedMemoryBytes == nil ? "unknown" : "detected"
        let memoryHeadroomBytes = detectedMemoryBytes == nil
            ? 0
            : defaultServingMemoryHeadroomBytes
        let modelResidentBytes = servingModelResidentBytes(model)
        let bytesPerToken = servingBytesPerToken(model)
        var estimatedActiveBytes = estimatedServingActiveBytes(
            modelResidentBytes: modelResidentBytes,
            context: effectiveContext,
            batch: effectiveBatch,
            bytesPerToken: bytesPerToken
        )
        var fitsMemory = true
        var admissionReason: String
        if explicitContext != nil {
            admissionReason = "explicit_override_preserved"
        } else if requestedContext > defaultServingContextCap {
            admissionReason = "default_context_cap"
        } else {
            admissionReason = "unknown_memory_safe_default"
        }

        if let detectedMemoryBytes {
            let usableMemoryBytes = detectedMemoryBytes > memoryHeadroomBytes
                ? detectedMemoryBytes - memoryHeadroomBytes
                : 0
            fitsMemory = estimatedActiveBytes <= usableMemoryBytes
            if fitsMemory, explicitContext == nil, requestedContext <= defaultServingContextCap {
                admissionReason = "detected_memory_fits"
            } else if !fitsMemory, explicitContext == nil {
                var selected: (context: UInt32, batch: UInt32, estimate: UInt64)?
                for candidate in servingMemoryFitCandidates(
                    effectiveContext: effectiveContext,
                    requestedBatch: requestedBatch
                ) {
                    let estimate = estimatedServingActiveBytes(
                        modelResidentBytes: modelResidentBytes,
                        context: candidate.context,
                        batch: candidate.batch,
                        bytesPerToken: bytesPerToken
                    )
                    if estimate <= usableMemoryBytes {
                        selected = (candidate.context, candidate.batch, estimate)
                        break
                    }
                }
                if let selected {
                    effectiveContext = selected.context
                    effectiveBatch = selected.batch
                    estimatedActiveBytes = selected.estimate
                    fitsMemory = true
                    admissionReason = "memory_step_down"
                } else {
                    let fallbackContext = min(effectiveContext, minimumServingContext)
                    effectiveContext = fallbackContext
                    effectiveBatch = 1
                    estimatedActiveBytes = estimatedServingActiveBytes(
                        modelResidentBytes: modelResidentBytes,
                        context: fallbackContext,
                        batch: 1,
                        bytesPerToken: bytesPerToken
                    )
                    fitsMemory = false
                    admissionReason = "insufficient_memory"
                }
            } else if !fitsMemory {
                admissionReason = "explicit_override_memory_warning"
            }
        }

        return ServingMemoryAdmissionReceipt(
            requestedContext: requestedContext,
            effectiveContext: effectiveContext,
            requestedBatch: requestedBatch,
            effectiveBatch: effectiveBatch,
            memoryHeadroomBytes: memoryHeadroomBytes,
            estimatedActiveBytes: estimatedActiveBytes,
            memoryTelemetrySource: memoryTelemetrySource,
            admissionReason: admissionReason,
            fitsMemory: fitsMemory
        )
    }

    public static func servingMemoryAdmissionAuditMetadata(
        _ receipt: ServingMemoryAdmissionReceipt
    ) -> [String: String] {
        [
            "melix.serving.memory_admission.schema_version": ServingMemoryAdmissionReceipt.schemaVersion,
            "melix.serving.memory_admission.requested_context": String(receipt.requestedContext),
            "melix.serving.memory_admission.effective_context": String(receipt.effectiveContext),
            "melix.serving.memory_admission.requested_batch": String(receipt.requestedBatch),
            "melix.serving.memory_admission.effective_batch": String(receipt.effectiveBatch),
            "melix.serving.memory_admission.memory_headroom_bytes": String(receipt.memoryHeadroomBytes),
            "melix.serving.memory_admission.estimated_active_bytes": String(receipt.estimatedActiveBytes),
            "melix.serving.memory_admission.memory_telemetry_source": receipt.memoryTelemetrySource,
            "melix.serving.memory_admission.admission_reason": receipt.admissionReason,
            "melix.serving.memory_admission.fits_memory": receipt.fitsMemory ? "true" : "false",
        ]
    }

    private static func resolvedAccelerationDisabledReason(
        validation: AccelerationReceiptValidation,
        executionMetadata: [String: String]
    ) -> String {
        if let disabledReason = executionMetadata["melix.gateway.speculative.disabled_reason"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .nilIfEmpty,
            disabledReason != "none" {
            return disabledReason
        }
        guard !validation.ok else {
            return "none"
        }
        if validation.receipt.state != .capabilitySupported {
            let reason = unsupportedReasonIdentifier(validation.unsupportedReason)
            return reason == "none" ? "unsupported_mode" : reason
        }
        return validation.profileReceipt.fallbackReason.nilIfEmpty
            ?? validation.profileReceipt.profileAdmissionStatus.nilIfEmpty
            ?? "experimental_unverified"
    }

    private static func resolvedAccelerationConflictingFlags(
        receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt,
        profileReceipt: ServingProfileAdmissionReceipt,
        executionMetadata: [String: String]
    ) -> [String] {
        var flags = servingCapabilityIgnoredFlags(receipt, profileReceipt: profileReceipt)
        for flag in parsedList(executionMetadata["melix.gateway.suppressed_overrides"]) {
            appendUnique(flag, to: &flags)
        }
        return flags
    }

    private static func resolvedAccelerationRequestedMethod(
        receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt,
        conflictingFlags: [String]
    ) -> String {
        if conflictingFlags.contains("speculative_decode") {
            return "speculative_decode"
        }
        return accelerationModeIdentifier(receipt.requestedAccelerationMode)
    }

    private static func appendUnique(_ value: String, to values: inout [String]) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !values.contains(trimmed) else {
            return
        }
        values.append(trimmed)
    }

    private static func servingMemoryFitCandidates(
        effectiveContext: UInt32,
        requestedBatch: UInt32
    ) -> [(context: UInt32, batch: UInt32)] {
        var candidates: [(context: UInt32, batch: UInt32)] = []
        appendServingMemoryCandidate(
            context: effectiveContext,
            batch: 1,
            to: &candidates
        )
        for context in [defaultServingContextCap / 2, minimumServingContext] {
            appendServingMemoryCandidate(context: context, batch: 1, to: &candidates)
        }
        if requestedBatch == 1 {
            return candidates.filter { $0.context < effectiveContext }
        }
        return candidates
    }

    private static func appendServingMemoryCandidate(
        context: UInt32,
        batch: UInt32,
        to candidates: inout [(context: UInt32, batch: UInt32)]
    ) {
        let context = max(context, minimumServingContext)
        let batch = max(batch, 1)
        guard !candidates.contains(where: { $0.context == context && $0.batch == batch }) else {
            return
        }
        candidates.append((context, batch))
    }

    private static func servingModelResidentBytes(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> UInt64 {
        parsedPositiveUInt64(model.settings.ext["melix.serving.memory.estimated_model_bytes"])
            ?? model.settings.memoryBudgetBytes
    }

    private static func servingBytesPerToken(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> UInt64 {
        parsedPositiveUInt64(model.settings.ext["melix.serving.memory.bytes_per_token"])
            ?? defaultServingBytesPerToken
    }

    private static func estimatedServingActiveBytes(
        modelResidentBytes: UInt64,
        context: UInt32,
        batch: UInt32,
        bytesPerToken: UInt64
    ) -> UInt64 {
        saturatedAdd(
            modelResidentBytes,
            saturatedMultiply(UInt64(context), UInt64(batch), bytesPerToken)
        )
    }

    private static func parsedPositiveUInt64(_ rawValue: String?) -> UInt64? {
        guard let rawValue = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines),
              !rawValue.isEmpty,
              let value = UInt64(rawValue),
              value > 0
        else {
            return nil
        }
        return value
    }

    private static func saturatedMultiply(_ lhs: UInt64, _ rhs: UInt64, _ extra: UInt64) -> UInt64 {
        let first = lhs.multipliedReportingOverflow(by: rhs)
        guard !first.overflow else {
            return UInt64.max
        }
        let second = first.partialValue.multipliedReportingOverflow(by: extra)
        return second.overflow ? UInt64.max : second.partialValue
    }

    private static func saturatedAdd(_ lhs: UInt64, _ rhs: UInt64) -> UInt64 {
        let result = lhs.addingReportingOverflow(rhs)
        return result.overflow ? UInt64.max : result.partialValue
    }

    private static func servingCapabilityAccelerationProfile(
        _ profileReceipt: ServingProfileAdmissionReceipt?
    ) -> String {
        guard let profileReceipt else {
            return ServingAccelerationProfiles.defaultProfileID
        }
        if profileReceipt.isAdmitted {
            return profileReceipt.effectiveProfile
        }
        return profileReceipt.requestedProfile
    }

    private static func servingCapabilityFallbackPolicy(
        _ receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt,
        profileReceipt: ServingProfileAdmissionReceipt?
    ) -> String {
        if receipt.state != .capabilitySupported {
            return "fail_closed"
        }
        if let profileReceipt, !profileReceipt.isAdmitted {
            return "fail_closed"
        }
        return "observable_fallback"
    }

    private static func servingCapabilityIgnoredFlags(
        _ receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt,
        profileReceipt: ServingProfileAdmissionReceipt?
    ) -> [String] {
        var flags: [String] = []
        switch receipt.unsupportedReason {
        case .unsupportedReasonDraftModelNotAllowed, .unsupportedReasonMissingDraftModel:
            flags.append("draft_model_id")
        case .unsupportedReasonUnsupportedMode,
             .unsupportedReasonTargetDisabled,
             .unsupportedReasonDrafterDisabled,
             .unsupportedReasonRuntimeUnavailable:
            flags.append("acceleration_mode")
        default:
            break
        }
        if receipt.state == .capabilitySupported,
           let profileReceipt,
           !profileReceipt.isAdmitted {
            flags.append("acceleration_profile")
        }
        return flags
    }

    public static func unsupportedReasonIdentifier(
        _ reason: Melix_Controlplane_V1_UnsupportedCapabilityReason
    ) -> String {
        switch reason {
        case .unsupportedReasonNone:
            return "none"
        case .unsupportedReasonUnsupportedTask:
            return "unsupported_task"
        case .unsupportedReasonUnsupportedMode:
            return "unsupported_mode"
        case .unsupportedReasonMissingDraftModel:
            return "missing_draft_model"
        case .unsupportedReasonDraftModelNotAllowed:
            return "draft_model_not_allowed"
        case .unsupportedReasonTargetDisabled:
            return "target_disabled"
        case .unsupportedReasonDrafterDisabled:
            return "drafter_disabled"
        case .unsupportedReasonMetadataInconsistent:
            return "metadata_inconsistent"
        case .unsupportedReasonRuntimeUnavailable:
            return "runtime_unavailable"
        case .unsupportedReasonExperimentalUnverified:
            // Reserved: not yet assigned by any code path; present for schema completeness.
            return "experimental_unverified"
        case .unspecified:
            return "unspecified"
        case .UNRECOGNIZED(let rawValue):
            return "unrecognized_\(rawValue)"
        }
    }

    public static func supportStateIdentifier(
        _ state: Melix_Controlplane_V1_CapabilitySupportState
    ) -> String {
        switch state {
        case .capabilitySupported:
            return "supported"
        case .capabilityUnsupported:
            return "unsupported"
        case .capabilityExperimental:
            // Reserved: not yet assigned by any code path; present for schema completeness.
            return "experimental"
        case .capabilityMetadataInconsistent:
            return "metadata_inconsistent"
        case .unspecified:
            return "unspecified"
        case .UNRECOGNIZED(let rawValue):
            return "unrecognized_\(rawValue)"
        }
    }

    public static func accelerationModeIdentifier(
        _ mode: Melix_Controlplane_V1_AccelerationMode
    ) -> String {
        switch mode {
        case .baseline:
            return "baseline"
        case .speculativeDecode:
            return "speculative_decode"
        case .acceleratedPrefill:
            return "accelerated_prefill"
        case .activeKvQuantized:
            return "active_kv_quantized"
        case .sparsePrefill:
            return "sparse_prefill"
        case .unspecified:
            return "unspecified"
        case .UNRECOGNIZED(let rawValue):
            return "unrecognized_\(rawValue)"
        }
    }

    public static func workerAccelerationMode(
        from controlPlaneMode: Melix_Controlplane_V1_AccelerationMode
    ) -> Melix_Worker_V1_AccelerationMode {
        switch controlPlaneMode {
        case .baseline:
            return .baseline
        case .speculativeDecode:
            return .speculativeDecode
        case .acceleratedPrefill:
            return .acceleratedPrefill
        case .activeKvQuantized:
            return .activeKvQuantized
        case .sparsePrefill:
            return .sparsePrefill
        case .unspecified, .UNRECOGNIZED:
            return .unspecified
        }
    }

    public static func controlPlaneAccelerationMode(
        from workerMode: Melix_Worker_V1_AccelerationMode
    ) -> Melix_Controlplane_V1_AccelerationMode {
        switch workerMode {
        case .baseline:
            return .baseline
        case .speculativeDecode:
            return .speculativeDecode
        case .acceleratedPrefill:
            return .acceleratedPrefill
        case .activeKvQuantized:
            return .activeKvQuantized
        case .sparsePrefill:
            return .sparsePrefill
        case .unspecified, .UNRECOGNIZED:
            return .unspecified
        }
    }

    private static func taskReceipts(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [Melix_Controlplane_V1_TaskCapabilityReceipt] {
        let supportedTasks = Set(model.supportedTasks.map(normalized))
        let supportedModalities = Set(model.supportedModalities.map(normalized))
        let supportedParsers = Set(parsedList(model.settings.ext["melix.capability.supported_parsers"]).map(normalized))
        let features = Set(model.features.map(normalized))
        let capabilityClass = ModelCatalogPresentation.capabilityIdentifier(for: model)

        return [
            taskReceipt(
                capability: "completion",
                supported: supportedTasks.contains("generate") || supportedTasks.contains("completion") || capabilityClass == "text" || capabilityClass == "vlm",
                provenance: "supported_tasks",
                metadata: ["source_tasks": model.supportedTasks.joined(separator: ",")]
            ),
            taskReceipt(
                capability: "embedding",
                supported: supportedTasks.contains("embed") || capabilityClass == "embedding",
                provenance: "supported_tasks",
                metadata: ["source_tasks": model.supportedTasks.joined(separator: ",")]
            ),
            taskReceipt(
                capability: "vision",
                supported: supportedModalities.contains("image") || capabilityClass == "vlm",
                provenance: "supported_modalities",
                metadata: ["source_modalities": model.supportedModalities.joined(separator: ",")]
            ),
            taskReceipt(
                capability: "tools",
                supported: supportedParsers.subtracting(["", "text"]).isEmpty == false
                    || parseBool(model.settings.ext["vision_supports_tool_calls"]) == true
                    || parseBool(model.settings.ext["melix.capability.supports_tools"]) == true,
                provenance: "parser_metadata",
                metadata: ["supported_parsers": supportedParsers.sorted().joined(separator: ",")]
            ),
            taskReceipt(
                capability: "reasoning",
                supported: !model.settings.adaptiveThinking.mode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || features.contains("adaptive_thinking")
                    || parseBool(model.settings.ext["melix.capability.supports_reasoning"]) == true,
                provenance: "model_settings",
                metadata: ["adaptive_thinking": model.settings.adaptiveThinking.mode]
            ),
            taskReceipt(
                capability: "insert",
                supported: parseBool(model.settings.ext["melix.capability.supports_insert"]) == true,
                provenance: "model_settings",
                metadata: ["supports_insert": model.settings.ext["melix.capability.supports_insert"] ?? ""]
            ),
        ]
    }

    private static func taskReceipt(
        capability: String,
        supported: Bool,
        provenance: String,
        metadata: [String: String]
    ) -> Melix_Controlplane_V1_TaskCapabilityReceipt {
        var receipt = Melix_Controlplane_V1_TaskCapabilityReceipt()
        receipt.capability = capability
        receipt.state = supported ? .capabilitySupported : .capabilityUnsupported
        receipt.unsupportedReason = supported ? .unsupportedReasonNone : .unsupportedReasonUnsupportedTask
        receipt.provenance = provenance
        receipt.recoveryHint = supported ? "" : "Choose a model whose capability receipt lists \(capability) as supported."
        receipt.metadata = metadata
        return receipt
    }

    private static func servingCapabilities(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String] {
        let supportedTasks = model.supportedTasks.map(normalizedTaskIdentifier).filter { !$0.isEmpty }
        let capabilityClass = ModelCatalogPresentation.capabilityIdentifier(for: model)
        var capabilities: [String] = []
        if supportsTask(supportedTasks, matching: ["generate", "completion", "generate_text"])
            || capabilityClass == "text"
            || capabilityClass == "vlm" {
            capabilities.append("generate_text")
        }
        if supportsTask(supportedTasks, matching: ["vlm", "generate_multimodal"])
            || capabilityClass == "vlm" {
            capabilities.append("generate_multimodal")
        }
        if supportsTask(supportedTasks, matching: ["embed", "embedding", "embed_text"]) {
            capabilities.append("embed_text")
        }
        if supportsTask(supportedTasks, matching: ["rerank", "reranking", "rerank_text"]) {
            capabilities.append("rerank_text")
        }
        if supportsTask(supportedTasks, matching: ["transcribe", "transcription", "transcribe_audio"]) {
            capabilities.append("transcribe_audio")
        }
        if supportsTask(supportedTasks, matching: ["speak", "speech", "speak_text"]) {
            capabilities.append("speak_text")
        }
        if supportsTask(supportedTasks, matching: ["image_generate", "image_generation", "generate_image"]) {
            capabilities.append("image_generate")
        }
        if supportsTask(supportedTasks, matching: ["image_edit", "edit_image"]) {
            capabilities.append("image_edit")
        }
        return capabilities
    }

    private static func supportsTask(_ taskIdentifiers: [String], matching aliases: [String]) -> Bool {
        let aliasIdentifiers = aliases.map(normalizedTaskIdentifier)
        return taskIdentifiers.contains { taskIdentifier in
            aliasIdentifiers.contains { aliasIdentifier in
                taskIdentifier == aliasIdentifier
                    || (allowsQualifiedTaskSuffix(aliasIdentifier) && taskIdentifier.hasSuffix("_\(aliasIdentifier)"))
            }
        }
    }

    private static func allowsQualifiedTaskSuffix(_ aliasIdentifier: String) -> Bool {
        aliasIdentifier.contains("_")
            || ["embedding", "reranking", "transcription", "speech"].contains(aliasIdentifier)
    }

    private static func normalizedTaskIdentifier(_ value: String?) -> String {
        var result = ""
        var lastWasSeparator = false
        for scalar in normalized(value).unicodeScalars {
            if CharacterSet.alphanumerics.contains(scalar) {
                result.append(String(scalar))
                lastWasSeparator = false
            } else if !lastWasSeparator {
                result.append("_")
                lastWasSeparator = true
            }
        }
        return result.split(separator: "_").joined(separator: "_")
    }

    private static func servingInputModalities(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String] {
        canonicalServingList(model.supportedModalities)
    }

    private static func servingOutputModalities(
        for capabilities: [String]
    ) -> [String] {
        var outputModalities: [String] = []
        if capabilities.contains("generate_text")
            || capabilities.contains("generate_multimodal")
            || capabilities.contains("embed_text")
            || capabilities.contains("rerank_text")
            || capabilities.contains("transcribe_audio") {
            outputModalities.append("text")
        }
        if capabilities.contains("speak_text") {
            outputModalities.append("audio")
        }
        if capabilities.contains("image_generate")
            || capabilities.contains("image_edit") {
            outputModalities.append("image")
        }
        return outputModalities
    }

    private static func canonicalServingList(_ values: [String]) -> [String] {
        let valueSet = Set(values.map(normalized).filter { !$0.isEmpty })
        let preferredOrder = [
            "text",
            "image",
            "video",
            "audio",
        ]
        var result = preferredOrder.filter(valueSet.contains)
        result.append(contentsOf: valueSet.subtracting(preferredOrder).sorted())
        return result
    }

    private static func supportedAccelerationModes(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [Melix_Controlplane_V1_AccelerationMode] {
        var modes: [Melix_Controlplane_V1_AccelerationMode] = [.baseline]
        for value in parsedList(model.settings.ext["melix.acceleration.supported_modes"]) {
            let mode = accelerationMode(from: value)
            if mode != .unspecified, !modes.contains(mode) {
                modes.append(mode)
            }
        }
        return modes
    }

    private static func defaultAccelerationMode(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_AccelerationMode {
        normalizedAccelerationMode(model.settings.defaultAccelerationMode)
    }

    private static func normalizedAccelerationMode(
        _ mode: Melix_Controlplane_V1_AccelerationMode
    ) -> Melix_Controlplane_V1_AccelerationMode {
        switch mode {
        case .unspecified, .UNRECOGNIZED:
            return .baseline
        default:
            return mode
        }
    }

    private static func accelerationMode(from rawValue: String) -> Melix_Controlplane_V1_AccelerationMode {
        switch normalized(rawValue) {
        case "baseline":
            return .baseline
        case "speculative_decode", "speculative-decode", "speculative":
            return .speculativeDecode
        case "accelerated_prefill", "accelerated-prefill":
            return .acceleratedPrefill
        case "active_kv_quantized", "active-kv-quantized":
            return .activeKvQuantized
        case "sparse_prefill", "sparse-prefill":
            return .sparsePrefill
        default:
            return .unspecified
        }
    }

    private static func speculativeHeadReceipt(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_SpeculativeHeadCapabilityReceipt {
        var receipt = Melix_Controlplane_V1_SpeculativeHeadCapabilityReceipt()
        let ext = model.settings.ext
        let configuredLayers = parseUInt32(ext["melix.speculative_head.configured_layers"])
        let indexedLayers = parseUInt32(ext["melix.speculative_head.indexed_layers"])
        let hasAnyMetadata = configuredLayers != nil
            || indexedLayers != nil
            || ext["melix.speculative_head.drop_flag_state"] != nil
            || ext["melix.speculative_head.runtime_available"] != nil
            || ext["melix.speculative_head.artifact_available"] != nil

        receipt.configured = parseBool(ext["melix.speculative_head.configured"]) ?? hasAnyMetadata
        receipt.configuredLayers = configuredLayers ?? 0
        receipt.indexedLayers = indexedLayers ?? 0
        receipt.dropFlagState = normalized(ext["melix.speculative_head.drop_flag_state"] ?? "absent")
        receipt.runtimeAvailable = parseBool(ext["melix.speculative_head.runtime_available"]) ?? false
        receipt.artifactAvailable = parseBool(ext["melix.speculative_head.artifact_available"]) ?? false
        receipt.provenance = hasAnyMetadata ? "model_metadata" : "not_configured"

        let dropFlagValid = ["absent", "true", "false"].contains(receipt.dropFlagState)
        let layersConsistent = receipt.configuredLayers == 0 || receipt.configuredLayers == receipt.indexedLayers
        if receipt.configured, (!dropFlagValid || !layersConsistent || parseBool(ext["melix.speculative_head.metadata_inconsistent"]) == true) {
            receipt.state = .capabilityMetadataInconsistent
            receipt.unsupportedReason = .unsupportedReasonMetadataInconsistent
            receipt.artifactAvailable = false
            receipt.runtimeAvailable = false
            receipt.recoveryHint = "Fix speculative-head metadata before enabling accelerated decode for this model."
        } else if receipt.configured, receipt.artifactAvailable, receipt.runtimeAvailable {
            receipt.state = .capabilitySupported
            receipt.unsupportedReason = .unsupportedReasonNone
        } else if receipt.configured {
            receipt.state = .capabilityUnsupported
            receipt.unsupportedReason = .unsupportedReasonRuntimeUnavailable
            receipt.recoveryHint = "Use baseline mode until speculative-head runtime artifacts are available."
        } else {
            receipt.state = .capabilityUnsupported
            receipt.unsupportedReason = .unsupportedReasonRuntimeUnavailable
            receipt.recoveryHint = ""
        }
        return receipt
    }

    private static func targetCapability(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        model.settings.ext["melix.acceleration.target_capability"]?.nilIfEmpty
            ?? (supportedAccelerationModes(for: model).contains(.speculativeDecode) ? "speculative_decode" : "baseline")
    }

    private static func drafterCapability(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        model.settings.ext["melix.acceleration.drafter_capability"]?.nilIfEmpty
            ?? (parsedList(model.settings.ext["melix.acceleration.valid_draft_model_ids"]).isEmpty ? "" : "speculative_draft")
    }

    private static func provenance(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        model.settings.ext["melix.acceleration.receipt_provenance"]?.nilIfEmpty
            ?? "model_catalog"
    }

    private static func accelerationMetadata(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String: String] {
        model.settings.ext.reduce(into: [String: String]()) { metadata, item in
            guard item.key.hasPrefix("melix.acceleration.") else {
                return
            }
            metadata[item.key] = item.value
        }
    }

    private static func validateSpeculativeDecode(
        draftModelID: String,
        supportedModes: [Melix_Controlplane_V1_AccelerationMode],
        draftIDs: [String],
        targetCapability: String,
        drafterCapability: String,
        speculativeHead: Melix_Controlplane_V1_SpeculativeHeadCapabilityReceipt
    ) -> (
        state: Melix_Controlplane_V1_CapabilitySupportState,
        unsupportedReason: Melix_Controlplane_V1_UnsupportedCapabilityReason,
        recoveryHint: String
    ) {
        guard supportedModes.contains(.speculativeDecode) else {
            return (
                .capabilityUnsupported,
                .unsupportedReasonUnsupportedMode,
                "Use baseline mode or choose a target model with speculative_decode in supported_modes."
            )
        }
        guard normalized(targetCapability) != "disabled" else {
            return (.capabilityUnsupported, .unsupportedReasonTargetDisabled, "Use baseline mode for this target model.")
        }
        guard !draftModelID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return (.capabilityUnsupported, .unsupportedReasonMissingDraftModel, "Provide a draft model ID allowed by the target receipt.")
        }
        guard draftIDs.contains(draftModelID) else {
            return (.capabilityUnsupported, .unsupportedReasonDraftModelNotAllowed, "Choose one of the target receipt's valid_draft_model_ids.")
        }
        guard normalized(drafterCapability) != "disabled" else {
            return (.capabilityUnsupported, .unsupportedReasonDrafterDisabled, "Choose a draft model whose receipt enables speculative draft capability.")
        }
        if speculativeHead.configured,
           speculativeHead.state == .capabilityMetadataInconsistent {
            return (.capabilityMetadataInconsistent, .unsupportedReasonMetadataInconsistent, speculativeHead.recoveryHint)
        }
        if speculativeHead.configured,
           speculativeHead.state == .capabilityUnsupported {
            return (speculativeHead.state, speculativeHead.unsupportedReason, speculativeHead.recoveryHint)
        }
        return (.capabilitySupported, .unsupportedReasonNone, "")
    }

    private static func draftCompatibilityReceipt(
        draftModelID: String,
        state: Melix_Controlplane_V1_CapabilitySupportState,
        unsupportedReason: Melix_Controlplane_V1_UnsupportedCapabilityReason,
        recoveryHint: String,
        model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_DraftCompatibilityReceipt {
        var receipt = Melix_Controlplane_V1_DraftCompatibilityReceipt()
        receipt.draftModelID = draftModelID
        receipt.state = state
        receipt.unsupportedReason = unsupportedReason
        receipt.provenance = provenance(for: model)
        receipt.recoveryHint = recoveryHint
        return receipt
    }

    private static func refusalMessage(
        reason: Melix_Controlplane_V1_UnsupportedCapabilityReason,
        receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt,
        draftModelID: String
    ) -> String {
        switch reason {
        case .unsupportedReasonMissingDraftModel:
            return "Speculative decode requires an explicit draft model."
        case .unsupportedReasonDraftModelNotAllowed:
            return "Draft model \(draftModelID) is not allowed for this target model."
        case .unsupportedReasonMetadataInconsistent:
            return "Speculative decode metadata is inconsistent for this target model."
        case .unsupportedReasonTargetDisabled:
            return "The target model disables the requested acceleration path."
        case .unsupportedReasonDrafterDisabled:
            return "The configured draft model disables speculative draft capability."
        case .unsupportedReasonUnsupportedMode:
            return "Acceleration mode \(accelerationModeIdentifier(receipt.requestedAccelerationMode)) is not supported for this model."
        default:
            return "Requested acceleration is not supported for this model."
        }
    }

    private static func taskPayload(_ receipt: Melix_Controlplane_V1_TaskCapabilityReceipt) -> [String: Any] {
        [
            "capability": receipt.capability,
            "state": supportStateIdentifier(receipt.state),
            "unsupported_reason": unsupportedReasonIdentifier(receipt.unsupportedReason),
            "provenance": receipt.provenance,
            "recovery_hint": receipt.recoveryHint,
            "metadata": receipt.metadata,
        ]
    }

    private static func accelerationPayload(
        _ receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt
    ) -> [String: Any] {
        [
            "requested_acceleration_mode": accelerationModeIdentifier(receipt.requestedAccelerationMode),
            "resolved_acceleration_mode": accelerationModeIdentifier(receipt.resolvedAccelerationMode),
            "supported_modes": receipt.supportedModes.map(accelerationModeIdentifier),
            "target_capability": receipt.targetCapability,
            "drafter_capability": receipt.drafterCapability,
            "valid_draft_model_ids": receipt.validDraftModelIds,
            "state": supportStateIdentifier(receipt.state),
            "unsupported_reason": unsupportedReasonIdentifier(receipt.unsupportedReason),
            "provenance": receipt.provenance,
            "recovery_hint": receipt.recoveryHint,
            "draft_compatibility": receipt.draftCompatibility.map(draftCompatibilityPayload),
            "speculative_head": speculativeHeadPayload(receipt.speculativeHead),
            "metadata": receipt.metadata,
        ]
    }

    private static func draftCompatibilityPayload(
        _ receipt: Melix_Controlplane_V1_DraftCompatibilityReceipt
    ) -> [String: Any] {
        [
            "draft_model_id": receipt.draftModelID,
            "state": supportStateIdentifier(receipt.state),
            "unsupported_reason": unsupportedReasonIdentifier(receipt.unsupportedReason),
            "provenance": receipt.provenance,
            "recovery_hint": receipt.recoveryHint,
            "metadata": receipt.metadata,
        ]
    }

    private static func speculativeHeadPayload(
        _ receipt: Melix_Controlplane_V1_SpeculativeHeadCapabilityReceipt
    ) -> [String: Any] {
        [
            "configured": receipt.configured,
            "configured_layers": NSNumber(value: receipt.configuredLayers),
            "indexed_layers": NSNumber(value: receipt.indexedLayers),
            "drop_flag_state": receipt.dropFlagState,
            "runtime_available": receipt.runtimeAvailable,
            "artifact_available": receipt.artifactAvailable,
            "state": supportStateIdentifier(receipt.state),
            "unsupported_reason": unsupportedReasonIdentifier(receipt.unsupportedReason),
            "provenance": receipt.provenance,
            "recovery_hint": receipt.recoveryHint,
        ]
    }

    private static func parsedList(_ rawValue: String?) -> [String] {
        guard let rawValue else {
            return []
        }
        return rawValue
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private static func parseBool(_ rawValue: String?) -> Bool? {
        switch normalized(rawValue) {
        case "true", "1", "yes", "enabled":
            return true
        case "false", "0", "no", "disabled":
            return false
        default:
            return nil
        }
    }

    private static func parseUInt32(_ rawValue: String?) -> UInt32? {
        guard let rawValue = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines) else {
            return nil
        }
        return UInt32(rawValue)
    }

    private static func normalized(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    }
}

private extension String {
    var nilIfEmpty: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
