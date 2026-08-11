import Darwin
import CryptoKit
import Foundation

public enum AgentApprovalPolicyEffect: String, Codable, Sendable, Equatable {
    case allow
    case ask
    case deny
}

public enum AgentApprovalRiskClass: String, Codable, Sendable, Equatable {
    case unknown
    case low
    case medium
    case high
    case critical

    static func fromRuntimeValue(_ value: String) -> Self? {
        switch value.trimmingCharacters(
            in: .whitespacesAndNewlines
        ).lowercased() {
        case "unknown":
            return .unknown
        case "low", "local_read_or_compute":
            return .low
        case "medium", "network_read":
            return .medium
        case "high", "argument_dependent", "computer_control":
            return .high
        case "critical":
            return .critical
        default:
            return nil
        }
    }
}

public enum AgentApprovalOperationKind: String, Codable, Sendable, Equatable {
    case unknown
    case read
    case write
    case credentialAccess
    case authentication
    case upload
    case send
    case purchase
    case destructiveMutation
    case processExecution
    case secureFieldInteraction
}

public enum AgentApprovalSchemaState: String, Codable, Sendable, Equatable {
    case current
    case changed
    case unknown
}

public struct AgentApprovalPolicyContext: Sendable, Equatable {
    public let sourceID: String
    public let toolName: String
    public let riskClass: AgentApprovalRiskClass
    public let operationKind: AgentApprovalOperationKind
    public let workspaceScope: String?
    public let appBundleID: String?
    public let networkHost: String?
    public let toolKnown: Bool
    public let schemaState: AgentApprovalSchemaState

    public init(
        sourceID: String,
        toolName: String,
        riskClass: AgentApprovalRiskClass,
        operationKind: AgentApprovalOperationKind,
        workspaceScope: String? = nil,
        appBundleID: String? = nil,
        networkHost: String? = nil,
        toolKnown: Bool,
        schemaState: AgentApprovalSchemaState
    ) {
        self.sourceID = sourceID
        self.toolName = toolName
        self.riskClass = riskClass
        self.operationKind = operationKind
        self.workspaceScope = workspaceScope
        self.appBundleID = appBundleID
        self.networkHost = networkHost?.lowercased()
        self.toolKnown = toolKnown
        self.schemaState = schemaState
    }
}

public protocol AgentApprovalContextProviding: Sendable {
    func context(
        for call: AgentToolCall,
        runID: String
    ) async -> AgentApprovalPolicyContext?
}

public protocol AgentApprovalPolicyAdministering:
    AgentApprovalPolicyManaging,
    Actor
{
    func snapshot() throws -> AgentApprovalPolicySnapshot
    func replaceRules(
        _ rules: [AgentApprovalPolicyRule],
        expectedRevision: UInt64,
        deadlineUnixMs: Int64
    ) async throws -> AgentApprovalPolicyMutationReceipt
}

public extension AgentApprovalPolicyAdministering {
    func replaceRules(
        _ rules: [AgentApprovalPolicyRule],
        expectedRevision: UInt64
    ) async throws -> AgentApprovalPolicyMutationReceipt {
        try await replaceRules(
            rules,
            expectedRevision: expectedRevision,
            deadlineUnixMs: 0
        )
    }
}

public struct AgentApprovalPolicyRule: Codable, Sendable, Equatable {
    public let id: String
    public let effect: AgentApprovalPolicyEffect
    public let sourceID: String?
    public let toolName: String?
    public let riskClass: AgentApprovalRiskClass?
    public let operationKind: AgentApprovalOperationKind?
    public let workspaceScope: String?
    public let appBundleID: String?
    public let networkHost: String?
    public let schemaDigest: String?

    public init(
        id: String,
        effect: AgentApprovalPolicyEffect,
        sourceID: String? = nil,
        toolName: String? = nil,
        riskClass: AgentApprovalRiskClass? = nil,
        operationKind: AgentApprovalOperationKind? = nil,
        workspaceScope: String? = nil,
        appBundleID: String? = nil,
        networkHost: String? = nil,
        schemaDigest: String? = nil
    ) {
        self.id = id
        self.effect = effect
        self.sourceID = sourceID
        self.toolName = toolName
        self.riskClass = riskClass
        self.operationKind = operationKind
        self.workspaceScope = workspaceScope
        self.appBundleID = appBundleID
        self.networkHost = networkHost?.lowercased()
        self.schemaDigest = schemaDigest
    }
}

