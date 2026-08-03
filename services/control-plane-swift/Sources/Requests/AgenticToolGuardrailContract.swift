import CryptoKit
import Foundation

public enum AgenticToolGuardrailContractError: Error, Equatable {
    case invalidConfig(String)
    case unsupportedConfigSchema(String)
    case unsupportedStateSchema(String)
    case stateRequestMismatch(configRequestID: String, stateRequestID: String)
    case invalidState(String)
    case invalidParkingConfig(String)
    case unsupportedParkingConfigSchema(String)
    case unsupportedParkingStateSchema(String)
    case invalidParkingState(String)
}

public enum AgenticToolGuardrailContract {
    public static let configSchemaVersion = "melix.agentic_tool_guardrail_config.v1"
    public static let stateSchemaVersion = "melix.agentic_tool_guardrail_state.v1"
    public static let eventSchemaVersion = "melix.agentic_tool_guardrail_event.v1"
    public static let diagnosticSchemaVersion = "melix.agentic_tool_guardrail_diagnostic.v1"
    public static let toolResultExportPolicy = "model_text_summary_ui_full"
    public static let parkingConfigSchemaVersion =
        "melix.agentic_tool_approval_parking_config.v1"
    public static let parkingStateSchemaVersion =
        "melix.agentic_tool_approval_parking_state.v1"
    public static let parkingEventSchemaVersion =
        "melix.agentic_tool_approval_parking_event.v1"
    public static let parkingDiagnosticSchemaVersion =
        "melix.agentic_tool_approval_parking_diagnostic.v1"

