import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Snapshot Stores")
struct SnapshotStoreTests {
    @Test("cache mode metadata bridges worker enums into labels and metrics")
    func cacheModeMetadataBridgesEnumsAndMetrics() {
        #expect(makeControlPlaneCacheMode(from: .tiered) == .tiered)
        #expect(makeControlPlaneCacheMode(from: .rotating) == .rotating)
        #expect(makeControlPlaneCacheMode(from: .hybrid) == .hybrid)
        #expect(makeControlPlaneCacheMode(from: .unspecified) == .unspecified)
        #expect(makeControlPlaneCacheMode(from: .UNRECOGNIZED(99)) == .unspecified)

        #expect(cacheModeLabel(.tiered) == "tiered")
        #expect(cacheModeLabel(.rotating) == "rotating")
        #expect(cacheModeLabel(.hybrid) == "hybrid")
        #expect(cacheModeLabel(.unspecified) == "unspecified")
        #expect(cacheModeLabel(.UNRECOGNIZED(99)) == "unspecified")

        #expect(cacheModeMetricValue(.tiered) == 1)
        #expect(cacheModeMetricValue(.rotating) == 2)
        #expect(cacheModeMetricValue(.hybrid) == 3)
        #expect(cacheModeMetricValue(.unspecified) == 0)
        #expect(cacheModeMetricValue(.UNRECOGNIZED(99)) == 0)
    }

    @Test("cache metadata store defaults to an empty typed snapshot")
    func cacheMetadataStoreDefaultsToEmptySnapshot() async {
        let store = CacheMetadataStore()

        let snapshot = await store.cacheSnapshot()
        let summary = await store.cacheSummary()

        #expect(snapshot.summary.blockCount == 0)
        #expect(snapshot.summary.quantizedBytes == 0)
        #expect(snapshot.summary.compressionRatio == 0)
        #expect(summary.blockCount == 0)
        #expect(summary.l2RestoreHitRate == 0)
        #expect(summary.activeMode == .tiered)
    }

    @Test("cache metadata store replaces the live snapshot")
    func cacheMetadataStoreReplacesSnapshot() async {
        let store = CacheMetadataStore()
        var snapshot = Melix_Controlplane_V1_CacheSnapshot()
        snapshot.summary.l1Bytes = 128
        snapshot.summary.blockCount = 3
        snapshot.summary.quantizedBytes = 64
        snapshot.summary.activeMode = .hybrid

        await store.replace(snapshot: snapshot)

        let updated = await store.cacheSnapshot()
        #expect(updated.summary.l1Bytes == 128)
        #expect(updated.summary.blockCount == 3)
        #expect(updated.summary.quantizedBytes == 64)
        #expect(updated.summary.activeMode == .hybrid)
    }

    @Test("cache metadata store preserves restore plans across replacements and trims appended plans")
    func cacheMetadataStorePreservesAndTrimsRestorePlans() async {
        var existingSnapshot = Melix_Controlplane_V1_CacheSnapshot()
        existingSnapshot.recentRestorePlans = (0..<10).map { index in
            var plan = Melix_Controlplane_V1_CacheRestorePlan()
            plan.planID = "existing-\(index)"
            plan.restoredTokenCount = UInt32(index)
            return plan
        }
        let store = CacheMetadataStore(snapshot: existingSnapshot)

        var replacement = Melix_Controlplane_V1_CacheSnapshot()
        replacement.summary.blockCount = 4
        await store.replace(snapshot: replacement)

        var latest = Melix_Controlplane_V1_CacheRestorePlan()
        latest.planID = "latest"
        latest.restoredTokenCount = 99
        await store.appendRecentRestorePlan(latest)

        let snapshot = await store.cacheSnapshot()
        #expect(snapshot.summary.blockCount == 4)
        #expect(snapshot.recentRestorePlans.count == 10)
        #expect(snapshot.recentRestorePlans.first?.planID == "latest")
        #expect(snapshot.recentRestorePlans.last?.planID == "existing-8")
    }

