import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Approval Policy Store", .serialized)
struct ApprovalPolicyStoreTests {
    @Test("always allow persists atomically with mode 0600 and no raw arguments")
    func alwaysAllowPersistsSecurelyWithoutRawArguments() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let context = safeContext()
        let provider = MutableApprovalContextProvider(contexts: ["run-secure": context])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        let call = toolCall(argumentsJSON: #"{"password":"credential-secret"}"#)

        let manager: any AgentApprovalPolicyManaging = store
        let revision = try await manager.persistAlwaysAllow(for: call, runID: "run-secure")

        #expect(revision == "1")
        let attributes = try FileManager.default.attributesOfItem(
            atPath: fixture.fileURL.path
        )
        let permissions = try #require(attributes[.posixPermissions] as? NSNumber)
        #expect(permissions.intValue & 0o777 == 0o600)

        let persisted = try String(contentsOf: fixture.fileURL, encoding: .utf8)
        #expect(!persisted.contains("credential-secret"))
        #expect(!persisted.contains("password"))
        #expect(!persisted.contains("argumentsJSON"))
        let siblingNames = try FileManager.default.contentsOfDirectory(
            atPath: fixture.directoryURL.path
        )
        #expect(!siblingNames.contains { $0.contains(".tmp-") })

        let reloaded = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        let snapshot = try await reloaded.snapshot()
        #expect(snapshot.revision == 1)
        #expect(snapshot.rules.count == 1)
        let exactRule = try #require(snapshot.rules.first)
        #expect(exactRule.sourceID == context.sourceID)
        #expect(exactRule.toolName == context.toolName)
        #expect(exactRule.riskClass == context.riskClass)
        #expect(exactRule.operationKind == context.operationKind)
        #expect(exactRule.workspaceScope == context.workspaceScope)
        #expect(exactRule.appBundleID == context.appBundleID)
        #expect(exactRule.networkHost == context.networkHost)
        #expect(exactRule.schemaDigest == call.schemaDigest)
        let evaluation = await reloaded.approvalEvaluation(for: call, runID: "run-secure")
        #expect(evaluation.requirement == .notRequired)
        #expect(evaluation.policyRevision == "1")

        await provider.setContext(
            safeContext(workspaceScope: "workspace-b"),
            runID: "other-workspace"
        )
        let otherWorkspace = await reloaded.approvalEvaluation(
            for: call,
            runID: "other-workspace"
        )
        #expect(otherWorkspace.requirement == .required)
    }