    public static func workerExecutionExtFields(
        config: AgenticToolGuardrailConfig,
        state: AgenticToolGuardrailState? = nil
    ) throws -> [String: String] {
        guard config.schemaVersion == configSchemaVersion else {
            throw AgenticToolGuardrailContractError.unsupportedConfigSchema(config.schemaVersion)
        }
        let normalizedRequestID = config.requestID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedRequestID.isEmpty, config.requestID == normalizedRequestID else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "request_id must be non-empty and normalized"
            )
        }
        let normalizedThreadScopeID = config.threadScopeID.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !normalizedThreadScopeID.isEmpty,
              config.threadScopeID == normalizedThreadScopeID
        else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "thread_scope_id must be non-empty and normalized"
            )
        }
        guard config.currentTurnToolStart >= 0 else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "current_turn_tool_start cannot be negative"
            )
        }
        guard config.toolResultExportPolicy == toolResultExportPolicy else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "tool_result_export_policy is unsupported"
            )
        }
        let normalizedRequiredTools = config.requiredTools.map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard config.requiredTools == normalizedRequiredTools,
              normalizedRequiredTools.allSatisfy({ !$0.isEmpty }),
              Set(normalizedRequiredTools).count == normalizedRequiredTools.count
        else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "required_tools must contain unique normalized names"
            )
        }
        guard config.prerequisites.allSatisfy({ prerequisite in
            let normalizedToolName = prerequisite.toolName.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            let normalizedRequiredToolName = prerequisite.requiredToolName.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            let normalizedArgumentMatchKeys = prerequisite.argumentMatchKeys.map {
                $0.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            return !normalizedToolName.isEmpty
                && prerequisite.toolName == normalizedToolName
                && !normalizedRequiredToolName.isEmpty
                && prerequisite.requiredToolName == normalizedRequiredToolName
                && prerequisite.argumentMatchKeys == normalizedArgumentMatchKeys
                && normalizedArgumentMatchKeys.allSatisfy({ !$0.isEmpty })
        }) else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "prerequisites must contain normalized non-empty names and match keys"
            )
        }
        guard config.maxConsecutiveMalformedResponses >= 0 else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "max_consecutive_malformed_responses cannot be negative"
            )
        }
        guard config.maxConsecutiveToolFailures >= 0 else {
            throw AgenticToolGuardrailContractError.invalidConfig(
                "max_consecutive_tool_failures cannot be negative"
            )
        }
        guard config.maxTurns > 0 else {
            throw AgenticToolGuardrailContractError.invalidConfig("max_turns must be positive")
        }
        var fields = [
            "melix.agentic_guardrail.config_schema": configSchemaVersion,
            "melix.agentic_guardrail.config_json": try canonicalJSONString(config),
        ]
        if let state {
            guard state.schemaVersion == stateSchemaVersion else {
                throw AgenticToolGuardrailContractError.unsupportedStateSchema(
                    state.schemaVersion
                )
            }
            guard state.requestID == config.requestID else {
                throw AgenticToolGuardrailContractError.stateRequestMismatch(
                    configRequestID: config.requestID,
                    stateRequestID: state.requestID
                )
            }
            try validate(state: state, config: config)
            fields["melix.agentic_guardrail.state_schema"] = stateSchemaVersion
            fields["melix.agentic_guardrail.state_json"] = try canonicalJSONString(state)
        }
        return fields
    }

    public static func approvalParkingExecutionExtFields(
        config: AgenticToolApprovalParkingConfig,
        state: AgenticToolApprovalParkingState? = nil
    ) throws -> [String: String] {
        try validate(parkingConfig: config)
        var fields = [
            "melix.agentic_guardrail.parking_config_schema": parkingConfigSchemaVersion,
            "melix.agentic_guardrail.parking_config_json": try canonicalJSONString(config),
        ]
        if let state {
            try validate(parkingState: state, config: config)
            fields["melix.agentic_guardrail.parking_state_schema"] = parkingStateSchemaVersion
            fields["melix.agentic_guardrail.parking_state_json"] = try canonicalJSONString(state)
        }
        return fields
    }

    private static func validate(
        state: AgenticToolGuardrailState,
        config: AgenticToolGuardrailConfig
    ) throws {
        guard state.threadScopeID == config.threadScopeID,
              state.currentTurnToolStart == config.currentTurnToolStart,
              state.toolResultExportPolicy == config.toolResultExportPolicy
        else {
            throw AgenticToolGuardrailContractError.invalidState(
                "state thread, turn, or export-policy boundary does not match config"
            )
        }
        let counters = [
            state.responsesSeen,
            state.healedResponseCount,
            state.admissionRejectionCount,
            state.malformedResponseCount,
            state.toolExecutionCount,
            state.toolFailureCount,
            state.replaySuppressionCount,
            state.duplicateExecutionCount,
            state.retryNudgeCount,
            state.terminalFailureCount,
            state.consecutiveMalformedResponses,
            state.consecutiveToolFailures,
            state.eventSequence,
        ]
        guard counters.allSatisfy({ $0 >= 0 }) else {
            throw AgenticToolGuardrailContractError.invalidState(
                "guardrail counters must be non-negative"
            )
        }
        guard state.responsesSeen <= config.maxTurns else {
            throw AgenticToolGuardrailContractError.invalidState(
                "responses_seen exceeds max_turns"
            )
        }
        guard state.healedResponseCount <= state.responsesSeen,
              state.malformedResponseCount <= state.responsesSeen,
              state.admissionRejectionCount <= state.malformedResponseCount
        else {
            throw AgenticToolGuardrailContractError.invalidState(
                "response counters are inconsistent"
            )
        }
        let dispatchedEntries = state.executionLedger.values.filter {
            $0.lifecycleState != "authorized"
        }
        let uncertainEntries = state.executionLedger.values.filter {
            $0.lifecycleState == "executing"
        }
        guard state.toolExecutionCount == dispatchedEntries.count,
              state.toolFailureCount <= uncertainEntries.count,
              state.duplicateExecutionCount == 0
        else {
            throw AgenticToolGuardrailContractError.invalidState(
                "execution ledger counters are inconsistent"
            )
        }
        guard state.consecutiveMalformedResponses <= state.malformedResponseCount,
              state.consecutiveToolFailures <= state.toolFailureCount,
              state.terminalFailureCount <= 1
        else {
            throw AgenticToolGuardrailContractError.invalidState(
                "failure counters are inconsistent"
            )
        }
        guard state.preflightEventEmitted == (state.eventSequence > 0),
              state.eventSequence >= state.responsesSeen
        else {
            throw AgenticToolGuardrailContractError.invalidState(
                "preflight and event sequence evidence are inconsistent"
            )
        }

        let lowercaseHex = CharacterSet(charactersIn: "0123456789abcdef")
        let ledgerLifecycleStates = Set(["authorized", "executing", "completed", "retired"])
        guard state.executionLedger.values.allSatisfy({ entry in
            entry.fingerprint.count == 64
                && entry.fingerprint.unicodeScalars.allSatisfy(lowercaseHex.contains)
                && !entry.toolName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && ledgerLifecycleStates.contains(entry.lifecycleState)
        }) else {
            throw AgenticToolGuardrailContractError.invalidState(
                "execution ledger entries are invalid"
            )
        }
        var completedIDs = Set<String>()
        for call in state.completedToolCalls {
            guard !call.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !call.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  completedIDs.insert(call.id).inserted,
                  state.executionLedger[call.id]?.toolName == call.name,
                  ["completed", "retired"].contains(
                      state.executionLedger[call.id]?.lifecycleState ?? ""
                  )
            else {
                throw AgenticToolGuardrailContractError.invalidState(
                    "completed calls must be unique and match the execution ledger"
                )
            }
        }

        let requiredLifecycleStates = Set([
            "required", "authorized", "executing", "completed", "retired",
        ])
        guard Set(state.requiredToolLifecycle.keys) == Set(config.requiredTools),
              state.requiredToolLifecycle.values.allSatisfy(requiredLifecycleStates.contains)
        else {
            throw AgenticToolGuardrailContractError.invalidState(
                "required tool lifecycle does not match config"
            )
        }
        let completedNames = Set(state.completedToolCalls.map(\.name))
        for (toolName, lifecycleState) in state.requiredToolLifecycle {
            let matchingLedgerEntries = state.executionLedger.values.filter {
                $0.toolName == toolName
            }
            if lifecycleState == "required" {
                guard matchingLedgerEntries.isEmpty, !completedNames.contains(toolName) else {
                    throw AgenticToolGuardrailContractError.invalidState(
                        "required lifecycle contains execution evidence"
                    )
                }
            } else if matchingLedgerEntries.count != 1 ||
                matchingLedgerEntries[0].lifecycleState != lifecycleState
            {
                throw AgenticToolGuardrailContractError.invalidState(
                    "required lifecycle does not uniquely match ledger evidence"
                )
            }
            if ["completed", "retired"].contains(lifecycleState),
               !completedNames.contains(toolName)
            {
                throw AgenticToolGuardrailContractError.invalidState(
                    "completed lifecycle lacks a completed call"
                )
            }
        }

        guard ["running", "completed", "failed"].contains(state.finalOutcome) else {
            throw AgenticToolGuardrailContractError.invalidState(
                "final_outcome is unsupported"
            )
        }
        if state.finalOutcome == "running" {
            guard !state.terminal,
                  state.finalFailureReason.isEmpty,
                  state.terminalFailureCount == 0
            else {
                throw AgenticToolGuardrailContractError.invalidState(
                    "running state contains terminal evidence"
                )
            }
        } else {
            guard state.terminal, !state.awaitingFinalAnswer else {
                throw AgenticToolGuardrailContractError.invalidState(
                    "terminal state is inconsistent"
                )
            }
            if state.finalOutcome == "completed" {
                guard state.finalFailureReason.isEmpty,
                      state.terminalFailureCount == 0,
                      state.responsesSeen > 0
                else {
                    throw AgenticToolGuardrailContractError.invalidState(
                        "completed state contains invalid evidence"
                    )
                }
            } else {
                guard !state.finalFailureReason.isEmpty,
                      state.terminalFailureCount == 1
                else {
                    throw AgenticToolGuardrailContractError.invalidState(
                        "failed state requires one terminal failure"
                    )
                }
            }
        }

        try validateBudgetCounter(
            state.consecutiveMalformedResponses,
            budget: config.maxConsecutiveMalformedResponses,
            exhaustedReason: "malformed_response_budget_exhausted",
            state: state
        )
        try validateBudgetCounter(
            state.consecutiveToolFailures,
            budget: config.maxConsecutiveToolFailures,
            exhaustedReason: "tool_failure_budget_exhausted",
            state: state
        )

        let requiredTools = Set(config.requiredTools)
        let requiredStepsComplete = !requiredTools.isEmpty
            && requiredTools.isSubset(of: completedNames)
        if state.finalOutcome == "completed",
           !requiredTools.isEmpty,
           !requiredStepsComplete
        {
            throw AgenticToolGuardrailContractError.invalidState(
                "completed state is missing required steps"
            )
        }
        if state.terminal, !state.preflightEventEmitted {
            throw AgenticToolGuardrailContractError.invalidState(
                "terminal state requires preflight evidence"
            )
        }
        if state.awaitingFinalAnswer,
           state.terminal || state.finalOutcome != "running" || !requiredStepsComplete
        {
            throw AgenticToolGuardrailContractError.invalidState(
                "awaiting_final_answer is inconsistent"
            )
        }
        if state.finalOutcome == "running",
           requiredStepsComplete,
           !state.awaitingFinalAnswer
        {
            throw AgenticToolGuardrailContractError.invalidState(
                "completed required steps must await a final answer"
            )
        }
        let allRequiredRetired = state.requiredToolLifecycle.values.allSatisfy {
            $0 == "retired"
        }
        if (state.awaitingFinalAnswer || state.finalOutcome == "completed"),
           !config.requiredTools.isEmpty,
           !allRequiredRetired
        {
            throw AgenticToolGuardrailContractError.invalidState(
                "final-answer state requires retired required steps"
            )
        }
    }

    private static func validateBudgetCounter(
        _ counter: Int,
        budget: Int,
        exhaustedReason: String,
        state: AgenticToolGuardrailState
    ) throws {
        let exhausted = state.finalOutcome == "failed"
            && state.finalFailureReason == exhaustedReason
        if counter > budget, !exhausted {
            throw AgenticToolGuardrailContractError.invalidState(
                "over-budget counter requires matching terminal failure"
            )
        }
        if exhausted, counter != budget + 1 {
            throw AgenticToolGuardrailContractError.invalidState(
                "budget exhaustion requires exact over-budget counter"
            )
        }
    }

    private static func validate(
        parkingConfig config: AgenticToolApprovalParkingConfig
    ) throws {
        guard config.schemaVersion == parkingConfigSchemaVersion else {
            throw AgenticToolGuardrailContractError.unsupportedParkingConfigSchema(
                config.schemaVersion
            )
        }
        guard config.totalExecutorCapacity >= 3,
              config.reservedExecutorCapacity >= 2,
              config.reservedExecutorCapacity < config.totalExecutorCapacity,
              config.maxParkedApprovalWaits > 0,
              config.maxReleasedTombstones > 0
        else {
            throw AgenticToolGuardrailContractError.invalidParkingConfig(
                "parking capacity must retain at least two executor slots"
            )
        }
    }

    private static func validate(
        parkingState state: AgenticToolApprovalParkingState,
        config: AgenticToolApprovalParkingConfig
    ) throws {
        guard state.schemaVersion == parkingStateSchemaVersion else {
            throw AgenticToolGuardrailContractError.unsupportedParkingStateSchema(
                state.schemaVersion
            )
        }
        guard state.configFingerprint == (try parkingConfigFingerprint(config)) else {
            throw AgenticToolGuardrailContractError.invalidParkingState(
                "parking state config fingerprint is inconsistent"
            )
        }
        guard state.capacityRejectionCount >= 0,
              state.releaseSuppressionCount >= 0,
              state.eventSequence >= 0,
              state.releasedRequestCount >= 0,
              state.executorLeaseAcquisitionCount >= 0,
              state.approvalParkCount >= 0
        else {
            throw AgenticToolGuardrailContractError.invalidParkingState(
                "parking counters must be non-negative"
            )
        }
        var requestIDs = Set<String>()
        var executingCount = 0
        var parkedCount = 0
        var releasedRequestIDs = Set<String>()
        var retainedAcquisitionCount = 0
        var retainedParkCount = 0
        for entry in state.entries {
            guard !entry.requestID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  requestIDs.insert(entry.requestID).inserted,
                  entry.executorLeaseAcquisitionCount > 0,
                  entry.approvalParkCount >= 0,
                  entry.approvalParkCount <= entry.executorLeaseAcquisitionCount
            else {
                throw AgenticToolGuardrailContractError.invalidParkingState(
                    "parking ledger entry counters are inconsistent"
                )
            }
            retainedAcquisitionCount += entry.executorLeaseAcquisitionCount
            retainedParkCount += entry.approvalParkCount
            switch entry.lifecycleState {
            case "executing":
                executingCount += 1
                guard entry.releaseReason.isEmpty else {
                    throw AgenticToolGuardrailContractError.invalidParkingState(
                        "active parking entry cannot have a release reason"
                    )
                }
            case "parked_for_approval":
                parkedCount += 1
                guard entry.releaseReason.isEmpty, entry.approvalParkCount > 0 else {
                    throw AgenticToolGuardrailContractError.invalidParkingState(
                        "parked entry requires parking evidence"
                    )
                }
            case "released":
                guard ["completed", "cancelled", "timed_out", "runtime_reload"]
                    .contains(entry.releaseReason)
                else {
                    throw AgenticToolGuardrailContractError.invalidParkingState(
                        "released entry requires a supported reason"
                    )
                }
                releasedRequestIDs.insert(entry.requestID)
            default:
                throw AgenticToolGuardrailContractError.invalidParkingState(
                    "parking lifecycle state is unsupported"
                )
            }
        }
        guard executingCount <= config.totalExecutorCapacity,
              parkedCount <= config.maxParkedApprovalWaits,
              state.releasedTombstoneOrder.count <= config.maxReleasedTombstones,
              Set(state.releasedTombstoneOrder) == releasedRequestIDs,
              Set(state.releasedTombstoneOrder).count == state.releasedTombstoneOrder.count,
              state.releasedRequestCount >= state.releasedTombstoneOrder.count,
              state.executorLeaseAcquisitionCount >= retainedAcquisitionCount,
              state.approvalParkCount >= retainedParkCount
        else {
            throw AgenticToolGuardrailContractError.invalidParkingState(
                "parking state exceeds configured capacity"
            )
        }
        let releaseReasons = Set(["completed", "cancelled", "timed_out", "runtime_reload"])
        guard Set(state.releaseReasonCounts.keys) == releaseReasons,
              state.releaseReasonCounts.values.allSatisfy({ $0 >= 0 }),
              state.releaseReasonCounts.values.reduce(0, +) == state.releasedRequestCount
        else {
            throw AgenticToolGuardrailContractError.invalidParkingState(
                "parking release reason counts are inconsistent"
            )
        }
    }

    private static func parkingConfigFingerprint(
        _ config: AgenticToolApprovalParkingConfig
    ) throws -> String {
        let data = try JSONEncoder.canonical.encode(config)
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func canonicalJSONString<T: Encodable>(_ value: T) throws -> String {
        String(decoding: try JSONEncoder.canonical.encode(value), as: UTF8.self)
    }
}

