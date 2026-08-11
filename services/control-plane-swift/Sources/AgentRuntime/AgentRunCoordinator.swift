import Foundation
import CryptoKit

private actor AgentCancellationTimeoutRace<Value: Sendable> {
    private enum Winner {
        case operation
        case timeout
    }

    private var continuation: CheckedContinuation<Value?, Never>?
    private var resolved = false
    private var operationTask: Task<Void, Never>?
    private var timeoutTask: Task<Void, Never>?

    func run(
        timeout: Duration,
        operation: @escaping @Sendable () async -> Value
    ) async -> Value? {
        await withCheckedContinuation { continuation in
            self.continuation = continuation
            operationTask = Task { [weak self] in
                let value = await operation()
                await self?.resolve(value, winner: .operation)
            }
            timeoutTask = Task { [weak self] in
                do {
                    try await Task.sleep(for: timeout)
                } catch {
                    return
                }
                await self?.resolve(nil, winner: .timeout)
            }
        }
    }

    private func resolve(_ value: Value?, winner: Winner) {
        guard !resolved, let continuation else {
            return
        }
        resolved = true
        self.continuation = nil
        switch winner {
        case .operation:
            timeoutTask?.cancel()
        case .timeout:
            operationTask?.cancel()
        }
        operationTask = nil
        timeoutTask = nil
        continuation.resume(returning: value)
    }
}