    @Test("revision comparison prevents stale writers across store instances")
    func revisionComparisonPreventsStaleWriters() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: [:])
        let firstStore = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        let secondStore = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)

        let first = try await firstStore.replaceRules(
            [AgentApprovalPolicyRule(id: "default-ask", effect: .ask)],
            expectedRevision: 0
        )
        #expect(first.revision == 1)

        do {
            _ = try await secondStore.replaceRules(
                [AgentApprovalPolicyRule(id: "default-deny", effect: .deny)],
                expectedRevision: 0
            )
            Issue.record("Expected a stale policy revision to be rejected.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .revisionMismatch(expected: 0, actual: 1))
        }

        let second = try await secondStore.replaceRules(
            [AgentApprovalPolicyRule(id: "default-deny", effect: .deny)],
            expectedRevision: 1
        )
        #expect(second.revision == 2)
        let refreshed = try await firstStore.snapshot()
        #expect(refreshed.revision == 2)
    }

    @Test("policy replacement revalidates its deadline immediately before persistence")
    func policyReplacementDeadlineExpiresBeforePersistence() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let clock = PolicyScriptedClock(
            values: [
                Date(timeIntervalSince1970: 1_000),
                Date(timeIntervalSince1970: 1_002),
            ]
        )
        let store = ApprovalPolicyStore(
            fileURL: fixture.fileURL,
            contextProvider: MutableApprovalContextProvider(contexts: [:]),
            now: { clock.now() }
        )

        await #expect(throws: ApprovalPolicyStoreError.deadlineExceeded) {
            try await store.replaceRules(
                [AgentApprovalPolicyRule(id: "must-not-persist", effect: .deny)],
                expectedRevision: 0,
                deadlineUnixMs: 1_001_000
            )
        }

        #expect(!FileManager.default.fileExists(atPath: fixture.fileURL.path))
        let snapshot = try await store.snapshot()
        #expect(snapshot.revision == 0)
        #expect(snapshot.rules.isEmpty)
    }

    @Test("every policy selector participates in matching")
    func everyPolicySelectorParticipatesInMatching() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let exactContext = safeContext()
        let provider = MutableApprovalContextProvider(contexts: ["exact": exactContext])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        _ = try await store.replaceRules(
            [
                AgentApprovalPolicyRule(
                    id: "full-match",
                    effect: .allow,
                    sourceID: "mcp-source",
                    toolName: "mail.send-draft",
                    riskClass: .low,
                    operationKind: .read,
                    workspaceScope: "workspace-a",
                    appBundleID: "com.example.Mail",
                    networkHost: "api.example.test",
                    schemaDigest: "schema-v1"
                ),
            ],
            expectedRevision: 0
        )

        let exact = await store.approvalEvaluation(for: toolCall(), runID: "exact")
        #expect(exact.requirement == .notRequired)

        let mismatches: [(String, AgentToolCall, AgentApprovalPolicyContext)] = [
            (
                "source",
                toolCall(sourceID: "other-source"),
                safeContext(sourceID: "other-source")
            ),
            (
                "tool",
                toolCall(toolName: "mail.other"),
                safeContext(toolName: "mail.other")
            ),
            ("risk", toolCall(), safeContext(riskClass: .medium)),
            ("operation", toolCall(), safeContext(operationKind: .write)),
            ("workspace", toolCall(), safeContext(workspaceScope: "workspace-b")),
            ("app", toolCall(), safeContext(appBundleID: "com.example.Other")),
            ("host", toolCall(), safeContext(networkHost: "other.example.test")),
        ]
        for (label, call, context) in mismatches {
            let runID = "mismatch-\(label)"
            await provider.setContext(context, runID: runID)
            let evaluation = await store.approvalEvaluation(for: call, runID: runID)
            #expect(evaluation.requirement == .required, "selector mismatch: \(label)")
        }
    }

    @Test("deny wins, then ask, with specificity breaking same-effect ties")
    func specificityAndEffectPrecedenceAreDeterministic() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: [
            "specific": safeContext(),
            "tie": safeContext(toolName: "mail.unmatched"),
            "ask-over-allow": safeContext(
                sourceID: "mcp-ask",
                workspaceScope: "workspace-b"
            ),
        ])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        _ = try await store.replaceRules(
            [
                AgentApprovalPolicyRule(
                    id: "broad-deny",
                    effect: .deny,
                    sourceID: "mcp-source"
                ),
                AgentApprovalPolicyRule(
                    id: "specific-allow",
                    effect: .allow,
                    sourceID: "mcp-source",
                    toolName: "mail.send-draft"
                ),
                AgentApprovalPolicyRule(
                    id: "tie-allow",
                    effect: .allow,
                    riskClass: .low
                ),
                AgentApprovalPolicyRule(
                    id: "tie-ask",
                    effect: .ask,
                    operationKind: .read
                ),
                AgentApprovalPolicyRule(
                    id: "tie-deny",
                    effect: .deny,
                    workspaceScope: "workspace-a"
                ),
                AgentApprovalPolicyRule(
                    id: "broad-ask",
                    effect: .ask,
                    sourceID: "mcp-ask"
                ),
                AgentApprovalPolicyRule(
                    id: "specific-allow-under-ask",
                    effect: .allow,
                    sourceID: "mcp-ask",
                    toolName: "mail.send-draft"
                ),
            ],
            expectedRevision: 0
        )

        let specific = await store.approvalEvaluation(for: toolCall(), runID: "specific")
        #expect(specific.requirement == .denied)

        let tieCall = toolCall(toolName: "mail.unmatched")
        let tie = await store.approvalEvaluation(for: tieCall, runID: "tie")
        #expect(tie.requirement == .denied)

        let askOverAllow = await store.approvalEvaluation(
            for: toolCall(sourceID: "mcp-ask"),
            runID: "ask-over-allow"
        )
        #expect(askOverAllow.requirement == .required)
    }

    @Test("unsafe and unknown calls cannot be opened by a broad allow rule")
    func failClosedFloorOverridesBroadAllow() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: [:])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        _ = try await store.replaceRules(
            [AgentApprovalPolicyRule(id: "allow-all", effect: .allow)],
            expectedRevision: 0
        )

        let cases: [(String, AgentApprovalPolicyContext, AgentApprovalRequirement)] = [
            ("unknown-tool", safeContext(toolKnown: false), .required),
            ("unknown-schema", safeContext(schemaState: .unknown), .required),
            ("changed-schema", safeContext(schemaState: .changed), .required),
            ("unknown-risk", safeContext(riskClass: .unknown), .required),
            ("unknown-operation", safeContext(operationKind: .unknown), .required),
            ("credential", safeContext(operationKind: .credentialAccess), .denied),
            ("authentication", safeContext(operationKind: .authentication), .denied),
            ("upload", safeContext(operationKind: .upload), .required),
            ("send", safeContext(operationKind: .send), .required),
            ("purchase", safeContext(operationKind: .purchase), .denied),
            ("destructive", safeContext(operationKind: .destructiveMutation), .denied),
            ("process", safeContext(operationKind: .processExecution), .denied),
            ("secure-field", safeContext(operationKind: .secureFieldInteraction), .denied),
            ("critical-risk", safeContext(riskClass: .critical), .denied),
        ]

        for (label, context, expected) in cases {
            let runID = "unsafe-\(label)"
            await provider.setContext(context, runID: runID)
            let evaluation = await store.approvalEvaluation(
                for: toolCall(riskClass: context.riskClass.rawValue),
                runID: runID
            )
            #expect(evaluation.requirement == expected, "fail-closed case: \(label)")
            #expect(evaluation.policyRevision == "1")
        }

        let missingContext = await store.approvalEvaluation(
            for: toolCall(),
            runID: "missing-context"
        )
        #expect(missingContext.requirement == .required)
        #expect(missingContext.policyRevision == "1")

        await provider.setContext(safeContext(), runID: "risk-mismatch")
        let riskMismatch = await store.approvalEvaluation(
            for: toolCall(riskClass: "critical"),
            runID: "risk-mismatch"
        )
        #expect(riskMismatch.requirement == .required)
    }

    @Test("always allow upserts one exact rule and schema changes invalidate it")
    func alwaysAllowUpsertsAndSchemaChangesInvalidateIt() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: [
            "current": safeContext(),
            "changed": safeContext(),
        ])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        let firstRevision = try await store.persistAlwaysAllow(
            for: toolCall(),
            runID: "current"
        )
        let secondRevision = try await store.persistAlwaysAllow(
            for: toolCall(),
            runID: "current"
        )

        #expect(firstRevision == "1")
        #expect(secondRevision == "2")
        let snapshot = try await store.snapshot()
        #expect(snapshot.revision == 2)
        #expect(snapshot.rules.count == 1)
        let current = await store.approvalEvaluation(for: toolCall(), runID: "current")
        #expect(current.requirement == .notRequired)

        let changedCall = toolCall(schemaDigest: "schema-v2")
        let changed = await store.approvalEvaluation(for: changedCall, runID: "changed")
        #expect(changed.requirement == .required)
    }

    @Test("runtime risk vocabulary maps to durable policy classes")
    func runtimeRiskVocabularyMapsToPolicyClasses() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let registry = AgentApprovalContextRegistry()
        await registry.register(
            runID: "computer-run",
            sessionID: "chat-session",
            branchID: "branch-main"
        )
        let store = ApprovalPolicyStore(
            fileURL: fixture.fileURL,
            contextProvider: registry
        )
        let call = toolCall(
            sourceID: "computer",
            toolName: "computer_use",
            riskClass: "computer_control",
            argumentsJSON: #"{"operation":"press_element","target":{"bundle_id":"com.example.Target"}}"#
        )

        let initial = await store.approvalEvaluation(
            for: call,
            runID: "computer-run"
        )
        #expect(initial.requirement == .required)

        let revision = try await store.persistAlwaysAllow(
            for: call,
            runID: "computer-run"
        )
        #expect(revision == "1")
        let admitted = await store.approvalEvaluation(
            for: call,
            runID: "computer-run"
        )
        #expect(admitted.requirement == .notRequired)

        let snapshot = try await store.snapshot()
        let rule = try #require(snapshot.rules.first)
        #expect(rule.riskClass == .high)
        #expect(rule.operationKind == .write)
        #expect(rule.appBundleID == "com.example.Target")
        #expect(rule.workspaceScope == "session:chat-session/branch:branch-main")
    }

    @Test("unknown runtime risk remains ineligible for always allow")
    func unknownRuntimeRiskRemainsIneligibleForAlwaysAllow() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let registry = AgentApprovalContextRegistry()
        await registry.register(
            runID: "mcp-run",
            sessionID: "chat-session",
            branchID: "branch-main"
        )
        let store = ApprovalPolicyStore(
            fileURL: fixture.fileURL,
            contextProvider: registry
        )
        let call = toolCall(
            sourceID: "mcp-source",
            toolName: "mcp-source.search",
            riskClass: "unknown"
        )

        do {
            _ = try await store.persistAlwaysAllow(for: call, runID: "mcp-run")
            Issue.record("Expected unknown MCP metadata to remain fail closed.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .approvalContextMismatch)
        }
        let evaluation = await store.approvalEvaluation(
            for: call,
            runID: "mcp-run"
        )
        #expect(evaluation.requirement == .required)
    }

    @Test("safety-floor operations cannot persist an ineffective always-allow rule")
    func safetyFloorOperationsCannotPersistAlwaysAllow() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: [
            "upload-run": safeContext(operationKind: .upload),
            "send-run": safeContext(operationKind: .send),
        ])
        let store = ApprovalPolicyStore(
            fileURL: fixture.fileURL,
            contextProvider: provider
        )

        for runID in ["upload-run", "send-run"] {
            await #expect(throws: ApprovalPolicyStoreError.approvalContextMismatch) {
                try await store.persistAlwaysAllow(for: toolCall(), runID: runID)
            }
            let evaluation = await store.approvalEvaluation(
                for: toolCall(),
                runID: runID
            )
            #expect(evaluation.requirement == .required)
        }

        let snapshot = try await store.snapshot()
        #expect(snapshot.revision == 0)
        #expect(snapshot.rules.isEmpty)
    }

    @Test("always allow preserves unrelated rules when optional scope is absent")
    func alwaysAllowPreservesUnrelatedRulesWithoutOptionalScope() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let context = safeContext(
            workspaceScope: nil,
            appBundleID: nil,
            networkHost: nil
        )
        let provider = MutableApprovalContextProvider(contexts: ["run": context])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)
        _ = try await store.replaceRules(
            [
                AgentApprovalPolicyRule(
                    id: "preserved-rule",
                    effect: .ask,
                    sourceID: "other-source"
                ),
            ],
            expectedRevision: 0
        )

        let revision = try await store.persistAlwaysAllow(for: toolCall(), runID: "run")

        #expect(revision == "2")
        let snapshot = try await store.snapshot()
        #expect(snapshot.rules.count == 2)
        #expect(snapshot.rules.contains { $0.id == "preserved-rule" })
        let exactRule = try #require(snapshot.rules.first { $0.effect == .allow })
        #expect(exactRule.workspaceScope == nil)
        #expect(exactRule.appBundleID == nil)
        #expect(exactRule.networkHost == nil)
        let evaluation = await store.approvalEvaluation(for: toolCall(), runID: "run")
        #expect(evaluation.requirement == .notRequired)
    }

    @Test("always allow fails closed without a current call context")
    func alwaysAllowRequiresCurrentContext() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: [:])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)

        do {
            _ = try await store.persistAlwaysAllow(for: toolCall(), runID: "missing")
            Issue.record("Expected missing approval context to reject Always Allow.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .approvalContextUnavailable)
        }

        let snapshot = try await store.snapshot()
        #expect(snapshot.revision == 0)
        #expect(snapshot.rules.isEmpty)
        #expect(!FileManager.default.fileExists(atPath: fixture.fileURL.path))
    }

    @Test("invalid mutations fail before policy persistence")
    func invalidMutationsFailBeforePersistence() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: ["run": safeContext()])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)

        do {
            _ = try await store.replaceRules(
                [AgentApprovalPolicyRule(id: " ", effect: .allow)],
                expectedRevision: 0
            )
            Issue.record("Expected an empty policy rule ID to be rejected.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .invalidRule(id: " "))
        }

        do {
            _ = try await store.replaceRules(
                [
                    AgentApprovalPolicyRule(id: "duplicate", effect: .ask),
                    AgentApprovalPolicyRule(id: "duplicate", effect: .deny),
                ],
                expectedRevision: 0
            )
            Issue.record("Expected duplicate policy rule IDs to be rejected.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .duplicateRuleID(id: "duplicate"))
        }

        do {
            _ = try await store.persistAlwaysAllow(
                for: toolCall(sourceID: " "),
                runID: "run"
            )
            Issue.record("Expected an incomplete tool identity to be rejected.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .invalidRule(id: "always-allow"))
        }

        do {
            _ = try await store.persistAlwaysAllow(
                for: toolCall(riskClass: "critical"),
                runID: "run"
            )
            Issue.record("Expected a call/context mismatch to be rejected.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .approvalContextMismatch)
        }

        let snapshot = try await store.snapshot()
        #expect(snapshot.revision == 0)
        #expect(!FileManager.default.fileExists(atPath: fixture.fileURL.path))
    }

    @Test("revision exhaustion rejects every policy mutation")
    func revisionExhaustionRejectsEveryMutation() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let document = AgentApprovalPolicySnapshot(revision: UInt64.max, rules: [])
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        try encoder.encode(document).write(to: fixture.fileURL)
        let provider = MutableApprovalContextProvider(contexts: ["run": safeContext()])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)

        do {
            _ = try await store.replaceRules([], expectedRevision: UInt64.max)
            Issue.record("Expected replaceRules to reject an exhausted revision.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .revisionExhausted)
        }

        do {
            _ = try await store.persistAlwaysAllow(for: toolCall(), runID: "run")
            Issue.record("Expected Always Allow to reject an exhausted revision.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .revisionExhausted)
        }
    }

    @Test("lock and atomic-write filesystem failures remain typed")
    func filesystemFailuresRemainTyped() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: [:])

        let blockingFile = fixture.directoryURL.appendingPathComponent("not-a-directory")
        try Data("blocking".utf8).write(to: blockingFile)
        let blockedStore = ApprovalPolicyStore(
            fileURL: blockingFile.appendingPathComponent("policy.json"),
            contextProvider: provider
        )
        do {
            _ = try await blockedStore.replaceRules([], expectedRevision: 0)
            Issue.record("Expected lock preparation below a file to fail.")
        } catch let error as ApprovalPolicyStoreError {
            guard case let .ioFailure(operation, _) = error else {
                Issue.record("Expected a typed lock-preparation failure, got \(error).")
                return
            }
            #expect(operation == "prepare-lock")
        }

        let lockDirectoryPolicy = fixture.directoryURL.appendingPathComponent("lock-dir.json")
        try FileManager.default.createDirectory(
            at: lockDirectoryPolicy.appendingPathExtension("lock"),
            withIntermediateDirectories: true
        )
        let lockDirectoryStore = ApprovalPolicyStore(
            fileURL: lockDirectoryPolicy,
            contextProvider: provider
        )
        do {
            _ = try await lockDirectoryStore.replaceRules([], expectedRevision: 0)
            Issue.record("Expected a directory at the lock path to fail acquisition.")
        } catch let error as ApprovalPolicyStoreError {
            guard case let .ioFailure(operation, _) = error else {
                Issue.record("Expected a typed lock-acquisition failure, got \(error).")
                return
            }
            #expect(operation == "acquire-lock")
        }

        let permissionStore = ApprovalPolicyStore(
            fileURL: fixture.fileURL,
            contextProvider: provider
        )
        _ = try await permissionStore.replaceRules([], expectedRevision: 0)
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o500)],
            ofItemAtPath: fixture.directoryURL.path
        )
        defer {
            try? FileManager.default.setAttributes(
                [.posixPermissions: NSNumber(value: 0o700)],
                ofItemAtPath: fixture.directoryURL.path
            )
        }
        do {
            _ = try await permissionStore.replaceRules([], expectedRevision: 1)
            Issue.record("Expected a read-only policy directory to reject its temp file.")
        } catch let error as ApprovalPolicyStoreError {
            guard case let .ioFailure(operation, _) = error else {
                Issue.record("Expected a typed atomic-write failure, got \(error).")
                return
            }
            #expect(operation == "open-temporary")
        }
    }

    @Test("corrupt policy JSON fails closed through the nonthrowing port")
    func corruptPolicyJSONFailsClosed() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        try Data(#"{"schemaVersion":"wrong"}"#.utf8).write(to: fixture.fileURL)
        let provider = MutableApprovalContextProvider(contexts: ["run": safeContext()])
        let store = ApprovalPolicyStore(fileURL: fixture.fileURL, contextProvider: provider)

        let evaluation = await store.approvalEvaluation(for: toolCall(), runID: "run")

        #expect(evaluation.requirement == .denied)
        #expect(evaluation.policyRevision == "unavailable")
        do {
            _ = try await store.snapshot()
            Issue.record("Expected corrupt policy JSON to fail snapshot loading.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .invalidDocument)
        }

        let wrongVersionURL = fixture.directoryURL.appendingPathComponent("wrong-version.json")
        let wrongVersion = AgentApprovalPolicySnapshot(
            schemaVersion: "wrong",
            revision: 0,
            rules: []
        )
        try JSONEncoder().encode(wrongVersion).write(to: wrongVersionURL)
        let wrongVersionStore = ApprovalPolicyStore(
            fileURL: wrongVersionURL,
            contextProvider: provider
        )
        do {
            _ = try await wrongVersionStore.snapshot()
            Issue.record("Expected an unknown policy schema version to be rejected.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .invalidDocument)
        }
    }

    @Test("always allow uses a compare-and-swap revision and leaves no stale allow")
    func alwaysAllowRejectsStaleExpectedRevision() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: ["run": safeContext()])
        let store = ApprovalPolicyStore(
            fileURL: fixture.fileURL,
            contextProvider: provider
        )
        _ = try await store.replaceRules(
            [AgentApprovalPolicyRule(id: "default-ask", effect: .ask)],
            expectedRevision: 0
        )

        do {
            _ = try await store.persistAlwaysAllow(
                for: toolCall(),
                runID: "run",
                expectedRevision: "0"
            )
            Issue.record("Expected stale Always Allow CAS to fail.")
        } catch let error as ApprovalPolicyStoreError {
            #expect(error == .revisionMismatch(expected: 0, actual: 1))
        }

        let snapshot = try await store.snapshot()
        #expect(snapshot.revision == 1)
        #expect(snapshot.rules == [
            AgentApprovalPolicyRule(id: "default-ask", effect: .ask),
        ])
        #expect(!snapshot.rules.contains { $0.effect == .allow })
    }

    @Test("scope changes invalidate a binding even when policy revision is unchanged")
    func scopeDigestInvalidatesBindingWithoutRevisionChange() async throws {
        let fixture = try PolicyStoreFixture()
        defer { fixture.remove() }
        let provider = MutableApprovalContextProvider(contexts: ["run": safeContext()])
        let store = ApprovalPolicyStore(
            fileURL: fixture.fileURL,
            contextProvider: provider
        )
        let call = toolCall()
        let evaluation = await store.approvalEvaluation(for: call, runID: "run")
        let binding = AgentApprovalBinding.make(
            runID: "run",
            call: call,
            policyRevision: evaluation.policyRevision,
            scopeDigest: evaluation.scopeDigest
        )
        #expect(await store.isApprovalBindingCurrent(
            binding,
            for: call,
            runID: "run",
            expectedRequirement: .required
        ))

        await provider.setContext(
            safeContext(workspaceScope: "workspace-b"),
            runID: "run"
        )
        #expect(!(await store.isApprovalBindingCurrent(
            binding,
            for: call,
            runID: "run",
            expectedRequirement: .required
        )))
    }
}

