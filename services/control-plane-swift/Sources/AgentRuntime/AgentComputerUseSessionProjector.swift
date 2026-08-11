import CryptoKit
import CoreFoundation
import Foundation
import MelixControlPlaneProtocol

enum AgentComputerUseSessionProjector {
    typealias Projection =
        Melix_Controlplane_V1_AgentComputerUseSessionProjection
    typealias Availability =
        Melix_Controlplane_V1_AgentComputerUseFieldAvailability

    static let projectionSchemaVersion =
        "melix.agent-computer-use-session.v1"

    private static let adapterReceiptSchemaVersion =
        "melix.computer_use_adapter_receipt.v1"
    private static let observationBindingSchemaVersion =
        "melix.computer_use_observation_binding.v1"
    private static let operatorProjectionSchemaVersion =
        "melix.computer_use_operator_projection.v1"
    private static let maximumReceiptBytes = 65_536
    private static let maximumObservationBytes = 1_048_576

    static func record(
        call: AgentToolCall,
        state: AgentToolCallState,
        current: Projection?,
        updatedAtUnixMs: Int64
    ) -> Projection? {
        guard isComputerUse(call) else {
            return current
        }
        var projection = current ?? unavailableProjection(
            updatedAtUnixMs: updatedAtUnixMs
        )
        projection.updatedAtUnixMs = updatedAtUnixMs
        switch state {
        case .requested, .waitingForApproval, .running:
            projection.lastOperation = .unavailable
            projection.lastResult = .agentComputerUseResultUnavailable
            projection.lastActionID = ""
            projection.lastCallID = ""
        case .failed:
            projection.lastOperation = .unavailable
            projection.lastResult = .agentComputerUseResultFailed
            projection.lastActionID = ""
            projection.lastCallID = ""
        case .cancelled:
            projection.lastOperation = .unavailable
            projection.lastResult = .agentComputerUseResultCancelled
            projection.lastActionID = ""
            projection.lastCallID = ""
        case .completed:
            break
        }
        return projection
    }

    static func project(
        call: AgentToolCall,
        result: AgentToolExecutionResult,
        current: Projection?,
        updatedAtUnixMs: Int64
    ) -> Projection? {
        guard isComputerUse(call) else {
            return current
        }
        var projection = current ?? unavailableProjection(
            updatedAtUnixMs: updatedAtUnixMs
        )
        guard let receipt = trustedReceipt(
            result.receiptJSON,
            callID: call.callID,
            outputJSON: result.outputJSON
        ) else {
            projection.lastOperation = .unavailable
            projection.lastResult = .agentComputerUseResultUnavailable
            projection.lastActionID = ""
            projection.lastCallID = ""
            projection.updatedAtUnixMs = updatedAtUnixMs
            return projection
        }

        let applied: Bool
        let payload = receipt.operatorProjection
        switch receipt.operation {
        case "get_permissions":
            applyPermissions(payload, to: &projection)
            applied = true
        case "open_session":
            applied = applyOpenSession(
                payload,
                receipt: receipt,
                callID: call.callID,
                to: &projection
            )
        case "capture_frame":
            applied = applyCaptureFrame(
                payload,
                receipt: receipt,
                callID: call.callID,
                to: &projection
            )
        case "press_element":
            applied = applyPressElement(
                payload,
                receipt: receipt,
                callID: call.callID,
                to: &projection
            )
        case "close_session":
            applied = applyCloseSession(
                payload,
                receipt: receipt,
                to: &projection
            )
        default:
            applied = false
        }

        guard applied else {
            projection.lastOperation = .unavailable
            projection.lastResult = .agentComputerUseResultUnavailable
            projection.lastActionID = ""
            projection.lastCallID = ""
            projection.updatedAtUnixMs = updatedAtUnixMs
            return projection
        }
        projection.lastOperation = operationState(receipt.operation)
        projection.lastResult = .agentComputerUseResultCompleted
        projection.lastActionID = receipt.actionID
        projection.lastCallID = call.callID
        projection.updatedAtUnixMs = updatedAtUnixMs
        return projection
    }