public actor AgentRunCoordinator {
    private enum ApprovalResolution: Sendable {
        case approved(AgentApprovalDecision)
        case denied
        case cancelled
    }

    private struct RunRecord {
        let request: AgentRunRequest
        let eventContinuation: AsyncStream<AgentRunEvent>.Continuation
        var state: AgentRunState
        var messages: [AgentRunMessage]
        var modelTurnCount: Int
        var toolCallCount: Int
        var healingNudgeCount: Int
        var seenCallIDs: Set<String>
        var currentCall: AgentToolCall?
        var expectedApprovalBinding: AgentApprovalBinding?
        var approvalContinuation: CheckedContinuation<ApprovalResolution, Never>?
        var task: Task<Void, Never>?
        var cancellationTask: Task<AgentCancellationReceipt, Never>?
        var cancellationReceipt: AgentCancellationReceipt?
        var terminalCleanupTask: Task<AgentRunToolCancellationReceipt, Never>?
        var terminalCleanupReceipt: AgentRunToolCancellationReceipt?
    }

    private let modelTurns: any AgentModelTurnPort
    private let tools: any AgentToolExecutionPort
    private let approvalPolicy: any AgentApprovalPolicyPort
    private let runIDGenerator: @Sendable () -> String
    private let cancellationBackendTimeout: Duration
    private var runs: [String: RunRecord] = [:]

    public init(
        modelTurns: any AgentModelTurnPort,
        tools: any AgentToolExecutionPort,
        approvalPolicy: any AgentApprovalPolicyPort,
        cancellationBackendTimeout: Duration = .seconds(2),
        runIDGenerator: @escaping @Sendable () -> String = {
            "agent-run-\(UUID().uuidString)"
        }
    ) {
        self.modelTurns = modelTurns
        self.tools = tools
        self.approvalPolicy = approvalPolicy
        self.cancellationBackendTimeout = cancellationBackendTimeout
        self.runIDGenerator = runIDGenerator
    }

    public func start(
        _ request: AgentRunRequest,
        suspended: Bool = false
    ) async throws -> AgentRunExecution {
        guard
            request.limits.maxModelTurns > 0,
            request.limits.maxToolCalls > 0,
            request.limits.maxHealingNudges >= 0
        else {
            throw AgentRunCoordinatorError.invalidLimits
        }

        let runID = runIDGenerator().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !runID.isEmpty else {
            throw AgentRunCoordinatorError.invalidRunID
        }
        guard runs[runID] == nil else {
            throw AgentRunCoordinatorError.duplicateRunID(runID: runID)
        }

        let pair = AsyncStream<AgentRunEvent>.makeStream(bufferingPolicy: .unbounded)
        runs[runID] = RunRecord(
            request: request,
            eventContinuation: pair.continuation,
            state: .created,
            messages: request.messages,
            modelTurnCount: 0,
            toolCallCount: 0,
            healingNudgeCount: 0,
            seenCallIDs: [],
            currentCall: nil,
            expectedApprovalBinding: nil,
            approvalContinuation: nil,
            task: nil,
            cancellationTask: nil,
            cancellationReceipt: nil,
            terminalCleanupTask: nil,
            terminalCleanupReceipt: nil
        )
        pair.continuation.yield(.started(runID: runID))
        pair.continuation.yield(.stateChanged(.created))

        if !suspended {
            installRunTask(runID: runID)
        }

        return AgentRunExecution(runID: runID, events: pair.stream)
    }

    /// Starts model execution for a run that was prepared with
    /// `suspended: true`. Control-plane admission uses this seam so the run is
    /// durably addressable by Stop before any provider or tool work begins.
    public func resume(runID: String) {
        guard let record = runs[runID],
              record.task == nil,
              !record.state.isTerminal else {
            return
        }
        installRunTask(runID: runID)
    }

    private func installRunTask(runID: String) {
        let task = Task { [weak self] in
            guard let self else {
                return
            }
            await self.driveRun(runID: runID)
        }
        runs[runID]?.task = task
    }

    public func decideApproval(_ decision: AgentApprovalDecision) async throws {
        guard var record = runs[decision.runID] else {
            throw AgentRunCoordinatorError.unknownRun(runID: decision.runID)
        }
        guard !record.state.isTerminal else {
            throw AgentRunCoordinatorError.runTerminal(runID: decision.runID)
        }
        guard case .waitingForApproval(let expectedCallID) = record.state,
              let expectedBinding = record.expectedApprovalBinding,
              let continuation = record.approvalContinuation
        else {
            throw AgentRunCoordinatorError.notAwaitingApproval(runID: decision.runID)
        }
        guard expectedCallID == decision.callID, expectedBinding == decision.binding else {
            throw AgentRunCoordinatorError.approvalBindingMismatch(callID: expectedCallID)
        }

        record.expectedApprovalBinding = nil
        record.approvalContinuation = nil
        record.eventContinuation.yield(.approvalDecided(decision))
        runs[decision.runID] = record
        switch decision.choice {
        case .allowOnce, .alwaysAllow:
            continuation.resume(returning: .approved(decision))
        case .deny:
            continuation.resume(returning: .denied)
        }
    }

    public func cancel(
        runID: String,
        reason: AgentCancellationReason
    ) async -> AgentCancellationReceipt {
        guard var record = runs[runID] else {
            return AgentCancellationReceipt(
                runID: runID,
                reason: reason,
                disposition: .notFound,
                sideEffectCommitted: false
            )
        }
        if let existingReceipt = record.cancellationReceipt {
            return existingReceipt
        }
        if let cancellationTask = record.cancellationTask {
            let receipt = await cancellationTask.value
            return finalizeCancellation(runID: runID, receipt: receipt)
        }
        if let terminalCleanupTask = record.terminalCleanupTask {
            let cleanup = await terminalCleanupTask.value
            return AgentCancellationReceipt(
                runID: runID,
                reason: reason,
                disposition: .alreadyTerminal,
                sideEffectState: cleanup.sideEffectState,
                runToolCancellation: cleanup
            )
        }
        guard !record.state.isTerminal else {
            let receipt = AgentCancellationReceipt(
                runID: runID,
                reason: reason,
                disposition: .alreadyTerminal,
                sideEffectState: record.terminalCleanupReceipt?.sideEffectState
                    ?? .none,
                runToolCancellation: record.terminalCleanupReceipt
            )
            record.cancellationReceipt = receipt
            runs[runID] = record
            return receipt
        }

        let previousState = record.state
        let currentCall = record.currentCall
        let approvalContinuation = record.approvalContinuation
        let runTask = record.task
        let modelTurns = self.modelTurns
        let tools = self.tools
        let cancellationBackendTimeout = self.cancellationBackendTimeout

        record.state = .cancelled
        record.expectedApprovalBinding = nil
        record.approvalContinuation = nil
        record.task = nil
        approvalContinuation?.resume(returning: .cancelled)

        let cancellationTask = Task<AgentCancellationReceipt, Never> {
            runTask?.cancel()
            let modelCancellationTask = Task<Bool, Never> {
                guard case .modelTurn = previousState else {
                    return true
                }
                return await AgentCancellationTimeoutRace<Bool>().run(
                    timeout: cancellationBackendTimeout
                ) {
                    await modelTurns.cancelTurn(runID: runID)
                    return true
                } != nil
            }
            let callCancellationTask = Task<AgentToolCancellationReceipt?, Never> {
                guard let currentCall,
                      previousState == .toolRunning(callID: currentCall.callID)
                else {
                    return nil
                }
                return await AgentCancellationTimeoutRace<
                    AgentToolCancellationReceipt
                >().run(timeout: cancellationBackendTimeout) {
                    await tools.cancel(
                        runID: runID,
                        callID: currentCall.callID
                    )
                } ?? AgentToolCancellationReceipt(
                    runID: runID,
                    callID: currentCall.callID,
                    disposition: .unavailable,
                    sideEffectState: .unknown
                )
            }
            let runCleanupTask = Task<AgentRunToolCancellationReceipt, Never> {
                await AgentCancellationTimeoutRace<
                    AgentRunToolCancellationReceipt
                >().run(timeout: cancellationBackendTimeout) {
                    await tools.cancelRun(runID: runID)
                } ?? AgentRunToolCancellationReceipt(
                    runID: runID,
                    disposition: .unavailable,
                    sideEffectState: .unknown,
                    computerUseDisposition: .unavailable
                )
            }
            let modelCancellationCompleted = await modelCancellationTask.value
            let toolReceipt = await callCancellationTask.value
            let runCleanup = await runCleanupTask.value
            return AgentCancellationReceipt(
                runID: runID,
                reason: reason,
                disposition: Self.combinedCancellationDisposition(
                    modelCancellationCompleted: modelCancellationCompleted,
                    toolReceipt: toolReceipt,
                    runCleanup: runCleanup
                ),
                sideEffectState: Self.combinedSideEffectState(
                    modelCancellationCompleted: modelCancellationCompleted,
                    toolReceipt: toolReceipt,
                    runCleanup: runCleanup
                ),
                toolCancellation: toolReceipt,
                runToolCancellation: runCleanup
            )
        }
        record.cancellationTask = cancellationTask
        runs[runID] = record

        let receipt = await cancellationTask.value
        return finalizeCancellation(runID: runID, receipt: receipt)
    }

    private func driveRun(runID: String) async {
        while isRunActive(runID) {
            guard var record = runs[runID] else {
                return
            }
            guard record.modelTurnCount < record.request.limits.maxModelTurns else {
                await finishWithFailure(
                    runID: runID,
                    reason: .modelTurnLimitExceeded(limit: record.request.limits.maxModelTurns)
                )
                return
            }

            record.modelTurnCount += 1
            let turn = AgentModelTurn(runID: runID, index: record.modelTurnCount)
            let turnRequest = AgentModelTurnRequest(
                runID: runID,
                turnIndex: record.modelTurnCount,
                messages: record.messages
            )
            record.state = .modelTurn(index: record.modelTurnCount)
            runs[runID] = record
            record.eventContinuation.yield(.stateChanged(record.state))
            record.eventContinuation.yield(.modelTurnStarted(turn))

            let result: AgentModelTurnResult
            do {
                if let streamingModelTurns = modelTurns as? any AgentStreamingModelTurnPort {
                    result = try await streamingModelTurns.performTurn(
                        turnRequest,
                        onEvent: { [weak self] event in
                            await self?.emit(
                                runID: runID,
                                event: .modelTurnStreamed(turn, event)
                            )
                        }
                    )
                } else {
                    result = try await modelTurns.performTurn(turnRequest)
                }
            } catch {
                guard isRunActive(runID) else {
                    return
                }
                await finishWithFailure(
                    runID: runID,
                    reason: .modelTurnFailed(failure: publicFailure(from: error))
                )
                return
            }

            guard isRunActive(runID), var resumedRecord = runs[runID] else {
                return
            }
            resumedRecord.eventContinuation.yield(.modelTurnCompleted(turn, result))
            if !result.assistantText.isEmpty {
                resumedRecord.messages.append(.assistant(result.assistantText))
            }
            runs[runID] = resumedRecord

            guard !result.toolCallFragments.isEmpty else {
                await finishSuccessfully(runID: runID, assistantText: result.assistantText)
                return
            }

            let assembledCalls: [AgentToolCall]
            do {
                assembledCalls = try assembleToolCalls(from: result.toolCallFragments)
            } catch let reason as AgentRunFailureReason {
                if let recoverable = recoverableAdmissionFailure(from: reason) {
                    guard await registerHealingNudge(
                        runID: runID,
                        callID: recoverable.callID,
                        failure: recoverable.failure
                    ) else {
                        return
                    }
                    continue
                }
                await finishWithFailure(runID: runID, reason: reason)
                return
            } catch {
                await finishWithFailure(
                    runID: runID,
                    reason: .modelTurnFailed(failure: .internalFailure)
                )
                return
            }

            guard isRunActive(runID), var batchRecord = runs[runID] else {
                return
            }
            var calls: [AgentToolCall] = []
            calls.reserveCapacity(assembledCalls.count)
            var recoverableFailure: (callID: String, failure: AgentToolCallAdmissionFailure)?
            var terminalAdmissionFailure: AgentRunFailureReason?
            for call in assembledCalls {
                switch batchRecord.request.toolCatalog.admissionResult(for: call) {
                case .admitted(let canonicalCall):
                    calls.append(canonicalCall)
                case .recoverable(let failure):
                    recoverableFailure = (call.callID, failure)
                case .terminal(let reason):
                    terminalAdmissionFailure = reason
                }
                if recoverableFailure != nil || terminalAdmissionFailure != nil {
                    break
                }
            }
            if let terminalAdmissionFailure {
                await finishWithFailure(runID: runID, reason: terminalAdmissionFailure)
                return
            }
            if let recoverableFailure {
                guard await registerHealingNudge(
                    runID: runID,
                    callID: recoverableFailure.callID,
                    failure: recoverableFailure.failure
                ) else {
                    return
                }
                continue
            }
            if let duplicate = calls.first(where: { batchRecord.seenCallIDs.contains($0.callID) }) {
                await finishWithFailure(
                    runID: runID,
                    reason: .duplicateToolCallID(callID: duplicate.callID)
                )
                return
            }
            guard
                batchRecord.toolCallCount + calls.count <= batchRecord.request.limits.maxToolCalls
            else {
                await finishWithFailure(
                    runID: runID,
                    reason: .toolCallLimitExceeded(limit: batchRecord.request.limits.maxToolCalls)
                )
                return
            }

            batchRecord.toolCallCount += calls.count
            for call in calls {
                batchRecord.seenCallIDs.insert(call.callID)
                batchRecord.messages.append(
                    .assistantToolCall(
                        callID: call.callID,
                        toolName: call.toolName,
                        argumentsJSON: call.argumentsJSON
                    )
                )
            }
            runs[runID] = batchRecord

            guard await executeToolCalls(calls, runID: runID) else {
                return
            }
        }
    }

    private func executeToolCalls(_ calls: [AgentToolCall], runID: String) async -> Bool {
        for call in calls {
            guard isRunActive(runID), var callRecord = runs[runID] else {
                return false
            }
            callRecord.currentCall = call
            runs[runID] = callRecord
            callRecord.eventContinuation.yield(.toolCallStateChanged(call, .requested))

            let evaluation = await approvalPolicy.approvalEvaluation(for: call, runID: runID)
            guard isRunActive(runID) else {
                return false
            }
            let policyRevision = evaluation.policyRevision.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            guard !policyRevision.isEmpty else {
                emit(runID: runID, event: .toolCallStateChanged(call, .failed))
                await finishWithFailure(
                    runID: runID,
                    reason: .invalidApprovalPolicyRevision(callID: call.callID)
                )
                return false
            }
            let binding = makeApprovalBinding(
                runID: runID,
                call: call,
                evaluation: evaluation
            )

            let admission: AgentToolAdmission
            switch evaluation.requirement {
            case .notRequired:
                admission = makeAdmission(kind: .allow, binding: binding, choice: nil)
            case .denied:
                emit(runID: runID, event: .toolCallStateChanged(call, .failed))
                await finishWithFailure(
                    runID: runID,
                    reason: .approvalDenied(callID: call.callID)
                )
                return false
            case .required:
                transition(runID: runID, to: .waitingForApproval(callID: call.callID))
                emit(runID: runID, event: .toolCallStateChanged(call, .waitingForApproval))

                let resolution = await waitForApproval(
                    runID: runID,
                    call: call,
                    binding: binding
                )
                guard isRunActive(runID) else {
                    return false
                }
                switch resolution {
                case .approved(let decision):
                    admission = makeAdmission(
                        kind: .approved,
                        binding: decision.resultingBinding ?? binding,
                        choice: decision.choice
                    )
                case .denied:
                    emit(runID: runID, event: .toolCallStateChanged(call, .failed))
                    await finishWithFailure(
                        runID: runID,
                        reason: .approvalDenied(callID: call.callID)
                    )
                    return false
                case .cancelled:
                    return false
                }
            }

            guard isRunActive(runID) else {
                return false
            }
            let expectedRequirement: AgentApprovalRequirement =
                admission.kind == .allow
                    || admission.binding != binding
                ? .notRequired
                : .required
            guard await approvalPolicy.isApprovalBindingCurrent(
                admission.binding,
                for: call,
                runID: runID,
                expectedRequirement: expectedRequirement
            ) else {
                emit(runID: runID, event: .toolCallStateChanged(call, .failed))
                await finishWithFailure(
                    runID: runID,
                    reason: .staleApprovalBinding(callID: call.callID)
                )
                return false
            }
            // Binding revalidation crosses an actor/async boundary. Stop may
            // become terminal while that check is in flight, so re-check the
            // run before admitting any new side-effecting work.
            guard isRunActive(runID) else {
                return false
            }
            transition(runID: runID, to: .toolRunning(callID: call.callID))
            emit(runID: runID, event: .toolCallStateChanged(call, .running))

            let toolResult: AgentToolExecutionResult
            do {
                toolResult = try await tools.execute(
                    AgentToolExecutionRequest(runID: runID, call: call, admission: admission)
                )
            } catch {
                guard isRunActive(runID) else {
                    return false
                }
                emit(runID: runID, event: .toolCallStateChanged(call, .failed))
                await finishWithFailure(
                    runID: runID,
                    reason: .toolExecutionFailed(
                        callID: call.callID,
                        failure: publicFailure(from: error)
                    )
                )
                return false
            }

            guard isRunActive(runID), var toolRecord = runs[runID] else {
                return false
            }
            toolRecord.currentCall = nil
            toolRecord.expectedApprovalBinding = nil
            toolRecord.messages.append(
                .toolResult(
                    callID: call.callID,
                    toolName: call.toolName,
                    outputJSON: toolResult.outputJSON
                )
            )
            runs[runID] = toolRecord
            toolRecord.eventContinuation.yield(.toolCallCompleted(call, toolResult))
        }
        return isRunActive(runID)
    }

    private func registerHealingNudge(
        runID: String,
        callID: String,
        failure: AgentToolCallAdmissionFailure
    ) async -> Bool {
        guard var record = runs[runID], !record.state.isTerminal else {
            return false
        }
        let nextAttempt = record.healingNudgeCount + 1
        let limit = record.request.limits.maxHealingNudges
        guard nextAttempt <= limit else {
            await finishWithFailure(
                runID: runID,
                reason: .toolCallHealingLimitExceeded(
                    callID: callID,
                    failure: failure,
                    limit: limit
                )
            )
            return false
        }
        let nudge = AgentToolHealingNudge(
            callID: callID,
            failure: failure,
            attemptIndex: nextAttempt,
            maxRetryNudges: limit
        )
        record.healingNudgeCount = nextAttempt
        record.messages.append(.guardrailNudge(nudge))
        runs[runID] = record
        record.eventContinuation.yield(.healingNudge(nudge))
        return true
    }

    private func recoverableAdmissionFailure(
        from reason: AgentRunFailureReason
    ) -> (callID: String, failure: AgentToolCallAdmissionFailure)? {
        switch reason {
        case .incompleteToolCall(let callID):
            return (callID, .incompleteWireShape)
        case .toolArgumentsMustBeJSONObject(let callID):
            return (callID, .argumentsMustBeJSONObject)
        default:
            return nil
        }
    }

    private func waitForApproval(
        runID: String,
        call: AgentToolCall,
        binding: AgentApprovalBinding
    ) async -> ApprovalResolution {
        await withCheckedContinuation { continuation in
            guard var record = runs[runID], !record.state.isTerminal else {
                continuation.resume(returning: .cancelled)
                return
            }
            record.expectedApprovalBinding = binding
            record.approvalContinuation = continuation
            runs[runID] = record
            record.eventContinuation.yield(
                .approvalRequired(AgentApprovalRequest(call: call, binding: binding))
            )
        }
    }

    private func assembleToolCalls(
        from fragments: [AgentToolCallFragment]
    ) throws -> [AgentToolCall] {
        guard !fragments.isEmpty else {
            throw AgentRunFailureReason.incompleteToolCall(callID: "")
        }

        var calls: [AgentToolCall] = []
        var completedCallIDs: Set<String> = []
        var activeCallID: String?
        var activeSourceID = ""
        var activeToolName = ""
        var activeTitle = ""
        var activeIntendedEffect = ""
        var activeRiskClass = ""
        var activeSchemaDigest = ""
        var argumentsJSON = ""

        for fragment in fragments {
            let callID = fragment.callID.trimmingCharacters(in: .whitespacesAndNewlines)
            let sourceID = fragment.sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
            let toolName = fragment.toolName.trimmingCharacters(in: .whitespacesAndNewlines)
            let title = fragment.title.trimmingCharacters(in: .whitespacesAndNewlines)
            let intendedEffect = fragment.intendedEffect.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            let riskClass = fragment.riskClass.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            let schemaDigest = fragment.schemaDigest.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            guard !callID.isEmpty, !toolName.isEmpty else {
                throw AgentRunFailureReason.inconsistentToolCallFragments(callID: callID)
            }
            guard !completedCallIDs.contains(callID) else {
                throw AgentRunFailureReason.duplicateToolCallID(callID: callID)
            }

            if let activeCallID {
                guard activeCallID == callID else {
                    throw AgentRunFailureReason.interleavedToolCallFragments(
                        activeCallID: activeCallID,
                        receivedCallID: callID
                    )
                }
                guard
                    activeSourceID == sourceID,
                    activeToolName == toolName,
                    activeTitle == title,
                    activeIntendedEffect == intendedEffect,
                    activeRiskClass == riskClass,
                    activeSchemaDigest == schemaDigest
                else {
                    throw AgentRunFailureReason.inconsistentToolCallFragments(callID: callID)
                }
            } else {
                activeCallID = callID
                activeSourceID = sourceID
                activeToolName = toolName
                activeTitle = title
                activeIntendedEffect = intendedEffect
                activeRiskClass = riskClass
                activeSchemaDigest = schemaDigest
                argumentsJSON = ""
            }

            guard
                activeSourceID == sourceID,
                activeToolName == toolName,
                activeTitle == title,
                activeIntendedEffect == intendedEffect,
                activeRiskClass == riskClass,
                activeSchemaDigest == schemaDigest
            else {
                throw AgentRunFailureReason.inconsistentToolCallFragments(callID: callID)
            }
            argumentsJSON += fragment.argumentsFragment
            guard fragment.isComplete else {
                continue
            }

            guard
                let data = argumentsJSON.data(using: .utf8),
                let object = try? JSONSerialization.jsonObject(with: data),
                object is [String: Any]
            else {
                throw AgentRunFailureReason.toolArgumentsMustBeJSONObject(callID: callID)
            }
            calls.append(
                AgentToolCall(
                    callID: callID,
                    sourceID: sourceID,
                    toolName: toolName,
                    title: title,
                    intendedEffect: intendedEffect,
                    riskClass: riskClass,
                    schemaDigest: schemaDigest,
                    argumentsJSON: argumentsJSON
                )
            )
            completedCallIDs.insert(callID)
            activeCallID = nil
            activeSourceID = ""
            activeToolName = ""
            activeTitle = ""
            activeIntendedEffect = ""
            activeRiskClass = ""
            activeSchemaDigest = ""
            argumentsJSON = ""
        }

        if let activeCallID {
            throw AgentRunFailureReason.incompleteToolCall(callID: activeCallID)
        }
        return calls
    }

    private func makeApprovalBinding(
        runID: String,
        call: AgentToolCall,
        evaluation: AgentApprovalPolicyEvaluation
    ) -> AgentApprovalBinding {
        AgentApprovalBinding.make(
            runID: runID,
            call: call,
            policyRevision: evaluation.policyRevision,
            scopeDigest: evaluation.scopeDigest
        )
    }

    private func makeAdmission(
        kind: AgentToolAdmissionKind,
        binding: AgentApprovalBinding,
        choice: AgentApprovalChoice?
    ) -> AgentToolAdmission {
        let choiceValue: String
        switch choice {
        case .allowOnce:
            choiceValue = "allow-once"
        case .alwaysAllow:
            choiceValue = "always-allow"
        case .deny:
            choiceValue = "deny"
        case nil:
            choiceValue = "policy-allow"
        }
        let kindValue = kind == .allow ? "allow" : "approved"
        let grantDigest = digest(
            canonicalDigestInput([
                "melix.agent-tool-admission.v1",
                binding.bindingDigest,
                kindValue,
                choiceValue,
            ])
        )
        return AgentToolAdmission(
            kind: kind,
            binding: binding,
            approvalChoice: choice,
            grantDigest: grantDigest
        )
    }

    private func canonicalDigestInput(_ fields: [String]) -> String {
        fields.map { field in
            "\(field.utf8.count):\(field)"
        }.joined(separator: "|")
    }

    private func digest(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { byte in
            String(format: "%02x", byte)
        }.joined()
    }

    private func publicFailure(from error: any Error) -> AgentPortFailure {
        if let failure = error as? AgentPortFailure {
            return failure
        }
        if error is CancellationError {
            return .cancelled
        }
        return .internalFailure
    }

    private func finalizeCancellation(
        runID: String,
        receipt: AgentCancellationReceipt
    ) -> AgentCancellationReceipt {
        guard var record = runs[runID] else {
            return receipt
        }
        if let existingReceipt = record.cancellationReceipt {
            return existingReceipt
        }

        let currentCall = record.currentCall
        record.currentCall = nil
        record.cancellationTask = nil
        record.cancellationReceipt = receipt
        runs[runID] = record

        if let currentCall {
            record.eventContinuation.yield(.toolCallStateChanged(currentCall, .cancelled))
        }
        record.eventContinuation.yield(.stateChanged(.cancelled))
        record.eventContinuation.yield(.cancelled(receipt))
        record.eventContinuation.finish()
        return receipt
    }

    private func transition(runID: String, to state: AgentRunState) {
        guard var record = runs[runID], !record.state.isTerminal else {
            return
        }
        record.state = state
        runs[runID] = record
        record.eventContinuation.yield(.stateChanged(state))
    }

    private func emit(runID: String, event: AgentRunEvent) {
        guard let record = runs[runID], !record.state.isTerminal else {
            return
        }
        record.eventContinuation.yield(event)
    }

    private func finishSuccessfully(
        runID: String,
        assistantText: String
    ) async {
        guard let cleanup = await performTerminalToolCleanup(runID: runID),
              var record = runs[runID],
              !record.state.isTerminal
        else {
            return
        }
        guard Self.cleanupWasAccepted(cleanup) else {
            emitTerminalFailure(
                runID: runID,
                record: &record,
                reason: .runToolCleanupFailed(
                    failure: Self.cleanupFailure(cleanup)
                )
            )
            return
        }
        let completion = AgentRunCompletion(
            runID: runID,
            assistantText: assistantText,
            modelTurnCount: record.modelTurnCount,
            toolCallCount: record.toolCallCount
        )
        record.state = .completed
        record.currentCall = nil
        record.expectedApprovalBinding = nil
        record.approvalContinuation = nil
        record.task = nil
        record.terminalCleanupTask = nil
        record.terminalCleanupReceipt = cleanup
        runs[runID] = record
        record.eventContinuation.yield(.stateChanged(.completed))
        record.eventContinuation.yield(.completed(completion))
        record.eventContinuation.finish()
    }

    private func finishWithFailure(
        runID: String,
        reason: AgentRunFailureReason
    ) async {
        guard let cleanup = await performTerminalToolCleanup(runID: runID),
              var record = runs[runID],
              !record.state.isTerminal
        else {
            return
        }
        let terminalReason = Self.cleanupWasAccepted(cleanup)
            ? reason
            : .runToolCleanupFailed(failure: Self.cleanupFailure(cleanup))
        record.terminalCleanupReceipt = cleanup
        emitTerminalFailure(
            runID: runID,
            record: &record,
            reason: terminalReason
        )
    }

    private func performTerminalToolCleanup(
        runID: String
    ) async -> AgentRunToolCancellationReceipt? {
        guard var record = runs[runID], !record.state.isTerminal else {
            return runs[runID]?.terminalCleanupReceipt
        }
        if let task = record.terminalCleanupTask {
            return await task.value
        }
        let tools = self.tools
        let timeout = cancellationBackendTimeout
        let task = Task<AgentRunToolCancellationReceipt, Never> {
            await AgentCancellationTimeoutRace<
                AgentRunToolCancellationReceipt
            >().run(timeout: timeout) {
                await tools.cancelRun(runID: runID)
            } ?? AgentRunToolCancellationReceipt(
                runID: runID,
                disposition: .unavailable,
                sideEffectState: .unknown,
                computerUseDisposition: .unavailable
            )
        }
        record.currentCall = nil
        record.expectedApprovalBinding = nil
        record.approvalContinuation = nil
        record.task = nil
        record.terminalCleanupTask = task
        runs[runID] = record
        let receipt = await task.value
        if var latest = runs[runID], latest.terminalCleanupTask != nil {
            latest.terminalCleanupTask = nil
            latest.terminalCleanupReceipt = receipt
            runs[runID] = latest
        }
        return receipt
    }

    private func emitTerminalFailure(
        runID: String,
        record: inout RunRecord,
        reason: AgentRunFailureReason
    ) {
        let failure = AgentRunFailure(runID: runID, reason: reason)
        record.state = .failed
        record.currentCall = nil
        record.expectedApprovalBinding = nil
        record.approvalContinuation = nil
        record.task = nil
        record.terminalCleanupTask = nil
        runs[runID] = record
        record.eventContinuation.yield(.stateChanged(.failed))
        record.eventContinuation.yield(.failed(failure))
        record.eventContinuation.finish()
    }

    private static func cleanupWasAccepted(
        _ receipt: AgentRunToolCancellationReceipt
    ) -> Bool {
        switch receipt.disposition {
        case .accepted, .alreadyTerminal, .notFound:
            true
        case .tooLate, .scopeMismatch, .unavailable:
            false
        }
    }

    private static func cleanupFailure(
        _ receipt: AgentRunToolCancellationReceipt
    ) -> AgentPortFailure {
        switch receipt.disposition {
        case .unavailable:
            .unavailable
        case .tooLate:
            .timedOut
        case .scopeMismatch:
            .rejected
        case .accepted, .alreadyTerminal, .notFound:
            .internalFailure
        }
    }

    private static func combinedCancellationDisposition(
        modelCancellationCompleted: Bool,
        toolReceipt: AgentToolCancellationReceipt?,
        runCleanup: AgentRunToolCancellationReceipt
    ) -> AgentCancellationDisposition {
        guard modelCancellationCompleted else {
            return .unavailable
        }
        let dispositions = [runCleanup.disposition, toolReceipt?.disposition]
            .compactMap { $0 }
        if dispositions.contains(.unavailable) {
            return .unavailable
        }
        if dispositions.contains(.scopeMismatch) {
            return .scopeMismatch
        }
        if dispositions.contains(.tooLate) {
            return .tooLate
        }
        return .accepted
    }

    private static func combinedSideEffectState(
        modelCancellationCompleted: Bool,
        toolReceipt: AgentToolCancellationReceipt?,
        runCleanup: AgentRunToolCancellationReceipt
    ) -> AgentToolSideEffectState {
        guard modelCancellationCompleted else {
            return .unknown
        }
        let states = [runCleanup.sideEffectState, toolReceipt?.sideEffectState]
            .compactMap { $0 }
        if states.contains(.unknown) {
            return .unknown
        }
        if states.contains(.committed) {
            return .committed
        }
        return .none
    }

    private func isRunActive(_ runID: String) -> Bool {
        guard let record = runs[runID] else {
            return false
        }
        return !record.state.isTerminal
    }
}

private extension AgentRunState {
    var isTerminal: Bool {
        switch self {
        case .completed, .failed, .cancelled:
            true
        case .created, .modelTurn, .waitingForApproval, .toolRunning:
            false
        }
    }
}