private extension JSONEncoder {
    static var canonical: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}

public struct AgenticToolGuardrailPrerequisite: Codable, Sendable, Equatable {
    public let toolName: String
    public let requiredToolName: String
    public let argumentMatchKeys: [String]

    enum CodingKeys: String, CodingKey {
        case toolName = "tool_name"
        case requiredToolName = "required_tool_name"
        case argumentMatchKeys = "argument_match_keys"
    }

    public init(
        toolName: String,
        requiredToolName: String,
        argumentMatchKeys: [String] = []
    ) {
        self.toolName = toolName
        self.requiredToolName = requiredToolName
        self.argumentMatchKeys = argumentMatchKeys
    }
}

public struct AgenticToolGuardrailConfig: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let requestID: String
    public let threadScopeID: String
    public let currentTurnToolStart: Int
    public let toolResultExportPolicy: String
    public let requiredTools: [String]
    public let prerequisites: [AgenticToolGuardrailPrerequisite]
    public let maxConsecutiveMalformedResponses: Int
    public let maxConsecutiveToolFailures: Int
    public let maxTurns: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case requestID = "request_id"
        case threadScopeID = "thread_scope_id"
        case currentTurnToolStart = "current_turn_tool_start"
        case toolResultExportPolicy = "tool_result_export_policy"
        case requiredTools = "required_tools"
        case prerequisites
        case maxConsecutiveMalformedResponses = "max_consecutive_malformed_responses"
        case maxConsecutiveToolFailures = "max_consecutive_tool_failures"
        case maxTurns = "max_turns"
    }

    public init(
        requestID: String,
        threadScopeID: String? = nil,
        currentTurnToolStart: Int = 0,
        toolResultExportPolicy: String = AgenticToolGuardrailContract.toolResultExportPolicy,
        requiredTools: [String] = [],
        prerequisites: [AgenticToolGuardrailPrerequisite] = [],
        maxConsecutiveMalformedResponses: Int = 2,
        maxConsecutiveToolFailures: Int = 2,
        maxTurns: Int = 12
    ) {
        self.schemaVersion = AgenticToolGuardrailContract.configSchemaVersion
        self.requestID = requestID
        self.threadScopeID = threadScopeID ?? requestID
        self.currentTurnToolStart = currentTurnToolStart
        self.toolResultExportPolicy = toolResultExportPolicy
        self.requiredTools = requiredTools
        self.prerequisites = prerequisites
        self.maxConsecutiveMalformedResponses = maxConsecutiveMalformedResponses
        self.maxConsecutiveToolFailures = maxConsecutiveToolFailures
        self.maxTurns = maxTurns
    }
}