private final class PolicyScriptedClock: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [Date]

    init(values: [Date]) {
        precondition(!values.isEmpty)
        self.values = values
    }

    func now() -> Date {
        lock.withLock {
            if values.count == 1 {
                return values[0]
            }
            return values.removeFirst()
        }
    }
}

private struct PolicyStoreFixture {
    let directoryURL: URL
    let fileURL: URL

    init() throws {
        directoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-approval-policy-\(UUID().uuidString)", isDirectory: true)
        fileURL = directoryURL.appendingPathComponent("policies.json", isDirectory: false)
        try FileManager.default.createDirectory(
            at: directoryURL,
            withIntermediateDirectories: true
        )
    }

    func remove() {
        try? FileManager.default.removeItem(at: directoryURL)
    }
}

private actor MutableApprovalContextProvider: AgentApprovalContextProviding {
    private var contexts: [String: AgentApprovalPolicyContext]

    init(contexts: [String: AgentApprovalPolicyContext]) {
        self.contexts = contexts
    }

    func context(for _: AgentToolCall, runID: String) async -> AgentApprovalPolicyContext? {
        contexts[runID]
    }

    func setContext(_ context: AgentApprovalPolicyContext, runID: String) {
        contexts[runID] = context
    }
}

private func safeContext(
    sourceID: String = "mcp-source",
    toolName: String = "mail.send-draft",
    riskClass: AgentApprovalRiskClass = .low,
    operationKind: AgentApprovalOperationKind = .read,
    workspaceScope: String? = "workspace-a",
    appBundleID: String? = "com.example.Mail",
    networkHost: String? = "api.example.test",
    toolKnown: Bool = true,
    schemaState: AgentApprovalSchemaState = .current
) -> AgentApprovalPolicyContext {
    AgentApprovalPolicyContext(
        sourceID: sourceID,
        toolName: toolName,
        riskClass: riskClass,
        operationKind: operationKind,
        workspaceScope: workspaceScope,
        appBundleID: appBundleID,
        networkHost: networkHost,
        toolKnown: toolKnown,
        schemaState: schemaState
    )
}

private func toolCall(
    sourceID: String = "mcp-source",
    toolName: String = "mail.send-draft",
    riskClass: String = "low",
    schemaDigest: String = "schema-v1",
    argumentsJSON: String = #"{"message":"hello"}"#
) -> AgentToolCall {
    AgentToolCall(
        callID: "call-1",
        sourceID: sourceID,
        toolName: toolName,
        title: "Send draft",
        intendedEffect: "Read draft metadata",
        riskClass: riskClass,
        schemaDigest: schemaDigest,
        argumentsJSON: argumentsJSON
    )
}
