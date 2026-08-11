import CryptoKit
import Darwin
import Foundation
import MelixControlPlaneProtocol
import Testing

@testable import MelixControlPlaneCore

@Suite("Agent Run Durable Store", .serialized)
struct AgentRunDurableStoreTests {
    @Test("snapshots and cancellation receipts hydrate across runtime instances")
    func runtimeQueriesHydrateDurableTruth() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(rootURL: fixture.rootURL)
        var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        snapshot.runID = "run-hydrated"
        snapshot.sessionID = "session-hydrated"
        snapshot.state = "cancelled"
        snapshot.updatedAtUnixMs = 42
        try await store.persistSnapshot(snapshot)
        let runsDirectory = fixture.rootURL.appendingPathComponent("runs")
        let runFiles = try FileManager.default.contentsOfDirectory(
            at: runsDirectory,
            includingPropertiesForKeys: nil
        )
        let runFile = try #require(runFiles.first)
        let directoryMode = try #require(
            FileManager.default.attributesOfItem(atPath: runsDirectory.path)[
                .posixPermissions
            ] as? NSNumber
        )
        let fileMode = try #require(
            FileManager.default.attributesOfItem(atPath: runFile.path)[
                .posixPermissions
            ] as? NSNumber
        )
        #expect(directoryMode.intValue & 0o777 == 0o700)
        #expect(fileMode.intValue & 0o777 == 0o600)

        var cancellation = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        cancellation.runID = snapshot.runID
        cancellation.cancellationID = "cancel-hydrated"
        cancellation.disposition = "accepted"
        cancellation.sideEffectState = .agentToolSideEffectUnknown
        try await store.persistCancellation(cancellation)

        let runtime = ControlPlaneAgentRuntime(durableStore: store)
        var hydrated = try await runtime.snapshot(runID: snapshot.runID)
        #expect(hydrated.cancellationReceipt == cancellation)
        hydrated.clearCancellationReceipt()
        #expect(hydrated == snapshot)
        var listed = try #require(
            await runtime.snapshots(
                sessionID: snapshot.sessionID,
                limit: 10
            ).first
        )
        #expect(listed.cancellationReceipt == cancellation)
        listed.clearCancellationReceipt()
        #expect(listed == snapshot)
        #expect(await runtime.retainedRunCount() == 0)
        #expect(
            await runtime.cancel(
                runID: snapshot.runID,
                reason: .operatorRequested
            ) == cancellation
        )
    }

    @Test("approval decisions are immutable, bounded, and contain no raw arguments")
    func approvalDecisionReceiptsAreImmutableAndRedacted() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(maxApprovalDecisions: 2)
        )
        let call = AgentToolCall(
            callID: "call-secret",
            sourceID: "mcp",
            toolName: "mail.send",
            schemaDigest: "schema-v1",
            argumentsJSON: #"{"token":"raw-secret-value"}"#
        )
        let binding = AgentApprovalBinding.make(
            runID: "run-secret",
            call: call,
            policyRevision: "7",
            scopeDigest: "scope-v1"
        )
        let first = AgentApprovalDecisionJournalReceipt(
            decisionID: "decision-1",
            actorID: "operator",
            decidedAtUnixMs: 1,
            binding: binding,
            choice: .alwaysAllow
        )
        try await store.persistApprovalDecision(first)
        try await store.persistApprovalDecision(first)

        let conflicting = AgentApprovalDecisionJournalReceipt(
            decisionID: "decision-1",
            actorID: "operator",
            decidedAtUnixMs: 2,
            binding: binding,
            choice: .alwaysAllow
        )
        await #expect(throws: AgentRunDurableStoreError.self) {
            try await store.persistApprovalDecision(conflicting)
        }

        for index in 2...3 {
            try await store.persistApprovalDecision(
                AgentApprovalDecisionJournalReceipt(
                    decisionID: "decision-\(index)",
                    actorID: "operator",
                    decidedAtUnixMs: Int64(index),
                    binding: binding,
                    choice: .allowOnce
                )
            )
        }
        try await store.persistApprovalDecision(
            AgentApprovalDecisionJournalReceipt(
                decisionID: "decision-denied",
                actorID: "operator",
                decidedAtUnixMs: 4,
                binding: binding,
                choice: .deny
            )
        )
        let receipts = try await store.approvalDecisions(
            runID: "run-secret",
            limit: 10
        )
        #expect(receipts.count == 2)

        let approvalDirectory = fixture.rootURL.appendingPathComponent("approvals")
        let contents = try FileManager.default.contentsOfDirectory(
            at: approvalDirectory,
            includingPropertiesForKeys: nil
        )
        let persisted = try contents.map {
            try String(contentsOf: $0, encoding: .utf8)
        }.joined()
        #expect(!persisted.contains("raw-secret-value"))
        #expect(!persisted.contains("argumentsJSON"))
    }

    @Test("snapshot retention and entry bytes are hard bounded")
    func snapshotRetentionAndEntrySizeAreBounded() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(
                maxSnapshots: 2,
                maxEntryBytes: 4_096
            )
        )
        for index in 1...3 {
            var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
            snapshot.runID = "run-\(index)"
            snapshot.sessionID = "session"
            snapshot.state = "completed"
            snapshot.updatedAtUnixMs = Int64(index)
            try await store.persistSnapshot(snapshot)
        }
        #expect(try await store.snapshots(limit: 10).count == 2)

        var oversized = Melix_Controlplane_V1_AgentRunSnapshot()
        oversized.runID = "run-oversized"
        oversized.assistantText = String(repeating: "x", count: 8_192)
        await #expect(throws: AgentRunDurableStoreError.self) {
            try await store.persistSnapshot(oversized)
        }
    }

    @Test("read paths reject mismatched and oversized identities and skip corrupt list entries")
    func readPathsFailClosedAndListsSkipInvalidEntries() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(maxEntryBytes: 4_096)
        )
        #expect(try await store.snapshots().isEmpty)
        #expect(try await store.cancellation(runID: "missing") == nil)
        #expect(try await store.approvalDecisions(runID: "missing").isEmpty)

        var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        snapshot.runID = "run-expected"
        snapshot.sessionID = "session-read"
        snapshot.updatedAtUnixMs = 11
        try await store.persistSnapshot(snapshot)
        let snapshotURL = journalURL(
            root: fixture.rootURL,
            kind: "runs",
            identifier: snapshot.runID,
            extension: "pb"
        )
        var mismatchedSnapshot = snapshot
        mismatchedSnapshot.runID = "run-other"
        try mismatchedSnapshot.serializedData().write(
            to: snapshotURL,
            options: .atomic
        )
        await #expect(
            throws: AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        ) {
            _ = try await store.snapshot(runID: snapshot.runID)
        }
        try Data(repeating: 0x78, count: 8_192).write(
            to: snapshotURL,
            options: .atomic
        )
        await #expect(throws: AgentRunDurableStoreError.self) {
            _ = try await store.snapshot(runID: snapshot.runID)
        }

        try FileManager.default.removeItem(at: snapshotURL)
        var first = snapshot
        first.runID = "run-a"
        first.updatedAtUnixMs = 20
        var second = snapshot
        second.runID = "run-b"
        second.updatedAtUnixMs = 20
        try await store.persistSnapshot(first)
        try await store.persistSnapshot(second)
        try Data([0xff]).write(
            to: fixture.rootURL
                .appendingPathComponent("runs")
                .appendingPathComponent("corrupt.pb")
        )
        let equalModificationDate = Date(timeIntervalSince1970: 100)
        for file in try FileManager.default.contentsOfDirectory(
            at: fixture.rootURL.appendingPathComponent("runs"),
            includingPropertiesForKeys: nil
        ) {
            try FileManager.default.setAttributes(
                [.modificationDate: equalModificationDate],
                ofItemAtPath: file.path
            )
        }
        let snapshots = try await store.snapshots(
            sessionID: "session-read",
            limit: 10
        )
        #expect(snapshots.map(\.runID) == ["run-b", "run-a"])

        var cancellation = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        cancellation.runID = "run-cancel-expected"
        cancellation.cancellationID = "cancel-expected"
        try await store.persistCancellation(cancellation)
        let cancellationURL = journalURL(
            root: fixture.rootURL,
            kind: "cancellations",
            identifier: cancellation.runID,
            extension: "pb"
        )
        var mismatchedCancellation = cancellation
        mismatchedCancellation.runID = "run-cancel-other"
        try mismatchedCancellation.serializedData().write(
            to: cancellationURL,
            options: .atomic
        )
        await #expect(
            throws: AgentRunDurableStoreError.invalidEntry(kind: "cancellation")
        ) {
            _ = try await store.cancellation(runID: cancellation.runID)
        }
    }

    @Test("approval and snapshot query ordering is deterministic at equal timestamps")
    func equalTimestampOrderingAndInvalidReceiptFiltering() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(rootURL: fixture.rootURL)
        let call = AgentToolCall(
            callID: "call-order",
            sourceID: "builtin",
            toolName: "local_add",
            schemaDigest: "schema-order",
            argumentsJSON: "{}"
        )
        let binding = AgentApprovalBinding.make(
            runID: "run-order",
            call: call,
            policyRevision: "1",
            scopeDigest: "scope-order"
        )
        for decisionID in ["decision-a", "decision-b"] {
            try await store.persistApprovalDecision(
                AgentApprovalDecisionJournalReceipt(
                    decisionID: decisionID,
                    actorID: "operator",
                    decidedAtUnixMs: 50,
                    binding: binding,
                    choice: .allowOnce
                )
            )
        }
        try Data("not-json".utf8).write(
            to: fixture.rootURL
                .appendingPathComponent("approvals")
                .appendingPathComponent("corrupt.json")
        )
        let receipts = try await store.approvalDecisions(
            runID: binding.runID,
            limit: 10
        )
        #expect(receipts.map(\.decisionID) == ["decision-b", "decision-a"])
        #expect(try await store.approvalDecisions(runID: "other-run").isEmpty)
    }

    @Test("filesystem conflicts are typed and failed atomic snapshots leave no temporary file")
    func filesystemConflictsRemainTypedAndAtomic() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }

        let rootFile = fixture.rootURL.appendingPathComponent("blocked-root")
        try Data("blocked".utf8).write(to: rootFile)
        let blockedStore = AgentRunDurableStore(rootURL: rootFile)
        var blockedSnapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        blockedSnapshot.runID = "run-blocked"
        await #expect(throws: AgentRunDurableStoreError.self) {
            try await blockedStore.persistSnapshot(blockedSnapshot)
        }

        let atomicRoot = fixture.rootURL.appendingPathComponent(
            "atomic-root",
            isDirectory: true
        )
        let runs = atomicRoot.appendingPathComponent("runs", isDirectory: true)
        try FileManager.default.createDirectory(
            at: runs,
            withIntermediateDirectories: true
        )
        var atomicSnapshot = Melix_Controlplane_V1_AgentRunSnapshot()
        atomicSnapshot.runID = "run-rename-conflict"
        let destination = journalURL(
            root: atomicRoot,
            kind: "runs",
            identifier: atomicSnapshot.runID,
            extension: "pb"
        )
        try FileManager.default.createDirectory(
            at: destination,
            withIntermediateDirectories: false
        )
        let atomicStore = AgentRunDurableStore(rootURL: atomicRoot)
        await #expect(throws: AgentRunDurableStoreError.self) {
            try await atomicStore.persistSnapshot(atomicSnapshot)
        }
        let entries = try FileManager.default.contentsOfDirectory(
            at: runs,
            includingPropertiesForKeys: nil,
            options: []
        )
        #expect(!entries.contains { $0.lastPathComponent.contains(".tmp-") })
    }

    @Test("retention keeps the just-written snapshot even when an older file has a future timestamp")
    func retentionProtectsTheNewlyWrittenEntry() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(maxSnapshots: 1)
        )
        var old = Melix_Controlplane_V1_AgentRunSnapshot()
        old.runID = "run-old-future-mtime"
        old.state = "completed"
        try await store.persistSnapshot(old)
        let oldURL = journalURL(
            root: fixture.rootURL,
            kind: "runs",
            identifier: old.runID,
            extension: "pb"
        )
        try FileManager.default.setAttributes(
            [.modificationDate: Date.distantFuture],
            ofItemAtPath: oldURL.path
        )

        var newest = Melix_Controlplane_V1_AgentRunSnapshot()
        newest.runID = "run-protected"
        newest.state = "completed"
        try await store.persistSnapshot(newest)
        #expect(try await store.snapshot(runID: newest.runID) == newest)
        #expect(try await store.snapshot(runID: old.runID) == nil)
    }

    @Test("retention never evicts a nonterminal run and restart reconciliation remains possible")
    func retentionProtectsNonterminalRunsAcrossRestart() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(maxSnapshots: 2)
        )
        var active = Melix_Controlplane_V1_AgentRunSnapshot()
        active.runID = "run-active-retained"
        active.sessionID = "session-retention"
        active.state = "tool_running"
        active.updatedAtUnixMs = 1
        try await store.persistSnapshot(active)
        for index in 1...2 {
            var terminal = Melix_Controlplane_V1_AgentRunSnapshot()
            terminal.runID = "run-terminal-\(index)"
            terminal.sessionID = active.sessionID
            terminal.state = "completed"
            terminal.updatedAtUnixMs = Int64(index + 1)
            try await store.persistSnapshot(terminal)
        }

        #expect(try await store.snapshot(runID: active.runID) == active)
        let safetyPage = try await store.nonterminalSnapshotPage(
            sessionID: active.sessionID,
            limit: 2
        )
        #expect(safetyPage.isComplete)
        #expect(safetyPage.snapshots.map(\.runID) == [active.runID])

        let restarted = ControlPlaneAgentRuntime(
            now: { Date(timeIntervalSince1970: 1_800_000_100) },
            durableStore: store
        )
        let recovered = await restarted.snapshots(
            sessionID: active.sessionID,
            limit: 2
        )
        let interrupted = try #require(
            recovered.first(where: { $0.runID == active.runID })
        )
        #expect(interrupted.state == "failed")
        #expect(interrupted.error.code == "agent_run_interrupted_by_restart")
        #expect(try await store.snapshot(runID: active.runID)?.state == "failed")
    }

    @Test("safety inventory recovers exact staging files and rejects every untrusted descriptor kind")
    func strictSafetyInventoryClassifiesEveryDirectoryEntry() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(rootURL: fixture.rootURL)
        var active = Melix_Controlplane_V1_AgentRunSnapshot()
        active.runID = "run-strict-inventory"
        active.sessionID = "session-strict-inventory"
        active.state = "created"
        try await store.persistSnapshot(active)
        let runsDirectory = fixture.rootURL.appendingPathComponent("runs")
        let activeURL = journalURL(
            root: fixture.rootURL,
            kind: "runs",
            identifier: active.runID,
            extension: "pb"
        )

        let stagingURL = runsDirectory.appendingPathComponent(
            ".\(activeURL.lastPathComponent).tmp-\(UUID().uuidString)"
        )
        try Data("staging".utf8).write(to: stagingURL)
        let recovered = try await store.nonterminalSnapshotPage(
            sessionID: active.sessionID
        )
        #expect(recovered.isComplete)
        #expect(recovered.snapshots.map(\.runID) == [active.runID])
        #expect(!FileManager.default.fileExists(atPath: stagingURL.path))

        let foreignHidden = runsDirectory.appendingPathComponent(".foreign")
        try Data("foreign".utf8).write(to: foreignHidden)
        await #expect(
            throws: AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        ) {
            _ = try await store.nonterminalSnapshotPage()
        }
        try FileManager.default.removeItem(at: foreignHidden)

        let malformedStaging = runsDirectory.appendingPathComponent(
            ".\(activeURL.lastPathComponent).tmp-not-a-uuid"
        )
        try Data("malformed-staging".utf8).write(to: malformedStaging)
        await #expect(
            throws: AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        ) {
            _ = try await store.nonterminalSnapshotPage()
        }
        try FileManager.default.removeItem(at: malformedStaging)

        let fifoURL = journalURL(
            root: fixture.rootURL,
            kind: "runs",
            identifier: "run-fifo",
            extension: "pb"
        )
        #expect(fifoURL.path.withCString { Darwin.mkfifo($0, 0o600) } == 0)
        await #expect(
            throws: AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        ) {
            _ = try await store.nonterminalSnapshotPage()
        }
        try FileManager.default.removeItem(at: fifoURL)

        let symlinkURL = journalURL(
            root: fixture.rootURL,
            kind: "runs",
            identifier: "run-symlink",
            extension: "pb"
        )
        try FileManager.default.createSymbolicLink(
            at: symlinkURL,
            withDestinationURL: activeURL
        )
        await #expect(
            throws: AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        ) {
            _ = try await store.nonterminalSnapshotPage()
        }
    }

    @Test("immutable retention refuses foreign approval and cancellation entries")
    func immutableRetentionRejectsForeignEntries() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(
                maxApprovalDecisions: 1,
                maxCancellations: 1
            )
        )
        let call = AgentToolCall(
            callID: "call-retention-foreign",
            sourceID: "builtin",
            toolName: "local_add",
            schemaDigest: "schema-v1",
            argumentsJSON: "{}"
        )
        let binding = AgentApprovalBinding.make(
            runID: "run-retention-foreign",
            call: call,
            policyRevision: "1",
            scopeDigest: "scope"
        )
        try await store.persistApprovalDecision(
            AgentApprovalDecisionJournalReceipt(
                decisionID: "decision-one",
                actorID: "operator",
                decidedAtUnixMs: 1,
                binding: binding,
                choice: .deny
            )
        )
        let approvals = fixture.rootURL.appendingPathComponent("approvals")
        try Data("foreign".utf8).write(
            to: approvals.appendingPathComponent("foreign.json")
        )
        await #expect(throws: AgentRunDurableStoreError.self) {
            try await store.persistApprovalDecision(
                AgentApprovalDecisionJournalReceipt(
                    decisionID: "decision-two",
                    actorID: "operator",
                    decidedAtUnixMs: 2,
                    binding: binding,
                    choice: .deny
                )
            )
        }

        var firstCancellation = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        firstCancellation.runID = "run-cancel-one"
        firstCancellation.cancellationID = "cancel-one"
        try await store.persistCancellation(firstCancellation)
        let cancellations = fixture.rootURL.appendingPathComponent("cancellations")
        try Data("foreign".utf8).write(
            to: cancellations.appendingPathComponent("foreign.pb")
        )
        var secondCancellation = firstCancellation
        secondCancellation.runID = "run-cancel-two"
        secondCancellation.cancellationID = "cancel-two"
        await #expect(throws: AgentRunDurableStoreError.self) {
            try await store.persistCancellation(secondCancellation)
        }
    }

    @Test("snapshot admission fails closed when retention has no terminal candidate")
    func retentionCapacityNeverDisplacesLiveTruth() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(maxSnapshots: 1)
        )
        var first = Melix_Controlplane_V1_AgentRunSnapshot()
        first.runID = "run-live-one"
        first.state = "created"
        try await store.persistSnapshot(first)
        var second = first
        second.runID = "run-live-two"

        await #expect(
            throws: AgentRunDurableStoreError.retentionCapacityExhausted(
                kind: "snapshot"
            )
        ) {
            try await store.persistSnapshot(second)
        }
        #expect(try await store.snapshot(runID: first.runID) == first)
        #expect(try await store.snapshot(runID: second.runID) == nil)
    }

    @Test("snapshot preflight validates every entry before committing a new identity")
    func snapshotPreflightRejectsCorruptEntryBeforeRename() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(maxSnapshots: 2)
        )
        var terminal = Melix_Controlplane_V1_AgentRunSnapshot()
        terminal.runID = "run-preflight-terminal"
        terminal.state = "completed"
        try await store.persistSnapshot(terminal)
        let corruptURL = journalURL(
            root: fixture.rootURL,
            kind: "runs",
            identifier: "run-preflight-corrupt",
            extension: "pb"
        )
        try Data("corrupt".utf8).write(to: corruptURL)
        var candidate = Melix_Controlplane_V1_AgentRunSnapshot()
        candidate.runID = "run-preflight-candidate"
        candidate.state = "created"

        await #expect(
            throws: AgentRunDurableStoreError.invalidEntry(kind: "snapshot")
        ) {
            try await store.persistSnapshot(candidate)
        }

        #expect(try await store.snapshot(runID: candidate.runID) == nil)
    }

    @Test("snapshot retention maintenance fences different identities until exact recovery")
    func snapshotRetentionMaintenanceFencesDifferentRunIdentity() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let probe = AgentJournalFsyncFailureSequence(
            failingCalls: [7, 8]
        )
        var calls = AgentRunDurableStoreSystemCalls.live
        calls.fsync = { probe.fsync($0) }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(maxSnapshots: 2),
            systemCalls: calls
        )
        for index in 1...2 {
            var terminal = Melix_Controlplane_V1_AgentRunSnapshot()
            terminal.runID = "run-maintenance-terminal-\(index)"
            terminal.state = "completed"
            terminal.updatedAtUnixMs = Int64(index)
            try await store.persistSnapshot(terminal)
        }
        var committed = Melix_Controlplane_V1_AgentRunSnapshot()
        committed.runID = "run-maintenance-committed"
        committed.state = "created"
        committed.updatedAtUnixMs = 3
        await #expect(
            throws: AgentRunDurableStoreError.ioFailure(
                operation: "sync-directory",
                code: EIO
            )
        ) {
            try await store.persistSnapshot(committed)
        }
        #expect(try await store.snapshot(runID: committed.runID) == committed)
        #expect(await store.hasPendingSnapshotRetentionMaintenance())

        var blocked = committed
        blocked.runID = "run-maintenance-blocked"
        blocked.updatedAtUnixMs = 4
        await #expect(
            throws: AgentRunDurableStoreError.ioFailure(
                operation: "sync-directory",
                code: EIO
            )
        ) {
            try await store.persistSnapshot(blocked)
        }
        #expect(try await store.snapshot(runID: blocked.runID) == nil)
        #expect(await store.hasPendingSnapshotRetentionMaintenance())

        try await store.persistSnapshot(committed)
        #expect(await store.hasPendingSnapshotRetentionMaintenance() == false)
        try await store.persistSnapshot(blocked)
        #expect(try await store.snapshot(runID: blocked.runID) == blocked)
        #expect(await store.hasPendingSnapshotRetentionMaintenance() == false)
        let files = try FileManager.default.contentsOfDirectory(
            at: fixture.rootURL.appendingPathComponent("runs"),
            includingPropertiesForKeys: nil
        )
        #expect(files.count <= 2)
    }

    @Test("POSIX durability failures remain typed at every write boundary")
    func injectedSystemCallFailuresAreTyped() async throws {
        enum Failure: CaseIterable, Equatable {
            case chmodEntry
            case writeEntry
            case syncEntry
            case closeEntry
            case openDirectory
            case syncDirectory
        }

        for failure in Failure.allCases {
            let fixture = try AgentJournalFixture()
            defer { fixture.remove() }
            var calls = AgentRunDurableStoreSystemCalls.live
            switch failure {
            case .chmodEntry:
                calls.fchmod = { _, _ in
                    errno = EACCES
                    return -1
                }
            case .writeEntry:
                calls.write = { _, _, _ in
                    errno = EIO
                    return -1
                }
            case .syncEntry:
                calls.fsync = { _ in
                    errno = EIO
                    return -1
                }
            case .closeEntry:
                calls.close = { descriptor in
                    _ = Darwin.close(descriptor)
                    errno = EIO
                    return -1
                }
            case .openDirectory:
                let liveOpen = calls.open
                calls.open = { url, flags, mode in
                    if flags & O_CREAT == 0 {
                        errno = EACCES
                        return -1
                    }
                    return liveOpen(url, flags, mode)
                }
            case .syncDirectory:
                calls.fsync = { descriptor in
                    let flags = Darwin.fcntl(descriptor, F_GETFL)
                    if flags & O_ACCMODE == O_RDONLY {
                        errno = EIO
                        return -1
                    }
                    return Darwin.fsync(descriptor)
                }
            }
            let store = AgentRunDurableStore(
                rootURL: fixture.rootURL,
                systemCalls: calls
            )

            if failure == .chmodEntry {
                var cancellation =
                    Melix_Controlplane_V1_AgentRunCancellationReceipt()
                cancellation.runID = "run-fault"
                cancellation.cancellationID = "cancel-fault"
                await #expect(throws: AgentRunDurableStoreError.self) {
                    try await store.persistCancellation(cancellation)
                }
            } else {
                var snapshot = Melix_Controlplane_V1_AgentRunSnapshot()
                snapshot.runID = "run-fault"
                await #expect(throws: AgentRunDurableStoreError.self) {
                    try await store.persistSnapshot(snapshot)
                }
            }
        }
    }

    @Test("immutable receipts require durable commit and preflight hard capacity")
    func immutableReceiptsStayDurableAndBounded() async throws {
        let fixture = try AgentJournalFixture()
        defer { fixture.remove() }
        let firstCreateProbe = AgentJournalFsyncFailureSequence(
            failingCalls: [2]
        )
        var calls = AgentRunDurableStoreSystemCalls.live
        calls.fsync = { firstCreateProbe.fsync($0) }
        let store = AgentRunDurableStore(
            rootURL: fixture.rootURL,
            limits: AgentRunDurableStoreLimits(
                maxApprovalDecisions: 1,
                maxCancellations: 1
            ),
            systemCalls: calls
        )
        let call = AgentToolCall(
            callID: "call-post-write",
            sourceID: "mcp",
            toolName: "mail.send",
            schemaDigest: "schema-post-write",
            argumentsJSON: "{}"
        )
        let binding = AgentApprovalBinding.make(
            runID: "run-post-write",
            call: call,
            policyRevision: "1",
            scopeDigest: "scope-post-write"
        )
        let decision = AgentApprovalDecisionJournalReceipt(
            decisionID: "decision-post-write",
            actorID: "operator",
            decidedAtUnixMs: 10,
            binding: binding,
            choice: .allowOnce
        )
        await #expect(
            throws: AgentRunDurableStoreError.ioFailure(
                operation: "sync-directory",
                code: EIO
            )
        ) {
            try await store.persistApprovalDecision(decision)
        }
        // The uncertain first create is not accepted as a commit merely
        // because its file is currently readable. An exact retry must first
        // establish directory durability, then it becomes idempotent.
        try await store.persistApprovalDecision(decision)
        try await store.persistApprovalDecision(decision)
        #expect(
            try await store.approvalDecisions(runID: binding.runID)
                == [decision]
        )

        let conflicting = AgentApprovalDecisionJournalReceipt(
            decisionID: decision.decisionID,
            actorID: "different-operator",
            decidedAtUnixMs: decision.decidedAtUnixMs,
            binding: binding,
            choice: .allowOnce
        )
        await #expect(
            throws: AgentRunDurableStoreError.conflictingImmutableEntry(
                kind: "approval"
            )
        ) {
            try await store.persistApprovalDecision(conflicting)
        }

        var cancellation = Melix_Controlplane_V1_AgentRunCancellationReceipt()
        cancellation.runID = binding.runID
        cancellation.cancellationID = "cancel-post-write"
        cancellation.disposition = "accepted"
        cancellation.sideEffectState = .agentToolSideEffectNone
        try await store.persistCancellation(cancellation)
        try await store.persistCancellation(cancellation)
        #expect(
            try await store.cancellation(runID: binding.runID)
                == cancellation
        )

        let boundedRoot = fixture.rootURL.appendingPathComponent(
            "bounded-preflight",
            isDirectory: true
        )
        let capacityProbe = AgentJournalFsyncFailureSequence(
            failingCalls: [3]
        )
        var capacityCalls = AgentRunDurableStoreSystemCalls.live
        capacityCalls.fsync = { capacityProbe.fsync($0) }
        let boundedStore = AgentRunDurableStore(
            rootURL: boundedRoot,
            limits: AgentRunDurableStoreLimits(maxApprovalDecisions: 1),
            systemCalls: capacityCalls
        )
        let firstBounded = AgentApprovalDecisionJournalReceipt(
            decisionID: "decision-bounded-first",
            actorID: "operator",
            decidedAtUnixMs: 20,
            binding: binding,
            choice: .allowOnce
        )
        let secondBounded = AgentApprovalDecisionJournalReceipt(
            decisionID: "decision-bounded-second",
            actorID: "operator",
            decidedAtUnixMs: 21,
            binding: binding,
            choice: .deny
        )
        try await boundedStore.persistApprovalDecision(firstBounded)
        await #expect(
            throws: AgentRunDurableStoreError.ioFailure(
                operation: "sync-entry",
                code: EIO
            )
        ) {
            try await boundedStore.persistApprovalDecision(secondBounded)
        }
        let secondURL = journalURL(
            root: boundedRoot,
            kind: "approvals",
            identifier: secondBounded.decisionID,
            extension: "json"
        )
        #expect(!FileManager.default.fileExists(atPath: secondURL.path))
        #expect(
            try await boundedStore.approvalDecisions(
                runID: binding.runID
            ) == [firstBounded]
        )
        let boundedFiles = try FileManager.default.contentsOfDirectory(
            at: boundedRoot.appendingPathComponent("approvals"),
            includingPropertiesForKeys: nil
        )
        #expect(boundedFiles.count <= 1)

        let retryRoot = fixture.rootURL.appendingPathComponent(
            "exact-retry-double-sync-failure",
            isDirectory: true
        )
        let retryProbe = AgentJournalFsyncFailureSequence(
            failingCalls: [4, 5]
        )
        var retryCalls = AgentRunDurableStoreSystemCalls.live
        retryCalls.fsync = { retryProbe.fsync($0) }
        let retryStore = AgentRunDurableStore(
            rootURL: retryRoot,
            limits: AgentRunDurableStoreLimits(maxApprovalDecisions: 1),
            systemCalls: retryCalls
        )
        try await retryStore.persistApprovalDecision(firstBounded)
        await #expect(
            throws: AgentRunDurableStoreError.ioFailure(
                operation: "sync-directory",
                code: EIO
            )
        ) {
            try await retryStore.persistApprovalDecision(secondBounded)
        }
        await #expect(
            throws: AgentRunDurableStoreError.ioFailure(
                operation: "sync-directory",
                code: EIO
            )
        ) {
            try await retryStore.persistApprovalDecision(secondBounded)
        }
        let retryFirstURL = journalURL(
            root: retryRoot,
            kind: "approvals",
            identifier: firstBounded.decisionID,
            extension: "json"
        )
        let retrySecondURL = journalURL(
            root: retryRoot,
            kind: "approvals",
            identifier: secondBounded.decisionID,
            extension: "json"
        )
        // Neither failed exact-retry directory sync may delete the previous
        // committed receipt before the new identity is confirmed durable.
        #expect(FileManager.default.fileExists(atPath: retryFirstURL.path))
        #expect(FileManager.default.fileExists(atPath: retrySecondURL.path))
        try await retryStore.persistApprovalDecision(secondBounded)
        #expect(
            try await retryStore.approvalDecisions(runID: binding.runID)
                == [secondBounded]
        )

        let maintenanceRoot = fixture.rootURL.appendingPathComponent(
            "post-commit-maintenance",
            isDirectory: true
        )
        let maintenanceProbe = AgentJournalFsyncFailureSequence(
            failingCalls: [5]
        )
        var maintenanceCalls = AgentRunDurableStoreSystemCalls.live
        maintenanceCalls.fsync = { maintenanceProbe.fsync($0) }
        let maintenanceStore = AgentRunDurableStore(
            rootURL: maintenanceRoot,
            limits: AgentRunDurableStoreLimits(maxApprovalDecisions: 1),
            systemCalls: maintenanceCalls
        )
        try await maintenanceStore.persistApprovalDecision(firstBounded)
        // Call five is the second write's post-commit retention directory
        // sync. The new immutable decision is already durable, so persistence
        // returns success and exposes pending maintenance instead of lying to
        // the caller that the decision failed.
        try await maintenanceStore.persistApprovalDecision(secondBounded)
        #expect(
            try await maintenanceStore.approvalDecisions(
                runID: binding.runID
            ) == [secondBounded]
        )
        #expect(
            await maintenanceStore.pendingImmutableMaintenanceKinds()
                == ["approval"]
        )
        try await maintenanceStore.persistApprovalDecision(secondBounded)
        #expect(
            await maintenanceStore.pendingImmutableMaintenanceKinds().isEmpty
        )
        let maintenanceFiles = try FileManager.default.contentsOfDirectory(
            at: maintenanceRoot.appendingPathComponent("approvals"),
            includingPropertiesForKeys: nil
        )
        #expect(maintenanceFiles.count <= 2)
    }
}

private struct AgentJournalFixture {
    let rootURL: URL

    init() throws {
        rootURL = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-agent-journal-tests-\(UUID().uuidString)",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: rootURL,
            withIntermediateDirectories: true
        )
    }

    func remove() {
        try? FileManager.default.removeItem(at: rootURL)
    }
}

private final class AgentJournalFsyncFailureSequence: @unchecked Sendable {
    private let lock = NSLock()
    private let failingCalls: Set<Int>
    private var callCount = 0

    init(failingCalls: Set<Int>) {
        self.failingCalls = failingCalls
    }

    func fsync(_ descriptor: Int32) -> Int32 {
        lock.lock()
        callCount += 1
        let shouldFail = failingCalls.contains(callCount)
        lock.unlock()
        if shouldFail {
            errno = EIO
            return -1
        }
        return Darwin.fsync(descriptor)
    }
}

private func journalURL(
    root: URL,
    kind: String,
    identifier: String,
    extension pathExtension: String
) -> URL {
    let key = SHA256.hash(data: Data(identifier.utf8)).map { byte in
        String(format: "%02x", byte)
    }.joined()
    return root
        .appendingPathComponent(kind, isDirectory: true)
        .appendingPathComponent(key)
        .appendingPathExtension(pathExtension)
}
