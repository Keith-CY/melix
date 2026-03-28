import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Request Coordinator")
struct RequestCoordinatorTests {
    @Test("empty model identifiers are rejected before dispatch")
    func emptyModelIdentifiersAreRejectedBeforeDispatch() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: BlockingWorkerClient()),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(
                makeTranslatedChatRequest(requestID: "req-empty-model", modelID: "")
            )
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }
    }

    @Test("request cancellation triggers worker abort")
    func cancellationTriggersWorkerAbort() async throws {
        let workerClient = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let translated = makeTranslatedChatRequest(requestID: "req-cancel")

        let execution = try await coordinator.startChatCompletion(translated)
        let cancelled = try await coordinator.cancel(requestID: "req-cancel")
        _ = execution

        #expect(cancelled)
        #expect(await workerClient.abortedRequestIDs == ["req-cancel"])
    }

    @Test("queued request cancellation succeeds before a worker is bound")
    func queuedRequestCancellationSucceedsBeforeAWorkerIsBound() async throws {
        let workerClient = SlowDispatchWorkerClient()
        let schedulerReadModel = SchedulerReadModel()
        let metricsStore = MetricsStore()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel,
            metricsStore: metricsStore
        )

        let task = Task {
            try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-queued-abort"))
        }

        await workerClient.waitUntilDispatchCheckStarted()

        let queuedProgress = await schedulerReadModel.progressSnapshot(for: "req-queued-abort")
        #expect(queuedProgress?.phase == .requestQueued)

        let cancelled = try await coordinator.cancel(requestID: "req-queued-abort")
        #expect(cancelled)

        await workerClient.allowDispatch()

        let execution = try await task.value
        var iterator = execution.stream.makeAsyncIterator()
        let terminalEvent = try #require(await iterator.next())
        let metrics = await metricsStore.snapshot()
        let terminalProgress = await schedulerReadModel.progressSnapshot(for: "req-queued-abort")

        #expect(terminalEvent.completed.finishReason == "cancelled")
        #expect(terminalProgress?.phase == .requestAborted)
        #expect(metrics.values["swift_text.abort_queued_ms", default: 0] >= 0)
        #expect(await workerClient.abortedRequestIDs.isEmpty)
    }

    @Test("admitted request cancellation before generate returns yields a cancelled execution")
    func admittedRequestCancellationBeforeGenerateReturnsYieldsACancelledExecution() async throws {
        let workerClient = SlowGenerateWorkerClient()
        let schedulerReadModel = SchedulerReadModel()
        let metricsStore = MetricsStore()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel,
            metricsStore: metricsStore
        )

        let task = Task {
            try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-admitted-abort"))
        }

        await workerClient.waitUntilGenerateStarted()
        let admittedProgress = await schedulerReadModel.progressSnapshot(for: "req-admitted-abort")
        #expect(admittedProgress?.phase == .requestAdmitted)

        let cancelled = try await coordinator.cancel(requestID: "req-admitted-abort")
        #expect(cancelled)

        await workerClient.allowGenerate()
        let execution = try await task.value
        var iterator = execution.stream.makeAsyncIterator()
        let terminalEvent = try #require(await iterator.next())
        let terminalProgress = await schedulerReadModel.progressSnapshot(for: "req-admitted-abort")
        let metrics = await metricsStore.snapshot()

        #expect(terminalEvent.completed.finishReason == "cancelled")
        #expect(terminalProgress?.phase == .requestAborted)
        #expect(metrics.values["http.abort_ms", default: 0] >= 0)
    }

    @Test("second request queues until the active request releases admission")
    func secondRequestQueuesUntilTheActiveRequestReleasesAdmission() async throws {
        let workerClient = BlockingWorkerClient()
        let schedulerReadModel = SchedulerReadModel()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel
        )

        let execution1 = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-1"))
        let consumer1 = Task {
            do {
                for try await _ in execution1.stream {
                }
            } catch {
            }
        }

        let secondExecutionTask = Task {
            try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-2"))
        }
        let queuedProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-2",
            phase: .requestQueued
        )
        #expect(queuedProgress?.phase == .requestQueued)
        #expect(queuedProgress?.queuePosition == 1)

        #expect(try await coordinator.cancel(requestID: "req-1"))
        _ = await consumer1.result
        let execution2 = try await secondExecutionTask.value
        let consumer2 = Task {
            do {
                for try await _ in execution2.stream {
                }
            } catch {
            }
        }
        let admittedProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-2",
            phase: .requestAdmitted
        )
        #expect(admittedProgress?.phase == .requestAdmitted)

        #expect(try await coordinator.cancel(requestID: "req-2"))
        _ = await consumer2.result

        let execution3 = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-3"))
        #expect(execution3.requestID == "req-3")
        let consumer3 = Task {
            do {
                for try await _ in execution3.stream {
                }
            } catch {
            }
        }
        #expect(try await coordinator.cancel(requestID: "req-3"))
        _ = await consumer3.result

        #expect(await workerClient.generatedRequestIDs == ["req-1", "req-2", "req-3"])
    }

    @Test("duplicate request identifiers are rejected while the original request is tracked")
    func duplicateRequestIdentifiersAreRejectedWhileTracked() async throws {
        let workerClient = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(requestID: "req-duplicate")
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-duplicate"))
            Issue.record("Expected duplicate request tracking to be rejected.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .requestAlreadyActive)
        }

        _ = execution
    }

    @Test("worker unavailable requests are rejected before dispatch")
    func workerUnavailableRequestsAreRejected() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: UnavailableCoordinatorWorkerClient()),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-unavailable"))
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }
    }

    @Test("cancelling an unknown request returns false")
    func cancellingUnknownRequestReturnsFalse() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: BlockingWorkerClient()),
            abortRegistry: AbortRegistry()
        )
        let cancelled = try await coordinator.cancel(requestID: "missing-request")
        #expect(!cancelled)
    }

    @Test("text requests route to the swift text client by default")
    func textRequestsRouteToTheSwiftTextClientByDefault() async throws {
        let swiftWorker = BlockingWorkerClient()
        let pythonWorker = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(
                defaultTextClient: swiftWorker,
                pythonCompatibilityClient: pythonWorker
            ),
            abortRegistry: AbortRegistry()
        )

        _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-swift"))

        #expect(await swiftWorker.generatedRequestIDs == ["req-swift"])
        #expect(await pythonWorker.generatedRequestIDs.isEmpty)
    }

    @Test("session tagged requests hydrate session graph request heads")
    func sessionTaggedRequestsHydrateSessionGraphRequestHeads() async throws {
        let workerClient = BlockingWorkerClient()
        let sessionGraphStore = SessionGraphStore(nowUnixMs: { 7_000 })
        let metricsStore = MetricsStore()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            metricsStore: metricsStore,
            sessionGraphStore: sessionGraphStore
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(
                requestID: "req-session-hydrated",
                sessionID: "session-hydrated",
                branchID: "branch-main"
            )
        )
        _ = execution

        let state = await sessionGraphStore.state(for: "session-hydrated")
        let metrics = await metricsStore.snapshot()

        #expect(state?.latestRequestID == "req-session-hydrated")
        #expect(state?.activeBranchID == "branch-main")
        #expect(state?.branches.first?.headRequestID == "req-session-hydrated")
        #expect(metrics.values["session_graph.request_hydration_ms", default: -1] >= 0)

        #expect(try await coordinator.cancel(requestID: "req-session-hydrated"))
    }

    @Test("tool call deltas hydrate session graph tool metadata")
    func toolCallDeltasHydrateSessionGraphToolMetadata() async throws {
        let workerClient = ToolCallingWorkerClient()
        let sessionGraphStore = SessionGraphStore(nowUnixMs: { 8_000 })
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            sessionGraphStore: sessionGraphStore
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(
                requestID: "req-tool-hydrated",
                sessionID: "session-tools",
                branchID: "branch-main"
            )
        )

        for try await _ in execution.stream {
        }

        let state = await sessionGraphStore.state(for: "session-tools")
        #expect(state?.latestToolCallID == "tool-call-1")
        #expect(state?.branches.first?.lastToolCallID == "tool-call-1")
    }

    @Test("session follow-up requests restore the latest branch snapshot through phase-aware prefill")
    func sessionFollowUpRequestsRestoreLatestBranchSnapshot() async throws {
        let workerClient = PhaseAwareWorkerClient()
        let sessionGraphStore = SessionGraphStore(nowUnixMs: { 9_000 })
        let metricsStore = MetricsStore()
        _ = await sessionGraphStore.recordRequestStart(
            sessionID: "session-resume",
            branchID: "branch-main",
            requestID: "req-parent"
        )
        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-parent"
        snapshot.requestID = "req-parent"
        snapshot.tokenBoundary = 6
        _ = await sessionGraphStore.recordSnapshotHydration(
            sessionID: "session-resume",
            branchID: "branch-main",
            snapshot: snapshot
        )

        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            metricsStore: metricsStore,
            sessionGraphStore: sessionGraphStore
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(
                requestID: "req-resume",
                sessionID: "session-resume",
                branchID: "branch-main",
                parentRequestID: "req-parent",
                saveBoundarySnapshot: true
            )
        )
        let consumer = Task {
            do {
                for try await _ in execution.stream {
                }
            } catch {
            }
        }

        let prefillRequest = try #require(await workerClient.lastPrefillRequest())
        #expect(prefillRequest.execution.cacheHints.restoreSnapshotID == "snap-parent")
        #expect(await workerClient.generatedRequestIDs.isEmpty)

        await workerClient.emitDecodeStarted(requestID: "req-resume", decodeHandle: prefillRequest.execution.id.requestID)
        await workerClient.emitToken(requestID: "req-resume", text: "restored")
        await workerClient.finishDecode(requestID: "req-resume")
        _ = await consumer.result

        let metrics = await metricsStore.snapshot()
        #expect(metrics.values["session_graph.restore_snapshot_count", default: 0] >= 1)
    }

    @Test("warm follow-up requests prefer hot prefill lanes and refresh cache observability")
    func warmFollowUpRequestsPreferHotPrefillLanesAndRefreshCacheObservability() async throws {
        let workerClient = PhaseAwareWorkerClient()
        var runtimeStats = Melix_Worker_V1_GetRuntimeStatsResponse()
        runtimeStats.stats.residentBytes = 8_192
        await workerClient.setRuntimeStatsResponse(runtimeStats)

        var cacheStats = Melix_Worker_V1_GetCacheStatsResponse()
        cacheStats.stats.l1Bytes = 2_048
        cacheStats.stats.l2Bytes = 4_096
        cacheStats.stats.l1HitRate = 0.5
        cacheStats.stats.l2RestoreHitRate = 1.0
        cacheStats.stats.compressionRatio = 0.25
        await workerClient.setCacheStatsResponse(cacheStats)

        let sessionGraphStore = SessionGraphStore(nowUnixMs: { 11_000 })
        let metricsStore = MetricsStore()
        let schedulerReadModel = SchedulerReadModel()
        let cacheMetadataStore = CacheMetadataStore()

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.scope.modelID = "melix-dev-text"
        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-hot"
        snapshot.requestID = "req-parent"
        _ = await sessionGraphStore.recordSnapshotHydration(
            sessionID: "session-hot",
            branchID: "branch-main",
            snapshot: snapshot,
            headCacheKey: cacheKey
        )

        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel,
            metricsStore: metricsStore,
            sessionGraphStore: sessionGraphStore,
            cacheMetadataStore: cacheMetadataStore
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(
                requestID: "req-hot",
                sessionID: "session-hot",
                branchID: "branch-main",
                parentRequestID: "req-parent",
                saveBoundarySnapshot: true
            )
        )
        let consumer = Task {
            do {
                for try await _ in execution.stream {
                }
            } catch {
            }
        }

        let admittedProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-hot",
            phase: .requestAdmitted
        )
        #expect(admittedProgress?.lane == "text.prefill.hot")

        await workerClient.emitDecodeStarted(requestID: "req-hot", decodeHandle: "decode-hot")
        await workerClient.emitToken(requestID: "req-hot", text: "hot")
        await workerClient.finishDecode(requestID: "req-hot")
        _ = await consumer.result

        let metrics = await metricsStore.snapshot()
        let cacheSummary = await cacheMetadataStore.cacheSummary()

        #expect(metrics.values["scheduler.prefix_affinity_hit_rate"] == 100)
        #expect(metrics.values["scheduler.warm_route_preference_rate"] == 100)
        #expect(metrics.values["scheduler.restored_route_rate"] == 100)
        #expect(metrics.values["cache.memory_bytes"] == 2_048)
        #expect(metrics.values["cache.disk_bytes"] == 4_096)
        #expect(metrics.values["cache.hit_rate"] == 50)
        #expect(metrics.values["cache.l2_restore_hit_rate"] == 100)
        #expect(metrics.values["scheduler.cache_pressure"] == 0.25)
        #expect(cacheSummary.l1Bytes == 2_048)
        #expect(cacheSummary.l2Bytes == 4_096)
    }

    @Test("cold session requests prefer background prefill lanes before reuse exists")
    func coldSessionRequestsPreferBackgroundPrefillLanesBeforeReuseExists() async throws {
        let workerClient = PhaseAwareWorkerClient()
        let schedulerReadModel = SchedulerReadModel()
        let metricsStore = MetricsStore()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel,
            metricsStore: metricsStore,
            sessionGraphStore: SessionGraphStore(nowUnixMs: { 12_000 })
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(
                requestID: "req-cold-prefill",
                sessionID: "session-cold-prefill",
                branchID: "branch-main",
                saveBoundarySnapshot: true
            )
        )
        let consumer = Task {
            do {
                for try await _ in execution.stream {
                }
            } catch {
            }
        }

        let admittedProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-cold-prefill",
            phase: .requestAdmitted
        )
        #expect(admittedProgress?.lane == "text.prefill.background")

        await workerClient.emitDecodeStarted(requestID: "req-cold-prefill", decodeHandle: "decode-cold")
        await workerClient.finishDecode(requestID: "req-cold-prefill")
        _ = await consumer.result

        let metrics = await metricsStore.snapshot()
        #expect(metrics.values["scheduler.warm_route_preference_rate"] == 0)
        #expect(metrics.values["scheduler.prefix_affinity_hit_rate"] == 0)
    }

    @Test("snapshot created events hydrate branch resume metadata during phase-aware decode")
    func snapshotCreatedEventsHydrateBranchResumeMetadata() async throws {
        let workerClient = PhaseAwareWorkerClient()
        let sessionGraphStore = SessionGraphStore(nowUnixMs: { 10_000 })
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            sessionGraphStore: sessionGraphStore
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(
                requestID: "req-snapshot",
                sessionID: "session-snapshot",
                branchID: "branch-main",
                saveBoundarySnapshot: true
            )
        )
        let consumer = Task {
            do {
                for try await _ in execution.stream {
                }
            } catch {
            }
        }

        await workerClient.emitDecodeStarted(requestID: "req-snapshot", decodeHandle: "decode-snapshot")
        await workerClient.emitSnapshotCreated(
            requestID: "req-snapshot",
            snapshotID: "snap-created",
            tokenBoundary: 12
        )
        await workerClient.finishDecode(requestID: "req-snapshot")
        _ = await consumer.result

        let state = await sessionGraphStore.state(for: "session-snapshot")
        #expect(state?.latestSnapshotID == "snap-created")
        #expect(state?.branches.first?.resumeSnapshotID == "snap-created")
        #expect(state?.branches.first?.headRequestID == "req-snapshot")
    }

    @Test("swift route failure does not fall back to python text execution")
    func swiftRouteFailureDoesNotFallBackToPythonTextExecution() async throws {
        let pythonWorker = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(
                defaultTextClient: UnavailableCoordinatorWorkerClient(),
                pythonCompatibilityClient: pythonWorker
            ),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-no-fallback"))
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }

        #expect(await pythonWorker.generatedRequestIDs.isEmpty)
    }

    @Test("stream failures propagate and release request tracking")
    func streamFailuresPropagateAndReleaseRequestTracking() async throws {
        let workerClient = ThrowingStreamWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(requestID: "req-stream-error")
        )

        do {
            for try await _ in execution.stream {
            }
            Issue.record("Expected the upstream stream to fail.")
        } catch let error as TestWorkerFailure {
            #expect(error == .streamFailed)
        }

        let cancelled = try await coordinator.cancel(requestID: "req-stream-error")
        #expect(!cancelled)
    }

    @Test("generate unavailability is surfaced without fallback")
    func generateUnavailabilityIsSurfacedWithoutFallback() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: FailingGenerateWorkerClient(error: WorkerClientError.unavailable)),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-generate-unavailable"))
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }
    }

    @Test("generate failures propagate when the worker throws a generic error")
    func generateFailuresPropagateWhenTheWorkerThrowsAGenericError() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: FailingGenerateWorkerClient(error: TestWorkerFailure.generateFailed)),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-generate-failure"))
            Issue.record("Expected the worker failure to be thrown.")
        } catch let error as TestWorkerFailure {
            #expect(error == .generateFailed)
        }
    }

    @Test("cancel succeeds when request tracking exists without an active worker")
    func cancelSucceedsWhenRequestTrackingExistsWithoutAnActiveWorker() async throws {
        let abortRegistry = AbortRegistry()
        _ = await abortRegistry.begin(requestID: "req-missing-worker")
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: BlockingWorkerClient()),
            abortRegistry: abortRegistry
        )

        let cancelled = try await coordinator.cancel(requestID: "req-missing-worker")
        #expect(cancelled)
    }

    @Test("scheduler snapshots track queued admitted and aborted coordinator lifecycle")
    func schedulerSnapshotsTrackCoordinatorLifecycle() async throws {
        let workerClient = BlockingWorkerClient()
        let schedulerReadModel = SchedulerReadModel()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel
        )

        let execution = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-1"))
        let streamTask = Task {
            do {
                for try await _ in execution.stream {
                }
            } catch {
            }
        }

        let admittedSnapshot = await schedulerReadModel.snapshot()
        let admittedProgress = await schedulerReadModel.progressSnapshot(for: "req-1")

        #expect(admittedSnapshot.activeRequests == 1)
        #expect(admittedSnapshot.admittedRequests == 1)
        #expect(admittedProgress?.phase == .requestAdmitted)
        #expect(admittedProgress?.lane == "text.decode.interactive")
        #expect(admittedProgress?.admissionState == .admissionAdmitted)

        let secondExecutionTask = Task {
            try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-2"))
        }

        let queuedProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-2",
            phase: .requestQueued
        )
        let queuedSnapshot = await schedulerReadModel.snapshot()

        #expect(queuedSnapshot.activeRequests == 1)
        #expect(queuedSnapshot.queuedRequests == 1)
        #expect(queuedProgress?.phase == .requestQueued)
        #expect(queuedProgress?.queuePosition == 1)
        #expect(queuedProgress?.admissionState == .admissionQueued)

        let cancelled = try await coordinator.cancel(requestID: "req-1")
        #expect(cancelled)
        _ = await streamTask.result
        let execution2 = try await secondExecutionTask.value
        let streamTask2 = Task {
            do {
                for try await _ in execution2.stream {
                }
            } catch {
            }
        }
        let admittedSecondProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-2",
            phase: .requestAdmitted
        )
        #expect(admittedSecondProgress?.phase == .requestAdmitted)

        #expect(try await coordinator.cancel(requestID: "req-2"))
        _ = await streamTask2.result

        let terminalSnapshot = await schedulerReadModel.snapshot()
        let terminalProgress = await schedulerReadModel.progressSnapshot(for: "req-2")

        #expect(terminalSnapshot.activeRequests == 0)
        #expect(terminalSnapshot.backpressure == 0)
        #expect(terminalProgress?.phase == .requestAborted)
    }

    @Test("worker stream events advance scheduler progress through prefill and decode")
    func workerStreamEventsAdvanceSchedulerProgressThroughPrefillAndDecode() async throws {
        let workerClient = PhaseAwareWorkerClient()
        let schedulerReadModel = SchedulerReadModel()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel
        )

        let execution = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-phase-events"))
        let consumer = Task {
            do {
                for try await _ in execution.stream {
                }
            } catch {
            }
        }

        await workerClient.emitPrefillStarted(requestID: "req-phase-events")
        let prefillProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-phase-events",
            phase: .requestPrefilling
        )
        #expect(prefillProgress?.phase == .requestPrefilling)
        #expect(prefillProgress?.lane == "text.prefill.hot")

        await workerClient.emitToken(requestID: "req-phase-events", text: "hello")
        await workerClient.finish(requestID: "req-phase-events")
        _ = await consumer.result

        let decodeProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-phase-events",
            phase: .requestCompleted
        )
        #expect(decodeProgress?.phase == .requestCompleted)
        #expect(decodeProgress?.lane == "text.decode.interactive")
        #expect(prefillProgress?.accelerationMode == .acceleratedPrefill || prefillProgress?.accelerationMode == .unspecified)
    }

    @Test("cancellation records prefill and decode phase metrics")
    func cancellationRecordsPrefillAndDecodePhaseMetrics() async throws {
        let prefillWorker = PhaseAwareWorkerClient()
        let prefillMetrics = MetricsStore()
        let prefillScheduler = SchedulerReadModel()
        let prefillCoordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: prefillWorker),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: prefillScheduler,
            metricsStore: prefillMetrics
        )

        let prefillExecution = try await prefillCoordinator.startChatCompletion(
            makeTranslatedChatRequest(requestID: "req-prefill-abort")
        )
        let prefillConsumer = Task {
            do {
                for try await _ in prefillExecution.stream {
                }
            } catch {
            }
        }

        await prefillWorker.emitPrefillStarted(requestID: "req-prefill-abort")
        let prefillCancelled = try await prefillCoordinator.cancel(requestID: "req-prefill-abort")
        await prefillWorker.finish(requestID: "req-prefill-abort")
        _ = await prefillConsumer.result

        let prefillSnapshot = await prefillMetrics.snapshot()
        #expect(prefillCancelled)
        #expect(prefillSnapshot.values["swift_text.abort_prefill_ms", default: 0] >= 0)

        let decodeWorker = PhaseAwareWorkerClient()
        let decodeMetrics = MetricsStore()
        let decodeScheduler = SchedulerReadModel()
        let decodeCoordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: decodeWorker),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: decodeScheduler,
            metricsStore: decodeMetrics
        )

        let decodeExecution = try await decodeCoordinator.startChatCompletion(
            makeTranslatedChatRequest(requestID: "req-decode-abort")
        )
        let decodeConsumer = Task {
            do {
                for try await _ in decodeExecution.stream {
                }
            } catch {
            }
        }

        await decodeWorker.emitPrefillStarted(requestID: "req-decode-abort")
        await decodeWorker.emitToken(requestID: "req-decode-abort", text: "world")
        _ = await waitForProgress(
            schedulerReadModel: decodeScheduler,
            requestID: "req-decode-abort",
            phase: .requestDecoding
        )
        let decodeCancelled = try await decodeCoordinator.cancel(requestID: "req-decode-abort")
        await decodeWorker.finish(requestID: "req-decode-abort")
        _ = await decodeConsumer.result

        let decodeSnapshot = await decodeMetrics.snapshot()
        #expect(decodeCancelled)
        #expect(decodeSnapshot.values["swift_text.abort_decode_ms", default: 0] >= 0)
    }

    @Test("phase-aware stream events preserve acceleration metadata and terminal aborts")
    func phaseAwareStreamEventsPreserveAccelerationMetadataAndTerminalAborts() async throws {
        let workerClient = PhaseAwareWorkerClient()
        let schedulerReadModel = SchedulerReadModel()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry(),
            schedulerReadModel: schedulerReadModel
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(requestID: "req-phase-metadata")
        )
        let consumer = Task {
            do {
                for try await _ in execution.stream {
                }
            } catch {
            }
        }

        await workerClient.emitPrefillStarted(
            requestID: "req-phase-metadata",
            accelerationMode: .acceleratedPrefill
        )
        let prefillProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-phase-metadata",
            phase: .requestPrefilling
        )
        #expect(prefillProgress?.accelerationMode == .acceleratedPrefill)

        await workerClient.emitDecodeStarted(
            requestID: "req-phase-metadata",
            decodeHandle: "decode-phase",
            accelerationMode: .speculativeDecode
        )
        let decodeProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-phase-metadata",
            phase: .requestDecoding
        )
        #expect(decodeProgress?.decodeHandle == "decode-phase")
        #expect(decodeProgress?.accelerationMode == .speculativeDecode)

        await workerClient.emitReasoningDelta(
            requestID: "req-phase-metadata",
            text: "reason",
            accelerationMode: .baseline
        )
        await workerClient.emitUsageDelta(
            requestID: "req-phase-metadata",
            promptTokens: 4,
            completionTokens: 2,
            accelerationMode: .activeKvQuantized
        )
        await workerClient.emitToken(
            requestID: "req-phase-metadata",
            text: "ignored",
            accelerationMode: .UNRECOGNIZED(999)
        )
        await workerClient.emitHeartbeat(requestID: "req-phase-metadata")
        await workerClient.finishAborted(requestID: "req-phase-metadata")
        _ = await consumer.result

        let terminalProgress = await waitForProgress(
            schedulerReadModel: schedulerReadModel,
            requestID: "req-phase-metadata",
            phase: .requestAborted
        )
        #expect(terminalProgress?.phase == .requestAborted)
        #expect(terminalProgress?.lane == "text.decode.interactive")
    }

}