public struct AgenticToolGuardrailCompletedCall: Codable, Sendable, Equatable {
    public let id: String
    public let name: String
    public let arguments: [String: StructuredJSONValue]
}

public struct AgenticToolGuardrailExecutionLedgerEntry: Codable, Sendable, Equatable {
    public let fingerprint: String
    public let toolName: String
    public let lifecycleState: String

    enum CodingKeys: String, CodingKey {
        case fingerprint
        case toolName = "tool_name"
        case lifecycleState = "lifecycle_state"
    }
}

public struct AgenticToolGuardrailState: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let requestID: String
    public let threadScopeID: String
    public let currentTurnToolStart: Int
    public let toolResultExportPolicy: String
    public let completedToolCalls: [AgenticToolGuardrailCompletedCall]
    public let executionLedger: [String: AgenticToolGuardrailExecutionLedgerEntry]
    public let requiredToolLifecycle: [String: String]
    public let responsesSeen: Int
    public let healedResponseCount: Int
    public let admissionRejectionCount: Int
    public let malformedResponseCount: Int
    public let toolExecutionCount: Int
    public let toolFailureCount: Int
    public let replaySuppressionCount: Int
    public let duplicateExecutionCount: Int
    public let retryNudgeCount: Int
    public let terminalFailureCount: Int
    public let consecutiveMalformedResponses: Int
    public let consecutiveToolFailures: Int
    public let lastNudgeType: String
    public let finalOutcome: String
    public let finalFailureReason: String
    public let terminal: Bool
    public let awaitingFinalAnswer: Bool
    public let preflightEventEmitted: Bool
    public let eventSequence: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case requestID = "request_id"
        case threadScopeID = "thread_scope_id"
        case currentTurnToolStart = "current_turn_tool_start"
        case toolResultExportPolicy = "tool_result_export_policy"
        case completedToolCalls = "completed_tool_calls"
        case executionLedger = "execution_ledger"
        case requiredToolLifecycle = "required_tool_lifecycle"
        case responsesSeen = "responses_seen"
        case healedResponseCount = "healed_response_count"
        case admissionRejectionCount = "admission_rejection_count"
        case malformedResponseCount = "malformed_response_count"
        case toolExecutionCount = "tool_execution_count"
        case toolFailureCount = "tool_failure_count"
        case replaySuppressionCount = "replay_suppression_count"
        case duplicateExecutionCount = "duplicate_execution_count"
        case retryNudgeCount = "retry_nudge_count"
        case terminalFailureCount = "terminal_failure_count"
        case consecutiveMalformedResponses = "consecutive_malformed_responses"
        case consecutiveToolFailures = "consecutive_tool_failures"
        case lastNudgeType = "last_nudge_type"
        case finalOutcome = "final_outcome"
        case finalFailureReason = "final_failure_reason"
        case terminal
        case awaitingFinalAnswer = "awaiting_final_answer"
        case preflightEventEmitted = "preflight_event_emitted"
        case eventSequence = "event_sequence"
    }
}