    static func trustedOperatorProjection(
        call: AgentToolCall,
        result: AgentToolExecutionResult,
        expectedOperation: String
    ) -> [String: Any]? {
        guard isComputerUse(call),
              let receipt = trustedReceipt(
                  result.receiptJSON,
                  callID: call.callID,
                  outputJSON: result.outputJSON
              ),
              receipt.operation == expectedOperation
        else {
            return nil
        }
        return receipt.operatorProjection
    }

    private static func isComputerUse(_ call: AgentToolCall) -> Bool {
        call.sourceID == "computer" && call.toolName == "computer_use"
    }

    private static func unavailableProjection(
        updatedAtUnixMs: Int64
    ) -> Projection {
        var projection = Projection()
        projection.schemaVersion = projectionSchemaVersion
        projection.sessionState = .agentComputerUseSessionUnavailable
        projection.allowedTargetsAvailability =
            .agentComputerUseFieldUnavailable
        projection.activeTarget = unavailableTarget()
        projection.frameBudget = unavailableBudget()
        projection.actionBudget = unavailableBudget()
        projection.idleDeadline = unavailableDeadline()
        projection.absoluteDeadline = unavailableDeadline()
        projection.screenRecordingPermission =
            .agentComputerUsePermissionUnavailable
        projection.accessibilityPermission =
            .agentComputerUsePermissionUnavailable
        projection.restartState = .agentComputerUseRestartUnavailable
        projection.lastOperation = .unavailable
        projection.lastResult = .agentComputerUseResultUnavailable
        projection.updatedAtUnixMs = updatedAtUnixMs
        return projection
    }

    private static func unavailableTarget()
        -> Melix_Controlplane_V1_AgentComputerUseTargetProjection {
        var target = Melix_Controlplane_V1_AgentComputerUseTargetProjection()
        target.availability = .agentComputerUseFieldUnavailable
        return target
    }

    private static func unavailableBudget()
        -> Melix_Controlplane_V1_AgentComputerUseBudgetProjection {
        var budget = Melix_Controlplane_V1_AgentComputerUseBudgetProjection()
        budget.limitAvailability = .agentComputerUseFieldUnavailable
        budget.usedAvailability = .agentComputerUseFieldUnavailable
        return budget
    }

    private static func unavailableDeadline()
        -> Melix_Controlplane_V1_AgentComputerUseDeadlineProjection {
        var deadline = Melix_Controlplane_V1_AgentComputerUseDeadlineProjection()
        deadline.availability = .agentComputerUseFieldUnavailable
        return deadline
    }

    private struct TrustedReceipt {
        let operation: String
        let sessionID: String
        let actionID: String
        let observationSHA256: String
        let operatorProjection: [String: Any]
    }

    private static func trustedReceipt(
        _ json: String,
        callID: String,
        outputJSON: String
    ) -> TrustedReceipt? {
        guard outputJSON.utf8.count <= maximumObservationBytes,
              let receipt = jsonObject(
            json,
            maximumBytes: maximumReceiptBytes
        ),
        string(receipt["schema_version"], maximumBytes: 128)
            == adapterReceiptSchemaVersion,
        string(receipt["adapter_kind"], maximumBytes: 64) == "computer",
        string(receipt["source_id"], maximumBytes: 64) == "computer",
        string(receipt["status"], maximumBytes: 64) == "completed",
        string(
            receipt["observation_binding_schema_version"],
            maximumBytes: 128
        ) == observationBindingSchemaVersion,
        let observationSHA256 = string(
            receipt["observation_sha256"],
            maximumBytes: 64,
            allowEmpty: false
        ),
        isLowercaseSHA256(observationSHA256),
        sha256(outputJSON) == observationSHA256,
        string(
            receipt["operator_projection_schema_version"],
            maximumBytes: 128
        ) == operatorProjectionSchemaVersion,
        let operatorProjection = receipt["operator_projection"]
            as? [String: Any],
        let operation = string(
            receipt["operation"],
            maximumBytes: 64,
            allowEmpty: false
        ),
        supportedReceiptOperations.contains(operation),
        string(operatorProjection["operation"], maximumBytes: 64)
            == operation
        else {
            return nil
        }

        let sessionID = string(
            receipt["session_id"],
            maximumBytes: 256,
            allowEmpty: true
        ) ?? ""
        var actionID = ""
        if operation == "press_element" {
            guard let receiptActionID = string(
                receipt["action_id"],
                maximumBytes: 256,
                allowEmpty: false
            ),
            receiptActionID == callID,
            string(receipt["terminal_phase"], maximumBytes: 64)
                == "completed"
            else {
                return nil
            }
            actionID = receiptActionID
        }
        return TrustedReceipt(
            operation: operation,
            sessionID: sessionID,
            actionID: actionID,
            observationSHA256: observationSHA256,
            operatorProjection: operatorProjection
        )
    }