public struct AgentApprovalPolicySnapshot: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let revision: UInt64
    public let rules: [AgentApprovalPolicyRule]

    public init(
        schemaVersion: String = ApprovalPolicyStore.documentSchemaVersion,
        revision: UInt64,
        rules: [AgentApprovalPolicyRule]
    ) {
        self.schemaVersion = schemaVersion
        self.revision = revision
        self.rules = rules
    }
}

public struct AgentApprovalPolicyMutationReceipt: Sendable, Equatable {
    public let revision: UInt64
    public let ruleCount: Int

    public init(revision: UInt64, ruleCount: Int) {
        self.revision = revision
        self.ruleCount = ruleCount
    }
}

public enum ApprovalPolicyStoreError: Error, Sendable, Equatable {
    case deadlineExceeded
    case invalidDocument
    case invalidRule(id: String)
    case duplicateRuleID(id: String)
    case approvalContextUnavailable
    case approvalContextMismatch
    case revisionMismatch(expected: UInt64, actual: UInt64)
    case revisionExhausted
    case ioFailure(operation: String, code: Int32)
}

public actor ApprovalPolicyStore: AgentApprovalPolicyAdministering {
    public static let documentSchemaVersion = "melix.agent-approval-policy.v1"

    private let fileURL: URL
    private let contextProvider: any AgentApprovalContextProviding
    private let now: @Sendable () -> Date

    public init(
        fileURL: URL,
        contextProvider: any AgentApprovalContextProviding,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.fileURL = fileURL
        self.contextProvider = contextProvider
        self.now = now
    }

    public func snapshot() throws -> AgentApprovalPolicySnapshot {
        try loadSnapshot()
    }

    public func replaceRules(
        _ rules: [AgentApprovalPolicyRule],
        expectedRevision: UInt64,
        deadlineUnixMs: Int64
    ) async throws -> AgentApprovalPolicyMutationReceipt {
        try requireUnexpiredMutation(deadlineUnixMs)
        try Self.validateRules(rules)
        return try await withExclusiveLock {
            let current = try loadSnapshot()
            guard current.revision == expectedRevision else {
                throw ApprovalPolicyStoreError.revisionMismatch(
                    expected: expectedRevision,
                    actual: current.revision
                )
            }
            guard current.revision < UInt64.max else {
                throw ApprovalPolicyStoreError.revisionExhausted
            }
            let next = AgentApprovalPolicySnapshot(
                revision: current.revision + 1,
                rules: rules
            )
            try requireUnexpiredMutation(deadlineUnixMs)
            try persist(next)
            return AgentApprovalPolicyMutationReceipt(
                revision: next.revision,
                ruleCount: next.rules.count
            )
        }
    }

    public func persistAlwaysAllow(
        for call: AgentToolCall,
        runID: String
    ) async throws -> String {
        let current = try loadSnapshot()
        return try await persistAlwaysAllow(
            for: call,
            runID: runID,
            expectedRevision: String(current.revision)
        )
    }

    public func persistAlwaysAllow(
        for call: AgentToolCall,
        runID: String,
        expectedRevision: String
    ) async throws -> String {
        try await persistAlwaysAllow(
            for: call,
            runID: runID,
            expectedRevision: expectedRevision,
            deadlineUnixMs: 0
        )
    }

    public func persistAlwaysAllow(
        for call: AgentToolCall,
        runID: String,
        expectedRevision: String,
        deadlineUnixMs: Int64
    ) async throws -> String {
        try requireUnexpiredMutation(deadlineUnixMs)
        guard
            let sourceID = Self.nonempty(call.sourceID),
            let toolName = Self.nonempty(call.toolName),
            let schemaDigest = Self.nonempty(call.schemaDigest),
            let expectedRevisionValue = UInt64(expectedRevision)
        else {
            throw ApprovalPolicyStoreError.invalidRule(id: "always-allow")
        }
        guard let context = await contextProvider.context(for: call, runID: runID) else {
            throw ApprovalPolicyStoreError.approvalContextUnavailable
        }
        guard Self.callMatchesContext(call, context: context),
              context.toolKnown,
              context.schemaState == .current,
              context.riskClass != .unknown,
              context.operationKind != .unknown,
              Self.safetyFloor(for: context) == .notRequired
        else {
            throw ApprovalPolicyStoreError.approvalContextMismatch
        }

        let workspaceScope = Self.nonempty(context.workspaceScope)
        let appBundleID = Self.nonempty(context.appBundleID)
        let networkHost = Self.nonempty(context.networkHost)?.lowercased()
        if sourceID == "computer", appBundleID == nil {
            throw ApprovalPolicyStoreError.approvalContextMismatch
        }

        return try await withExclusiveLock {
            let current = try loadSnapshot()
            guard current.revision == expectedRevisionValue else {
                throw ApprovalPolicyStoreError.revisionMismatch(
                    expected: expectedRevisionValue,
                    actual: current.revision
                )
            }
            guard current.revision < UInt64.max else {
                throw ApprovalPolicyStoreError.revisionExhausted
            }

            let exactRule = AgentApprovalPolicyRule(
                id: Self.alwaysAllowRuleID(
                    sourceID: sourceID,
                    toolName: toolName,
                    schemaDigest: schemaDigest,
                    context: context,
                    workspaceScope: workspaceScope,
                    appBundleID: appBundleID,
                    networkHost: networkHost
                ),
                effect: .allow,
                sourceID: sourceID,
                toolName: toolName,
                riskClass: context.riskClass,
                operationKind: context.operationKind,
                workspaceScope: workspaceScope,
                appBundleID: appBundleID,
                networkHost: networkHost,
                schemaDigest: schemaDigest
            )
            var nextRules = current.rules.filter {
                !Self.hasExactToolScope(
                    $0,
                    sourceID: sourceID,
                    toolName: toolName,
                    schemaDigest: schemaDigest,
                    context: context,
                    workspaceScope: workspaceScope,
                    appBundleID: appBundleID,
                    networkHost: networkHost
                )
            }
            nextRules.append(exactRule)
            nextRules.sort { $0.id < $1.id }
            try Self.validateRules(nextRules)

            let next = AgentApprovalPolicySnapshot(
                revision: current.revision + 1,
                rules: nextRules
            )
            try requireUnexpiredMutation(deadlineUnixMs)
            try persist(next)

            // The revision is deliberately produced only after the atomic
            // replacement and directory sync have both succeeded.
            return String(next.revision)
        }
    }

    private func requireUnexpiredMutation(
        _ deadlineUnixMs: Int64
    ) throws {
        guard deadlineUnixMs > 0 else {
            return
        }
        let nowUnixMs = Int64(now().timeIntervalSince1970 * 1_000)
        guard deadlineUnixMs > nowUnixMs else {
            throw ApprovalPolicyStoreError.deadlineExceeded
        }
    }

    public func approvalEvaluation(
        for call: AgentToolCall,
        runID: String
    ) async -> AgentApprovalPolicyEvaluation {
        let context = await contextProvider.context(for: call, runID: runID)
        do {
            let document = try loadSnapshot()
            guard let context else {
                return AgentApprovalPolicyEvaluation(
                    requirement: .required,
                    policyRevision: String(document.revision),
                    scopeDigest: Self.scopeDigest(context: nil)
                )
            }
            let requirement = Self.evaluate(
                rules: document.rules,
                call: call,
                context: context
            )
            return AgentApprovalPolicyEvaluation(
                requirement: requirement,
                policyRevision: String(document.revision),
                scopeDigest: Self.scopeDigest(context: context)
            )
        } catch {
            return AgentApprovalPolicyEvaluation(
                requirement: .denied,
                policyRevision: "unavailable",
                scopeDigest: Self.scopeDigest(context: nil)
            )
        }
    }

    private func withExclusiveLock<T: Sendable>(
        _ operation: () throws -> T
    ) async throws -> T {
        let lockURL: URL
        do {
            lockURL = try SiblingFileAdvisoryLock.prepareLockURL(
                storeURL: fileURL,
                fileManager: .default
            )
        } catch let error as NSError {
            throw ApprovalPolicyStoreError.ioFailure(
                operation: "prepare-lock",
                code: Int32(error.code)
            )
        }
        let lease: SiblingFileAdvisoryLock.Lease
        do {
            lease = try await SiblingFileAdvisoryLock.acquire(lockURL: lockURL)
        } catch let error as NSError {
            throw ApprovalPolicyStoreError.ioFailure(
                operation: "acquire-lock",
                code: Int32(error.code)
            )
        }
        defer { lease.release() }
        return try operation()
    }

    private func loadSnapshot() throws -> AgentApprovalPolicySnapshot {
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return AgentApprovalPolicySnapshot(revision: 0, rules: [])
        }
        do {
            let document = try JSONDecoder().decode(
                AgentApprovalPolicySnapshot.self,
                from: Data(contentsOf: fileURL)
            )
            guard document.schemaVersion == Self.documentSchemaVersion else {
                throw ApprovalPolicyStoreError.invalidDocument
            }
            try Self.validateRules(document.rules)
            return document
        } catch let error as ApprovalPolicyStoreError {
            throw error
        } catch {
            throw ApprovalPolicyStoreError.invalidDocument
        }
    }

    private func persist(_ document: AgentApprovalPolicySnapshot) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data: Data
        do {
            data = try encoder.encode(document)
        } catch {
            throw ApprovalPolicyStoreError.invalidDocument
        }
        try Self.atomicSecureWrite(data, to: fileURL)
    }

    private static func evaluate(
        rules: [AgentApprovalPolicyRule],
        call: AgentToolCall,
        context: AgentApprovalPolicyContext
    ) -> AgentApprovalRequirement {
        guard callMatchesContext(call, context: context),
            nonempty(call.sourceID) != nil,
            nonempty(call.toolName) != nil,
            nonempty(call.schemaDigest) != nil
        else {
            return .required
        }

        let selectedEffect = rules
            .filter { matches($0, call: call, context: context) }
            .max { lhs, rhs in
                // Safety effect is the primary precedence boundary: any
                // matching deny outranks ask, and any matching ask outranks
                // allow. Specificity only selects within the same effect.
                let left = (effectPriority(lhs.effect), specificity(lhs))
                let right = (effectPriority(rhs.effect), specificity(rhs))
                return left < right
            }?
            .effect ?? .ask

        let policyRequirement = requirement(for: selectedEffect)
        let floor = safetyFloor(for: context)
        return stricter(policyRequirement, floor)
    }

    private static func safetyFloor(
        for context: AgentApprovalPolicyContext
    ) -> AgentApprovalRequirement {
        switch context.operationKind {
        case .credentialAccess, .authentication, .purchase,
             .destructiveMutation, .processExecution, .secureFieldInteraction:
            return .denied
        case .upload, .send:
            return .required
        case .unknown, .read, .write:
            break
        }
        if context.riskClass == .critical {
            return .denied
        }
        if !context.toolKnown
            || context.schemaState != .current
            || context.operationKind == .unknown
            || context.riskClass == .unknown
        {
            return .required
        }
        return .notRequired
    }

    private static func matches(
        _ rule: AgentApprovalPolicyRule,
        call: AgentToolCall,
        context: AgentApprovalPolicyContext
    ) -> Bool {
        (rule.sourceID == nil || rule.sourceID == context.sourceID)
            && (rule.toolName == nil || rule.toolName == context.toolName)
            && (rule.riskClass == nil || rule.riskClass == context.riskClass)
            && (rule.operationKind == nil || rule.operationKind == context.operationKind)
            && (rule.workspaceScope == nil || rule.workspaceScope == context.workspaceScope)
            && (rule.appBundleID == nil || rule.appBundleID == context.appBundleID)
            && (rule.networkHost == nil || rule.networkHost == context.networkHost)
            && (rule.schemaDigest == nil || rule.schemaDigest == call.schemaDigest)
    }

    private static func specificity(_ rule: AgentApprovalPolicyRule) -> Int {
        [
            rule.sourceID != nil,
            rule.toolName != nil,
            rule.riskClass != nil,
            rule.operationKind != nil,
            rule.workspaceScope != nil,
            rule.appBundleID != nil,
            rule.networkHost != nil,
            rule.schemaDigest != nil,
        ].filter { $0 }.count
    }

    private static func effectPriority(_ effect: AgentApprovalPolicyEffect) -> Int {
        switch effect {
        case .allow: 1
        case .ask: 2
        case .deny: 3
        }
    }

    private static func requirement(
        for effect: AgentApprovalPolicyEffect
    ) -> AgentApprovalRequirement {
        switch effect {
        case .allow: .notRequired
        case .ask: .required
        case .deny: .denied
        }
    }

    private static func stricter(
        _ lhs: AgentApprovalRequirement,
        _ rhs: AgentApprovalRequirement
    ) -> AgentApprovalRequirement {
        if lhs == .denied || rhs == .denied {
            return .denied
        }
        if lhs == .required || rhs == .required {
            return .required
        }
        return .notRequired
    }

    private static func validateRules(_ rules: [AgentApprovalPolicyRule]) throws {
        var ids = Set<String>()
        for rule in rules {
            guard nonempty(rule.id) != nil,
                  validOptional(rule.sourceID),
                  validOptional(rule.toolName),
                  validOptional(rule.workspaceScope),
                  validOptional(rule.appBundleID),
                  validOptional(rule.networkHost),
                  validOptional(rule.schemaDigest)
            else {
                throw ApprovalPolicyStoreError.invalidRule(id: rule.id)
            }
            guard ids.insert(rule.id).inserted else {
                throw ApprovalPolicyStoreError.duplicateRuleID(id: rule.id)
            }
        }
    }

    private static func validOptional(_ value: String?) -> Bool {
        value == nil || nonempty(value) != nil
    }

    private static func nonempty(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func riskClass(from value: String) -> AgentApprovalRiskClass? {
        AgentApprovalRiskClass.fromRuntimeValue(value)
    }

    private static func callMatchesContext(
        _ call: AgentToolCall,
        context: AgentApprovalPolicyContext
    ) -> Bool {
        nonempty(call.sourceID) == nonempty(context.sourceID)
            && nonempty(call.toolName) == nonempty(context.toolName)
            && riskClass(from: call.riskClass) == context.riskClass
    }

    private static func scopeDigest(
        context: AgentApprovalPolicyContext?
    ) -> String {
        let fields: [String]
        if let context {
            fields = [
                "melix.agent-approval-scope.v1",
                context.sourceID,
                context.toolName,
                context.riskClass.rawValue,
                context.operationKind.rawValue,
                context.workspaceScope ?? "<none>",
                context.appBundleID ?? "<none>",
                context.networkHost ?? "<none>",
                context.toolKnown ? "known" : "unknown",
                context.schemaState.rawValue,
            ]
        } else {
            fields = ["melix.agent-approval-scope.v1", "<missing-context>"]
        }
        let material = fields.map { field in
            "\(field.utf8.count):\(field)"
        }.joined(separator: "|")
        return SHA256.hash(data: Data(material.utf8)).map { byte in
            String(format: "%02x", byte)
        }.joined()
    }

    private static func hasExactToolScope(
        _ rule: AgentApprovalPolicyRule,
        sourceID: String,
        toolName: String,
        schemaDigest: String,
        context: AgentApprovalPolicyContext,
        workspaceScope: String?,
        appBundleID: String?,
        networkHost: String?
    ) -> Bool {
        rule.sourceID == sourceID
            && rule.toolName == toolName
            && rule.schemaDigest == schemaDigest
            && rule.riskClass == context.riskClass
            && rule.operationKind == context.operationKind
            && rule.workspaceScope == workspaceScope
            && rule.appBundleID == appBundleID
            && rule.networkHost == networkHost
    }

    private static func alwaysAllowRuleID(
        sourceID: String,
        toolName: String,
        schemaDigest: String,
        context: AgentApprovalPolicyContext,
        workspaceScope: String?,
        appBundleID: String?,
        networkHost: String?
    ) -> String {
        let material = [
            sourceID,
            toolName,
            schemaDigest,
            context.riskClass.rawValue,
            context.operationKind.rawValue,
            workspaceScope ?? "<none>",
            appBundleID ?? "<none>",
            networkHost ?? "<none>",
        ].joined(separator: "\u{1F}")
        return "always-allow:\(Data(material.utf8).base64EncodedString())"
    }

    private static func atomicSecureWrite(_ data: Data, to destination: URL) throws {
        let directory = destination.deletingLastPathComponent()
        do {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: NSNumber(value: 0o700)]
            )
        } catch let error as NSError {
            throw ApprovalPolicyStoreError.ioFailure(
                operation: "create-directory",
                code: Int32(error.code)
            )
        }

        let temporary = directory.appendingPathComponent(
            ".\(destination.lastPathComponent).tmp-\(UUID().uuidString)",
            isDirectory: false
        )
        let descriptor = temporary.withUnsafeFileSystemRepresentation { path -> Int32 in
            guard let path else {
                errno = EINVAL
                return -1
            }
            return Darwin.open(
                path,
                O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC,
                mode_t(S_IRUSR | S_IWUSR)
            )
        }
        guard descriptor >= 0 else {
            throw posixFailure("open-temporary")
        }

        var descriptorOpen = true
        var renamed = false
        defer {
            if descriptorOpen {
                _ = Darwin.close(descriptor)
            }
            if !renamed {
                temporary.withUnsafeFileSystemRepresentation { path in
                    if let path { _ = Darwin.unlink(path) }
                }
            }
        }

        guard Darwin.fchmod(descriptor, mode_t(S_IRUSR | S_IWUSR)) == 0 else {
            throw posixFailure("chmod-temporary")
        }
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let result = Darwin.write(
                    descriptor,
                    bytes.baseAddress?.advanced(by: offset),
                    bytes.count - offset
                )
                if result < 0 {
                    if errno == EINTR { continue }
                    throw posixFailure("write-temporary")
                }
                guard result > 0 else {
                    throw ApprovalPolicyStoreError.ioFailure(
                        operation: "write-temporary",
                        code: EIO
                    )
                }
                offset += result
            }
        }
        guard Darwin.fsync(descriptor) == 0 else {
            throw posixFailure("sync-temporary")
        }
        guard Darwin.close(descriptor) == 0 else {
            descriptorOpen = false
            throw posixFailure("close-temporary")
        }
        descriptorOpen = false

        let renameResult: Int32 = temporary.withUnsafeFileSystemRepresentation { sourcePath -> Int32 in
            destination.withUnsafeFileSystemRepresentation { destinationPath -> Int32 in
                guard let sourcePath, let destinationPath else {
                    errno = EINVAL
                    return -1
                }
                return Darwin.rename(sourcePath, destinationPath)
            }
        }
        guard renameResult == 0 else {
            throw posixFailure("rename-policy")
        }
        renamed = true

        let directoryDescriptor = directory.withUnsafeFileSystemRepresentation { path -> Int32 in
            guard let path else {
                errno = EINVAL
                return -1
            }
            return Darwin.open(path, O_RDONLY | O_CLOEXEC)
        }
        guard directoryDescriptor >= 0 else {
            throw posixFailure("open-directory")
        }
        defer { _ = Darwin.close(directoryDescriptor) }
        guard Darwin.fsync(directoryDescriptor) == 0 else {
            throw posixFailure("sync-directory")
        }
    }

    private static func posixFailure(_ operation: String) -> ApprovalPolicyStoreError {
        ApprovalPolicyStoreError.ioFailure(operation: operation, code: errno)
    }
}