    @Test("server session runtime store preserves seeded runtime sessions")
    func serverSessionRuntimeStorePreservesSeededRuntimeSessions() async {
        var seeded = ServerSessionRuntimeStore.defaultRuntimeSession(
            serverSessionID: "server-session-seeded",
            updatedAtUnixMS: 9_000
        )
        seeded.lifecycleState = .paused
        seeded.powerState = .lightSleep

        let store = ServerSessionRuntimeStore(
            runtimeSessions: [seeded],
            nowUnixMS: { 10_000 }
        )

        let snapshot = await store.snapshot()

        #expect(snapshot.count == 1)
        #expect(snapshot.first?.serverSessionID == "server-session-seeded")
        #expect(snapshot.first?.lifecycleState == .paused)
        #expect(snapshot.first?.powerState == .lightSleep)
        #expect(snapshot.first?.updatedAtUnixMs == 9_000)
    }

    @Test("server session runtime store applies idle sleep thresholds when auto sleep is enabled")
    func serverSessionRuntimeStoreAppliesIdleSleepThresholds() async {
        final class Clock: @unchecked Sendable {
            var now: Int64
            init(now: Int64) { self.now = now }
        }

        let lightSleepClock = Clock(now: 0)
        let store = ServerSessionRuntimeStore(nowUnixMS: { lightSleepClock.now })

        _ = await store.updateIdlePolicy(
            serverSessionID: ServerSessionRuntimeStore.defaultServerSessionID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 2,
            deepSleepAfterSeconds: 5
        )
        lightSleepClock.now = 3_000

        let lightSleepSnapshot = await store.snapshot()
        #expect(lightSleepSnapshot.first?.lifecycleState == .sleeping)
        #expect(lightSleepSnapshot.first?.powerState == .lightSleep)
        #expect(lightSleepSnapshot.first?.idleTimerSeconds == 3)

        let deepSleepClock = Clock(now: 0)
        let storeForDeepSleep = ServerSessionRuntimeStore(nowUnixMS: { deepSleepClock.now })
        _ = await storeForDeepSleep.updateIdlePolicy(
            serverSessionID: ServerSessionRuntimeStore.defaultServerSessionID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 2,
            deepSleepAfterSeconds: 5
        )
        deepSleepClock.now = 20_000
        let deepSleepSnapshot = await storeForDeepSleep.snapshot()
        #expect(deepSleepSnapshot.first?.lifecycleState == .sleeping)
        #expect(deepSleepSnapshot.first?.powerState == .deepSleep)
    }

    @Test("server session runtime store wakes sleeping sessions on request activity")
    func serverSessionRuntimeStoreWakesSleepingSessionsOnRequestActivity() async {
        var sleeping = ServerSessionRuntimeStore.defaultRuntimeSession(
            updatedAtUnixMS: 1_000
        )
        sleeping.lifecycleState = .sleeping
        sleeping.powerState = .deepSleep
        let store = ServerSessionRuntimeStore(runtimeSessions: [sleeping], nowUnixMS: { 2_000 })

        _ = await store.noteRequestActivity()
        let snapshot = await store.snapshot()

        #expect(snapshot.first?.lifecycleState == .ready)
        #expect(snapshot.first?.powerState == .active)
        #expect(snapshot.first?.wakeReason == .requestActivity)
        #expect(snapshot.first?.idleTimerSeconds == 0)
    }

    @Test("server session runtime store preserves stopped sessions while active requests inhibit idle timers")
    func serverSessionRuntimeStorePreservesStoppedSessionsWhileRequestsAreActive() async {
        let store = ServerSessionRuntimeStore(nowUnixMS: { 8_000 })

        _ = await store.stopServerSession(serverSessionID: ServerSessionRuntimeStore.defaultServerSessionID)
        _ = await store.noteRequestActivity()
        let stoppedSnapshot = await store.snapshot()
        #expect(stoppedSnapshot.first?.lifecycleState == .stopped)
        #expect(stoppedSnapshot.first?.powerState == .stopped)

        final class Clock: @unchecked Sendable {
            var now: Int64
            init(now: Int64) { self.now = now }
        }
        let activeClock = Clock(now: 0)
        let storeWithInFlightWork = ServerSessionRuntimeStore(nowUnixMS: { activeClock.now })
        _ = await storeWithInFlightWork.updateIdlePolicy(
            serverSessionID: ServerSessionRuntimeStore.defaultServerSessionID,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 1,
            deepSleepAfterSeconds: 2
        )
        activeClock.now = 12_000
        let activeSnapshot = await storeWithInFlightWork.snapshot(hasActiveRequests: true)
        #expect(activeSnapshot.first?.idleTimerSeconds == 0)
        #expect(activeSnapshot.first?.lifecycleState == .ready)
        #expect(activeSnapshot.first?.powerState == .active)
    }