    private static let supportedReceiptOperations: Set<String> = [
        "get_permissions",
        "list_targets",
        "open_session",
        "capture_frame",
        "press_element",
        "close_session",
    ]

    private static func sha256(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { byte in
            String(format: "%02x", byte)
        }.joined()
    }

    private static func isLowercaseSHA256(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy { byte in
            (48...57).contains(byte) || (97...102).contains(byte)
        }
    }

    private static func applyPermissions(
        _ payload: [String: Any],
        to projection: inout Projection
    ) {
        projection.screenRecordingPermission = permissionState(
            string(payload["screen_recording"], maximumBytes: 64)
        )
        projection.accessibilityPermission = permissionState(
            string(payload["accessibility"], maximumBytes: 64)
        )
        projection.restartState = restartState(
            screenRecording: projection.screenRecordingPermission,
            accessibility: projection.accessibilityPermission
        )
    }

    private static func applyOpenSession(
        _ payload: [String: Any],
        receipt: TrustedReceipt,
        callID: String,
        to projection: inout Projection
    ) -> Bool {
        guard let sessionID = requiredSessionID(payload),
              !receipt.sessionID.isEmpty,
              sessionID == receipt.sessionID
        else {
            return false
        }
        let isNewSession = projection.sessionID != sessionID
        if isNewSession {
            resetSessionFields(&projection)
        }
        projection.sessionID = sessionID
        projection.sessionState = .agentComputerUseSessionOpen

        if let targets = targetArray(payload["allowed_targets"]),
           targets.isEmpty == false {
            projection.allowedTargetsAvailability =
                .agentComputerUseFieldAvailable
            projection.allowedTargets = targets
        } else {
            projection.allowedTargetsAvailability =
                .agentComputerUseFieldUnavailable
            projection.allowedTargets = []
        }
        if isNewSession {
            projection.activeTarget = unavailableTarget()
        }

        projection.frameBudget = openedBudget(
            limitValue: payload["maximum_frames"],
            previous: isNewSession ? nil : projection.frameBudget
        )
        projection.actionBudget = openedBudget(
            limitValue: payload["maximum_actions"],
            previous: isNewSession ? nil : projection.actionBudget
        )
        projection.idleDeadline = deadline(
            payload["idle_deadline_unix_ms"]
        )
        projection.absoluteDeadline = deadline(
            payload["absolute_deadline_unix_ms"]
        )
        return callID.isEmpty == false
    }

    private static func applyCaptureFrame(
        _ payload: [String: Any],
        receipt: TrustedReceipt,
        callID: String,
        to projection: inout Projection
    ) -> Bool {
        guard let sessionID = requiredSessionID(payload),
              sessionID == receipt.sessionID,
              canApplyActivity(sessionID: sessionID, to: projection)
        else {
            return false
        }
        prepareActivitySession(sessionID: sessionID, projection: &projection)
        projection.activeTarget = target(payload["actual_target"])
            ?? unavailableTarget()
        if projection.lastCallID != callID {
            incrementUsage(&projection.frameBudget)
        }
        projection.idleDeadline = unavailableDeadline()
        return true
    }

    private static func applyPressElement(
        _ payload: [String: Any],
        receipt: TrustedReceipt,
        callID: String,
        to projection: inout Projection
    ) -> Bool {
        guard let sessionID = requiredSessionID(payload),
              sessionID == receipt.sessionID,
              string(payload["action_id"], maximumBytes: 256) == callID,
              string(payload["status"], maximumBytes: 64) == "completed",
              string(payload["terminal_phase"], maximumBytes: 64)
                == "completed",
              let actionResult = payload["result"] as? [String: Any],
              string(actionResult["status"], maximumBytes: 64)
                == "completed",
              canApplyActivity(sessionID: sessionID, to: projection)
        else {
            return false
        }
        prepareActivitySession(sessionID: sessionID, projection: &projection)
        projection.activeTarget = target(actionResult["actual_target"])
            ?? unavailableTarget()
        if projection.lastCallID != callID {
            incrementUsage(&projection.actionBudget)
        }
        projection.idleDeadline = unavailableDeadline()
        return true
    }