private actor BlockingWorkerClient: WorkerRoutingClient {
    private(set) var generatedRequestIDs: [String] = []
    private(set) var abortedRequestIDs: [String] = []
    private var continuations: [String: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation] = [:]

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        generatedRequestIDs.append(request.execution.id.requestID)
        let requestID = request.execution.id.requestID
        return AsyncThrowingStream { continuation in
            continuations[requestID] = continuation
        }
    }

    func abort(requestID: String) async throws -> Bool {
        abortedRequestIDs.append(requestID)
        continuations.removeValue(forKey: requestID)?.finish()
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor SlowGenerateWorkerClient: WorkerRoutingClient {
    private var generateStartedWaiters: [CheckedContinuation<Void, Never>] = []
    private var generateGate: CheckedContinuation<Void, Never>?
    private var generateStarted = false

    func waitUntilGenerateStarted() async {
        if generateStarted {
            return
        }
        await withCheckedContinuation { continuation in
            generateStartedWaiters.append(continuation)
        }
    }

    func allowGenerate() {
        generateGate?.resume()
        generateGate = nil
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        generateStarted = true
        let waiters = generateStartedWaiters
        generateStartedWaiters.removeAll()
        waiters.forEach { $0.resume() }
        await withCheckedContinuation { continuation in
            generateGate = continuation
        }
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor SlowDispatchWorkerClient: WorkerRoutingClient {
    private(set) var generatedRequestIDs: [String] = []
    private(set) var abortedRequestIDs: [String] = []
    private var continuations: [String: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation] = [:]
    private var dispatchStartedWaiters: [CheckedContinuation<Void, Never>] = []
    private var dispatchGate: CheckedContinuation<Void, Never>?
    private var dispatchStarted = false

    func waitUntilDispatchCheckStarted() async {
        if dispatchStarted {
            return
        }
        await withCheckedContinuation { continuation in
            dispatchStartedWaiters.append(continuation)
        }
    }

    func allowDispatch() {
        dispatchGate?.resume()
        dispatchGate = nil
    }

    func canDispatchRequests() async -> Bool {
        dispatchStarted = true
        let waiters = dispatchStartedWaiters
        dispatchStartedWaiters.removeAll()
        waiters.forEach { $0.resume() }
        await withCheckedContinuation { continuation in
            dispatchGate = continuation
        }
        return true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        generatedRequestIDs.append(request.execution.id.requestID)
        let requestID = request.execution.id.requestID
        return AsyncThrowingStream { continuation in
            continuations[requestID] = continuation
        }
    }

    func abort(requestID: String) async throws -> Bool {
        abortedRequestIDs.append(requestID)
        continuations.removeValue(forKey: requestID)?.finish()
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor UnavailableCoordinatorWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool {
        false
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        throw WorkerClientError.unavailable
    }
}

private actor ThrowingStreamWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish(throwing: TestWorkerFailure.streamFailed)
        }
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor PhaseAwareWorkerClient:
    WorkerRoutingClient,
    PhaseAwareWorkerClientProtocol,
    CacheIntrospectingWorkerClientProtocol
{
    private var continuations: [String: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation] = [:]
    private var prefillRequests: [Melix_Worker_V1_PrefillRequest] = []
    private var decodeRequests: [Melix_Worker_V1_DecodeRequest] = []
    private(set) var abortedRequestIDs: [String] = []
    private(set) var generatedRequestIDs: [String] = []
    private var runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
    private var cacheStatsResponse = Melix_Worker_V1_GetCacheStatsResponse()

    func setRuntimeStatsResponse(_ response: Melix_Worker_V1_GetRuntimeStatsResponse) {
        runtimeStatsResponse = response
    }

    func setCacheStatsResponse(_ response: Melix_Worker_V1_GetCacheStatsResponse) {
        cacheStatsResponse = response
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        generatedRequestIDs.append(request.execution.id.requestID)
        let requestID = request.execution.id.requestID
        return AsyncThrowingStream { continuation in
            continuations[requestID] = continuation
        }
    }

    func prefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        prefillRequests.append(request)

        var response = Melix_Worker_V1_PrefillResponse()
        response.ok = true
        response.decodeHandle = "decode-\(request.execution.id.requestID)"
        response.blockTableID = "block-\(request.execution.id.requestID)"
        response.promptTokens = 4
        response.lifecyclePhase = .executionPrefilling
        response.admissionState = .admissionAdmitted
        response.restoredSnapshotID = request.execution.cacheHints.restoreSnapshotID
        if response.appliedAcceleration.mode == .unspecified {
            response.appliedAcceleration.mode = .baseline
        }
        return response
    }

    func decode(
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        decodeRequests.append(request)
        let requestID = request.execution.id.requestID
        return AsyncThrowingStream { continuation in
            continuations[requestID] = continuation
        }
    }

    func abort(requestID: String) async throws -> Bool {
        abortedRequestIDs.append(requestID)
        continuations[requestID]?.finish()
        return true
    }

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        runtimeStatsResponse
    }

    func cacheStats() async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        cacheStatsResponse
    }

    func emitPrefillStarted(
        requestID: String,
        accelerationMode: Melix_Worker_V1_AccelerationMode = .unspecified
    ) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionPrefilling
        event.admissionState = .admissionAdmitted
        event.lane = "text.prefill.hot"
        event.accelerationMode = accelerationMode
        var payload = Melix_Worker_V1_PrefillStarted()
        payload.inputTokens = 4
        event.prefillStarted = payload
        continuation.yield(event)
    }

    func emitDecodeStarted(
        requestID: String,
        decodeHandle: String,
        accelerationMode: Melix_Worker_V1_AccelerationMode = .unspecified
    ) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionDecoding
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        event.accelerationMode = accelerationMode
        var payload = Melix_Worker_V1_DecodeStarted()
        payload.decodeHandle = decodeHandle
        payload.maxOutputTokens = 64
        payload.resumedFromPrefill = true
        event.decodeStarted = payload
        continuation.yield(event)
    }

    func emitSnapshotCreated(
        requestID: String,
        snapshotID: String,
        tokenBoundary: UInt32
    ) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "decode"
        event.phase = .executionDecoding
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        var payload = Melix_Worker_V1_BoundarySnapshotCreated()
        payload.snapshotID = snapshotID
        payload.tokenBoundary = tokenBoundary
        event.snapshotCreated = payload
        continuation.yield(event)
    }

    func emitToken(
        requestID: String,
        text: String,
        accelerationMode: Melix_Worker_V1_AccelerationMode = .unspecified
    ) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionDecoding
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        event.accelerationMode = accelerationMode
        var payload = Melix_Worker_V1_TokenDelta()
        payload.text = text
        event.tokenDelta = payload
        continuation.yield(event)
    }

    func emitReasoningDelta(
        requestID: String,
        text: String,
        accelerationMode: Melix_Worker_V1_AccelerationMode = .unspecified
    ) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionDecoding
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        event.accelerationMode = accelerationMode
        var payload = Melix_Worker_V1_ReasoningDelta()
        payload.text = text
        event.reasoningDelta = payload
        continuation.yield(event)
    }

    func emitUsageDelta(
        requestID: String,
        promptTokens: UInt32,
        completionTokens: UInt32,
        accelerationMode: Melix_Worker_V1_AccelerationMode = .unspecified
    ) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionDecoding
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        event.accelerationMode = accelerationMode
        var payload = Melix_Worker_V1_UsageDelta()
        payload.promptTokens = promptTokens
        payload.completionTokens = completionTokens
        event.usageDelta = payload
        continuation.yield(event)
    }

    func emitHeartbeat(requestID: String) {
        guard let continuation = continuations[requestID] else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionDecoding
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        var payload = Melix_Worker_V1_Heartbeat()
        payload.unixMs = 1
        event.heartbeat = payload
        continuation.yield(event)
    }

    func finish(requestID: String) {
        finishDecode(requestID: requestID)
    }

    func finishDecode(requestID: String) {
        guard let continuation = continuations.removeValue(forKey: requestID) else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionCompleted
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        var completed = Melix_Worker_V1_Completed()
        completed.finishReason = "stop"
        completed.assistantText = "done"
        event.completed = completed
        continuation.yield(event)
        continuation.finish()
    }

    func lastPrefillRequest() -> Melix_Worker_V1_PrefillRequest? {
        prefillRequests.last
    }

    func lastDecodeRequest() -> Melix_Worker_V1_DecodeRequest? {
        decodeRequests.last
    }

    func finishAborted(requestID: String) {
        guard let continuation = continuations.removeValue(forKey: requestID) else {
            return
        }
        var event = Melix_Worker_V1_ExecuteEvent()
        event.requestID = requestID
        event.executionKind = "generate"
        event.phase = .executionAborted
        event.admissionState = .admissionAdmitted
        event.lane = "text.decode.interactive"
        var completed = Melix_Worker_V1_Completed()
        completed.finishReason = "cancelled"
        event.completed = completed
        continuation.yield(event)
        continuation.finish()
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor FailingGenerateWorkerClient: WorkerRoutingClient {
    let error: Error

    init(error: Error) {
        self.error = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw error
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor ToolCallingWorkerClient: WorkerRoutingClient {
    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            var toolCall = Melix_Worker_V1_ToolCallDelta()
            toolCall.callID = "tool-call-1"
            toolCall.toolName = "search"

            var toolEvent = Melix_Worker_V1_ExecuteEvent()
            toolEvent.requestID = request.execution.id.requestID
            toolEvent.executionKind = "generate"
            toolEvent.phase = .executionDecoding
            toolEvent.toolCallDelta = toolCall
            continuation.yield(toolEvent)

            var completed = Melix_Worker_V1_Completed()
            completed.finishReason = "stop"

            var terminal = Melix_Worker_V1_ExecuteEvent()
            terminal.requestID = request.execution.id.requestID
            terminal.executionKind = "generate"
            terminal.phase = .executionCompleted
            terminal.completed = completed
            continuation.yield(terminal)
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private enum TestWorkerFailure: Error, Equatable {
    case streamFailed
    case generateFailed
}

private func makeTranslatedChatRequest(
    requestID: String,
    modelID: String = "melix-dev-text",
    sessionID: String = "",
    branchID: String = "",
    parentRequestID: String = "",
    restoreSnapshotID: String = "",
    saveBoundarySnapshot: Bool = false
) -> TranslatedChatRequest {
    var workerRequest = Melix_Worker_V1_GenerateRequest()
    workerRequest.execution = Melix_Worker_V1_ExecutionMetadata()
    workerRequest.execution.id = Melix_Worker_V1_RequestIdentity()
    workerRequest.execution.id.requestID = requestID
    workerRequest.execution.id.sessionID = sessionID
    workerRequest.execution.id.branchID = branchID
    workerRequest.execution.id.parentRequestID = parentRequestID
    workerRequest.execution.modelHandle = "melix-dev-text::local"
    workerRequest.execution.scheduling = Melix_Worker_V1_SchedulingHints()
    workerRequest.execution.scheduling.lane = "text.decode.interactive"
    workerRequest.execution.scheduling.priority = 100
    workerRequest.execution.scheduling.latencySensitive = true
    workerRequest.execution.cacheHints = Melix_Worker_V1_CacheHints()
    workerRequest.execution.cacheHints.restoreSnapshotID = restoreSnapshotID
    workerRequest.execution.cacheHints.saveBoundarySnapshot = saveBoundarySnapshot

    return TranslatedChatRequest(
        requestID: requestID,
        modelID: modelID,
        workerRequest: workerRequest,
        stream: true
    )
}

private func waitForProgress(
    schedulerReadModel: SchedulerReadModel,
    requestID: String,
    phase: Melix_Controlplane_V1_RequestPhase,
    attempts: Int = 50
) async -> Melix_Controlplane_V1_RequestProgressEvent? {
    for _ in 0..<attempts {
        let progress = await schedulerReadModel.progressSnapshot(for: requestID)
        if progress?.phase == phase {
            return progress
        }
        await Task.yield()
    }
    return await schedulerReadModel.progressSnapshot(for: requestID)
}