    @Test("server session runtime store creates missing sessions and resets idle inhibition on the next snapshot")
    func serverSessionRuntimeStoreCreatesMissingSessionsAndResetsIdleInhibition() async {
        final class Clock: @unchecked Sendable {
            var now: Int64
            init(now: Int64) { self.now = now }
        }

        let clock = Clock(now: 0)
        let store = ServerSessionRuntimeStore(nowUnixMS: { clock.now })

        _ = await store.updateIdlePolicy(
            serverSessionID: "server-session-2",
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 2,
            deepSleepAfterSeconds: 5
        )
        let seededSnapshot = await store.snapshot()
        #expect(seededSnapshot.contains(where: { $0.serverSessionID == "server-session-2" }))

        clock.now = 12_000
        let inhibitedSnapshot = await store.snapshot(hasActiveRequests: true)
        guard let inhibitedSession = inhibitedSnapshot.first(where: { $0.serverSessionID == "server-session-2" }) else {
            Issue.record("Expected inhibited session to exist")
            return
        }
        #expect(inhibitedSession.idleTimerSeconds == 0)

        let resumedSnapshot = await store.snapshot()
        guard let resumedSession = resumedSnapshot.first(where: { $0.serverSessionID == "server-session-2" }) else {
            Issue.record("Expected resumed session to exist")
            return
        }
        #expect(resumedSession.idleTimerSeconds == 0)
        #expect(resumedSession.lifecycleState == .ready)
    }

    @Test("server session runtime store skips auto-sleep transitions for paused stopped and failed sessions")
    func serverSessionRuntimeStoreSkipsAutoSleepForPausedStoppedAndFailedSessions() async {
        var paused = ServerSessionRuntimeStore.defaultRuntimeSession(
            serverSessionID: "server-session-paused",
            updatedAtUnixMS: 0
        )
        paused.autoSleepEnabled = true
        paused.lightSleepAfterSeconds = 1
        paused.deepSleepAfterSeconds = 2
        paused.lifecycleState = .paused

        var stopped = ServerSessionRuntimeStore.defaultRuntimeSession(
            serverSessionID: "server-session-stopped",
            updatedAtUnixMS: 0
        )
        stopped.autoSleepEnabled = true
        stopped.lightSleepAfterSeconds = 1
        stopped.deepSleepAfterSeconds = 2
        stopped.lifecycleState = .stopped
        stopped.powerState = .stopped

        var failed = ServerSessionRuntimeStore.defaultRuntimeSession(
            serverSessionID: "server-session-failed",
            updatedAtUnixMS: 0
        )
        failed.autoSleepEnabled = true
        failed.lightSleepAfterSeconds = 1
        failed.deepSleepAfterSeconds = 2
        failed.lifecycleState = .error

        let store = ServerSessionRuntimeStore(
            runtimeSessions: [paused, stopped, failed],
            nowUnixMS: { 10_000 }
        )

        let snapshot = await store.snapshot()
        guard let pausedSnapshot = snapshot.first(where: { $0.serverSessionID == "server-session-paused" }),
              let stoppedSnapshot = snapshot.first(where: { $0.serverSessionID == "server-session-stopped" }),
              let failedSnapshot = snapshot.first(where: { $0.serverSessionID == "server-session-failed" }) else {
            Issue.record("Expected paused, stopped, and failed sessions to exist")
            return
        }

        #expect(pausedSnapshot.lifecycleState == .paused)
        #expect(pausedSnapshot.powerState == .active)
        #expect(stoppedSnapshot.lifecycleState == .stopped)
        #expect(stoppedSnapshot.powerState == .stopped)
        #expect(failedSnapshot.lifecycleState == .error)
        #expect(failedSnapshot.powerState == .active)
    }

