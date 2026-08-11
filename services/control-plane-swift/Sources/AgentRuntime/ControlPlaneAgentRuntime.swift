import CryptoKit
import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

private actor AgentRunCommandGate {
    private var locked = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func acquire() async {
        if !locked {
            locked = true
            return
        }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func release() {
        if waiters.isEmpty {
            locked = false
            return
        }
        waiters.removeFirst().resume()
    }

    func waiterCount() -> Int {
        waiters.count
    }
}

public enum ControlPlaneAgentRuntimeError: Error, Sendable, Equatable {
    case deadlineExceeded
    case invalidRequest(String)
    case unknownRun(String)
    case invalidApprovalBinding
    case approvalNotPending
    case staleApprovalBinding
    case policyPersistenceFailed
    case decisionPersistenceFailed
    case journalPersistenceFailed
}

public struct ControlPlaneAgentRuntimeStartDependencies: Sendable {
    public typealias ValidateComputerUseTargets = @Sendable (
        [TrustedComputerUseTarget],
        AgentRuntimeToolDescriptor,
        Int64
    ) async throws -> Void

    public let worker: any AgentToolRuntimeWorkerClientProtocol
    public let approvalPolicy: any AgentApprovalPolicyManaging
    public let approvalContextRegistry: AgentApprovalContextRegistry?
    public let sourceConfigs: [Melix_Worker_V1_AgentToolSourceConfig]
    public let remoteTarget: ControlPlaneChatRequest.RemoteTarget?
    public let computerUseAuthorizationSigner:
        ComputerUseToolAuthorizationSigner?
    public let validateComputerUseTargets: ValidateComputerUseTargets?
    public let startChat: ControlPlaneAgentModelPort.StartChat

    public init(
        worker: any AgentToolRuntimeWorkerClientProtocol,
        approvalPolicy: any AgentApprovalPolicyManaging,
        approvalContextRegistry: AgentApprovalContextRegistry? = nil,
        sourceConfigs: [Melix_Worker_V1_AgentToolSourceConfig],
        remoteTarget: ControlPlaneChatRequest.RemoteTarget? = nil,
        computerUseAuthorizationSigner:
            ComputerUseToolAuthorizationSigner? = nil,
        validateComputerUseTargets: ValidateComputerUseTargets? = nil,
        startChat: @escaping ControlPlaneAgentModelPort.StartChat
    ) {
        self.worker = worker
        self.approvalPolicy = approvalPolicy
        self.approvalContextRegistry = approvalContextRegistry
        self.sourceConfigs = sourceConfigs
        self.remoteTarget = remoteTarget
        self.computerUseAuthorizationSigner =
            computerUseAuthorizationSigner
        self.validateComputerUseTargets = validateComputerUseTargets
        self.startChat = startChat
    }
}

public actor ControlPlaneAgentRuntime {
    private static let interruptedByRestartErrorCode =
        "agent_run_interrupted_by_restart"

    public typealias EventPublisher = @Sendable (
        Melix_Controlplane_V1_AgentRunSnapshot,
        String
    ) async -> Void

    private struct RunRecord {
        let coordinator: AgentRunCoordinator
        let commandGate: AgentRunCommandGate
        let eventGate: AgentRunCommandGate
        let approvalPolicy: any AgentApprovalPolicyManaging
        let approvalContextRegistry: AgentApprovalContextRegistry?
        var snapshot: Melix_Controlplane_V1_AgentRunSnapshot
        var pendingApproval: AgentApprovalRequest?
        var toolStartedAt: [String: Date]
        var eventTask: Task<Void, Never>?
        var deadlineTask: Task<Void, Never>?
        var snapshotFlushTask: Task<Void, Never>?
        var journalPersistenceFailed: Bool
        var lastSnapshotPersistedAtUnixMs: Int64
        var unpersistedSnapshotBytes: Int
        let toolSourceOwnerKey: ToolSourceOwnerKey?
        var toolSourcesReleased: Bool
    }

    private struct ToolSourceOwnerKey: Hashable, Sendable {
        let sessionID: String
        let branchID: String
        let actorID: String
        let sourceConfigDigest: String
    }

    private struct ToolSourceOwnerLease: Sendable {
        var userCount: Int
        var expiresAtUnixMs: Int64
        var leaseTTLMilliseconds: UInt32
        var renew: @Sendable (UInt32) async throws -> Void
        var release: @Sendable () async -> Void
        let operationGate: AgentRunCommandGate
        let generation: UUID
        var heartbeatTask: Task<Void, Never>?
    }

    private struct ToolSourceLeaseReservation: Sendable {
        let ttlMilliseconds: UInt32
        let operationGate: AgentRunCommandGate
    }

    private let now: @Sendable () -> Date
    private let runIDGenerator: @Sendable () -> String
    private let eventPublisher: EventPublisher
    private let durableStore: AgentRunDurableStore?
    private let memoryRetentionLimit: Int
    private let backendCancellationTimeout: Duration
    private let sourceLeaseHeartbeatInterval: Duration
    private var runs: [String: RunRecord] = [:]
    private var runOrder: [String] = []
    private var startingRunIDs: Set<String> = []
    private var startingRunSessions: [String: String] = [:]
    private var startingRunCancellationReasons: [String: AgentCancellationReason] = [:]
    private var toolSourceOwnerLeases: [
        ToolSourceOwnerKey: ToolSourceOwnerLease
    ] = [:]
    private var cancellationReceipts: [
        String: Melix_Controlplane_V1_AgentRunCancellationReceipt
    ] = [:]
    private var cancellationReceiptOrder: [String] = []

    public init(
        now: @escaping @Sendable () -> Date = Date.init,
        runIDGenerator: @escaping @Sendable () -> String = {
            "agent-run-\(UUID().uuidString)"
        },
        durableStore: AgentRunDurableStore? = nil,
        memoryRetentionLimit: Int = 100,
        backendCancellationTimeout: Duration = .seconds(2),
        sourceLeaseHeartbeatInterval: Duration = .seconds(30),
        eventPublisher: @escaping EventPublisher = { _, _ in }
    ) {
        self.now = now
        self.runIDGenerator = runIDGenerator
        self.durableStore = durableStore
        self.memoryRetentionLimit = min(max(memoryRetentionLimit, 1), 500)
        self.backendCancellationTimeout = backendCancellationTimeout
        self.sourceLeaseHeartbeatInterval = max(
            .milliseconds(1),
            sourceLeaseHeartbeatInterval
        )
        self.eventPublisher = eventPublisher
    }

    public func start(
        command: Melix_Controlplane_V1_StartAgentRun,
        actorID: String,
        dependencies: ControlPlaneAgentRuntimeStartDependencies
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        let deadlineUnixMs = command.deadlineUnixMs
        let startedAt = try requireUnexpiredMutation(deadlineUnixMs)
        let modelID = command.modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let sessionID = command.sessionID.trimmingCharacters(in: .whitespacesAndNewlines)
        let requestedBranchID = command.branchID.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let branchID = requestedBranchID.isEmpty ? "branch-main" : requestedBranchID
        let actorID = actorID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !modelID.isEmpty else {
            throw ControlPlaneAgentRuntimeError.invalidRequest("model_id is required")
        }
        guard !sessionID.isEmpty else {
            throw ControlPlaneAgentRuntimeError.invalidRequest("session_id is required")
        }
        guard !actorID.isEmpty else {
            throw ControlPlaneAgentRuntimeError.invalidRequest("actor_id is required")
        }
        guard Self.isValidOwnerComponent(sessionID),
              Self.isValidOwnerComponent(branchID),
              Self.isValidOwnerComponent(actorID) else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "session_id, branch_id, and actor_id must be valid owner identifiers"
            )
        }
        guard command.mode == .act else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "Agent runs require ACT interaction mode"
            )
        }
        guard !command.messages.isEmpty else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "at least one message is required"
            )
        }
        guard command.messages.count <= Self.maximumMessageCount,
              Self.messagesFitWireBudget(command.messages)
        else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "agent messages exceed bounded size or cardinality"
            )
        }
        let maxModelTurns = command.maxModelTurns > 0
            ? Int(command.maxModelTurns)
            : 8
        let maxToolCalls = command.maxToolCalls > 0
            ? Int(command.maxToolCalls)
            : 8
        guard maxModelTurns <= Self.maximumModelTurns,
              maxToolCalls <= Self.maximumToolCalls
        else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "agent run limits exceed the supported maximum"
            )
        }
        let parsedMessages = try Self.messages(from: command.messages)
        let trustedComputerUseTargets: [TrustedComputerUseTarget]
        do {
            trustedComputerUseTargets = try command.computerUseTargets.map(
                TrustedComputerUseTarget.init
            )
        } catch {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "computer_use_targets contains an invalid target identity"
            )
        }
        guard trustedComputerUseTargets.count <= 1 else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "computer_use_targets must contain at most one selected window"
            )
        }

        let requestedRunID = command.runID.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let runID = (requestedRunID.isEmpty ? runIDGenerator() : requestedRunID)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard Self.isValidRunID(runID),
              runs[runID] == nil,
              !startingRunIDs.contains(runID),
              cancellationReceipts[runID] == nil else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "agent run ID must be unique and non-empty"
            )
        }
        startingRunIDs.insert(runID)
        startingRunSessions[runID] = sessionID
        defer {
            startingRunIDs.remove(runID)
            startingRunSessions.removeValue(forKey: runID)
            startingRunCancellationReasons.removeValue(forKey: runID)
        }
        if let durableStore {
            let existing: Melix_Controlplane_V1_AgentRunSnapshot?
            let existingCancellation:
                Melix_Controlplane_V1_AgentRunCancellationReceipt?
            do {
                existing = try await durableStore.snapshot(runID: runID)
                existingCancellation = try await durableStore.cancellation(
                    runID: runID
                )
            } catch {
                throw ControlPlaneAgentRuntimeError.journalPersistenceFailed
            }
            guard existing == nil, existingCancellation == nil else {
                throw ControlPlaneAgentRuntimeError.invalidRequest(
                    "agent run ID must be unique and non-empty"
                )
            }
        }
        try requireStartAdmissionOpen(runID)

        let catalogLoader = AgentRuntimeToolCatalogLoader(
            worker: dependencies.worker,
            sourceConfigs: dependencies.sourceConfigs
        )
        let requestedSourceLeaseTTL = Self.sourceLeaseTTLMilliseconds(
            deadlineUnixMs: deadlineUnixMs,
            now: startedAt
        )
        var effectiveSourceLeaseTTL = requestedSourceLeaseTTL
        let toolSourceOwnerKey: ToolSourceOwnerKey?
        var catalogOperationGate: AgentRunCommandGate?
        if dependencies.sourceConfigs.isEmpty {
            toolSourceOwnerKey = nil
        } else {
            let ownerKey = ToolSourceOwnerKey(
                sessionID: sessionID,
                branchID: branchID,
                actorID: actorID,
                sourceConfigDigest: Self.toolSourceConfigDigest(
                    dependencies.sourceConfigs
                )
            )
            let reservation = try await reserveToolSourceOwnerLease(
                ownerKey,
                requestedTTLMilliseconds: requestedSourceLeaseTTL,
                now: startedAt,
                renew: { @Sendable ttlMilliseconds in
                    _ = try await catalogLoader.load(
                        sessionID: sessionID,
                        branchID: branchID,
                        actorID: actorID,
                        deadlineUnixMs: Self.unixMilliseconds(Date()) + 2_000,
                        leaseTtlMs: ttlMilliseconds,
                        refreshSources: false
                    )
                },
                release: { @Sendable in
                    _ = try? await catalogLoader.release(
                        sessionID: sessionID,
                        branchID: branchID,
                        actorID: actorID,
                        deadlineUnixMs: Self.unixMilliseconds(Date()) + 2_000
                    )
                }
            )
            effectiveSourceLeaseTTL = reservation.ttlMilliseconds
            await reservation.operationGate.acquire()
            catalogOperationGate = reservation.operationGate
            toolSourceOwnerKey = ownerKey
        }
        let catalog: AgentRuntimeToolCatalog
        do {
            let unscopedCatalog = try await catalogLoader.load(
                sessionID: sessionID,
                branchID: branchID,
                actorID: actorID,
                deadlineUnixMs: deadlineUnixMs,
                leaseTtlMs: effectiveSourceLeaseTTL
            )
            if !trustedComputerUseTargets.isEmpty {
                guard let computerDescriptor = unscopedCatalog.descriptor(
                    named: "computer_use"
                ),
                computerDescriptor.sourceID == "computer",
                dependencies.computerUseAuthorizationSigner != nil,
                let validateComputerUseTargets =
                    dependencies.validateComputerUseTargets else {
                    throw ControlPlaneAgentRuntimeError.invalidRequest(
                        "Computer Use target selection is unavailable"
                    )
                }
                try await validateComputerUseTargets(
                    trustedComputerUseTargets,
                    computerDescriptor,
                    deadlineUnixMs
                )
            }
            catalog = try unscopedCatalog.withTrustedComputerUseTargets(
                trustedComputerUseTargets
            )
            _ = try requireUnexpiredMutation(deadlineUnixMs)
            try requireStartAdmissionOpen(runID)
            if let catalogOperationGate {
                await catalogOperationGate.release()
            }
            catalogOperationGate = nil
        } catch {
            if let catalogOperationGate {
                await catalogOperationGate.release()
            }
            catalogOperationGate = nil
            if let toolSourceOwnerKey {
                await relinquishToolSourceOwnerLease(toolSourceOwnerKey)
            }
            throw error
        }
        do {
            try requireStartAdmissionOpen(runID)
        } catch {
            if let toolSourceOwnerKey {
                await relinquishToolSourceOwnerLease(toolSourceOwnerKey)
            }
            throw error
        }
        let modelPort = ControlPlaneAgentModelPort(
            configuration: ControlPlaneAgentModelConfiguration(
                modelID: modelID,
                serverSessionID: command.serverSessionID,
                remoteTarget: dependencies.remoteTarget
            ),
            catalog: catalog,
            startChat: dependencies.startChat
        )
        let toolPort = WorkerAgentToolExecutionPort(
            worker: dependencies.worker,
            context: WorkerAgentToolExecutionContext(
                sessionID: sessionID,
                branchID: branchID,
                actorID: actorID,
                deadlineUnixMs: deadlineUnixMs,
                trustedComputerUseTargets: trustedComputerUseTargets,
                computerUseAuthorizationSigner:
                    dependencies.computerUseAuthorizationSigner
            )
        )
        if let approvalContextRegistry = dependencies.approvalContextRegistry {
            await approvalContextRegistry.register(
                runID: runID,
                sessionID: sessionID,
                branchID: branchID
            )
        }
        let coordinator = AgentRunCoordinator(
            modelTurns: modelPort,
            tools: toolPort,
            approvalPolicy: dependencies.approvalPolicy,
            cancellationBackendTimeout: backendCancellationTimeout,
            runIDGenerator: { runID }
        )

        var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        snapshot.runID = runID
        snapshot.sessionID = sessionID
        snapshot.branchID = branchID
        snapshot.modelID = modelID
        snapshot.state = "created"
        snapshot.startedAtUnixMs = Int64(startedAt.timeIntervalSince1970 * 1_000)
        snapshot.updatedAtUnixMs = snapshot.startedAtUnixMs
        snapshot.revision = 1

        let request = AgentRunRequest(
            messages: parsedMessages,
            toolCatalog: catalog,
            limits: AgentRunLimits(
                maxModelTurns: maxModelTurns,
                maxToolCalls: maxToolCalls,
                maxHealingNudges: 2
            )
        )
        let execution: AgentRunExecution
        do {
            _ = try requireUnexpiredMutation(deadlineUnixMs)
            try requireStartAdmissionOpen(runID)
            execution = try await coordinator.start(request, suspended: true)
            if let durableStore {
                _ = try requireUnexpiredMutation(deadlineUnixMs)
                try await durableStore.persistSnapshot(snapshot)
            }
            try requireStartAdmissionOpen(runID)
        } catch {
            _ = await coordinator.cancel(
                runID: runID,
                reason: .system("agent-run-journal-start-failed")
            )
            if let toolSourceOwnerKey {
                await relinquishToolSourceOwnerLease(toolSourceOwnerKey)
            }
            if let approvalContextRegistry = dependencies.approvalContextRegistry {
                await approvalContextRegistry.unregister(runID: runID)
            }
            if error is AgentRunDurableStoreError {
                throw ControlPlaneAgentRuntimeError.journalPersistenceFailed
            }
            throw error
        }
        let record = RunRecord(
            coordinator: coordinator,
            commandGate: AgentRunCommandGate(),
            eventGate: AgentRunCommandGate(),
            approvalPolicy: dependencies.approvalPolicy,
            approvalContextRegistry: dependencies.approvalContextRegistry,
            snapshot: snapshot,
            pendingApproval: nil,
            toolStartedAt: [:],
            eventTask: nil,
            deadlineTask: nil,
            snapshotFlushTask: nil,
            journalPersistenceFailed: false,
            lastSnapshotPersistedAtUnixMs: snapshot.updatedAtUnixMs,
            unpersistedSnapshotBytes: 0,
            toolSourceOwnerKey: toolSourceOwnerKey,
            toolSourcesReleased: false
        )
        runs[runID] = record
        runOrder.append(runID)

        if deadlineUnixMs > 0 {
            let delayMilliseconds = max(
                0,
                deadlineUnixMs - Int64(startedAt.timeIntervalSince1970 * 1_000)
            )
            runs[runID]?.deadlineTask = Task { [weak self] in
                do {
                    try await Task.sleep(
                        for: .milliseconds(delayMilliseconds)
                    )
                } catch {
                    return
                }
                guard let self else {
                    return
                }
                _ = await self.cancel(
                    runID: runID,
                    reason: .deadlineExceeded
                )
            }
        }
        await eventPublisher(snapshot, "started")
        let eventTask = Task { [weak self] in
            guard let self else {
                return
            }
            for await event in execution.events {
                await self.consume(event, runID: runID)
            }
        }
        runs[runID]?.eventTask = eventTask
        if let cancellationReason = startingRunCancellationReasons[runID] {
            _ = await cancel(runID: runID, reason: cancellationReason)
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "agent run was cancelled before admission completed"
            )
        }
        if !command.deferActivation {
            await coordinator.resume(runID: runID)
            if let cancellationReason = startingRunCancellationReasons[runID] {
                _ = await cancel(runID: runID, reason: cancellationReason)
                throw ControlPlaneAgentRuntimeError.invalidRequest(
                    "agent run was cancelled before admission completed"
                )
            }
        }
        return snapshot
    }

    public func activate(
        runID: String,
        deadlineUnixMs: Int64 = 0
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        _ = try requireUnexpiredMutation(deadlineUnixMs)
        guard let initialRecord = runs[runID] else {
            throw ControlPlaneAgentRuntimeError.unknownRun(runID)
        }
        let gate = initialRecord.commandGate
        await gate.acquire()
        do {
            _ = try requireUnexpiredMutation(deadlineUnixMs)
            guard let record = runs[runID] else {
                throw ControlPlaneAgentRuntimeError.unknownRun(runID)
            }
            await record.coordinator.resume(runID: runID)
            let snapshot = await attachingCancellationReceipt(
                to: record.snapshot
            )
            await gate.release()
            return snapshot
        } catch {
            await gate.release()
            throw error
        }
    }

    public func decideApproval(
        command: Melix_Controlplane_V1_DecideAgentApproval,
        actorID: String,
        deadlineUnixMs: Int64 = 0
    ) async throws -> Melix_Controlplane_V1_AgentApprovalDecisionReceipt {
        _ = try requireUnexpiredMutation(deadlineUnixMs)
        let binding = Self.binding(from: command.binding)
        let actorID = actorID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !actorID.isEmpty else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "actor_id is required"
            )
        }
        guard let initialRecord = runs[binding.runID] else {
            throw ControlPlaneAgentRuntimeError.unknownRun(binding.runID)
        }
        let gate = initialRecord.commandGate
        await gate.acquire()
        do {
            _ = try requireUnexpiredMutation(deadlineUnixMs)
            guard let record = runs[binding.runID] else {
                throw ControlPlaneAgentRuntimeError.unknownRun(binding.runID)
            }
            guard let pending = record.pendingApproval else {
                throw ControlPlaneAgentRuntimeError.approvalNotPending
            }
            guard pending.binding == binding else {
                throw ControlPlaneAgentRuntimeError.invalidApprovalBinding
            }
            guard await record.approvalPolicy.isApprovalBindingCurrent(
                binding,
                for: pending.call,
                runID: binding.runID,
                expectedRequirement: .required
            ) else {
                throw ControlPlaneAgentRuntimeError.staleApprovalBinding
            }
            _ = try requireUnexpiredMutation(deadlineUnixMs)

            let choice: AgentApprovalChoice
            switch command.choice {
            case .agentApprovalAllowOnce:
                choice = .allowOnce
            case .agentApprovalAlwaysAllow:
                choice = .alwaysAllow
            case .agentApprovalDeny:
                choice = .deny
            case .unspecified, .UNRECOGNIZED:
                throw ControlPlaneAgentRuntimeError.invalidRequest(
                    "approval choice is required"
                )
            }

            let decisionID = "agent-decision-\(UUID().uuidString)"
            let decidedAtUnixMs = Self.unixMilliseconds(
                try requireUnexpiredMutation(deadlineUnixMs)
            )
            if let durableStore {
                do {
                    try await durableStore.persistApprovalDecision(
                        AgentApprovalDecisionJournalReceipt(
                            decisionID: decisionID,
                            actorID: actorID,
                            decidedAtUnixMs: decidedAtUnixMs,
                            binding: binding,
                            choice: choice
                        )
                    )
                } catch {
                    throw ControlPlaneAgentRuntimeError.decisionPersistenceFailed
                }
            }

            var policyRevisionAfterDecision = binding.policyRevision
            var resultingBinding: AgentApprovalBinding?
            var policyPersistenceDisposition:
                Melix_Controlplane_V1_AgentApprovalPolicyPersistenceDisposition =
                    .agentApprovalPolicyPersistenceNotRequested
            var policyPersistenceError = Melix_Controlplane_V1_ErrorStatus()
            if choice == .alwaysAllow {
                do {
                    let reconciliation = try await reconcileCommittedAlwaysAllow(
                        policy: record.approvalPolicy,
                        call: pending.call,
                        binding: binding,
                        requestDeadlineUnixMs: deadlineUnixMs
                    )
                    policyRevisionAfterDecision = reconciliation.revision
                    resultingBinding = reconciliation.binding
                    policyPersistenceDisposition =
                        .agentApprovalPolicyPersistenceApplied
                } catch {
                    // The immutable operator decision already committed. Keep
                    // its exact choice bound to the current call, but do not
                    // claim that the persistent policy was saved. With no
                    // resulting binding the coordinator revalidates this call
                    // against the original required-approval scope.
                    policyPersistenceDisposition =
                        .agentApprovalPolicyPersistenceNotApplied
                    policyPersistenceError.code =
                        "agent_approval_policy_persistence_failed"
                    policyPersistenceError.message =
                        "This call was approved, but Always Allow could not be saved."
                    policyPersistenceError.retriable = false
                }
            }
            // The immutable operator-decision journal is the command's commit
            // boundary. Once it has been persisted (and an Always Allow CAS
            // has possibly advanced policy), finish delivering that exact
            // decision to the already-bound coordinator even if the RPC
            // deadline expires in the meantime. Rechecking here would strand
            // the run on a stale pending binding after durable policy changed.
            do {
                try await record.coordinator.decideApproval(
                    AgentApprovalDecision(
                        binding: binding,
                        choice: choice,
                        resultingBinding: resultingBinding
                    )
                )
            } catch {
                _ = await record.coordinator.cancel(
                    runID: binding.runID,
                    reason: .system(
                        "committed-approval-delivery-failed"
                    )
                )
                if var current = runs[binding.runID],
                   current.pendingApproval?.binding == binding {
                    current.pendingApproval = nil
                    current.snapshot.clearPendingApproval()
                    current.snapshot.updatedAtUnixMs = Self.unixMilliseconds(
                        now()
                    )
                    current.snapshot.revision = Self.nextSnapshotRevision(
                        after: current.snapshot.revision
                    )
                    runs[binding.runID] = current
                }
                throw error
            }
            if var current = runs[binding.runID] {
                if current.pendingApproval?.binding == binding {
                    current.pendingApproval = nil
                    current.snapshot.clearPendingApproval()
                    current.snapshot.updatedAtUnixMs = Self.unixMilliseconds(
                        now()
                    )
                    current.snapshot.revision = Self.nextSnapshotRevision(
                        after: current.snapshot.revision
                    )
                    runs[binding.runID] = current
                    await eventPublisher(current.snapshot, "approval_decided")
                }
            }

            var receipt = Melix_Controlplane_V1_AgentApprovalDecisionReceipt()
            receipt.binding = command.binding
            receipt.choice = command.choice
            receipt.decisionID = decisionID
            receipt.actorID = actorID
            receipt.decidedAtUnixMs = decidedAtUnixMs
            receipt.policyRevisionAfterDecision = policyRevisionAfterDecision
            receipt.policyPersistenceDisposition =
                policyPersistenceDisposition
            if !policyPersistenceError.code.isEmpty {
                receipt.policyPersistenceError = policyPersistenceError
            }
            await gate.release()
            return receipt
        } catch {
            await gate.release()
            throw error
        }
    }

    @discardableResult
    private func requireUnexpiredMutation(
        _ deadlineUnixMs: Int64
    ) throws -> Date {
        try Task.checkCancellation()
        let observedAt = now()
        guard deadlineUnixMs <= 0
            || deadlineUnixMs > Self.unixMilliseconds(observedAt)
        else {
            throw ControlPlaneAgentRuntimeError.deadlineExceeded
        }
        return observedAt
    }

    private func requireStartAdmissionOpen(_ runID: String) throws {
        guard startingRunCancellationReasons[runID] == nil else {
            throw ControlPlaneAgentRuntimeError.invalidRequest(
                "agent run was cancelled before admission completed"
            )
        }
    }

    private func reconcileCommittedAlwaysAllow(
        policy: any AgentApprovalPolicyManaging,
        call: AgentToolCall,
        binding: AgentApprovalBinding,
        requestDeadlineUnixMs: Int64
    ) async throws -> (revision: String, binding: AgentApprovalBinding) {
        var deadlineUnixMs = requestDeadlineUnixMs
        for _ in 0..<8 {
            let evaluation = await policy.approvalEvaluation(
                for: call,
                runID: binding.runID
            )
            let currentRevision = evaluation.policyRevision.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            guard !currentRevision.isEmpty else {
                throw ControlPlaneAgentRuntimeError.policyPersistenceFailed
            }
            if evaluation.requirement == .notRequired {
                return (
                    currentRevision,
                    AgentApprovalBinding.make(
                        runID: binding.runID,
                        call: call,
                        policyRevision: currentRevision,
                        scopeDigest: evaluation.scopeDigest
                    )
                )
            }
            do {
                _ = try await policy.persistAlwaysAllow(
                    for: call,
                    runID: binding.runID,
                    expectedRevision: currentRevision,
                    deadlineUnixMs: deadlineUnixMs
                )
            } catch ApprovalPolicyStoreError.revisionMismatch,
                    ApprovalPolicyStoreError.deadlineExceeded {
                deadlineUnixMs = 0
                await Task.yield()
                continue
            } catch {
                deadlineUnixMs = 0
                await Task.yield()
                continue
            }
            deadlineUnixMs = 0
        }
        throw ControlPlaneAgentRuntimeError.policyPersistenceFailed
    }

    public func cancel(
        runID: String,
        reason: AgentCancellationReason
    ) async -> Melix_Controlplane_V1_AgentRunCancellationReceipt {
        // A caller-generated run ID lets Stop close admission while the start
        // RPC is still loading catalogs or validating targets. Record that
        // terminal intent before any await so a re-entrant start path cannot
        // cross into provider or tool execution.
        if runs[runID] == nil, startingRunIDs.contains(runID) {
            if let cached = cancellationReceipts[runID] {
                return cached
            }
            if startingRunCancellationReasons[runID] == nil {
                startingRunCancellationReasons[runID] = reason
            }
            let receipt = Self.admissionCancellationReceipt(for: runID)
            if let durableStore {
                do {
                    try await durableStore.persistCancellation(receipt)
                } catch {
                    return Self.unavailableCancellationReceipt(for: runID)
                }
            }
            cacheCancellationReceipt(receipt)
            return receipt
        }
        // A corrupt or unavailable historical receipt must never prevent the
        // bounded live cancellation path from reaching the coordinator. Only
        // consult archived truth when no in-memory run currently exists; if a
        // run appears while an async journal read is in flight, fall through
        // to the live path instead of returning the historical observation.
        if runs[runID] == nil, let durableStore,
           let archivedReceipt = await archivedCancellationReceipt(
            runID: runID,
            durableStore: durableStore
           ), runs[runID] == nil {
            return archivedReceipt
        }
        guard let initialRecord = runs[runID] else {
            var missing = Melix_Controlplane_V1_AgentRunCancellationReceipt()
            missing.runID = runID
            missing.cancellationID = Self.cancellationID(for: runID)
            missing.disposition = "not_found"
            return missing
        }
        let gate = initialRecord.commandGate
        await gate.acquire()
        guard let record = runs[runID] else {
            await gate.release()
            var missing = Melix_Controlplane_V1_AgentRunCancellationReceipt()
            missing.runID = runID
            missing.cancellationID = Self.cancellationID(for: runID)
            missing.disposition = "not_found"
            return missing
        }
        let eventGate = record.eventGate
        let eventTask = record.eventTask
        let cancellation = await record.coordinator.cancel(
            runID: runID,
            reason: reason
        )
        await releaseToolSourcesIfNeeded(runID: runID)
        // `finalizeCancellation` closes the event stream after enqueueing the
        // exact cancelled receipt. Drain that captured task before the final
        // gated replacement so no older queued event can regress the durable
        // snapshot after this cancellation RPC returns.
        await eventTask?.value
        guard let receipt = await persistLiveCancellationTruth(
            cancellation,
            runID: runID,
            eventGate: eventGate
        ) else {
            let unavailable = Self.unavailableCancellationReceipt(for: runID)
            await gate.release()
            return unavailable
        }
        if let durableStore {
            // The terminal snapshot is the authoritative receipt. This
            // bounded secondary index accelerates lookup but its maintenance
            // or eviction must never downgrade embedded side-effect truth.
            try? await durableStore.persistCancellation(receipt)
        }
        cacheCancellationReceipt(receipt)
        await gate.release()
        return receipt
    }

    public func snapshot(
        runID: String
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        if let record = runs[runID] {
            return await attachingCancellationReceipt(to: record.snapshot)
        }
        if let durableStore {
            do {
                if let persisted = try await durableStore.snapshot(runID: runID) {
                    let reconciled = try await reconcileArchivedSnapshotIfNeeded(
                        persisted,
                        durableStore: durableStore
                    )
                    return await attachingCancellationReceipt(to: reconciled)
                }
            } catch {
                throw ControlPlaneAgentRuntimeError.journalPersistenceFailed
            }
        }
        throw ControlPlaneAgentRuntimeError.unknownRun(runID)
    }

    public func snapshots(
        sessionID: String = "",
        limit: Int = 100
    ) async -> [Melix_Controlplane_V1_AgentRunSnapshot] {
        let boundedLimit = min(max(limit, 1), 500)
        var byRunID: [String: Melix_Controlplane_V1_AgentRunSnapshot] = [:]
        if let durableStore,
           let persisted = try? await durableStore.snapshots(
            sessionID: sessionID,
            limit: boundedLimit
           ) {
            for snapshot in persisted {
                let reconciled = Self.interruptedByRestartSnapshot(
                    snapshot,
                    at: now()
                )
                if reconciled.state != snapshot.state {
                    try? await durableStore.persistSnapshot(reconciled)
                }
                byRunID[reconciled.runID] = reconciled
            }
        }
        for runID in runOrder {
            guard let snapshot = runs[runID]?.snapshot else {
                continue
            }
            guard sessionID.isEmpty || snapshot.sessionID == sessionID else {
                continue
            }
            byRunID[runID] = snapshot
        }
        let ordered = Array(byRunID.values.sorted { lhs, rhs in
            if lhs.updatedAtUnixMs == rhs.updatedAtUnixMs {
                return lhs.runID > rhs.runID
            }
            return lhs.updatedAtUnixMs > rhs.updatedAtUnixMs
        }.prefix(boundedLimit))
        var enriched: [Melix_Controlplane_V1_AgentRunSnapshot] = []
        enriched.reserveCapacity(ordered.count)
        for snapshot in ordered {
            enriched.append(
                await attachingCancellationReceipt(to: snapshot)
            )
        }
        return enriched
    }

    /// Authoritative safety inventory for destructive-action reconciliation.
    /// Unlike presentation history, this path never skips a corrupt durable
    /// entry and never rewrites an interrupted nonterminal run into terminal
    /// history before the caller has observed the recovery conflict.
    public func nonterminalSnapshotPage(
        sessionID: String = "",
        limit: Int = 500
    ) async throws -> AgentRunDurableSnapshotPage {
        let boundedLimit = min(max(limit, 1), 500)
        var byRunID: [String: Melix_Controlplane_V1_AgentRunSnapshot] = [:]
        var durableComplete = true
        if let durableStore {
            do {
                let page = try await durableStore.nonterminalSnapshotPage(
                    sessionID: sessionID,
                    limit: boundedLimit
                )
                durableComplete = page.isComplete
                for snapshot in page.snapshots {
                    byRunID[snapshot.runID] = snapshot
                }
            } catch {
                throw ControlPlaneAgentRuntimeError.journalPersistenceFailed
            }
        }
        for runID in runOrder {
            guard let snapshot = runs[runID]?.snapshot,
                  !Self.isTerminalStateName(snapshot.state),
                  sessionID.isEmpty || snapshot.sessionID == sessionID else {
                continue
            }
            byRunID[runID] = snapshot
        }
        let ordered = byRunID.values.sorted { lhs, rhs in
            if lhs.updatedAtUnixMs == rhs.updatedAtUnixMs {
                return lhs.runID > rhs.runID
            }
            return lhs.updatedAtUnixMs > rhs.updatedAtUnixMs
        }
        var enriched: [Melix_Controlplane_V1_AgentRunSnapshot] = []
        for snapshot in ordered.prefix(boundedLimit) {
            enriched.append(await attachingCancellationReceipt(to: snapshot))
        }
        return AgentRunDurableSnapshotPage(
            snapshots: enriched,
            isComplete: durableComplete
                && ordered.count <= boundedLimit
                && !startingRunSessions.values.contains(where: {
                    sessionID.isEmpty || $0 == sessionID
                })
        )
    }

    private func archivedCancellationReceipt(
        runID: String,
        durableStore: AgentRunDurableStore
    ) async -> Melix_Controlplane_V1_AgentRunCancellationReceipt? {
        let archived: Melix_Controlplane_V1_AgentRunSnapshot?
        do {
            archived = try await durableStore.snapshot(runID: runID)
        } catch {
            // A separately durable exact receipt still carries more truth than
            // a corrupt presentation snapshot. It remains the migration
            // fallback for journals written before receipt embedding.
            if let persisted = try? await durableStore.cancellation(
                runID: runID
            ) {
                cacheCancellationReceipt(persisted)
                return persisted
            }
            return Self.unavailableCancellationReceipt(for: runID)
        }

        let cached = cancellationReceipts[runID]
        let persisted: Melix_Controlplane_V1_AgentRunCancellationReceipt?
        let secondaryReadFailed: Bool
        do {
            persisted = try await durableStore.cancellation(runID: runID)
            secondaryReadFailed = false
        } catch {
            persisted = nil
            secondaryReadFailed = true
        }
        guard let archived else {
            if secondaryReadFailed {
                return Self.unavailableCancellationReceipt(for: runID)
            }
            if let cached, let persisted, cached != persisted {
                return Self.unavailableCancellationReceipt(for: runID)
            }
            if let receipt = cached ?? persisted {
                cacheCancellationReceipt(receipt)
                return receipt
            }
            return nil
        }

        let reconciled: Melix_Controlplane_V1_AgentRunSnapshot
        do {
            reconciled = try await reconcileArchivedSnapshotIfNeeded(
                archived,
                durableStore: durableStore
            )
        } catch {
            return Self.unavailableCancellationReceipt(for: runID)
        }
        if reconciled.hasCancellationReceipt {
            let embedded = reconciled.cancellationReceipt
            if let cached, cached != embedded {
                return Self.unavailableCancellationReceipt(for: runID)
            }
            if let persisted, persisted != embedded {
                return Self.unavailableCancellationReceipt(for: runID)
            }
            cacheCancellationReceipt(embedded)
            return embedded
        }
        if secondaryReadFailed {
            return Self.unavailableCancellationReceipt(for: runID)
        }
        if let cached, let persisted, cached != persisted {
            return Self.unavailableCancellationReceipt(for: runID)
        }
        if let receipt = cached ?? persisted {
            do {
                _ = try await persistEmbeddedCancellationReceipt(
                    receipt,
                    in: reconciled,
                    durableStore: durableStore
                )
            } catch {
                return Self.unavailableCancellationReceipt(for: runID)
            }
            cacheCancellationReceipt(receipt)
            return receipt
        }

        // A cancelled snapshot without the receipt that established its
        // side-effect disposition is incomplete durable truth. Never invent
        // `already_terminal/none` for that corruption case.
        guard reconciled.state != "cancelled" else {
            return Self.unavailableCancellationReceipt(for: runID)
        }
        guard Self.isTerminalStateName(reconciled.state) else {
            return Self.unavailableCancellationReceipt(for: runID)
        }
        var receipt = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        receipt.runID = runID
        receipt.cancellationID = Self.cancellationID(for: runID)
        receipt.disposition = "already_terminal"
        receipt.sideEffectState = reconciled.error.code
            == Self.interruptedByRestartErrorCode
            ? .agentToolSideEffectUnknown
            : .agentToolSideEffectNone
        do {
            _ = try await persistEmbeddedCancellationReceipt(
                receipt,
                in: reconciled,
                durableStore: durableStore
            )
        } catch {
            return Self.unavailableCancellationReceipt(for: runID)
        }
        try? await durableStore.persistCancellation(receipt)
        cacheCancellationReceipt(receipt)
        return receipt
    }

    private func persistEmbeddedCancellationReceipt(
        _ receipt: Melix_Controlplane_V1_AgentRunCancellationReceipt,
        in snapshot: Melix_Controlplane_V1_AgentRunSnapshot,
        durableStore: AgentRunDurableStore
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        guard !snapshot.hasCancellationReceipt else {
            guard snapshot.cancellationReceipt == receipt else {
                throw ControlPlaneAgentRuntimeError.journalPersistenceFailed
            }
            return snapshot
        }
        var enriched = snapshot
        enriched.cancellationReceipt = receipt
        enriched.updatedAtUnixMs = Self.unixMilliseconds(now())
        enriched.revision = Self.nextSnapshotRevision(after: enriched.revision)
        try await durableStore.persistSnapshot(enriched)
        return enriched
    }

    /// Commits the cancellation receipt and terminal state through the same
    /// per-run event gate used by snapshot events. The run record may already
    /// have been evicted after its terminal event, so durable truth is also a
    /// valid source for the final exact replacement.
    private func persistLiveCancellationTruth(
        _ cancellation: AgentCancellationReceipt,
        runID: String,
        eventGate: AgentRunCommandGate
    ) async -> Melix_Controlplane_V1_AgentRunCancellationReceipt? {
        await eventGate.acquire()
        var snapshot: Melix_Controlplane_V1_AgentRunSnapshot
        if var record = runs[runID] {
            let projected = Self.cancellationReceipt(
                from: cancellation,
                runID: runID,
                snapshot: record.snapshot
            )
            if record.snapshot.hasCancellationReceipt,
               record.snapshot.cancellationReceipt != projected {
                await eventGate.release()
                return nil
            }
            guard Self.isTerminalStateName(record.snapshot.state) else {
                await eventGate.release()
                return nil
            }
            let changed = !record.snapshot.hasCancellationReceipt
            record.snapshot.cancellationReceipt = projected
            if changed {
                record.snapshot.updatedAtUnixMs = Self.unixMilliseconds(now())
                record.snapshot.revision = Self.nextSnapshotRevision(
                    after: record.snapshot.revision
                )
            }
            record.snapshotFlushTask?.cancel()
            record.snapshotFlushTask = nil
            record.unpersistedSnapshotBytes = 0
            record.lastSnapshotPersistedAtUnixMs =
                record.snapshot.updatedAtUnixMs
            snapshot = record.snapshot
            runs[runID] = record
        } else if let durableStore {
            do {
                guard var durable = try await durableStore.snapshot(
                    runID: runID
                ) else {
                    await eventGate.release()
                    return nil
                }
                let projected = Self.cancellationReceipt(
                    from: cancellation,
                    runID: runID,
                    snapshot: durable
                )
                if durable.hasCancellationReceipt,
                   durable.cancellationReceipt != projected {
                    await eventGate.release()
                    return nil
                }
                guard Self.isTerminalStateName(durable.state) else {
                    await eventGate.release()
                    return nil
                }
                let changed = !durable.hasCancellationReceipt
                durable.cancellationReceipt = projected
                if changed {
                    durable.updatedAtUnixMs = Self.unixMilliseconds(now())
                    durable.revision = Self.nextSnapshotRevision(
                        after: durable.revision
                    )
                }
                snapshot = durable
            } catch {
                await eventGate.release()
                return nil
            }
        } else {
            await eventGate.release()
            if let cached = cancellationReceipts[runID],
               cached.runID == runID {
                return cached
            }
            return Self.cancellationReceipt(
                from: cancellation,
                runID: runID,
                snapshot: .init()
            )
        }
        if let durableStore {
            do {
                try await durableStore.persistSnapshot(snapshot)
            } catch {
                if runs[runID] != nil {
                    await failRunForJournalPersistence(runID: runID)
                }
                await eventGate.release()
                return nil
            }
        }
        let exact = snapshot.cancellationReceipt
        await eventGate.release()
        return exact
    }

    private func attachingCancellationReceipt(
        to snapshot: Melix_Controlplane_V1_AgentRunSnapshot
    ) async -> Melix_Controlplane_V1_AgentRunSnapshot {
        var enriched = snapshot
        if snapshot.hasCancellationReceipt {
            let embedded = snapshot.cancellationReceipt
            if let cached = cancellationReceipts[snapshot.runID],
               cached != embedded {
                enriched.cancellationReceipt =
                    Self.unavailableCancellationReceipt(for: snapshot.runID)
                return enriched
            }
            if let durableStore {
                do {
                    if let persisted = try await durableStore.cancellation(
                        runID: snapshot.runID
                    ), persisted != embedded {
                        enriched.cancellationReceipt =
                            Self.unavailableCancellationReceipt(
                                for: snapshot.runID
                            )
                        return enriched
                    }
                } catch {
                    // The embedded receipt is primary durable truth. A corrupt
                    // or unavailable secondary index cannot erase it.
                }
            }
            cacheCancellationReceipt(embedded)
            return enriched
        }
        if let cached = cancellationReceipts[snapshot.runID] {
            enriched.cancellationReceipt = cached
            return enriched
        }
        guard let durableStore else {
            if snapshot.state == "cancelled" {
                enriched.cancellationReceipt =
                    Self.unavailableCancellationReceipt(for: snapshot.runID)
            }
            return enriched
        }
        do {
            guard let persisted = try await durableStore.cancellation(
                runID: snapshot.runID
            ) else {
                if snapshot.state == "cancelled" {
                    enriched.cancellationReceipt =
                        Self.unavailableCancellationReceipt(
                            for: snapshot.runID
                        )
                }
                return enriched
            }
            cacheCancellationReceipt(persisted)
            enriched.cancellationReceipt = persisted
        } catch {
            let unavailable = Self.unavailableCancellationReceipt(
                for: snapshot.runID
            )
            cacheCancellationReceipt(unavailable)
            enriched.cancellationReceipt = unavailable
        }
        return enriched
    }

    private func reconcileArchivedSnapshotIfNeeded(
        _ snapshot: Melix_Controlplane_V1_AgentRunSnapshot,
        durableStore: AgentRunDurableStore
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        let reconciled = Self.interruptedByRestartSnapshot(
            snapshot,
            at: now()
        )
        guard reconciled.state != snapshot.state else {
            return snapshot
        }
        try await durableStore.persistSnapshot(reconciled)
        return reconciled
    }

    public func approvalDecisionReceipts(
        runID: String,
        limit: Int = 100
    ) async -> [AgentApprovalDecisionJournalReceipt] {
        guard let durableStore else {
            return []
        }
        return (try? await durableStore.approvalDecisions(
            runID: runID,
            limit: limit
        )) ?? []
    }

    func retainedRunCount() -> Int {
        runs.count
    }

    func pendingSerializedEventCount(runID: String) async -> Int {
        guard let gate = runs[runID]?.eventGate else {
            return 0
        }
        return await gate.waiterCount()
    }

    private func consume(_ event: AgentRunEvent, runID: String) async {
        guard let gate = runs[runID]?.eventGate else {
            return
        }
        await gate.acquire()
        await consumeSerialized(event, runID: runID)
        await gate.release()
    }

    private func consumeSerialized(
        _ event: AgentRunEvent,
        runID: String
    ) async {
        guard var record = runs[runID], !record.journalPersistenceFailed else {
            return
        }
        var changeKind = "updated"
        var shouldReleaseApprovalContext = false
        var highFrequencyPayloadBytes = 0
        var exactCancellationReceipt:
            Melix_Controlplane_V1_AgentRunCancellationReceipt?
        switch event {
        case .started:
            record.snapshot.state = "created"
            changeKind = "started"
        case .stateChanged(let state):
            if case .cancelled = state {
                // The following `.cancelled(receipt)` event is the only
                // cancellation terminal commit. Persisting this intermediate
                // state would create a crash window with no side-effect truth.
                return
            }
            record.snapshot.state = Self.stateName(state)
            changeKind = "state"
        case .modelTurnStarted(let turn):
            record.snapshot.modelTurnCount = UInt32(turn.index)
            changeKind = "model_turn_started"
        case .modelTurnStreamed(_, let streamEvent):
            switch streamEvent {
            case .textDelta(let text):
                record.snapshot.assistantText += text
                highFrequencyPayloadBytes = text.utf8.count
                changeKind = "assistant_delta"
            case .reasoningDelta:
                changeKind = "reasoning_delta"
            case .toolCallDelta:
                changeKind = "tool_call_delta"
            }
        case .modelTurnCompleted(_, let result):
            if !result.assistantText.isEmpty,
               record.snapshot.assistantText != result.assistantText,
               !record.snapshot.assistantText.hasSuffix(result.assistantText) {
                record.snapshot.assistantText += result.assistantText
            }
            changeKind = "model_turn_completed"
        case .healingNudge:
            changeKind = "tool_call_healing_nudge"
        case .toolCallStateChanged(let call, let state):
            let toolUpdatedAt = now()
            Self.upsertToolCall(
                call,
                state: state,
                record: &record,
                at: toolUpdatedAt
            )
            if let projection = AgentComputerUseSessionProjector.record(
                call: call,
                state: state,
                current: record.snapshot.hasComputerUseSession
                    ? record.snapshot.computerUseSession
                    : nil,
                updatedAtUnixMs: Self.unixMilliseconds(toolUpdatedAt)
            ) {
                record.snapshot.computerUseSession = projection
            }
            changeKind = "tool_call"
        case .toolCallCompleted(let call, let result):
            let toolUpdatedAt = now()
            Self.upsertToolCall(
                call,
                state: .completed,
                result: result,
                record: &record,
                at: toolUpdatedAt
            )
            if let projection = AgentComputerUseSessionProjector.project(
                call: call,
                result: result,
                current: record.snapshot.hasComputerUseSession
                    ? record.snapshot.computerUseSession
                    : nil,
                updatedAtUnixMs: Self.unixMilliseconds(toolUpdatedAt)
            ) {
                record.snapshot.computerUseSession = projection
            }
            changeKind = "tool_call_completed"
        case .approvalRequired(let approval):
            record.pendingApproval = approval
            record.snapshot.pendingApproval = Self.pendingApproval(
                from: approval,
                sessionID: record.snapshot.sessionID,
                branchID: record.snapshot.branchID
            )
            changeKind = "approval_required"
        case .approvalDecided:
            record.pendingApproval = nil
            record.snapshot.clearPendingApproval()
            changeKind = "approval_decided"
        case .completed(let completion):
            record.snapshot.state = "completed"
            record.snapshot.modelTurnCount = UInt32(completion.modelTurnCount)
            record.snapshot.toolCallCount = UInt32(completion.toolCallCount)
            if !completion.assistantText.isEmpty {
                record.snapshot.assistantText = completion.assistantText
            }
            record.deadlineTask?.cancel()
            record.deadlineTask = nil
            changeKind = "completed"
            shouldReleaseApprovalContext = true
        case .failed(let failure):
            record.snapshot.state = "failed"
            let failureCode = Self.failureCode(failure.reason)
            let failureStage = Self.failureStage(failure.reason)
            record.snapshot.error.code = failureCode
            record.snapshot.error.message = Self.failureMessage(
                failure.reason
            )
            record.snapshot.error.retriable = false
            record.snapshot.failureStage = failureStage
            if let callID = Self.failureCallID(failure.reason),
               let index = record.snapshot.toolCalls.firstIndex(where: {
                $0.callID == callID
               }) {
                record.snapshot.toolCalls[index].error.code = failureCode
                record.snapshot.toolCalls[index].error.message =
                    Self.failureMessage(failure.reason)
                record.snapshot.toolCalls[index].error.retriable = false
                record.snapshot.toolCalls[index].failureStage = failureStage
            }
            record.deadlineTask?.cancel()
            record.deadlineTask = nil
            changeKind = "failed"
            shouldReleaseApprovalContext = true
        case .cancelled(let cancellation):
            let receipt = Self.cancellationReceipt(
                from: cancellation,
                runID: runID,
                snapshot: record.snapshot
            )
            if record.snapshot.hasCancellationReceipt,
               record.snapshot.cancellationReceipt != receipt {
                await failRunForJournalPersistence(runID: runID)
                return
            }
            record.snapshot.state = "cancelled"
            record.snapshot.error.code = "agent_run_cancelled"
            record.snapshot.error.message = Self.dispositionName(
                cancellation.disposition
            )
            record.snapshot.error.retriable = false
            record.snapshot.cancellationReceipt = receipt
            exactCancellationReceipt = receipt
            record.deadlineTask?.cancel()
            record.deadlineTask = nil
            changeKind = "cancelled"
            shouldReleaseApprovalContext = true
        }
        if shouldReleaseApprovalContext {
            record.snapshotFlushTask?.cancel()
            record.snapshotFlushTask = nil
        }
        let updatedAtUnixMs = Self.unixMilliseconds(now())
        record.snapshot.updatedAtUnixMs = updatedAtUnixMs
        record.snapshot.revision = Self.nextSnapshotRevision(
            after: record.snapshot.revision
        )
        let isHighFrequencyUpdate = [
            "assistant_delta",
            "reasoning_delta",
            "tool_call_delta",
        ].contains(changeKind)
        if isHighFrequencyUpdate {
            let (newByteCount, overflow) = record.unpersistedSnapshotBytes
                .addingReportingOverflow(highFrequencyPayloadBytes)
            record.unpersistedSnapshotBytes = overflow
                ? Int.max
                : newByteCount
        }
        let shouldPersistSnapshot = !isHighFrequencyUpdate
            || updatedAtUnixMs - record.lastSnapshotPersistedAtUnixMs
                >= Self.snapshotPersistenceIntervalMilliseconds
            || record.unpersistedSnapshotBytes
                >= Self.snapshotPersistenceByteThreshold
        if shouldPersistSnapshot {
            record.snapshotFlushTask?.cancel()
            record.snapshotFlushTask = nil
            record.lastSnapshotPersistedAtUnixMs = updatedAtUnixMs
            record.unpersistedSnapshotBytes = 0
        }
        let snapshot = record.snapshot
        runs[runID] = record
        if let durableStore, shouldPersistSnapshot {
            do {
                try await durableStore.persistSnapshot(snapshot)
            } catch {
                await failRunForJournalPersistence(runID: runID)
                return
            }
        } else if isHighFrequencyUpdate, durableStore != nil {
            scheduleSnapshotFlushIfNeeded(runID: runID)
        }
        if let exactCancellationReceipt {
            cacheCancellationReceipt(exactCancellationReceipt)
        }
        if shouldReleaseApprovalContext,
           let approvalContextRegistry = record.approvalContextRegistry {
            await approvalContextRegistry.unregister(runID: runID)
        }
        if shouldReleaseApprovalContext {
            await releaseToolSourcesIfNeeded(runID: runID)
        }
        await eventPublisher(snapshot, changeKind)
        if shouldReleaseApprovalContext {
            enforceMemoryRetention()
        }
    }

    private func scheduleSnapshotFlushIfNeeded(runID: String) {
        guard durableStore != nil,
              var record = runs[runID],
              !record.journalPersistenceFailed,
              record.unpersistedSnapshotBytes > 0,
              record.snapshotFlushTask == nil,
              !Self.isTerminalStateName(record.snapshot.state)
        else {
            return
        }
        record.snapshotFlushTask = Task { [weak self] in
            do {
                try await Task.sleep(
                    for: .milliseconds(
                        Self.snapshotPersistenceIntervalMilliseconds
                    )
                )
            } catch {
                return
            }
            guard !Task.isCancelled else {
                return
            }
            await self?.flushPendingSnapshot(runID: runID)
        }
        runs[runID] = record
    }

    private func flushPendingSnapshot(runID: String) async {
        guard let gate = runs[runID]?.eventGate else {
            return
        }
        await gate.acquire()
        await flushPendingSnapshotSerialized(runID: runID)
        await gate.release()
    }

    private func flushPendingSnapshotSerialized(runID: String) async {
        guard let durableStore,
              var record = runs[runID],
              !record.journalPersistenceFailed,
              record.unpersistedSnapshotBytes > 0,
              !Self.isTerminalStateName(record.snapshot.state)
        else {
            if var record = runs[runID] {
                record.snapshotFlushTask = nil
                runs[runID] = record
            }
            return
        }
        record.snapshotFlushTask = nil
        record.lastSnapshotPersistedAtUnixMs = Self.unixMilliseconds(now())
        record.unpersistedSnapshotBytes = 0
        let snapshot = record.snapshot
        runs[runID] = record
        do {
            try await durableStore.persistSnapshot(snapshot)
        } catch {
            await failRunForJournalPersistence(runID: runID)
        }
    }

    private func failRunForJournalPersistence(runID: String) async {
        guard var record = runs[runID], !record.journalPersistenceFailed else {
            return
        }
        record.journalPersistenceFailed = true
        record.pendingApproval = nil
        record.snapshot.clearPendingApproval()
        record.snapshotFlushTask?.cancel()
        record.snapshotFlushTask = nil
        record.unpersistedSnapshotBytes = 0
        record.deadlineTask?.cancel()
        record.deadlineTask = nil
        runs[runID] = record

        // Do not expose the terminal snapshot until coordinator cancellation,
        // approval cleanup, and source release have finished. Publishing the
        // failure first lets observers race ahead of the safety cleanup. The
        // journalPersistenceFailed flag above already makes later coordinator
        // events inert while this bounded cancellation is in flight.
        _ = await record.coordinator.cancel(
            runID: runID,
            reason: .system("agent-run-journal-persistence-failed")
        )
        if let approvalContextRegistry = record.approvalContextRegistry {
            await approvalContextRegistry.unregister(runID: runID)
        }
        await releaseToolSourcesIfNeeded(runID: runID)

        guard var terminalRecord = runs[runID] else {
            return
        }
        terminalRecord.snapshot.state = "failed"
        terminalRecord.snapshot.error.code =
            "agent_run_journal_persistence_failed"
        terminalRecord.snapshot.error.message =
            "Agent run stopped because its durable journal was unavailable."
        terminalRecord.snapshot.error.retriable = false
        terminalRecord.snapshot.failureStage = "journal_persistence"
        terminalRecord.snapshot.updatedAtUnixMs = Self.unixMilliseconds(now())
        terminalRecord.snapshot.revision = Self.nextSnapshotRevision(
            after: terminalRecord.snapshot.revision
        )
        terminalRecord.eventTask?.cancel()
        terminalRecord.eventTask = nil
        runs[runID] = terminalRecord
        if let durableStore {
            // A transient or entry-specific write failure may still allow the
            // smaller terminal failure receipt to commit. Retry only this
            // fail-closed snapshot so durable and in-memory terminal truth
            // converge whenever the journal has recovered.
            try? await durableStore.persistSnapshot(terminalRecord.snapshot)
        }
        await eventPublisher(terminalRecord.snapshot, "failed")
        enforceMemoryRetention()
    }

    private func enforceMemoryRetention() {
        guard runs.count > memoryRetentionLimit else {
            return
        }
        var retainedOrder: [String] = []
        retainedOrder.reserveCapacity(runOrder.count)
        var remainingCount = runs.count
        for runID in runOrder {
            if remainingCount > memoryRetentionLimit,
               let record = runs[runID],
               Self.isTerminalStateName(record.snapshot.state) {
                record.eventTask?.cancel()
                record.deadlineTask?.cancel()
                record.snapshotFlushTask?.cancel()
                runs.removeValue(forKey: runID)
                remainingCount -= 1
            } else {
                retainedOrder.append(runID)
            }
        }
        runOrder = retainedOrder
    }

    private func releaseToolSourcesIfNeeded(runID: String) async {
        guard var record = runs[runID], !record.toolSourcesReleased else {
            return
        }
        record.toolSourcesReleased = true
        runs[runID] = record
        if let ownerKey = record.toolSourceOwnerKey {
            await relinquishToolSourceOwnerLease(ownerKey)
        }
    }

    private func reserveToolSourceOwnerLease(
        _ ownerKey: ToolSourceOwnerKey,
        requestedTTLMilliseconds: UInt32,
        now: Date,
        renew: @escaping @Sendable (UInt32) async throws -> Void,
        release: @escaping @Sendable () async -> Void
    ) async throws -> ToolSourceLeaseReservation {
        while true {
            let nowUnixMs = Self.unixMilliseconds(now)
            let requestedExpiry = nowUnixMs
                + Int64(requestedTTLMilliseconds)
            if let conflict = toolSourceOwnerLeases.first(where: { key, _ in
                key.sessionID == ownerKey.sessionID
                    && key.branchID == ownerKey.branchID
                    && key.actorID == ownerKey.actorID
                    && key.sourceConfigDigest != ownerKey.sourceConfigDigest
            }) {
                if conflict.value.userCount == 0 {
                    let operationGate = conflict.value.operationGate
                    await operationGate.acquire()
                    await operationGate.release()
                    continue
                }
                throw ControlPlaneAgentRuntimeError.invalidRequest(
                    "concurrent Agent runs for one owner must use the same tool source configuration"
                )
            }
            if var lease = toolSourceOwnerLeases[ownerKey] {
                if lease.userCount == 0 {
                    let operationGate = lease.operationGate
                    await operationGate.acquire()
                    await operationGate.release()
                    continue
                }
                lease.userCount += 1
                lease.expiresAtUnixMs = max(
                    lease.expiresAtUnixMs,
                    requestedExpiry
                )
                lease.leaseTTLMilliseconds = max(
                    lease.leaseTTLMilliseconds,
                    requestedTTLMilliseconds
                )
                lease.renew = renew
                lease.release = release
                toolSourceOwnerLeases[ownerKey] = lease
                return ToolSourceLeaseReservation(
                    ttlMilliseconds: UInt32(
                        min(
                            3_600_000,
                            max(1, lease.expiresAtUnixMs - nowUnixMs)
                        )
                    ),
                    operationGate: lease.operationGate
                )
            }
            let generation = UUID()
            let operationGate = AgentRunCommandGate()
            toolSourceOwnerLeases[ownerKey] = ToolSourceOwnerLease(
                userCount: 1,
                expiresAtUnixMs: requestedExpiry,
                leaseTTLMilliseconds: requestedTTLMilliseconds,
                renew: renew,
                release: release,
                operationGate: operationGate,
                generation: generation,
                heartbeatTask: nil
            )
            let interval = sourceLeaseHeartbeatInterval
            let heartbeatTask = Task { [weak self] in
                while !Task.isCancelled {
                    do {
                        try await Task.sleep(for: interval)
                    } catch {
                        return
                    }
                    guard !Task.isCancelled, let self else {
                        return
                    }
                    await self.renewToolSourceOwnerLease(
                        ownerKey,
                        generation: generation
                    )
                }
            }
            toolSourceOwnerLeases[ownerKey]?.heartbeatTask = heartbeatTask
            return ToolSourceLeaseReservation(
                ttlMilliseconds: requestedTTLMilliseconds,
                operationGate: operationGate
            )
        }
    }

    private func relinquishToolSourceOwnerLease(
        _ ownerKey: ToolSourceOwnerKey
    ) async {
        guard var lease = toolSourceOwnerLeases[ownerKey] else {
            return
        }
        if lease.userCount > 1 {
            lease.userCount -= 1
            toolSourceOwnerLeases[ownerKey] = lease
            return
        }
        lease.userCount = 0
        lease.heartbeatTask?.cancel()
        toolSourceOwnerLeases[ownerKey] = lease
        await lease.operationGate.acquire()
        guard let current = toolSourceOwnerLeases[ownerKey],
              current.generation == lease.generation,
              current.userCount == 0 else {
            await lease.operationGate.release()
            return
        }
        await current.release()
        toolSourceOwnerLeases.removeValue(forKey: ownerKey)
        await lease.operationGate.release()
    }

    private func renewToolSourceOwnerLease(
        _ ownerKey: ToolSourceOwnerKey,
        generation: UUID
    ) async {
        guard let lease = toolSourceOwnerLeases[ownerKey],
              lease.generation == generation,
              lease.userCount > 0 else {
            return
        }
        let operationGate = lease.operationGate
        await operationGate.acquire()
        guard let current = toolSourceOwnerLeases[ownerKey],
              current.generation == generation,
              current.userCount > 0 else {
            await operationGate.release()
            return
        }
        let renewed: Bool
        do {
            try await current.renew(current.leaseTTLMilliseconds)
            renewed = true
        } catch {
            renewed = false
        }
        let observedAt = now()
        var runIDsToCancel: [String] = []
        if var latest = toolSourceOwnerLeases[ownerKey],
           latest.generation == generation,
           latest.userCount > 0 {
            if renewed {
                latest.expiresAtUnixMs = Self.unixMilliseconds(observedAt)
                    + Int64(latest.leaseTTLMilliseconds)
                toolSourceOwnerLeases[ownerKey] = latest
            } else if Self.unixMilliseconds(observedAt)
                >= latest.expiresAtUnixMs {
                runIDsToCancel = runs.compactMap { runID, record in
                    guard record.toolSourceOwnerKey == ownerKey,
                          !Self.isTerminalStateName(record.snapshot.state)
                    else {
                        return nil
                    }
                    return runID
                }
            }
        }
        await operationGate.release()
        for runID in runIDsToCancel {
            _ = await cancel(
                runID: runID,
                reason: .system("tool-source-lease-renewal-failed")
            )
        }
    }

    private func cacheCancellationReceipt(
        _ receipt: Melix_Controlplane_V1_AgentRunCancellationReceipt
    ) {
        // `unavailable` is a transport or durability observation, not a
        // terminal cancellation outcome. Keeping it in the in-memory cache
        // would make a transient journal failure permanently non-retryable.
        guard receipt.disposition != "unavailable" else { return }
        if cancellationReceipts[receipt.runID] == nil {
            cancellationReceiptOrder.append(receipt.runID)
        }
        cancellationReceipts[receipt.runID] = receipt
        while cancellationReceiptOrder.count > memoryRetentionLimit {
            let evictedRunID = cancellationReceiptOrder.removeFirst()
            cancellationReceipts.removeValue(forKey: evictedRunID)
        }
    }

    private static func messages(
        from messages: [Melix_Controlplane_V1_AgentRunMessage]
    ) throws -> [AgentRunMessage] {
        try messages.map { message in
            switch message.role.trimmingCharacters(
                in: .whitespacesAndNewlines
            ).lowercased() {
            case "system":
                return .system(message.content)
            case "user":
                return .user(message.content)
            case "assistant" where !message.toolCallID.isEmpty:
                return .assistantToolCall(
                    callID: message.toolCallID,
                    toolName: message.toolName,
                    argumentsJSON: message.toolArgumentsJson
                )
            case "assistant":
                return .assistant(message.content)
            case "tool":
                return .toolResult(
                    callID: message.toolCallID,
                    toolName: message.toolName,
                    outputJSON: message.content
                )
            default:
                throw ControlPlaneAgentRuntimeError.invalidRequest(
                    "unsupported agent message role"
                )
            }
        }
    }

    private static let maximumMessageCount = 1_024
    private static let maximumMessageBytes = 4 * 1_024 * 1_024
    private static let maximumMessageIdentityBytes = 512
    private static let maximumToolArgumentBytes = 512 * 1_024
    private static let maximumModelTurns = 64
    private static let maximumToolCalls = 64
    private static let snapshotPersistenceIntervalMilliseconds: Int64 = 100
    private static let snapshotPersistenceByteThreshold = 64 * 1_024

    private static func nextSnapshotRevision(after revision: UInt64) -> UInt64 {
        revision == UInt64.max ? UInt64.max : revision + 1
    }

    private static func toolSourceConfigDigest(
        _ configs: [Melix_Worker_V1_AgentToolSourceConfig]
    ) -> String {
        let entries = configs.map(canonicalToolSourceConfigData).sorted {
            $0.lexicographicallyPrecedes($1)
        }
        var hasher = SHA256()
        for entry in entries {
            var framed = Data()
            appendCanonicalField(entry, to: &framed)
            hasher.update(data: framed)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private static func canonicalToolSourceConfigData(
        _ config: Melix_Worker_V1_AgentToolSourceConfig
    ) -> Data {
        var data = Data()
        appendCanonicalField(config.sourceID, to: &data)
        appendCanonicalField(config.enabled ? "1" : "0", to: &data)
        appendCanonicalField(String(config.requestTimeoutMs), to: &data)
        appendCanonicalField(String(config.connectTimeoutMs), to: &data)
        appendCanonicalField(String(config.maxResultBytes), to: &data)
        appendCanonicalField(config.configurationRevision, to: &data)
        appendCanonicalField(String(config.redactionTerms.count), to: &data)
        for term in config.redactionTerms {
            appendCanonicalField(term, to: &data)
        }
        switch config.transport {
        case .stdio(let transport):
            appendCanonicalField("stdio", to: &data)
            appendCanonicalField(transport.command, to: &data)
            appendCanonicalField(String(transport.arguments.count), to: &data)
            for argument in transport.arguments {
                appendCanonicalField(argument, to: &data)
            }
            appendCanonicalField(transport.workingDirectory, to: &data)
            appendCanonicalMap(transport.environmentReferences, to: &data)
        case .streamableHTTP(let transport):
            appendCanonicalField("streamable_http", to: &data)
            appendCanonicalField(transport.url, to: &data)
            appendCanonicalMap(transport.headers, to: &data)
            appendCanonicalMap(
                transport.headerEnvironmentReferences,
                to: &data
            )
        case nil:
            appendCanonicalField("none", to: &data)
        }
        return data
    }

    private static func appendCanonicalMap(
        _ values: [String: String],
        to data: inout Data
    ) {
        appendCanonicalField(String(values.count), to: &data)
        for key in values.keys.sorted() {
            appendCanonicalField(key, to: &data)
            appendCanonicalField(values[key] ?? "", to: &data)
        }
    }

    private static func appendCanonicalField(
        _ value: String,
        to data: inout Data
    ) {
        appendCanonicalField(Data(value.utf8), to: &data)
    }

    private static func appendCanonicalField(
        _ value: Data,
        to data: inout Data
    ) {
        var length = UInt64(value.count).bigEndian
        withUnsafeBytes(of: &length) { bytes in
            data.append(contentsOf: bytes)
        }
        data.append(value)
    }

    private static func messagesFitWireBudget(
        _ messages: [Melix_Controlplane_V1_AgentRunMessage]
    ) -> Bool {
        var totalBytes = 0
        for message in messages {
            let roleBytes = message.role.utf8.count
            let contentBytes = message.content.utf8.count
            let callIDBytes = message.toolCallID.utf8.count
            let toolNameBytes = message.toolName.utf8.count
            let argumentBytes = message.toolArgumentsJson.utf8.count
            guard roleBytes <= maximumMessageIdentityBytes,
                  callIDBytes <= maximumMessageIdentityBytes,
                  toolNameBytes <= maximumMessageIdentityBytes,
                  argumentBytes <= maximumToolArgumentBytes
            else {
                return false
            }
            for byteCount in [
                roleBytes,
                contentBytes,
                callIDBytes,
                toolNameBytes,
                argumentBytes,
            ] {
                guard byteCount <= maximumMessageBytes - totalBytes else {
                    return false
                }
                totalBytes += byteCount
            }
        }
        return true
    }

    private static func upsertToolCall(
        _ call: AgentToolCall,
        state: AgentToolCallState,
        result: AgentToolExecutionResult? = nil,
        record: inout RunRecord,
        at date: Date
    ) {
        var snapshot = record.snapshot.toolCalls.first(where: {
            $0.callID == call.callID
        }) ?? Melix_Controlplane_V1_AgentToolCallSnapshot()
        snapshot.callID = call.callID
        snapshot.sourceID = call.sourceID
        snapshot.toolName = call.toolName
        snapshot.title = call.title
        snapshot.intendedEffect = call.intendedEffect
        snapshot.riskClass = call.riskClass
        snapshot.schemaDigest = call.schemaDigest
        snapshot.argumentDigest = digest(call.argumentsJSON)
        snapshot.state = toolStateName(state)
        switch state {
        case .running:
            record.toolStartedAt[call.callID] = date
        case .completed, .failed, .cancelled:
            if let startedAt = record.toolStartedAt.removeValue(forKey: call.callID) {
                snapshot.durationMs = date.timeIntervalSince(startedAt) * 1_000
            }
        case .requested, .waitingForApproval:
            break
        }
        if let result {
            if result.durationMs > 0 {
                snapshot.durationMs = result.durationMs
            }
            snapshot.evidenceReference = result.evidenceReference
            let presentation = toolResultPresentation(
                receiptJSON: result.receiptJSON
            )
            snapshot.resultTruncated = presentation.truncated
            snapshot.resultSummary = presentation.summary
            if result.evidencePersistenceFailed {
                snapshot.error.code = "agent_tool_evidence_unavailable"
                snapshot.error.message = "Tool completed, but its evidence artifact was unavailable."
                snapshot.error.retriable = false
            }
        }
        if let index = record.snapshot.toolCalls.firstIndex(where: {
            $0.callID == call.callID
        }) {
            record.snapshot.toolCalls[index] = snapshot
        } else {
            record.snapshot.toolCalls.append(snapshot)
            record.snapshot.toolCallCount = UInt32(record.snapshot.toolCalls.count)
        }
    }

    private static func toolResultPresentation(
        receiptJSON: String
    ) -> (truncated: Bool, summary: String) {
        guard receiptJSON.utf8.count <= 65_536,
              let data = receiptJSON.data(using: .utf8),
              let receipt = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else {
            return (false, "")
        }
        let truncated = (receipt["result_truncated"] as? Bool ?? false)
            || (receipt["observation_truncated"] as? Bool ?? false)
        guard let rawSummary = receipt["result_summary"] as? String else {
            return (
                truncated,
                truncated ? "Tool result was truncated." : ""
            )
        }
        let summary = rawSummary.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !summary.isEmpty, summary.utf8.count <= 1_024 else {
            return (
                truncated,
                truncated ? "Tool result was truncated." : ""
            )
        }
        return (truncated, summary)
    }

    private static func pendingApproval(
        from approval: AgentApprovalRequest,
        sessionID: String,
        branchID: String
    ) -> Melix_Controlplane_V1_AgentPendingApproval {
        let presentation = AgentApprovalPresentation.make(
            call: approval.call,
            sessionID: sessionID,
            branchID: branchID
        )
        var pending = Melix_Controlplane_V1_AgentPendingApproval()
        pending.binding = bindingProto(from: approval.binding)
        pending.sourceID = approval.call.sourceID
        pending.toolName = approval.call.toolName
        pending.title = approval.call.title
        pending.intendedEffect = approval.call.intendedEffect
        pending.riskClass = approval.call.riskClass
        pending.operationKind = presentation.operationKind
        pending.redactedArgumentsJson = presentation.redactedArgumentsJSON
        pending.targetScopes = presentation.targetScopes
        pending.argumentsTruncated = presentation.argumentsTruncated
        let persistentAllow = persistentAllowEligibility(
            call: approval.call,
            presentation: presentation
        )
        pending.persistentAllowEligible = persistentAllow.eligible
        pending.persistentAllowUnavailableReason = persistentAllow.reason
        return pending
    }

    static func persistentAllowEligibility(
        call: AgentToolCall,
        presentation: AgentApprovalPresentation
    ) -> (eligible: Bool, reason: String) {
        let risk = call.riskClass.trimmingCharacters(
            in: .whitespacesAndNewlines
        ).lowercased()
        let operation = presentation.operationKind.trimmingCharacters(
            in: .whitespacesAndNewlines
        ).lowercased()
        guard !call.sourceID.isEmpty,
              !call.toolName.isEmpty,
              !call.schemaDigest.isEmpty,
              !risk.isEmpty,
              risk != "unknown",
              ["read", "write"].contains(operation),
              risk != "critical" else {
            return (
                false,
                "This approval is missing a complete trusted identity or is protected by Melix's safety floor. You can still allow this call once."
            )
        }
        if call.sourceID == "computer" {
            let arguments: [String: Any]
            if let data = call.argumentsJSON.data(using: .utf8),
               let object = try? JSONSerialization.jsonObject(with: data),
               let parsed = object as? [String: Any] {
                arguments = parsed
            } else {
                arguments = [:]
            }
            let bundles: [String]
            if let target = arguments["target"] as? [String: Any],
               let bundle = target["bundle_id"] as? String {
                bundles = [bundle]
            } else if let targets = arguments["allowed_targets"]
                as? [[String: Any]] {
                bundles = targets.compactMap { $0["bundle_id"] as? String }
            } else {
                bundles = []
            }
            let normalized = Set(bundles.map {
                $0.trimmingCharacters(in: .whitespacesAndNewlines)
            }.filter { !$0.isEmpty })
            guard bundles.count == 1, normalized.count == 1 else {
                return (
                    false,
                    "Always Allow requires one exact broker-verified app/window scope. This call can still be allowed once."
                )
            }
        }
        return (true, "")
    }

    private static func binding(
        from proto: Melix_Controlplane_V1_AgentApprovalBinding
    ) -> AgentApprovalBinding {
        AgentApprovalBinding(
            runID: proto.runID,
            callID: proto.callID,
            schemaDigest: proto.schemaDigest,
            argumentDigest: proto.argumentDigest,
            policyRevision: proto.policyRevision,
            bindingDigest: proto.bindingDigest
        )
    }

    private static func bindingProto(
        from binding: AgentApprovalBinding
    ) -> Melix_Controlplane_V1_AgentApprovalBinding {
        var proto = Melix_Controlplane_V1_AgentApprovalBinding()
        proto.runID = binding.runID
        proto.callID = binding.callID
        proto.schemaDigest = binding.schemaDigest
        proto.argumentDigest = binding.argumentDigest
        proto.policyRevision = binding.policyRevision
        proto.bindingDigest = binding.bindingDigest
        return proto
    }

    private static func stateName(_ state: AgentRunState) -> String {
        switch state {
        case .created:
            return "created"
        case .modelTurn:
            return "model_turn"
        case .waitingForApproval:
            return "waiting_for_approval"
        case .toolRunning:
            return "tool_running"
        case .completed:
            return "completed"
        case .failed:
            return "failed"
        case .cancelled:
            return "cancelled"
        }
    }

    private static func toolStateName(_ state: AgentToolCallState) -> String {
        switch state {
        case .requested:
            return "requested"
        case .waitingForApproval:
            return "waiting_for_approval"
        case .running:
            return "running"
        case .completed:
            return "completed"
        case .failed:
            return "failed"
        case .cancelled:
            return "cancelled"
        }
    }

    private static func dispositionName(
        _ disposition: AgentCancellationDisposition
    ) -> String {
        switch disposition {
        case .accepted:
            return "accepted"
        case .alreadyTerminal:
            return "already_terminal"
        case .tooLate:
            return "too_late"
        case .notFound:
            return "not_found"
        case .scopeMismatch:
            return "scope_mismatch"
        case .unavailable:
            return "unavailable"
        }
    }

    private static func sideEffectState(
        _ state: AgentToolSideEffectState
    ) -> Melix_Controlplane_V1_AgentToolSideEffectState {
        switch state {
        case .none:
            return .agentToolSideEffectNone
        case .committed:
            return .agentToolSideEffectCommitted
        case .unknown:
            return .agentToolSideEffectUnknown
        }
    }

    private static func cancellationReceipt(
        from cancellation: AgentCancellationReceipt,
        runID: String,
        snapshot: Melix_Controlplane_V1_AgentRunSnapshot
    ) -> Melix_Controlplane_V1_AgentRunCancellationReceipt {
        var receipt = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        receipt.runID = runID
        receipt.cancellationID = cancellationID(for: runID)
        receipt.disposition = dispositionName(cancellation.disposition)
        receipt.sideEffectCommitted = cancellation.sideEffectCommitted
        receipt.sideEffectState = sideEffectState(cancellation.sideEffectState)
        if let tool = cancellation.toolCancellation {
            receipt.tool.callID = tool.callID
            receipt.tool.disposition = dispositionName(tool.disposition)
            receipt.tool.sideEffectCommitted = tool.sideEffectCommitted
            receipt.tool.sideEffectState = sideEffectState(tool.sideEffectState)
            if let call = snapshot.toolCalls.first(where: {
                $0.callID == tool.callID
            }) {
                receipt.tool.sourceID = call.sourceID
            }
        }
        if let runTools = cancellation.runToolCancellation {
            receipt.runTools.disposition = dispositionName(runTools.disposition)
            receipt.runTools.sideEffectState = sideEffectState(
                runTools.sideEffectState
            )
            receipt.runTools.computerUseDisposition = dispositionName(
                runTools.computerUseDisposition
            )
            receipt.runTools.calls = runTools.callReceipts.map { callReceipt in
                var projected =
                    Melix_Controlplane_V1_AgentToolCancellationReceipt()
                projected.callID = callReceipt.callID
                projected.disposition = dispositionName(
                    callReceipt.disposition
                )
                projected.sideEffectCommitted = callReceipt.sideEffectCommitted
                projected.sideEffectState = sideEffectState(
                    callReceipt.sideEffectState
                )
                if let call = snapshot.toolCalls.first(where: {
                    $0.callID == callReceipt.callID
                }) {
                    projected.sourceID = call.sourceID
                }
                return projected
            }
        }
        return receipt
    }

    private static func failureCode(_ failure: AgentRunFailureReason) -> String {
        switch failure {
        case .modelTurnLimitExceeded:
            return "agent_model_turn_limit_exceeded"
        case .toolCallLimitExceeded:
            return "agent_tool_call_limit_exceeded"
        case .approvalDenied:
            return "agent_approval_denied"
        case .modelTurnFailed:
            return "agent_model_turn_failed"
        case .toolExecutionFailed:
            return "agent_tool_execution_failed"
        case .runToolCleanupFailed:
            return "agent_run_tool_cleanup_failed"
        case .toolCallHealingLimitExceeded:
            return "agent_tool_call_healing_exhausted"
        case .toolSchemaDigestMismatch:
            return "agent_tool_schema_digest_mismatch"
        case .staleApprovalBinding:
            return "agent_approval_binding_stale"
        case .incompleteToolCall, .inconsistentToolCallFragments,
             .interleavedToolCallFragments, .toolArgumentsMustBeJSONObject,
             .missingToolSchemaDigest, .invalidApprovalPolicyRevision,
             .duplicateToolCallID:
            return "agent_tool_call_invalid"
        }
    }

    private static func failureStage(
        _ failure: AgentRunFailureReason
    ) -> String {
        switch failure {
        case .modelTurnLimitExceeded, .modelTurnFailed:
            return "model_turn"
        case .toolCallLimitExceeded:
            return "tool_call_limit"
        case .approvalDenied, .staleApprovalBinding:
            return "approval"
        case .toolExecutionFailed:
            return "tool_execution"
        case .runToolCleanupFailed:
            return "tool_cleanup"
        case .toolSchemaDigestMismatch:
            return "tool_schema"
        case .toolCallHealingLimitExceeded:
            return "tool_call_healing"
        case .incompleteToolCall, .inconsistentToolCallFragments,
             .interleavedToolCallFragments, .toolArgumentsMustBeJSONObject,
             .missingToolSchemaDigest, .invalidApprovalPolicyRevision,
             .duplicateToolCallID:
            return "tool_call_admission"
        }
    }

    private static func failureCallID(
        _ failure: AgentRunFailureReason
    ) -> String? {
        switch failure {
        case .incompleteToolCall(let callID),
             .inconsistentToolCallFragments(let callID),
             .toolArgumentsMustBeJSONObject(let callID),
             .missingToolSchemaDigest(let callID),
             .toolSchemaDigestMismatch(let callID),
             .invalidApprovalPolicyRevision(let callID),
             .staleApprovalBinding(let callID),
             .duplicateToolCallID(let callID),
             .approvalDenied(let callID),
             .toolExecutionFailed(let callID, _),
             .toolCallHealingLimitExceeded(let callID, _, _):
            return callID
        case .interleavedToolCallFragments(let activeCallID, _):
            return activeCallID
        case .modelTurnLimitExceeded, .toolCallLimitExceeded,
             .modelTurnFailed, .runToolCleanupFailed:
            return nil
        }
    }

    private static func failureMessage(
        _ failure: AgentRunFailureReason
    ) -> String {
        switch failure {
        case .modelTurnLimitExceeded:
            return "The Agent reached its model-turn limit."
        case .toolCallLimitExceeded:
            return "The Agent reached its tool-call limit."
        case .approvalDenied:
            return "The operator denied this tool call."
        case .staleApprovalBinding:
            return "The approval binding became stale before execution."
        case .modelTurnFailed(let portFailure):
            return portFailureMessage(portFailure, subject: "Model turn")
        case .toolExecutionFailed(_, let portFailure):
            return portFailureMessage(portFailure, subject: "Tool execution")
        case .runToolCleanupFailed(let portFailure):
            return portFailureMessage(portFailure, subject: "Tool cleanup")
        case .toolSchemaDigestMismatch:
            return "The tool schema changed before execution."
        case .toolCallHealingLimitExceeded:
            return "The Agent could not repair an invalid tool call."
        case .incompleteToolCall, .inconsistentToolCallFragments,
             .interleavedToolCallFragments, .toolArgumentsMustBeJSONObject,
             .missingToolSchemaDigest, .invalidApprovalPolicyRevision,
             .duplicateToolCallID:
            return "The model produced an invalid tool call."
        }
    }

    private static func portFailureMessage(
        _ failure: AgentPortFailure,
        subject: String
    ) -> String {
        switch failure {
        case .unavailable:
            return "\(subject) was unavailable."
        case .timedOut:
            return "\(subject) timed out."
        case .invalidResponse:
            return "\(subject) returned an invalid response."
        case .cancelled:
            return "\(subject) was cancelled."
        case .rejected:
            return "\(subject) was rejected."
        case .internalFailure:
            return "\(subject) failed internally."
        }
    }

    private static func digest(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }

    private static func cancellationID(for runID: String) -> String {
        "agent-cancel-\(digest("melix.agent-cancellation.v1:\(runID)").prefix(32))"
    }

    private static func unavailableCancellationReceipt(
        for runID: String
    ) -> Melix_Controlplane_V1_AgentRunCancellationReceipt {
        var receipt = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        receipt.runID = runID
        receipt.cancellationID = cancellationID(for: runID)
        receipt.disposition = "unavailable"
        receipt.sideEffectState = .agentToolSideEffectUnknown
        return receipt
    }

    private static func admissionCancellationReceipt(
        for runID: String
    ) -> Melix_Controlplane_V1_AgentRunCancellationReceipt {
        var receipt = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        receipt.runID = runID
        receipt.cancellationID = cancellationID(for: runID)
        receipt.disposition = "accepted"
        receipt.sideEffectState = .agentToolSideEffectNone
        return receipt
    }

    private static func interruptedByRestartSnapshot(
        _ snapshot: Melix_Controlplane_V1_AgentRunSnapshot,
        at date: Date
    ) -> Melix_Controlplane_V1_AgentRunSnapshot {
        guard !isTerminalStateName(snapshot.state) else {
            return snapshot
        }
        var recovered = snapshot
        recovered.state = "failed"
        recovered.clearPendingApproval()
        recovered.error.code = interruptedByRestartErrorCode
        recovered.error.message =
            "Agent run stopped because the control plane restarted."
        recovered.error.retriable = false
        recovered.failureStage = "runtime_restart"
        for index in recovered.toolCalls.indices where [
            "requested",
            "waiting_for_approval",
            "running",
        ].contains(recovered.toolCalls[index].state) {
            recovered.toolCalls[index].state = "failed"
            recovered.toolCalls[index].error.code =
                interruptedByRestartErrorCode
            recovered.toolCalls[index].error.message =
                "Tool execution stopped because the control plane restarted."
            recovered.toolCalls[index].error.retriable = false
            recovered.toolCalls[index].failureStage = "runtime_restart"
        }
        if recovered.hasComputerUseSession {
            recovered.computerUseSession.sessionState =
                .agentComputerUseSessionUnavailable
            recovered.computerUseSession.lastOperation = .unavailable
            recovered.computerUseSession.lastResult =
                .agentComputerUseResultFailed
            recovered.computerUseSession.lastActionID = ""
            recovered.computerUseSession.lastCallID = ""
            recovered.computerUseSession.updatedAtUnixMs =
                unixMilliseconds(date)
        }
        recovered.updatedAtUnixMs = unixMilliseconds(date)
        recovered.revision = nextSnapshotRevision(after: recovered.revision)
        return recovered
    }

    private static func isTerminalStateName(_ state: String) -> Bool {
        state == "completed" || state == "failed" || state == "cancelled"
    }

    private static func isValidOwnerComponent(_ value: String) -> Bool {
        !value.isEmpty
            && !value.contains("\0")
            && value.utf8.count <= 256
    }

    private static func isValidRunID(_ value: String) -> Bool {
        isValidOwnerComponent(value)
    }

    private static func unixMilliseconds(_ date: Date) -> Int64 {
        Int64(date.timeIntervalSince1970 * 1_000)
    }

    private static func sourceLeaseTTLMilliseconds(
        deadlineUnixMs: Int64,
        now: Date
    ) -> UInt32 {
        let defaultTTL: Int64 = 300_000
        guard deadlineUnixMs > 0 else {
            return UInt32(defaultTTL)
        }
        let nowUnixMs = unixMilliseconds(now)
        let remaining = max(1, deadlineUnixMs - nowUnixMs)
        let (withGrace, overflow) = remaining.addingReportingOverflow(60_000)
        return UInt32(
            min(3_600_000, overflow ? 3_600_000 : max(1, withGrace))
        )
    }
}
