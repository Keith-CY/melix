import Foundation
import Testing
@testable import MelixControlPlaneCore

@Suite("Agentic tool guardrail contract")
struct AgenticToolGuardrailContractTests {
    @Test("config metadata uses the worker schema and canonical JSON")
    func configMetadataUsesWorkerSchemaAndCanonicalJSON() throws {
        let config = AgenticToolGuardrailConfig(
            requestID: "request-1",
            requiredTools: ["text_search", "image_search"],
            prerequisites: [
                AgenticToolGuardrailPrerequisite(
                    toolName: "image_search",
                    requiredToolName: "text_search",
                    argumentMatchKeys: ["query"]
                ),
            ],
            maxConsecutiveMalformedResponses: 3,
            maxConsecutiveToolFailures: 4,
            maxTurns: 9
        )

        let fields = try AgenticToolGuardrailContract.workerExecutionExtFields(config: config)
        let configJSON = try #require(fields["melix.agentic_guardrail.config_json"])

        #expect(fields["melix.agentic_guardrail.config_schema"] == "melix.agentic_tool_guardrail_config.v1")
        #expect(fields["melix.agentic_guardrail.state_json"] == nil)
        #expect(
            configJSON ==
                #"{"max_consecutive_malformed_responses":3,"max_consecutive_tool_failures":4,"max_turns":9,"prerequisites":[{"argument_match_keys":["query"],"required_tool_name":"text_search","tool_name":"image_search"}],"request_id":"request-1","required_tools":["text_search","image_search"],"schema_version":"melix.agentic_tool_guardrail_config.v1"}"#
        )
    }

    @Test("Python-shaped state survives decoding and metadata shaping")
    func pythonShapedStateSurvivesDecodingAndMetadataShaping() throws {
        let state = try JSONDecoder().decode(
            AgenticToolGuardrailState.self,
            from: Data(Self.stateJSON.utf8)
        )
        let config = AgenticToolGuardrailConfig(requestID: "request-1")
        let fields = try AgenticToolGuardrailContract.workerExecutionExtFields(
            config: config,
            state: state
        )
        let stateJSON = try #require(fields["melix.agentic_guardrail.state_json"])
        let roundTripped = try JSONDecoder().decode(
            AgenticToolGuardrailState.self,
            from: Data(stateJSON.utf8)
        )

        #expect(fields["melix.agentic_guardrail.state_schema"] == "melix.agentic_tool_guardrail_state.v1")
        #expect(roundTripped == state)
        #expect(roundTripped.completedToolCalls[0].arguments["query"] == .string("PRIVATE_QUERY"))
        #expect(
            roundTripped.executionLedger["text-1"]?.fingerprint ==
                "aa8c52f9b423fa8934f054c9044fd18dde6c781f659732ec3aa823449e007d33"
        )
        #expect(roundTripped.executionLedger["text-1"]?.lifecycleState == "completed")
        #expect(roundTripped.requiredToolLifecycle.isEmpty)
        #expect(roundTripped.awaitingFinalAnswer == false)
        #expect(roundTripped.preflightEventEmitted)
    }

    @Test("required tools expose an explicit retired lifecycle before final answer")
    func requiredToolsExposeExplicitRetiredLifecycle() throws {
        let payload = Self.stateJSON
            .replacingOccurrences(
                of: #""lifecycle_state":"completed""#,
                with: #""lifecycle_state":"retired""#
            )
            .replacingOccurrences(
                of: #""required_tool_lifecycle": {}"#,
                with: #""required_tool_lifecycle": {"text_search":"retired"}"#
            )
            .replacingOccurrences(
                of: #""awaiting_final_answer": false"#,
                with: #""awaiting_final_answer": true"#
            )
        let state = try JSONDecoder().decode(
            AgenticToolGuardrailState.self,
            from: Data(payload.utf8)
        )

        let fields = try AgenticToolGuardrailContract.workerExecutionExtFields(
            config: AgenticToolGuardrailConfig(
                requestID: "request-1",
                requiredTools: ["text_search"]
            ),
            state: state
        )

        #expect(state.requiredToolLifecycle == ["text_search": "retired"])
        #expect(state.executionLedger["text-1"]?.lifecycleState == "retired")
        #expect(fields["melix.agentic_guardrail.state_json"] != nil)
    }

    @Test("event and diagnostic payloads decode without carrying arguments")
    func eventAndDiagnosticPayloadsDecodeWithoutCarryingArguments() throws {
        let event = try JSONDecoder().decode(
            AgenticToolGuardrailEvent.self,
            from: Data(Self.eventJSON.utf8)
        )
        let diagnostic = try JSONDecoder().decode(
            AgenticToolGuardrailDiagnostic.self,
            from: Data(Self.diagnosticJSON.utf8)
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let emitted = String(decoding: try encoder.encode([diagnostic]), as: UTF8.self)

        #expect(event.schemaVersion == AgenticToolGuardrailContract.eventSchemaVersion)
        #expect(event.eventType == "retry_nudge")
        #expect(event.nudgeType == "tool_prerequisite_violation")
        #expect(event.consecutiveMalformedResponses == 1)
        #expect(diagnostic.schemaVersion == AgenticToolGuardrailContract.diagnosticSchemaVersion)
        #expect(diagnostic.lastNudgeType == "tool_prerequisite_violation")
        #expect(diagnostic.completedRequiredTools == ["text_search"])
        #expect(emitted.contains("PRIVATE_QUERY") == false)
        #expect(emitted.contains("arguments") == false)
    }

    @Test("metadata shaping rejects invalid config and mismatched restore state")
    func metadataShapingRejectsInvalidConfigAndMismatchedRestoreState() throws {
        let invalidConfigs = [
            AgenticToolGuardrailConfig(requestID: " "),
            AgenticToolGuardrailConfig(
                requestID: "request-1",
                maxConsecutiveMalformedResponses: -1
            ),
            AgenticToolGuardrailConfig(
                requestID: "request-1",
                maxConsecutiveToolFailures: -1
            ),
            AgenticToolGuardrailConfig(requestID: "request-1", maxTurns: 0),
        ]
        for config in invalidConfigs {
            #expect(throws: AgenticToolGuardrailContractError.self) {
                try AgenticToolGuardrailContract.workerExecutionExtFields(config: config)
            }
        }

        let futureConfig = try JSONDecoder().decode(
            AgenticToolGuardrailConfig.self,
            from: Data(
                #"{"schema_version":"future","request_id":"request-1","required_tools":[],"prerequisites":[],"max_consecutive_malformed_responses":2,"max_consecutive_tool_failures":2,"max_turns":12}"#.utf8
            )
        )
        #expect(throws: AgenticToolGuardrailContractError.unsupportedConfigSchema("future")) {
            try AgenticToolGuardrailContract.workerExecutionExtFields(config: futureConfig)
        }

        let state = try JSONDecoder().decode(
            AgenticToolGuardrailState.self,
            from: Data(Self.stateJSON.utf8)
        )
        #expect(
            throws: AgenticToolGuardrailContractError.stateRequestMismatch(
                configRequestID: "another-request",
                stateRequestID: "request-1"
            )
        ) {
            try AgenticToolGuardrailContract.workerExecutionExtFields(
                config: AgenticToolGuardrailConfig(requestID: "another-request"),
                state: state
            )
        }

        let futureState = try JSONDecoder().decode(
            AgenticToolGuardrailState.self,
            from: Data(Self.stateJSON.replacingOccurrences(
                of: "melix.agentic_tool_guardrail_state.v1",
                with: "future"
            ).utf8)
        )
        #expect(throws: AgenticToolGuardrailContractError.unsupportedStateSchema("future")) {
            try AgenticToolGuardrailContract.workerExecutionExtFields(
                config: AgenticToolGuardrailConfig(requestID: "request-1"),
                state: futureState
            )
        }
    }

    @Test("metadata shaping rejects inconsistent restored state")
    func metadataShapingRejectsInconsistentRestoredState() throws {
        let invalidStatePayloads = [
            Self.stateJSON.replacingOccurrences(
                of: "aa8c52f9b423fa8934f054c9044fd18dde6c781f659732ec3aa823449e007d33",
                with: "not-a-fingerprint"
            ),
            Self.stateJSON.replacingOccurrences(
                of: #""tool_execution_count": 1"#,
                with: #""tool_execution_count": 2"#
            ),
            Self.stateJSON.replacingOccurrences(
                of: #""final_outcome": "running""#,
                with: #""final_outcome": "completed""#
            ),
            Self.stateJSON.replacingOccurrences(
                of: #""lifecycle_state":"completed""#,
                with: #""lifecycle_state":"future""#
            ),
        ]

        for payload in invalidStatePayloads {
            let state = try JSONDecoder().decode(
                AgenticToolGuardrailState.self,
                from: Data(payload.utf8)
            )
            #expect(throws: AgenticToolGuardrailContractError.self) {
                try AgenticToolGuardrailContract.workerExecutionExtFields(
                    config: AgenticToolGuardrailConfig(requestID: "request-1"),
                    state: state
                )
            }
        }
    }

    @Test("parking config and Python state share the v1 fingerprint contract")
    func parkingConfigAndPythonStateShareFingerprintContract() throws {
        let config = AgenticToolApprovalParkingConfig(totalExecutorCapacity: 4)
        let state = try JSONDecoder().decode(
            AgenticToolApprovalParkingState.self,
            from: Data(Self.parkingStateJSON.utf8)
        )

        let fields = try AgenticToolGuardrailContract.approvalParkingExecutionExtFields(
            config: config,
            state: state
        )
        let stateJSON = try #require(
            fields["melix.agentic_guardrail.parking_state_json"]
        )
        let roundTripped = try JSONDecoder().decode(
            AgenticToolApprovalParkingState.self,
            from: Data(stateJSON.utf8)
        )

        #expect(
            fields["melix.agentic_guardrail.parking_config_schema"] ==
                AgenticToolGuardrailContract.parkingConfigSchemaVersion
        )
        #expect(roundTripped == state)
        #expect(roundTripped.entries[0].lifecycleState == "parked_for_approval")
        #expect(roundTripped.entries[1].releaseReason == "cancelled")
        #expect(roundTripped.releasedTombstoneOrder == ["request-cancelled"])
        #expect(roundTripped.releasedRequestCount == 1)
    }

    @Test("parking events and diagnostics decode without prompt or arguments")
    func parkingEventsAndDiagnosticsDecodeWithoutPromptOrArguments() throws {
        let event = try JSONDecoder().decode(
            AgenticToolApprovalParkingEvent.self,
            from: Data(Self.parkingEventJSON.utf8)
        )
        let diagnostic = try JSONDecoder().decode(
            AgenticToolApprovalParkingDiagnostic.self,
            from: Data(Self.parkingDiagnosticJSON.utf8)
        )
        let emitted = String(
            decoding: try JSONEncoder().encode([event, event]),
            as: UTF8.self
        )

        #expect(event.schemaVersion == AgenticToolGuardrailContract.parkingEventSchemaVersion)
        #expect(event.eventType == "approval_wait_parked")
        #expect(diagnostic.schemaVersion == AgenticToolGuardrailContract.parkingDiagnosticSchemaVersion)
        #expect(diagnostic.executorCapacityAvailable == 4)
        #expect(diagnostic.parkingPermitsUsed == 100)
        #expect(diagnostic.maxReleasedTombstones == 1_000)
        #expect(emitted.contains("arguments") == false)
        #expect(emitted.contains("prompt") == false)
    }

    @Test("parking metadata rejects unsafe config and mismatched state")
    func parkingMetadataRejectsUnsafeConfigAndMismatchedState() throws {
        let invalidConfigs = [
            AgenticToolApprovalParkingConfig(totalExecutorCapacity: 2),
            AgenticToolApprovalParkingConfig(
                totalExecutorCapacity: 4,
                reservedExecutorCapacity: 1
            ),
            AgenticToolApprovalParkingConfig(
                totalExecutorCapacity: 4,
                reservedExecutorCapacity: 4
            ),
            AgenticToolApprovalParkingConfig(
                totalExecutorCapacity: 4,
                maxParkedApprovalWaits: 0
            ),
            AgenticToolApprovalParkingConfig(
                totalExecutorCapacity: 4,
                maxReleasedTombstones: 0
            ),
        ]
        for config in invalidConfigs {
            #expect(throws: AgenticToolGuardrailContractError.self) {
                try AgenticToolGuardrailContract.approvalParkingExecutionExtFields(
                    config: config
                )
            }
        }

        let state = try JSONDecoder().decode(
            AgenticToolApprovalParkingState.self,
            from: Data(Self.parkingStateJSON.replacingOccurrences(
                of: "2d9c2b6287848d731e7773115f45f050e640bef7a947daae031c52f2555c4838",
                with: String(repeating: "0", count: 64)
            ).utf8)
        )
        #expect(throws: AgenticToolGuardrailContractError.self) {
            try AgenticToolGuardrailContract.approvalParkingExecutionExtFields(
                config: AgenticToolApprovalParkingConfig(totalExecutorCapacity: 4),
                state: state
            )
        }
    }

    private static let stateJSON = #"""
    {
      "schema_version": "melix.agentic_tool_guardrail_state.v1",
      "request_id": "request-1",
      "completed_tool_calls": [{"id":"text-1","name":"text_search","arguments":{"query":"PRIVATE_QUERY"}}],
      "execution_ledger": {"text-1":{"fingerprint":"aa8c52f9b423fa8934f054c9044fd18dde6c781f659732ec3aa823449e007d33","tool_name":"text_search","lifecycle_state":"completed"}},
      "required_tool_lifecycle": {},
      "responses_seen": 1,
      "healed_response_count": 1,
      "admission_rejection_count": 0,
      "malformed_response_count": 0,
      "tool_execution_count": 1,
      "tool_failure_count": 0,
      "replay_suppression_count": 0,
      "duplicate_execution_count": 0,
      "retry_nudge_count": 1,
      "terminal_failure_count": 0,
      "consecutive_malformed_responses": 0,
      "consecutive_tool_failures": 0,
      "last_nudge_type": "required_steps_remaining",
      "final_outcome": "running",
      "final_failure_reason": "",
      "terminal": false,
      "awaiting_final_answer": false,
      "preflight_event_emitted": true,
      "event_sequence": 5
    }
    """#

    private static let eventJSON = #"""
    {
      "schema_version": "melix.agentic_tool_guardrail_event.v1",
      "sequence": 5,
      "event_type": "retry_nudge",
      "outcome": "retry",
      "nudge_type": "tool_prerequisite_violation",
      "failure_reason": "",
      "tool_call_id": "image-1",
      "tool_name": "image_search",
      "consecutive_malformed_responses": 1,
      "consecutive_tool_failures": 0
    }
    """#

    private static let diagnosticJSON = #"""
    {
      "schema_version": "melix.agentic_tool_guardrail_diagnostic.v1",
      "request_id": "request-1",
      "responses_seen": 2,
      "healed_response_count": 2,
      "admission_rejection_count": 1,
      "malformed_response_count": 1,
      "tool_execution_count": 1,
      "tool_failure_count": 0,
      "replay_suppression_count": 0,
      "duplicate_execution_count": 0,
      "retry_nudge_count": 2,
      "terminal_failure_count": 0,
      "consecutive_malformed_responses": 1,
      "consecutive_tool_failures": 0,
      "last_nudge_type": "tool_prerequisite_violation",
      "final_outcome": "running",
      "final_failure_reason": "",
      "completed_required_tools": ["text_search"]
    }
    """#

    private static let parkingStateJSON = #"""
    {
      "schema_version": "melix.agentic_tool_approval_parking_state.v1",
      "config_fingerprint": "2d9c2b6287848d731e7773115f45f050e640bef7a947daae031c52f2555c4838",
      "entries": [
        {
          "request_id": "request-parked",
          "lifecycle_state": "parked_for_approval",
          "release_reason": "",
          "executor_lease_acquisition_count": 1,
          "approval_park_count": 1
        },
        {
          "request_id": "request-cancelled",
          "lifecycle_state": "released",
          "release_reason": "cancelled",
          "executor_lease_acquisition_count": 1,
          "approval_park_count": 0
        }
      ],
      "released_tombstone_order": ["request-cancelled"],
      "release_reason_counts": {
        "cancelled": 1,
        "completed": 0,
        "runtime_reload": 0,
        "timed_out": 0
      },
      "capacity_rejection_count": 0,
      "release_suppression_count": 1,
      "event_sequence": 6,
      "released_request_count": 1,
      "executor_lease_acquisition_count": 2,
      "approval_park_count": 1
    }
    """#

    private static let parkingEventJSON = #"""
    {
      "schema_version": "melix.agentic_tool_approval_parking_event.v1",
      "sequence": 2,
      "event_type": "approval_wait_parked",
      "outcome": "parked",
      "request_id": "request-parked",
      "lifecycle_state": "parked_for_approval",
      "release_reason": "",
      "failure_reason": ""
    }
    """#

    private static let parkingDiagnosticJSON = #"""
    {
      "schema_version": "melix.agentic_tool_approval_parking_diagnostic.v1",
      "total_executor_capacity": 4,
      "reserved_executor_capacity": 2,
      "executor_leases_used": 0,
      "executor_capacity_available": 4,
      "executor_resume_capacity_available": 2,
      "max_parked_approval_waits": 100,
      "parking_permits_used": 100,
      "parking_permits_available": 0,
      "executing_request_count": 0,
      "parked_request_count": 100,
      "released_request_count": 0,
      "max_released_tombstones": 1000,
      "retained_released_tombstone_count": 0,
      "executor_lease_acquisition_count": 100,
      "approval_park_count": 100,
      "capacity_rejection_count": 0,
      "release_suppression_count": 0,
      "release_reason_counts": {
        "cancelled": 0,
        "completed": 0,
        "runtime_reload": 0,
        "timed_out": 0
      }
    }
    """#
}
