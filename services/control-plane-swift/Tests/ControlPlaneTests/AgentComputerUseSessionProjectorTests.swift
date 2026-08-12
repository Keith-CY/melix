import CryptoKit
import Foundation
import MelixControlPlaneProtocol
import Testing

@testable import MelixControlPlaneCore

@Suite("Agent Computer Use Session Projector")
struct AgentComputerUseSessionProjectorTests {
    @Test("trusted receipts build one durable session projection without capabilities")
    func trustedReceiptsBuildSessionProjection() throws {
        let permissions = AgentComputerUseSessionProjector.project(
            call: computerCall("permissions-call"),
            result: try computerResult(
                callID: "permissions-call",
                operation: "get_permissions",
                payload: [
                    "screen_recording": "granted",
                    "accessibility": "restart_required",
                ]
            ),
            current: nil,
            updatedAtUnixMs: 1_800_000_000_000
        )
        var projection = try #require(permissions)
        #expect(
            projection.screenRecordingPermission
                == .agentComputerUsePermissionGranted
        )
        #expect(
            projection.accessibilityPermission
                == .agentComputerUsePermissionRestartRequired
        )
        #expect(
            projection.restartState == .agentComputerUseRestartRequired
        )
        #expect(
            projection.sessionState == .agentComputerUseSessionUnavailable
        )

        let privateCapability = "private-capability-must-not-cross"
        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("open-call"),
            result: try computerResult(
                callID: "open-call",
                operation: "open_session",
                sessionID: "computer-session-1",
                payload: [
                    "session_id": "computer-session-1",
                    "allowed_targets": [[
                        "bundle_id": "com.example.Editor",
                        "process_id": 42,
                        "process_launch_identity": "ignored-launch-identity",
                        "window_id": 7,
                        "window_title": "Draft",
                    ]],
                    "maximum_frames": 16,
                    "maximum_actions": 8,
                    "maximum_artifact_bytes": 1_048_576,
                    "idle_deadline_unix_ms": 1_800_000_060_000,
                    "absolute_deadline_unix_ms": 1_800_000_300_000,
                    "session_capability": privateCapability,
                ],
                receiptExtras: ["session_capability": privateCapability]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_001_000
        ))
        #expect(projection.sessionID == "computer-session-1")
        #expect(projection.sessionState == .agentComputerUseSessionOpen)
        #expect(
            projection.allowedTargetsAvailability
                == .agentComputerUseFieldAvailable
        )
        #expect(projection.allowedTargets.map(\.bundleID) == [
            "com.example.Editor",
        ])
        #expect(projection.allowedTargets.first?.windowID == 7)
        #expect(projection.allowedTargets.first?.windowTitle == "Draft")
        #expect(
            projection.activeTarget.availability
                == .agentComputerUseFieldUnavailable
        )
        #expect(projection.frameBudget.limit == 16)
        #expect(projection.frameBudget.used == 0)
        #expect(projection.actionBudget.limit == 8)
        #expect(projection.actionBudget.used == 0)
        #expect(
            projection.idleDeadline.availability
                == .agentComputerUseFieldAvailable
        )
        #expect(projection.idleDeadline.unixMs == 1_800_000_060_000)
        #expect(
            projection.absoluteDeadline.unixMs == 1_800_000_300_000
        )
        let serialized = try projection.serializedData()
        #expect(serialized.range(of: Data(privateCapability.utf8)) == nil)

        let capture = try computerResult(
            callID: "capture-call",
            operation: "capture_frame",
            sessionID: projection.sessionID,
            payload: [
                "session_id": projection.sessionID,
                "actual_target": [
                    "bundle_id": "com.example.Editor",
                    "window_id": 7,
                    "window_title": "Draft",
                ],
            ]
        )
        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("capture-call"),
            result: capture,
            current: projection,
            updatedAtUnixMs: 1_800_000_002_000
        ))
        #expect(projection.activeTarget.bundleID == "com.example.Editor")
        #expect(projection.frameBudget.used == 1)
        #expect(
            projection.idleDeadline.availability
                == .agentComputerUseFieldUnavailable
        )
        #expect(
            projection.absoluteDeadline.availability
                == .agentComputerUseFieldAvailable
        )
        #expect(
            projection.lastOperation == .agentComputerUseCaptureFrame
        )
        #expect(
            projection.lastResult == .agentComputerUseResultCompleted
        )

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("capture-call"),
            result: capture,
            current: projection,
            updatedAtUnixMs: 1_800_000_002_100
        ))
        #expect(projection.frameBudget.used == 1)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("press-call"),
            result: try computerResult(
                callID: "press-call",
                operation: "press_element",
                sessionID: projection.sessionID,
                payload: [
                    "session_id": projection.sessionID,
                    "action_id": "press-call",
                    "status": "completed",
                    "terminal_phase": "completed",
                    "result": [
                        "status": "completed",
                        "actual_target": [
                            "bundle_id": "com.example.Editor",
                            "window_id": 7,
                            "window_title": "Draft saved",
                        ],
                    ],
                ],
                receiptExtras: [
                    "action_id": "press-call",
                    "terminal_phase": "completed",
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_003_000
        ))
        #expect(projection.actionBudget.used == 1)
        #expect(projection.lastActionID == "press-call")
        #expect(projection.activeTarget.windowTitle == "Draft saved")
        #expect(
            projection.lastOperation == .agentComputerUsePressElement
        )

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("close-call"),
            result: try computerResult(
                callID: "close-call",
                operation: "close_session",
                sessionID: projection.sessionID,
                payload: [
                    "session_id": projection.sessionID,
                    "closed": true,
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_004_000
        ))
        #expect(projection.sessionState == .agentComputerUseSessionClosed)
        #expect(
            projection.absoluteDeadline.availability
                == .agentComputerUseFieldUnavailable
        )
        #expect(
            projection.lastOperation == .agentComputerUseCloseSession
        )
    }

    @Test("missing or untrusted fields stay typed unavailable")
    func missingOrUntrustedFieldsStayUnavailable() throws {
        var projection = try #require(AgentComputerUseSessionProjector.record(
            call: computerCall("running-call"),
            state: .running,
            current: nil,
            updatedAtUnixMs: 1_800_000_000_000
        ))
        #expect(
            projection.sessionState == .agentComputerUseSessionUnavailable
        )
        #expect(projection.lastOperation == .unavailable)
        #expect(
            projection.lastResult == .agentComputerUseResultUnavailable
        )

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("open-call"),
            result: try computerResult(
                callID: "open-call",
                operation: "open_session",
                sessionID: "session-1",
                payload: [
                    "session_id": "session-1",
                    "allowed_targets": [[
                        "bundle_id": "com.example.Editor",
                        "window_id": 9,
                        "window_title": String(repeating: "x", count: 513),
                    ]],
                    "maximum_frames": true,
                    "maximum_actions": -1,
                    "idle_deadline_unix_ms": "soon",
                    "absolute_deadline_unix_ms": 1_800_000_300_000,
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_001_000
        ))
        #expect(projection.sessionID == "session-1")
        #expect(
            projection.allowedTargetsAvailability
                == .agentComputerUseFieldUnavailable
        )
        #expect(
            projection.frameBudget.limitAvailability
                == .agentComputerUseFieldUnavailable
        )
        #expect(
            projection.actionBudget.limitAvailability
                == .agentComputerUseFieldUnavailable
        )
        #expect(
            projection.idleDeadline.availability
                == .agentComputerUseFieldUnavailable
        )
        #expect(
            projection.absoluteDeadline.availability
                == .agentComputerUseFieldAvailable
        )

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("capture-cross-session"),
            result: try computerResult(
                callID: "capture-cross-session",
                operation: "capture_frame",
                sessionID: "session-2",
                payload: [
                    "session_id": "session-2",
                    "actual_target": [
                        "bundle_id": "com.example.Other",
                        "window_id": 2,
                        "window_title": "Other",
                    ],
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_002_000
        ))
        #expect(projection.sessionID == "session-1")
        #expect(projection.lastOperation == .unavailable)
        #expect(
            projection.lastResult == .agentComputerUseResultUnavailable
        )

        var invalidReceipt = try computerResult(
            callID: "invalid-receipt-call",
            operation: "capture_frame",
            sessionID: "session-1",
            payload: ["session_id": "session-1"]
        )
        invalidReceipt = AgentToolExecutionResult(
            outputJSON: invalidReceipt.outputJSON,
            receiptJSON: #"{"schema_version":"not-trusted"}"#
        )
        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("invalid-receipt-call"),
            result: invalidReceipt,
            current: projection,
            updatedAtUnixMs: 1_800_000_003_000
        ))
        #expect(projection.sessionID == "session-1")
        #expect(projection.lastOperation == .unavailable)

        let bound = try computerResult(
            callID: "tampered-observation-call",
            operation: "capture_frame",
            sessionID: "session-1",
            payload: ["session_id": "session-1"]
        )
        let tamperedOutput = bound.outputJSON.replacingOccurrences(
            of: #""session_id":"session-1""#,
            with: #""session_id":"session-2""#
        )
        #expect(tamperedOutput != bound.outputJSON)
        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("tampered-observation-call"),
            result: AgentToolExecutionResult(
                outputJSON: tamperedOutput,
                receiptJSON: bound.receiptJSON
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_003_500
        ))
        #expect(projection.sessionID == "session-1")
        #expect(projection.lastOperation == .unavailable)

        projection = try #require(AgentComputerUseSessionProjector.record(
            call: computerCall("failed-call"),
            state: .failed,
            current: projection,
            updatedAtUnixMs: 1_800_000_004_000
        ))
        #expect(projection.lastResult == .agentComputerUseResultFailed)

        let unchanged = AgentComputerUseSessionProjector.record(
            call: AgentToolCall(
                callID: "other-call",
                sourceID: "builtin",
                toolName: "environment_info",
                schemaDigest: "schema",
                argumentsJSON: "{}"
            ),
            state: .running,
            current: projection,
            updatedAtUnixMs: 1_800_000_005_000
        )
        #expect(unchanged == projection)
    }

    @Test("cancelled Computer calls clear terminal operation identity")
    func cancelledCallsClearTerminalIdentity() throws {
        let projection = try #require(AgentComputerUseSessionProjector.record(
            call: computerCall("cancelled-call"),
            state: .cancelled,
            current: nil,
            updatedAtUnixMs: 1_800_000_004_500
        ))
        #expect(projection.lastOperation == .unavailable)
        #expect(projection.lastResult == .agentComputerUseResultCancelled)
        #expect(projection.lastActionID.isEmpty)
        #expect(projection.lastCallID.isEmpty)
    }

    @Test("operator projection ignores conflicting untrusted observation fields")
    func operatorProjectionIgnoresObservationCopy() throws {
        let projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("receipt-only-permissions"),
            result: try computerResult(
                callID: "receipt-only-permissions",
                operation: "get_permissions",
                payload: [
                    "screen_recording": "denied",
                    "accessibility": "denied",
                ],
                operatorProjection: [
                    "screen_recording": "granted",
                    "accessibility": "restart_required",
                ]
            ),
            current: nil,
            updatedAtUnixMs: 1_800_000_005_000
        ))
        #expect(
            projection.screenRecordingPermission
                == .agentComputerUsePermissionGranted
        )
        #expect(
            projection.accessibilityPermission
                == .agentComputerUsePermissionRestartRequired
        )
    }

    @Test("permission projection preserves denied unavailable and restart truth")
    func permissionProjectionMatrix() throws {
        let cases: [(
            String,
            String,
            Melix_Controlplane_V1_AgentComputerUsePermissionState,
            Melix_Controlplane_V1_AgentComputerUsePermissionState,
            Melix_Controlplane_V1_AgentComputerUseRestartState
        )] = [
            (
                "not_determined",
                "denied",
                .agentComputerUsePermissionNotDetermined,
                .agentComputerUsePermissionDenied,
                .agentComputerUseRestartNotRequired
            ),
            (
                "unavailable",
                "granted",
                .agentComputerUsePermissionUnavailable,
                .agentComputerUsePermissionGranted,
                .agentComputerUseRestartUnavailable
            ),
            (
                "future-permission-state",
                "granted",
                .agentComputerUsePermissionUnavailable,
                .agentComputerUsePermissionGranted,
                .agentComputerUseRestartUnavailable
            ),
        ]

        for (index, entry) in cases.enumerated() {
            let callID = "permission-matrix-\(index)"
            let projection = try #require(
                AgentComputerUseSessionProjector.project(
                    call: computerCall(callID),
                    result: try computerResult(
                        callID: callID,
                        operation: "get_permissions",
                        payload: [
                            "screen_recording": entry.0,
                            "accessibility": entry.1,
                        ]
                    ),
                    current: nil,
                    updatedAtUnixMs: 1_800_000_010_000 + Int64(index)
                )
            )
            #expect(projection.screenRecordingPermission == entry.2)
            #expect(projection.accessibilityPermission == entry.3)
            #expect(projection.restartState == entry.4)
        }
    }

    @Test("malformed and cross-session receipts stay fail closed")
    func malformedAndCrossSessionReceiptsStayFailClosed() throws {
        var projection = try #require(AgentComputerUseSessionProjector.record(
            call: computerCall("completed-without-result"),
            state: .completed,
            current: nil,
            updatedAtUnixMs: 1_800_000_020_000
        ))
        #expect(projection.lastResult == .agentComputerUseResultUnavailable)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("list-targets-result"),
            result: try computerResult(
                callID: "list-targets-result",
                operation: "list_targets",
                payload: ["targets": []]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_100
        ))
        #expect(projection.lastOperation == .unavailable)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("empty-receipt"),
            result: AgentToolExecutionResult(
                outputJSON: "{}",
                receiptJSON: ""
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_200
        ))
        #expect(projection.lastOperation == .unavailable)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("mismatched-open"),
            result: try computerResult(
                callID: "mismatched-open",
                operation: "open_session",
                sessionID: "receipt-session",
                payload: [
                    "session_id": "payload-session",
                    "allowed_targets": [],
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_300
        ))
        #expect(projection.sessionID.isEmpty)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("capture-first"),
            result: try computerResult(
                callID: "capture-first",
                operation: "capture_frame",
                sessionID: "activity-session",
                payload: [
                    "session_id": "activity-session",
                    "actual_target": NSNull(),
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_400
        ))
        #expect(projection.sessionID == "activity-session")
        #expect(projection.frameBudget.used == 1)
        #expect(
            projection.frameBudget.usedAvailability
                == .agentComputerUseFieldAvailable
        )

        let invalidPressReceipt = try computerResult(
            callID: "press-receipt-mismatch",
            operation: "press_element",
            sessionID: "activity-session",
            payload: ["session_id": "activity-session"],
            receiptExtras: [
                "action_id": "another-call",
                "terminal_phase": "completed",
            ]
        )
        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("press-receipt-mismatch"),
            result: invalidPressReceipt,
            current: projection,
            updatedAtUnixMs: 1_800_000_020_500
        ))
        #expect(projection.lastOperation == .unavailable)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("press-payload-mismatch"),
            result: try computerResult(
                callID: "press-payload-mismatch",
                operation: "press_element",
                sessionID: "activity-session",
                payload: [
                    "session_id": "activity-session",
                    "action_id": "press-payload-mismatch",
                    "status": "failed",
                    "terminal_phase": "completed",
                    "result": ["status": "completed"],
                ],
                receiptExtras: [
                    "action_id": "press-payload-mismatch",
                    "terminal_phase": "completed",
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_600
        ))
        #expect(projection.lastOperation == .unavailable)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("close-invalid-boolean"),
            result: try computerResult(
                callID: "close-invalid-boolean",
                operation: "close_session",
                sessionID: "activity-session",
                payload: [
                    "session_id": "activity-session",
                    "closed": 1,
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_700
        ))
        #expect(projection.sessionState == .agentComputerUseSessionOpen)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("close-valid"),
            result: try computerResult(
                callID: "close-valid",
                operation: "close_session",
                sessionID: "activity-session",
                payload: [
                    "session_id": "activity-session",
                    "closed": true,
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_800
        ))
        #expect(projection.sessionState == .agentComputerUseSessionClosed)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("capture-after-close"),
            result: try computerResult(
                callID: "capture-after-close",
                operation: "capture_frame",
                sessionID: "activity-session",
                payload: ["session_id": "activity-session"]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_020_900
        ))
        #expect(projection.sessionState == .agentComputerUseSessionClosed)
        #expect(projection.lastOperation == .unavailable)

        projection = try #require(AgentComputerUseSessionProjector.project(
            call: computerCall("open-invalid-projections"),
            result: try computerResult(
                callID: "open-invalid-projections",
                operation: "open_session",
                sessionID: "new-session",
                payload: [
                    "session_id": "new-session",
                    "allowed_targets": [],
                    "maximum_frames": 1,
                    "maximum_actions": 1,
                    "absolute_deadline_unix_ms": 1.5,
                ]
            ),
            current: projection,
            updatedAtUnixMs: 1_800_000_021_000
        ))
        #expect(
            projection.allowedTargetsAvailability
                == .agentComputerUseFieldUnavailable
        )
        #expect(
            projection.absoluteDeadline.availability
                == .agentComputerUseFieldUnavailable
        )
    }
}