public struct AgenticToolGuardrailEvent: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sequence: Int
    public let eventType: String
    public let outcome: String
    public let nudgeType: String
    public let failureReason: String
    public let toolCallID: String
    public let toolName: String
    public let consecutiveMalformedResponses: Int
    public let consecutiveToolFailures: Int
    public let threadScopeID: String
    public let currentTurnToolStart: Int
    public let toolResultExportPolicy: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sequence
        case eventType = "event_type"
        case outcome
        case nudgeType = "nudge_type"
        case failureReason = "failure_reason"
        case toolCallID = "tool_call_id"
        case toolName = "tool_name"
        case consecutiveMalformedResponses = "consecutive_malformed_responses"
        case consecutiveToolFailures = "consecutive_tool_failures"
        case threadScopeID = "thread_scope_id"
        case currentTurnToolStart = "current_turn_tool_start"
        case toolResultExportPolicy = "tool_result_export_policy"
    }
}

public struct AgenticToolGuardrailDiagnostic: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let requestID: String
    public let responsesSeen: Int
    public let healedResponseCount: Int
    public let admissionRejectionCount: Int
    public let malformedResponseCount: Int
    public let toolExecutionCount: Int
    public let toolFailureCount: Int
    public let replaySuppressionCount: Int
    public let duplicateExecutionCount: Int
    public let retryNudgeCount: Int
    public let terminalFailureCount: Int
    public let consecutiveMalformedResponses: Int
    public let consecutiveToolFailures: Int
    public let lastNudgeType: String
    public let finalOutcome: String
    public let finalFailureReason: String
    public let completedRequiredTools: [String]
    public let threadScopeID: String
    public let currentTurnToolStart: Int
    public let toolResultExportPolicy: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case requestID = "request_id"
        case responsesSeen = "responses_seen"
        case healedResponseCount = "healed_response_count"
        case admissionRejectionCount = "admission_rejection_count"
        case malformedResponseCount = "malformed_response_count"
        case toolExecutionCount = "tool_execution_count"
        case toolFailureCount = "tool_failure_count"
        case replaySuppressionCount = "replay_suppression_count"
        case duplicateExecutionCount = "duplicate_execution_count"
        case retryNudgeCount = "retry_nudge_count"
        case terminalFailureCount = "terminal_failure_count"
        case consecutiveMalformedResponses = "consecutive_malformed_responses"
        case consecutiveToolFailures = "consecutive_tool_failures"
        case lastNudgeType = "last_nudge_type"
        case finalOutcome = "final_outcome"
        case finalFailureReason = "final_failure_reason"
        case completedRequiredTools = "completed_required_tools"
        case threadScopeID = "thread_scope_id"
        case currentTurnToolStart = "current_turn_tool_start"
        case toolResultExportPolicy = "tool_result_export_policy"
    }
}