    private static func applyCloseSession(
        _ payload: [String: Any],
        receipt: TrustedReceipt,
        to projection: inout Projection
    ) -> Bool {
        guard let sessionID = requiredSessionID(payload),
              sessionID == receipt.sessionID,
              boolean(payload["closed"]) == true,
              canApplyActivity(sessionID: sessionID, to: projection)
        else {
            return false
        }
        prepareActivitySession(sessionID: sessionID, projection: &projection)
        projection.sessionState = .agentComputerUseSessionClosed
        projection.idleDeadline = unavailableDeadline()
        projection.absoluteDeadline = unavailableDeadline()
        return true
    }

    private static func resetSessionFields(_ projection: inout Projection) {
        projection.sessionID = ""
        projection.sessionState = .agentComputerUseSessionUnavailable
        projection.allowedTargetsAvailability =
            .agentComputerUseFieldUnavailable
        projection.allowedTargets = []
        projection.activeTarget = unavailableTarget()
        projection.frameBudget = unavailableBudget()
        projection.actionBudget = unavailableBudget()
        projection.idleDeadline = unavailableDeadline()
        projection.absoluteDeadline = unavailableDeadline()
    }

    private static func canApplyActivity(
        sessionID: String,
        to projection: Projection
    ) -> Bool {
        guard projection.sessionState != .agentComputerUseSessionClosed else {
            return false
        }
        return projection.sessionID.isEmpty || projection.sessionID == sessionID
    }

    private static func prepareActivitySession(
        sessionID: String,
        projection: inout Projection
    ) {
        if projection.sessionID.isEmpty {
            resetSessionFields(&projection)
            projection.sessionID = sessionID
        }
        projection.sessionState = .agentComputerUseSessionOpen
    }

    private static func openedBudget(
        limitValue: Any?,
        previous: Melix_Controlplane_V1_AgentComputerUseBudgetProjection?
    ) -> Melix_Controlplane_V1_AgentComputerUseBudgetProjection {
        guard let limit = unsignedInteger(limitValue), limit > 0 else {
            return unavailableBudget()
        }
        var budget = previous ?? unavailableBudget()
        budget.limitAvailability = .agentComputerUseFieldAvailable
        budget.limit = limit
        if budget.usedAvailability != .agentComputerUseFieldAvailable {
            budget.usedAvailability = .agentComputerUseFieldAvailable
            budget.used = 0
        }
        return budget
    }

    private static func incrementUsage(
        _ budget: inout Melix_Controlplane_V1_AgentComputerUseBudgetProjection
    ) {
        if budget.usedAvailability == .agentComputerUseFieldAvailable {
            budget.used = budget.used == UInt32.max
                ? UInt32.max
                : budget.used + 1
        } else {
            budget.usedAvailability = .agentComputerUseFieldAvailable
            budget.used = 1
        }
    }

    private static func deadline(
        _ value: Any?
    ) -> Melix_Controlplane_V1_AgentComputerUseDeadlineProjection {
        guard let unixMs = signedInteger(value), unixMs > 0 else {
            return unavailableDeadline()
        }
        var deadline = Melix_Controlplane_V1_AgentComputerUseDeadlineProjection()
        deadline.availability = .agentComputerUseFieldAvailable
        deadline.unixMs = unixMs
        return deadline
    }

    private static func targetArray(
        _ value: Any?
    ) -> [Melix_Controlplane_V1_AgentComputerUseTargetProjection]? {
        guard let values = value as? [Any], 1...16 ~= values.count else {
            return nil
        }
        let targets = values.compactMap(target)
        return targets.count == values.count ? targets : nil
    }