    @Test("server snapshot builder derives failed booting and stopped server states from runtime sessions")
    func serverSnapshotBuilderDerivesRuntimeServerStates() {
        var failedSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        failedSession.lifecycleState = .error
        var loadingSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        loadingSession.lifecycleState = .loading
        var stoppedSession = ServerSessionRuntimeStore.defaultRuntimeSession(updatedAtUnixMS: 1_000)
        stoppedSession.lifecycleState = .stopped
        stoppedSession.powerState = .stopped

        let builder = ServerSnapshotBuilder()
        let failedSnapshot = builder.build(
            models: [],
            metrics: Melix_Controlplane_V1_MetricsSummary(),
            runtimeSessions: [failedSession]
        )
        let loadingSnapshot = builder.build(
            models: [],
            metrics: Melix_Controlplane_V1_MetricsSummary(),
            runtimeSessions: [loadingSession]
        )
        let stoppedSnapshot = builder.build(
            models: [],
            metrics: Melix_Controlplane_V1_MetricsSummary(),
            runtimeSessions: [stoppedSession]
        )

        #expect(failedSnapshot.serverState == .serverFailed)
        #expect(loadingSnapshot.serverState == .serverBooting)
        #expect(stoppedSnapshot.serverState == .serverStopped)
    }

    @Test("server snapshot builder resolves limited cache compatibility downgrades")
    func serverSnapshotBuilderResolvesLimitedCacheCompatibilityDowngrades() {
        var model = ModelCatalog.devTextModel()
        model.settings.cacheMode = .rotating
        model.settings.cacheDirectory = "/tmp/requested-cache"
        model.settings.cacheBlockSizeTokens = 32
        model.settings.cacheMemoryBudgetBytes = 4_096
        model.settings.cacheMemoryBudgetPct = 25
        model.settings.multimodalCacheBudgetBytes = 2_048
        model.settings.diskStreamingMode = .diskStreamingRequireDisk
        model.supportedModalities = ["text"]

        var cache = CacheMetadataStore.emptySummary()
        cache.activeMode = .hybrid
        cache.cacheRoot = "/var/melix/cache"
        cache.initialCacheBlocks = 4
        cache.supportedModes = [.tiered]
        cache.experimentalModes = [.rotating, .hybrid]
        cache.supportsPrefixCache = true
        cache.supportsPagedCache = true
        cache.supportsDiskCache = false
        cache.supportsBoundarySnapshots = true

        let snapshot = ServerSnapshotBuilder().build(
            models: [model],
            metrics: Melix_Controlplane_V1_MetricsSummary(),
            cache: cache
        )
        let policy = try? #require(snapshot.models.first?.cachePolicy)

        #expect(policy?.requestedMode == .rotating)
        #expect(policy?.effectiveMode == .tiered)
        #expect(policy?.supportedModes == [.tiered])
        #expect(policy?.supportsPrefixCache == true)
        #expect(policy?.supportsPagedCache == true)
        #expect(policy?.supportsDiskCache == false)
        #expect(policy?.supportsBoundarySnapshots == true)
        #expect(policy?.requestedDirectory == "/tmp/requested-cache")
        #expect(policy?.effectiveDirectory == "/var/melix/cache")
        #expect(policy?.requestedBlockSizeTokens == 32)
        #expect(policy?.effectiveBlockSizeTokens == 32)
        #expect(policy?.requestedCacheMemoryBudgetBytes == 4_096)
        #expect(policy?.effectiveCacheMemoryBudgetBytes == 4_096)
        #expect(policy?.requestedCacheMemoryBudgetPct == 25)
        #expect(policy?.effectiveCacheMemoryBudgetPct == 0)
        #expect(policy?.requestedMultimodalCacheBudgetBytes == 2_048)
        #expect(policy?.effectiveMultimodalCacheBudgetBytes == 0)
        #expect(policy?.initialCacheBlocks == 4)
        #expect(policy?.compatibility == .cacheCompatibilityLimited)
        #expect(policy?.compatibilityReason.contains("requested cache mode is not advertised by the worker") == true)
        #expect(policy?.compatibilityReason.contains("per-model cache directory overrides are not supported") == true)
        #expect(policy?.compatibilityReason.contains("disk streaming is requested") == true)
        #expect(policy?.compatibilityReason.contains("multimodal cache budget is ignored") == true)
        #expect(policy?.compatibilityReason.contains("fixed cache budget bytes take precedence") == true)
    }

