import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public struct AccelerationReceiptValidation: Sendable, Equatable {
    public let ok: Bool
    public let receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt
    public let unsupportedReason: Melix_Controlplane_V1_UnsupportedCapabilityReason
    public let message: String
    public let recoveryHint: String
}

public enum ModelCapabilityReceipts {
    public static let schemaVersion = "melix.model_capability_receipt.v1"

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
        draftModelID: String
    ) -> AccelerationReceiptValidation {
        let receipt = accelerationReceipt(
            for: model,
            requestedMode: requestedMode,
            draftModelID: draftModelID
        )
        guard receipt.state == .capabilitySupported else {
            let reason = receipt.unsupportedReason == .unspecified
                ? .unsupportedReasonUnsupportedMode
                : receipt.unsupportedReason
            return AccelerationReceiptValidation(
                ok: false,
                receipt: receipt,
                unsupportedReason: reason,
                message: refusalMessage(reason: reason, receipt: receipt, draftModelID: draftModelID),
                recoveryHint: receipt.recoveryHint
            )
        }
        return AccelerationReceiptValidation(
            ok: true,
            receipt: receipt,
            unsupportedReason: .unsupportedReasonNone,
            message: "",
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
        _ receipt: Melix_Controlplane_V1_AccelerationCapabilityReceipt
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
        return metadata
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