public struct AgenticToolApprovalParkingConfig: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let totalExecutorCapacity: Int
    public let reservedExecutorCapacity: Int
    public let maxParkedApprovalWaits: Int
    public let maxReleasedTombstones: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case totalExecutorCapacity = "total_executor_capacity"
        case reservedExecutorCapacity = "reserved_executor_capacity"
        case maxParkedApprovalWaits = "max_parked_approval_waits"
        case maxReleasedTombstones = "max_released_tombstones"
    }

    public init(
        totalExecutorCapacity: Int,
        reservedExecutorCapacity: Int = 2,
        maxParkedApprovalWaits: Int = 100,
        maxReleasedTombstones: Int = 1_000
    ) {
        self.schemaVersion = AgenticToolGuardrailContract.parkingConfigSchemaVersion
        self.totalExecutorCapacity = totalExecutorCapacity
        self.reservedExecutorCapacity = reservedExecutorCapacity
        self.maxParkedApprovalWaits = maxParkedApprovalWaits
        self.maxReleasedTombstones = maxReleasedTombstones
    }
}

public struct AgenticToolApprovalParkingLedgerEntry: Codable, Sendable, Equatable {
    public let requestID: String
    public let lifecycleState: String
    public let releaseReason: String
    public let executorLeaseAcquisitionCount: Int
    public let approvalParkCount: Int

    enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case lifecycleState = "lifecycle_state"
        case releaseReason = "release_reason"
        case executorLeaseAcquisitionCount = "executor_lease_acquisition_count"
        case approvalParkCount = "approval_park_count"
    }
}

public struct AgenticToolApprovalParkingState: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let configFingerprint: String
    public let entries: [AgenticToolApprovalParkingLedgerEntry]
    public let releasedTombstoneOrder: [String]
    public let releaseReasonCounts: [String: Int]
    public let capacityRejectionCount: Int
    public let releaseSuppressionCount: Int
    public let eventSequence: Int
    public let releasedRequestCount: Int
    public let executorLeaseAcquisitionCount: Int
    public let approvalParkCount: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case configFingerprint = "config_fingerprint"
        case entries
        case releasedTombstoneOrder = "released_tombstone_order"
        case releaseReasonCounts = "release_reason_counts"
        case capacityRejectionCount = "capacity_rejection_count"
        case releaseSuppressionCount = "release_suppression_count"
        case eventSequence = "event_sequence"
        case releasedRequestCount = "released_request_count"
        case executorLeaseAcquisitionCount = "executor_lease_acquisition_count"
        case approvalParkCount = "approval_park_count"
    }
}

public struct AgenticToolApprovalParkingEvent: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sequence: Int
    public let eventType: String
    public let outcome: String
    public let requestID: String
    public let lifecycleState: String
    public let releaseReason: String
    public let failureReason: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sequence
        case eventType = "event_type"
        case outcome
        case requestID = "request_id"
        case lifecycleState = "lifecycle_state"
        case releaseReason = "release_reason"
        case failureReason = "failure_reason"
    }
}