    @Test("server snapshot builder emits default cache compatibility reasons for compatible and unknown workers")
    func serverSnapshotBuilderEmitsDefaultCacheCompatibilityReasons() {
        var compatibleModel = ModelCatalog.devTextModel()
        compatibleModel.settings.cacheMode = .tiered

        var compatibleCache = CacheMetadataStore.emptySummary()
        compatibleCache.activeMode = .tiered
        compatibleCache.cacheRoot = "/var/melix/cache"
        compatibleCache.supportedModes = [.tiered, .rotating]

        let compatibleSnapshot = ServerSnapshotBuilder().build(
            models: [compatibleModel],
            metrics: Melix_Controlplane_V1_MetricsSummary(),
            cache: compatibleCache
        )

        var unknownCache = CacheMetadataStore.emptySummary()
        unknownCache.activeMode = .unspecified
        unknownCache.cacheRoot = "/var/melix/cache"
        unknownCache.supportedModes = []

        var unknownModel = ModelCatalog.devTextModel()
        unknownModel.settings.cacheMode = .unspecified

        let unknownSnapshot = ServerSnapshotBuilder().build(
            models: [unknownModel],
            metrics: Melix_Controlplane_V1_MetricsSummary(),
            cache: unknownCache
        )

        #expect(compatibleSnapshot.models.first?.cachePolicy.compatibility == .cacheCompatibilityCompatible)
        #expect(
            compatibleSnapshot.models.first?.cachePolicy.compatibilityReason
                == "requested policy is compatible with the current worker cache capabilities"
        )
        #expect(unknownSnapshot.models.first?.cachePolicy.compatibility == .cacheCompatibilityUnknown)
        #expect(
            unknownSnapshot.models.first?.cachePolicy.compatibilityReason
                == "worker cache compatibility evidence is unavailable"
        )
        #expect(unknownSnapshot.models.first?.cachePolicy.effectiveMode == .tiered)
    }

    @Test("session graph store exposes sorted summaries and session state")
    func sessionGraphStoreExposesSortedSummaries() async {
        let store = SessionGraphStore(sessions: [makeSessionState(id: "session-b"), makeSessionState(id: "session-a")])

        let summaries = await store.sessionSummaries()
        let state = await store.state(for: "session-b")

        #expect(summaries.map(\.sessionID) == ["session-a", "session-b"])
        #expect(summaries.last?.branchCount == 2)
        #expect(summaries.last?.latestSnapshotID == "snap-session-b")
        #expect(state?.activeBranchID == "branch-main")
        #expect(state?.availableSnapshots.first?.sessionID == "session-b")
    }

    @Test("session graph store replaces session state by identifier")
    func sessionGraphStoreReplacesState() async {
        let store = SessionGraphStore(sessions: [makeSessionState(id: "session-1")])
        var replacement = makeSessionState(id: "session-1")
        replacement.activeBranchID = "branch-alt"
        replacement.latestRequestID = "req-updated"

        await store.replace(session: replacement)

        let state = await store.state(for: "session-1")
        #expect(state?.activeBranchID == "branch-alt")
        #expect(state?.latestRequestID == "req-updated")
    }

    @Test("session graph store creates sessions and derived branches with lineage metadata")
    func sessionGraphStoreCreatesSessionsAndBranches() async throws {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(
            metricsStore: metricsStore,
            nowUnixMs: { 1_000 },
            sessionIDGenerator: { "session-created" },
            branchIDGenerator: { "branch-derived" }
        )

        let session = await store.createSession()
        let branched = try await store.createBranch(sessionID: session.sessionID, parentBranchID: "branch-main")
        let metrics = await metricsStore.snapshot()

        #expect(session.sessionID == "session-created")
        #expect(session.activeBranchID == "branch-main")
        #expect(branched.activeBranchID == "branch-derived")
        #expect(branched.branches.count == 2)
        #expect(branched.branches.last?.parentBranchID == "branch-main")
        #expect(metrics.values["session_graph.session_count"] == 1)
        #expect(metrics.values["session_graph.branch_count"] == 2)
    }

    @Test("session graph store tracks tool and resume metadata")
    func sessionGraphStoreTracksToolAndResumeMetadata() async throws {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(
            metricsStore: metricsStore,
            nowUnixMs: { 2_000 },
            sessionIDGenerator: { "session-stateful" }
        )
        _ = await store.createSession()

        let withTool = try await store.registerToolResult(
            sessionID: "session-stateful",
            branchID: "branch-main",
            toolCallID: "tool-123"
        )
        let resumed = try await store.resumeAfterTool(
            sessionID: "session-stateful",
            branchID: "branch-main",
            snapshotID: "snap-resume"
        )
        let metrics = await metricsStore.snapshot()

        #expect(withTool.latestToolCallID == "tool-123")
        #expect(withTool.branches.first?.lastToolCallID == "tool-123")
        #expect(resumed.latestSnapshotID == "snap-resume")
        #expect(resumed.branches.first?.resumeSnapshotID == "snap-resume")
        #expect(resumed.availableSnapshots.first?.snapshotID == "snap-resume")
        #expect(metrics.values["session_graph.resume_snapshot_count"] == 1)
    }

    @Test("session graph store rejects unknown session and branch mutations")
    func sessionGraphStoreRejectsUnknownMutations() async throws {
        let store = SessionGraphStore(
            sessions: [makeSessionState(id: "session-1")],
            nowUnixMs: { 4_000 }
        )

        await #expect(throws: SessionGraphStoreError.unknownSessionID) {
            _ = try await store.createBranch(sessionID: "missing-session", parentBranchID: "branch-main")
        }
        await #expect(throws: SessionGraphStoreError.unknownBranchID) {
            _ = try await store.createBranch(sessionID: "session-1", parentBranchID: "branch-missing")
        }
        await #expect(throws: SessionGraphStoreError.unknownSessionID) {
            _ = try await store.registerToolResult(
                sessionID: "missing-session",
                branchID: "branch-main",
                toolCallID: "tool-missing"
            )
        }
        await #expect(throws: SessionGraphStoreError.unknownBranchID) {
            _ = try await store.resumeAfterTool(
                sessionID: "session-1",
                branchID: "branch-missing",
                snapshotID: "snap-missing"
            )
        }
    }

    @Test("session graph store deduplicates generated identifiers and closing updates metrics")
    func sessionGraphStoreDeduplicatesGeneratedIdentifiers() async throws {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(
            sessions: [makeSessionState(id: "session-fixed")],
            metricsStore: metricsStore,
            nowUnixMs: { 5_000 },
            sessionIDGenerator: { "session-fixed" },
            branchIDGenerator: { "branch-main" }
        )

        let created = await store.createSession()
        let branched = try await store.createBranch(
            sessionID: "session-fixed",
            parentBranchID: "branch-main"
        )
        let closed = await store.closeSession(sessionID: "session-fixed")
        let missing = await store.closeSession(sessionID: "missing-session")
        let metrics = await metricsStore.snapshot()

        #expect(created.sessionID == "session-fixed-1")
        #expect(branched.activeBranchID == "branch-main-1")
        #expect(closed?.sessionID == "session-fixed")
        #expect(missing == nil)
        #expect(metrics.values["session_graph.session_count"] == 1)
        #expect(metrics.values["session_graph.branch_count"] == 1)
    }

    @Test("session graph store hydrates request and snapshot metadata for missing sessions")
    func sessionGraphStoreHydratesRequestAndSnapshotMetadata() async {
        let metricsStore = MetricsStore()
        let store = SessionGraphStore(metricsStore: metricsStore, nowUnixMs: { 3_000 })

        let started = await store.recordRequestStart(
            sessionID: "session-hydrated",
            branchID: "branch-review",
            requestID: "req-hydrated"
        )

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-hydrated"
        snapshot.requestID = "req-hydrated"
        snapshot.checkpointID = "ckpt-hydrated"

        let hydrated = await store.recordSnapshotHydration(
            sessionID: "session-hydrated",
            branchID: "branch-review",
            snapshot: snapshot
        )
        let metrics = await metricsStore.snapshot()

        #expect(started.activeBranchID == "branch-review")
        #expect(started.branches.first?.branchID == "branch-review")
        #expect(hydrated.latestRequestID == "req-hydrated")
        #expect(hydrated.latestSnapshotID == "snap-hydrated")
        #expect(hydrated.latestCheckpointID == "ckpt-hydrated")
        #expect(hydrated.branches.first?.headRequestID == "req-hydrated")
        #expect(hydrated.availableSnapshots.first?.branchID == "branch-review")
        #expect(metrics.values["session_graph.active_branch_changes"] == 1)
    }

    @Test("session graph store refreshes existing snapshots and branch cache keys")
    func sessionGraphStoreRefreshesExistingSnapshots() async {
        let store = SessionGraphStore(
            sessions: [makeSessionState(id: "session-1")],
            nowUnixMs: { 6_000 }
        )

        var scope = Melix_Controlplane_V1_CacheScopeKey()
        scope.modelID = "melix-dev-text"
        scope.tokenizerHash = "tok-v2"

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.scope = scope

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-session-1"
        snapshot.requestID = "req-refresh"
        snapshot.checkpointID = "ckpt-refresh"

        let hydrated = await store.recordSnapshotHydration(
            sessionID: "session-1",
            branchID: "branch-main",
            snapshot: snapshot,
            headCacheKey: cacheKey
        )

        #expect(hydrated.availableSnapshots.count == 1)
        #expect(hydrated.availableSnapshots.first?.requestID == "req-refresh")
        #expect(hydrated.branches.first?.headCacheKey.scope.tokenizerHash == "tok-v2")
        #expect(hydrated.latestCheckpointID == "ckpt-refresh")
    }

    @Test("control-plane restore metadata bridges worker restore plans")
    func controlPlaneRestoreMetadataBridgesWorkerPlans() throws {
        var cacheKey = Melix_Worker_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA, 0xBB])
        cacheKey.fingerprintHash = Data([0x10, 0x20, 0x30])
        cacheKey.scopeID = "scope-worker"

        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "blk-0"
        block.tokenStart = 0
        block.tokenEnd = 16
        block.bytes = 1024

        var page = Melix_Worker_V1_PageRef()
        page.pageID = "page-0"
        page.blockIds = ["blk-0"]
        page.tokenStart = 0
        page.tokenEnd = 16
        page.bytes = 1024

        var table = Melix_Worker_V1_BlockTable()
        table.blocks = [block]
        table.cacheKey = cacheKey
        table.scopeID = "scope-worker"
        table.pages = [page]
        table.totalTokenCount = 16

        var snapshot = Melix_Worker_V1_SnapshotRef()
        snapshot.snapshotID = "snap-1"
        snapshot.requestID = "req-1"
        snapshot.sessionID = "session-1"
        snapshot.branchID = "branch-main"
        snapshot.tokenBoundary = 16

        var boundary = Melix_Worker_V1_RestoreBoundaryRef()
        boundary.snapshot = snapshot
        boundary.cacheKey = cacheKey
        boundary.scopeID = "scope-worker"
        boundary.boundaryKind = "boundary_snapshot"

        var workerPlan = Melix_Worker_V1_CacheRestorePlan()
        workerPlan.planID = "restore-bt-1"
        workerPlan.boundary = boundary
        workerPlan.blockTableID = "bt-1"
        workerPlan.blockTable = table
        workerPlan.pages = [page]
        workerPlan.restoredTokenCount = 16
        workerPlan.partial = false
        workerPlan.tier = "l2"

        let controlPlan = makeControlPlaneRestorePlan(from: workerPlan)
        let decoded = try Melix_Controlplane_V1_CacheRestorePlan(
            serializedBytes: controlPlan.serializedData()
        )

        #expect(decoded.planID == "restore-bt-1")
        #expect(decoded.boundary.snapshot.snapshotID == "snap-1")
        #expect(decoded.boundary.scopeID == "scope-worker")
        #expect(decoded.boundary.fingerprintHash == Data([0x10, 0x20, 0x30]))
        #expect(decoded.blockTable.blockTableID == "bt-1")
        #expect(decoded.blockTable.pages.first?.pageID == "page-0")
        #expect(decoded.blockTable.fingerprintHash == Data([0x10, 0x20, 0x30]))
        #expect(decoded.blockTable.totalTokenCount == 16)
        #expect(decoded.tier == "l2")
    }

    @Test("control-plane restore metadata preserves copy-on-write block and page identifiers")
    func controlPlaneRestoreMetadataPreservesCopyOnWriteIdentifiers() throws {
        var cacheKey = Melix_Worker_V1_CacheKey()
        cacheKey.prefixHash = Data([0xCC])
        cacheKey.scopeID = "scope-cow"

        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "blk-0::cow-snap-1"
        block.tokenStart = 0
        block.tokenEnd = 16
        block.bytes = 1024

        var page = Melix_Worker_V1_PageRef()
        page.pageID = "page-blk-0::cow-snap-1"
        page.blockIds = ["blk-0::cow-snap-1"]
        page.tokenStart = 0
        page.tokenEnd = 16
        page.bytes = 1024

        var table = Melix_Worker_V1_BlockTable()
        table.blocks = [block]
        table.cacheKey = cacheKey
        table.scopeID = "scope-cow"
        table.pages = [page]
        table.totalTokenCount = 16

        var snapshot = Melix_Worker_V1_SnapshotRef()
        snapshot.snapshotID = "snap-cow"

        var boundary = Melix_Worker_V1_RestoreBoundaryRef()
        boundary.snapshot = snapshot
        boundary.cacheKey = cacheKey
        boundary.scopeID = "scope-cow"
        boundary.boundaryKind = "boundary_snapshot"

        var workerPlan = Melix_Worker_V1_CacheRestorePlan()
        workerPlan.planID = "restore-bt-cow"
        workerPlan.boundary = boundary
        workerPlan.blockTableID = "bt-1::cow-snap-1"
        workerPlan.blockTable = table
        workerPlan.pages = [page]
        workerPlan.restoredTokenCount = 16
        workerPlan.tier = "l2"

        let controlPlan = makeControlPlaneRestorePlan(from: workerPlan)

        #expect(controlPlan.blockTable.blockTableID == "bt-1::cow-snap-1")
        #expect(controlPlan.blockTable.blocks.first?.blockID == "blk-0::cow-snap-1")
        #expect(controlPlan.blockTable.pages.first?.pageID == "page-blk-0::cow-snap-1")
        #expect(controlPlan.blockTable.pages.first?.blockIds == ["blk-0::cow-snap-1"])
    }

    private func makeSessionState(id: String) -> Melix_Controlplane_V1_SessionState {
        var scope = Melix_Controlplane_V1_CacheScopeKey()
        scope.modelID = "melix-dev-text"

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.scope = scope

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-\(id)"
        snapshot.sessionID = id
        snapshot.branchID = "branch-main"

        var mainBranch = Melix_Controlplane_V1_BranchState()
        mainBranch.branchID = "branch-main"
        mainBranch.headRequestID = "req-\(id)"
        mainBranch.resumeSnapshotID = snapshot.snapshotID
        mainBranch.headCacheKey = cacheKey

        var altBranch = Melix_Controlplane_V1_BranchState()
        altBranch.branchID = "branch-alt"
        altBranch.parentBranchID = "branch-main"
        altBranch.headRequestID = "req-alt-\(id)"

        var session = Melix_Controlplane_V1_SessionState()
        session.sessionID = id
        session.activeBranchID = "branch-main"
        session.latestRequestID = "req-\(id)"
        session.latestSnapshotID = snapshot.snapshotID
        session.branches = [mainBranch, altBranch]
        session.availableSnapshots = [snapshot]
        return session
    }
}