    private static func target(
        _ value: Any?
    ) -> Melix_Controlplane_V1_AgentComputerUseTargetProjection? {
        guard let value = value as? [String: Any],
              let bundleID = string(
                value["bundle_id"],
                maximumBytes: 256,
                allowEmpty: false
              ),
              let windowID = unsignedInteger(value["window_id"]),
              windowID > 0,
              let windowTitle = string(
                value["window_title"],
                maximumBytes: 512,
                allowEmpty: true
              )
        else {
            return nil
        }
        var target = Melix_Controlplane_V1_AgentComputerUseTargetProjection()
        target.availability = .agentComputerUseFieldAvailable
        target.bundleID = bundleID
        target.windowID = windowID
        target.windowTitle = windowTitle
        return target
    }

    private static func requiredSessionID(
        _ payload: [String: Any]
    ) -> String? {
        string(
            payload["session_id"],
            maximumBytes: 256,
            allowEmpty: false
        )
    }

    private static func permissionState(
        _ value: String?
    ) -> Melix_Controlplane_V1_AgentComputerUsePermissionState {
        switch value {
        case "not_determined":
            .agentComputerUsePermissionNotDetermined
        case "denied":
            .agentComputerUsePermissionDenied
        case "granted":
            .agentComputerUsePermissionGranted
        case "restart_required":
            .agentComputerUsePermissionRestartRequired
        case "unavailable":
            .agentComputerUsePermissionUnavailable
        default:
            .agentComputerUsePermissionUnavailable
        }
    }

    private static func restartState(
        screenRecording:
            Melix_Controlplane_V1_AgentComputerUsePermissionState,
        accessibility:
            Melix_Controlplane_V1_AgentComputerUsePermissionState
    ) -> Melix_Controlplane_V1_AgentComputerUseRestartState {
        if screenRecording == .agentComputerUsePermissionRestartRequired
            || accessibility == .agentComputerUsePermissionRestartRequired {
            return .agentComputerUseRestartRequired
        }
        let unavailable: Set<
            Melix_Controlplane_V1_AgentComputerUsePermissionState
        > = [
            .unspecified,
            .agentComputerUsePermissionUnavailable,
        ]
        guard !unavailable.contains(screenRecording),
              !unavailable.contains(accessibility)
        else {
            return .agentComputerUseRestartUnavailable
        }
        return .agentComputerUseRestartNotRequired
    }

    private static func operationState(
        _ value: String
    ) -> Melix_Controlplane_V1_AgentComputerUseOperation {
        switch value {
        case "get_permissions": .agentComputerUseGetPermissions
        case "open_session": .agentComputerUseOpenSession
        case "capture_frame": .agentComputerUseCaptureFrame
        case "press_element": .agentComputerUsePressElement
        case "close_session": .agentComputerUseCloseSession
        default: .unavailable
        }
    }

    private static func jsonObject(
        _ json: String,
        maximumBytes: Int
    ) -> [String: Any]? {
        guard !json.isEmpty,
              json.utf8.count <= maximumBytes,
              let data = json.data(using: .utf8),
              let value = try? JSONSerialization.jsonObject(with: data),
              let object = value as? [String: Any]
        else {
            return nil
        }
        return object
    }

    private static func string(
        _ value: Any?,
        maximumBytes: Int,
        allowEmpty: Bool = false
    ) -> String? {
        guard let value = value as? String,
              value.utf8.count <= maximumBytes,
              allowEmpty || !value.isEmpty
        else {
            return nil
        }
        return value
    }

    private static func unsignedInteger(_ value: Any?) -> UInt32? {
        guard let number = jsonNumber(value) else {
            return nil
        }
        let candidate = number.doubleValue
        guard candidate.isFinite,
              candidate.rounded(.towardZero) == candidate,
              candidate >= 0,
              candidate <= Double(UInt32.max)
        else {
            return nil
        }
        return UInt32(candidate)
    }

    private static func signedInteger(_ value: Any?) -> Int64? {
        guard let number = jsonNumber(value) else {
            return nil
        }
        let candidate = number.doubleValue
        guard candidate.isFinite,
              candidate.rounded(.towardZero) == candidate,
              candidate >= Double(Int64.min),
              candidate <= Double(Int64.max)
        else {
            return nil
        }
        return Int64(candidate)
    }

    private static func boolean(_ value: Any?) -> Bool? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) == CFBooleanGetTypeID()
        else {
            return nil
        }
        return number.boolValue
    }

    private static func jsonNumber(_ value: Any?) -> NSNumber? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID()
        else {
            return nil
        }
        return number
    }
}