private func computerCall(_ callID: String) -> AgentToolCall {
    AgentToolCall(
        callID: callID,
        sourceID: "computer",
        toolName: "computer_use",
        schemaDigest: "computer-schema-v1",
        argumentsJSON: #"{"untrusted":"arguments are never parsed"}"#
    )
}

private func computerResult(
    callID: String,
    operation: String,
    sessionID: String = "",
    payload: [String: Any],
    receiptExtras: [String: Any] = [:],
    operatorProjection: [String: Any]? = nil
) throws -> AgentToolExecutionResult {
    var normalizedPayload = payload
    normalizedPayload["operation"] = operation
    var observation: [String: Any] = [
        "schema_version": "melix.agentic_tool_observation.v1",
        "tool_name": "computer_use",
        "tool_call_id": callID,
        "observation_kind": "computer_use_result",
        "status": "completed",
        "payload": normalizedPayload,
    ]
    observation["metrics"] = [:]
    let outputJSON = try jsonString(observation)
    var normalizedOperatorProjection = operatorProjection ?? normalizedPayload
    normalizedOperatorProjection["operation"] = operation
    var receipt: [String: Any] = [
        "schema_version": "melix.computer_use_adapter_receipt.v1",
        "adapter_kind": "computer",
        "source_id": "computer",
        "operation": operation,
        "status": "completed",
        "session_id": sessionID,
        "observation_binding_schema_version":
            "melix.computer_use_observation_binding.v1",
        "observation_sha256": SHA256.hash(data: Data(outputJSON.utf8)).map {
            String(format: "%02x", $0)
        }.joined(),
        "operator_projection_schema_version":
            "melix.computer_use_operator_projection.v1",
        "operator_projection": normalizedOperatorProjection,
    ]
    for (key, value) in receiptExtras {
        receipt[key] = value
    }
    return AgentToolExecutionResult(
        outputJSON: outputJSON,
        receiptJSON: try jsonString(receipt)
    )
}

private func jsonString(_ value: Any) throws -> String {
    let data = try JSONSerialization.data(
        withJSONObject: value,
        options: [.sortedKeys]
    )
    return try #require(String(data: data, encoding: .utf8))
}