public struct AgenticToolApprovalParkingDiagnostic: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let totalExecutorCapacity: Int
    public let reservedExecutorCapacity: Int
    public let executorLeasesUsed: Int
    public let executorCapacityAvailable: Int
    public let executorResumeCapacityAvailable: Int
    public let maxParkedApprovalWaits: Int
    public let parkingPermitsUsed: Int
    public let parkingPermitsAvailable: Int
    public let executingRequestCount: Int
    public let parkedRequestCount: Int
    public let releasedRequestCount: Int
    public let maxReleasedTombstones: Int
    public let retainedReleasedTombstoneCount: Int
    public let executorLeaseAcquisitionCount: Int
    public let approvalParkCount: Int
    public let capacityRejectionCount: Int
    public let releaseSuppressionCount: Int
    public let releaseReasonCounts: [String: Int]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case totalExecutorCapacity = "total_executor_capacity"
        case reservedExecutorCapacity = "reserved_executor_capacity"
        case executorLeasesUsed = "executor_leases_used"
        case executorCapacityAvailable = "executor_capacity_available"
        case executorResumeCapacityAvailable = "executor_resume_capacity_available"
        case maxParkedApprovalWaits = "max_parked_approval_waits"
        case parkingPermitsUsed = "parking_permits_used"
        case parkingPermitsAvailable = "parking_permits_available"
        case executingRequestCount = "executing_request_count"
        case parkedRequestCount = "parked_request_count"
        case releasedRequestCount = "released_request_count"
        case maxReleasedTombstones = "max_released_tombstones"
        case retainedReleasedTombstoneCount = "retained_released_tombstone_count"
        case executorLeaseAcquisitionCount = "executor_lease_acquisition_count"
        case approvalParkCount = "approval_park_count"
        case capacityRejectionCount = "capacity_rejection_count"
        case releaseSuppressionCount = "release_suppression_count"
        case releaseReasonCounts = "release_reason_counts"
    }
}
