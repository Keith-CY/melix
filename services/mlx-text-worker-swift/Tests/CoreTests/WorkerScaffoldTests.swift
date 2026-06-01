import Foundation
import XCTest
import GRPCCore
import MelixWorkerProtocol
#if canImport(MLX)
import MLX
#endif
#if canImport(MLXNN)
import MLXNN
#endif
#if canImport(MLXLMCommon)
import MLXLMCommon
#endif
#if canImport(MLXLLM)
import MLXLLM
#endif
#if canImport(Tokenizers)
import Tokenizers
#endif
@testable import MelixTextWorkerCore

@available(macOS 15.0, *)
final class WorkerScaffoldTests: XCTestCase {
    func testHarmonyChannelOutputFilterSuppressesInternalChannels() {
        var filter = HarmonyChannelOutputFilter()

        let first = filter.accept("<|chan")
        let second = filter.accept("nel>thought\n<channel|>\nsecret")
        let third = filter.accept("<|channel>debug\n<channel|>\ndropped")
        let fourth = filter.accept("<|channel>final\n<channel|>\nvisible")
        let finished = filter.finish()

        XCTAssertEqual(first, HarmonyChannelOutputFilter.Output())
        XCTAssertEqual(second.reasoningText, "\nsecret")
        XCTAssertEqual(second.visibleText, "")
        XCTAssertEqual(third, HarmonyChannelOutputFilter.Output())
        XCTAssertEqual(fourth.visibleText, "\nvisible")
        XCTAssertEqual(fourth.reasoningText, "")
        XCTAssertEqual(finished, HarmonyChannelOutputFilter.Output())
    }

    func testConfigurationDefaultsPreferDedicatedWorkerIdentity() {
        let configuration = WorkerConfiguration()
        let matchingConfiguration = WorkerConfiguration(
            backendMode: configuration.backendMode,
            runtimeVersion: configuration.runtimeVersion
        )

        XCTAssertEqual(configuration.workerID, "swift-text-worker-001")
        XCTAssertEqual(configuration.socketPath, "/var/run/melix/swift-text-worker.sock")
        XCTAssertEqual(configuration.backendMode, "swift")
        XCTAssertEqual(configuration.runtimeVersion, "melix-swift-text-worker/dev")
        XCTAssertFalse(configuration.runtimeCacheFingerprint.isEmpty)
        XCTAssertEqual(configuration.runtimeCacheFingerprint, matchingConfiguration.runtimeCacheFingerprint)
        XCTAssertEqual(configuration.cacheRootPath, ".runtime/swift-text-worker-cache")
        XCTAssertFalse(configuration.memoryEnforcementDisabled)
        XCTAssertEqual(configuration.processMemoryBudgetBytes, 0)
        XCTAssertEqual(configuration.modelLoadHeadroomBytes, 0)
        XCTAssertEqual(configuration.prefillMemoryHeadroomBytes, 0)
        XCTAssertEqual(configuration.prefillQuadraticGuardTokenThreshold, 0)
        XCTAssertEqual(configuration.initialCacheBlocks, 0)
        XCTAssertEqual(configuration.decodeBatchPendingWindowNanos, 2_000_000)
        XCTAssertEqual(configuration.decodeBatchCohortPendingWindowNanos, 2_000_000_000)
        XCTAssertFalse(configuration.turboQuantCandidateProbeEnabled)
    }

    func testConfigurationDefaultRuntimeFingerprintTracksCustomRuntimeInputs() {
        let baseline = WorkerConfiguration()
        let custom = WorkerConfiguration(
            backendMode: "swift-experimental",
            runtimeVersion: "melix-swift-text-worker/test"
        )
        let matchingCustom = WorkerConfiguration(
            backendMode: "swift-experimental",
            runtimeVersion: "melix-swift-text-worker/test"
        )

        XCTAssertNotEqual(custom.runtimeCacheFingerprint, baseline.runtimeCacheFingerprint)
        XCTAssertEqual(custom.runtimeCacheFingerprint, matchingCustom.runtimeCacheFingerprint)
    }

    func testConfigurationReadsEnvironmentOverrides() {
        let configuration = WorkerConfiguration.fromEnvironment([
            "MELIX_SWIFT_TEXT_WORKER_ID": "swift-text-worker-dev",
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift-text-worker.sock",
            "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "swift-experimental",
            "MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION": "melix-swift-text-worker/test",
            "MELIX_SWIFT_TEXT_WORKER_RUNTIME_CACHE_FINGERPRINT": "runtime-fingerprint-test",
            "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": "/tmp/melix-swift-text-worker-metrics.json",
            "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": "/tmp/melix-swift-text-worker-cache",
            "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT": "true",
            "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "65536",
            "MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES": "2048",
            "MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES": "4096",
            "MELIX_SWIFT_TEXT_WORKER_PREFILL_QUADRATIC_GUARD_TOKEN_THRESHOLD": "1024",
            "MELIX_SWIFT_TEXT_WORKER_INITIAL_CACHE_BLOCKS": "4",
            "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_PENDING_WINDOW_MS": "7",
            "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_COHORT_PENDING_WINDOW_MS": "50",
            "MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE": "true",
        ])

        XCTAssertEqual(configuration.workerID, "swift-text-worker-dev")
        XCTAssertEqual(configuration.socketPath, "/tmp/melix-swift-text-worker.sock")
        XCTAssertEqual(configuration.backendMode, "swift-experimental")
        XCTAssertEqual(configuration.runtimeVersion, "melix-swift-text-worker/test")
        XCTAssertEqual(configuration.runtimeCacheFingerprint, "runtime-fingerprint-test")
        XCTAssertEqual(configuration.metricsExportPath, "/tmp/melix-swift-text-worker-metrics.json")
        XCTAssertEqual(configuration.cacheRootPath, "/tmp/melix-swift-text-worker-cache")
        XCTAssertTrue(configuration.memoryEnforcementDisabled)
        XCTAssertEqual(configuration.processMemoryBudgetBytes, 65_536)
        XCTAssertEqual(configuration.modelLoadHeadroomBytes, 2_048)
        XCTAssertEqual(configuration.prefillMemoryHeadroomBytes, 4_096)
        XCTAssertEqual(configuration.prefillQuadraticGuardTokenThreshold, 1_024)
        XCTAssertEqual(configuration.initialCacheBlocks, 4)
        XCTAssertEqual(configuration.decodeBatchPendingWindowNanos, 7_000_000)
        XCTAssertEqual(configuration.decodeBatchCohortPendingWindowNanos, 50_000_000)
        XCTAssertTrue(configuration.turboQuantCandidateProbeEnabled)
    }

    func testConfigurationReadsVisionWorkerEnvironmentOverrides() {
        let configuration = WorkerConfiguration.fromEnvironment([
            "MELIX_SWIFT_WORKER_FAMILY": "vision",
            "MELIX_SWIFT_VISION_WORKER_ID": "swift-vision-worker-dev",
            "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH": "/tmp/melix-swift-vision-worker.sock",
            "MELIX_SWIFT_VISION_WORKER_BACKEND_MODE": "deterministic",
            "MELIX_SWIFT_VISION_WORKER_RUNTIME_VERSION": "melix-swift-vision-worker/test",
            "MELIX_SWIFT_VISION_WORKER_RUNTIME_CACHE_FINGERPRINT": "vision-runtime-fingerprint-test",
            "MELIX_SWIFT_VISION_WORKER_METRICS_PATH": "/tmp/melix-swift-vision-worker-metrics.json",
            "MELIX_SWIFT_VISION_WORKER_CACHE_ROOT": "/tmp/melix-swift-vision-worker-cache",
            "MELIX_SWIFT_VISION_PAYLOAD_RECEIPT_PATH": "/tmp/melix-swift-vision-payload.jsonl",
        ])

        XCTAssertEqual(configuration.workerFamily, .vision)
        XCTAssertEqual(configuration.workerID, "swift-vision-worker-dev")
        XCTAssertEqual(configuration.socketPath, "/tmp/melix-swift-vision-worker.sock")
        XCTAssertEqual(configuration.backendMode, "deterministic")
        XCTAssertEqual(configuration.runtimeVersion, "melix-swift-vision-worker/test")
        XCTAssertEqual(configuration.runtimeCacheFingerprint, "vision-runtime-fingerprint-test")
        XCTAssertEqual(configuration.metricsExportPath, "/tmp/melix-swift-vision-worker-metrics.json")
        XCTAssertEqual(configuration.cacheRootPath, "/tmp/melix-swift-vision-worker-cache")
        XCTAssertEqual(configuration.visionPayloadReceiptPath, "/tmp/melix-swift-vision-payload.jsonl")
    }

    func testConfigurationAllowsLongDecodeBatchCohortPendingWindowOverride() {
        let configuration = WorkerConfiguration.fromEnvironment([
            "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_COHORT_PENDING_WINDOW_MS": "2000",
        ])

        XCTAssertEqual(configuration.decodeBatchCohortPendingWindowNanos, 2_000_000_000)
    }

    func testConfigurationFallsBackToDefaultsForEmptyEnvironment() {
        let configuration = WorkerConfiguration.fromEnvironment([:])

        XCTAssertEqual(configuration, WorkerConfiguration())
    }

    func testConfigurationTreatsUnknownDisableFlagValuesAsFalse() {
        let configuration = WorkerConfiguration.fromEnvironment([
            "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT": "disabled",
        ])

        XCTAssertFalse(configuration.memoryEnforcementDisabled)
        XCTAssertTrue(configuration.memoryEnforcementEnabled)
    }

    func testDecodeOutputCadencePolicyScopesDefaultToGemmaAndHonorsOverrides() {
        var gemmaModel = Melix_Worker_V1_ModelSpec()
        gemmaModel.modelID = "unsloth/gemma-4-E4B-it-MLX-8bit"

        var execution = Melix_Worker_V1_ExecutionMetadata()
        XCTAssertEqual(
            decodeOutputCadencePolicy(model: gemmaModel, execution: execution),
            .gemmaDecodeDefault
        )

        execution.ext["melix.output_cadence"] = "off"
        XCTAssertEqual(
            decodeOutputCadencePolicy(model: gemmaModel, execution: execution),
            .immediate
        )

        var nonGemmaModel = Melix_Worker_V1_ModelSpec()
        nonGemmaModel.modelID = "melix-dev-text"
        execution.ext["melix.output_cadence"] = "coalesced"
        XCTAssertEqual(
            decodeOutputCadencePolicy(model: nonGemmaModel, execution: execution),
            .gemmaDecodeDefault
        )
    }

    func testDecodeOutputCadencePolicyAllowsFragmentOnlyFlushLimit() {
        let policy = FilteredTextOutputCadencePolicy(
            coalesceVisibleDeltas: true,
            maxBufferedVisibleFragments: 4,
            maxBufferedVisibleCharacters: 0
        )

        XCTAssertTrue(policy.shouldBufferVisibleDeltas)
        XCTAssertFalse(policy.shouldFlush(fragmentCount: 1, characterCount: 1))
        XCTAssertTrue(policy.shouldFlush(fragmentCount: 4, characterCount: 4))
    }

    func testDFlashSpeculativeProbeLoggerWritesJsonLinesWhenEnabled() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-dflash-probe-\(UUID().uuidString)", isDirectory: true)
        let fileURL = directory.appendingPathComponent("probe.jsonl")
        defer {
            try? FileManager.default.removeItem(at: directory)
        }

        XCTAssertFalse(DFlashSpeculativeProbeLogger.shouldEnable(environment: [:]))
        XCTAssertEqual(
            DFlashSpeculativeProbeLogger.resolvedProbeURL(environment: [
                "MELIX_RUNTIME_DIR": directory.path,
            ])?.lastPathComponent,
            DFlashSpeculativeProbeLogger.defaultFilename
        )

        let logger = try DFlashSpeculativeProbeLogger(
            fileURL: fileURL,
            sessionID: "test-session",
            startedAt: Date()
        )
        logger.record(
            stage: "draft_request",
            fields: [
                "round": 1,
                "uses_dflash_mlx": false,
                "draft_block_token_ids": [7, 0],
            ]
        )

        let lines = try String(contentsOf: fileURL, encoding: .utf8)
            .split(separator: "\n")
        XCTAssertEqual(lines.count, 1)

        let payload = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(lines[0].utf8)) as? [String: Any]
        )
        XCTAssertEqual(payload["schema_version"] as? Int, 1)
        XCTAssertEqual(payload["session_id"] as? String, "test-session")
        XCTAssertEqual(payload["stage"] as? String, "draft_request")
        XCTAssertEqual(payload["round"] as? Int, 1)
        XCTAssertEqual(payload["uses_dflash_mlx"] as? Bool, false)
        XCTAssertEqual(payload["draft_block_token_ids"] as? [Int], [7, 0])
    }

    func testAbortRegistryTracksRequestLifecycle() {
        let abortRegistry = AbortRegistry()

        abortRegistry.register("req-1")
        XCTAssertTrue(abortRegistry.abort("req-1"))
        XCTAssertFalse(abortRegistry.abort("req-1"))

        abortRegistry.register("req-2")
        abortRegistry.remove("req-2")
        XCTAssertFalse(abortRegistry.abort("req-2"))
    }

    func testAbortRegistryExposesHandleStateBeforeAndAfterAbort() {
        let abortRegistry = AbortRegistry()
        let handle = abortRegistry.register("req-handle")

        XCTAssertFalse(handle.isAborted)
        XCTAssertNotNil(abortRegistry.handle(for: "req-handle"))
        XCTAssertTrue(abortRegistry.abort("req-handle"))
        XCTAssertTrue(handle.isAborted)
        XCTAssertNil(abortRegistry.handle(for: "req-handle"))
    }

    func testMetricsStoreTracksCountersAndTimings() {
        let metrics = MetricsStore()
        metrics.increment("swift_text.unimplemented_rpc_count")
        metrics.increment("swift_text.custom_counter", by: 3)
        metrics.recordMilliseconds("swift_text.runtime_stats_ms", value: 12)

        let counters = metrics.counters
        XCTAssertEqual(counters["swift_text.spawn_to_bootstrap_ms"], 0)
        XCTAssertEqual(counters["swift_text.bootstrap_ms"], 0)
        XCTAssertEqual(counters["swift_text.unimplemented_rpc_count"], 1)
        XCTAssertEqual(counters["swift_text.custom_counter"], 3)
        XCTAssertEqual(counters["swift_text.runtime_stats_ms"], 12)
        XCTAssertEqual(counters["swift_text.worker_prefill_requested_step_tokens"], 0)
        XCTAssertEqual(counters["swift_text.worker_prefill_effective_window_tokens"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_backend_code"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_kernel_path_code"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_runtime_route_code"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_runtime_block_reason_code"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_model_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_model_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_token_eval_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_token_eval_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_model_eval_sync_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_model_eval_sync_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_model_eval_sync_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_sample_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_sample_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_sample_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_token_id_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_token_id_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_token_id_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_detokenize_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_detokenize_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_detokenize_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_stream_yield_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_stream_yield_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_stream_yield_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_summary_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_summary_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_summary_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_turboquant_candidate_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_turboquant_candidate_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_turboquant_candidate_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_loop_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_decode_quantize_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_fused_attention_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_fused_attention_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_fused_attention_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_fused_attention_route_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_fused_attention_route_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_cache_update_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_cache_update_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_cache_materialize_total_us"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_cache_materialize_call_count"], 0)
        XCTAssertEqual(counters["swift_text.active_kv_estimated_memory_savings_pct"], 0)
        XCTAssertEqual(counters["swift_text.decode_batch_token_eval_total_us"], 0)
        XCTAssertEqual(counters["swift_text.decode_batch_token_eval_call_count"], 0)
        XCTAssertEqual(counters["swift_text.decode_batch_token_eval_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.decode_harmony_filter_total_us"], 0)
        XCTAssertEqual(counters["swift_text.decode_harmony_filter_call_count"], 0)
        XCTAssertEqual(counters["swift_text.decode_harmony_filter_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.decode_grpc_write_total_us"], 0)
        XCTAssertEqual(counters["swift_text.decode_grpc_write_call_count"], 0)
        XCTAssertEqual(counters["swift_text.decode_grpc_write_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.generate_harmony_filter_total_us"], 0)
        XCTAssertEqual(counters["swift_text.generate_harmony_filter_call_count"], 0)
        XCTAssertEqual(counters["swift_text.generate_harmony_filter_avg_us"], 0)
        XCTAssertEqual(counters["swift_text.generate_grpc_write_total_us"], 0)
        XCTAssertEqual(counters["swift_text.generate_grpc_write_call_count"], 0)
        XCTAssertEqual(counters["swift_text.generate_grpc_write_avg_us"], 0)
    }

    func testWorkerServicesPublishMemoryEnforcementAndInitialCacheMetrics() {
        let services = makeServices(environment: [
            "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT": "1",
            "MELIX_SWIFT_TEXT_WORKER_INITIAL_CACHE_BLOCKS": "4",
        ])

        XCTAssertEqual(services.metrics.counters["swift_text.memory_enforcement_disabled"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.cache_initial_block_target"], 4)
    }

    func testMetricsStoreExportsCountersWhenConfigured() throws {
        let exportURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        let metrics = MetricsStore(exportPath: exportURL.path)
        metrics.set("swift_text.decode_ttft_ms", value: 24)

        let data = try Data(contentsOf: exportURL)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let values = try XCTUnwrap(payload["values"] as? [String: Int])

        XCTAssertEqual(values["swift_text.decode_ttft_ms"], 24)
    }

    func testCacheRestoreMetadataNormalizesLegacyBlockTables() throws {
        var cacheKey = Melix_Worker_V1_CacheKey()
        cacheKey.scopeID = "scope-worker"

        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "blk-0"
        block.tokenStart = 0
        block.tokenEnd = 16
        block.bytes = 1024

        var table = Melix_Worker_V1_BlockTable()
        table.blocks = [block]
        table.cacheKey = cacheKey

        let normalized = normalizedBlockTable(table)
        let decoded = try Melix_Worker_V1_BlockTable(serializedBytes: normalized.serializedData())

        XCTAssertEqual(decoded.scopeID, "scope-worker")
        XCTAssertEqual(decoded.totalTokenCount, 16)
        XCTAssertEqual(decoded.pages.count, 1)
        XCTAssertEqual(decoded.pages.first?.pageID, "page-blk-0")
        XCTAssertEqual(decoded.pages.first?.blockIds, ["blk-0"])
    }

    func testCacheRestoreMetadataBuildsStructuredRestorePlans() throws {
        var cacheKey = Melix_Worker_V1_CacheKey()
        cacheKey.scopeID = "scope-worker"

        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "blk-0"
        block.tokenStart = 0
        block.tokenEnd = 16
        block.bytes = 1024

        var table = Melix_Worker_V1_BlockTable()
        table.blocks = [block]
        table.cacheKey = cacheKey
        table = normalizedBlockTable(table)

        var snapshot = Melix_Worker_V1_SnapshotRef()
        snapshot.snapshotID = "snap-1"
        snapshot.requestID = "req-1"
        snapshot.sessionID = "session-1"
        snapshot.branchID = "branch-main"
        snapshot.tokenBoundary = 16

        let boundary = makeRestoreBoundaryRef(snapshot: snapshot, blockTable: table)
        let plan = makeCacheRestorePlan(
            snapshot: snapshot,
            blockTableID: "bt-1",
            blockTable: table,
            tier: "l2",
            cacheMode: .rotating,
            partial: false
        )
        let decoded = try Melix_Worker_V1_CacheRestorePlan(serializedBytes: plan.serializedData())

        XCTAssertEqual(boundary.snapshot.snapshotID, "snap-1")
        XCTAssertEqual(boundary.scopeID, "scope-worker")
        XCTAssertEqual(decoded.planID, "restore-bt-1")
        XCTAssertEqual(decoded.boundary.snapshot.snapshotID, "snap-1")
        XCTAssertEqual(decoded.blockTableID, "bt-1")
        XCTAssertEqual(decoded.pages.count, 1)
        XCTAssertEqual(decoded.restoredTokenCount, 16)
        XCTAssertEqual(decoded.tier, "l2")
        XCTAssertEqual(decoded.cacheMode, .rotating)
    }

    func testCacheRestoreMetadataWalkBackReturnsFullPlanForEmptyRequestMessages() throws {
        let cacheKey = makeCacheKey(
            scopeID: "scope-worker",
            prefixSeed: "prefix-empty-request",
            fingerprintSeed: "fingerprint-empty-request"
        )
        let snapshot = makeSnapshotRef(snapshotID: "snap-empty-request")
        let blockTable = normalizedBlockTable(
            makeBlockTable(
                scopeID: "scope-worker",
                cacheKey: cacheKey,
                blockIDs: ["blk-0", "blk-1"],
                bytes: [512, 512]
            )
        )

        let plan = try XCTUnwrap(
            makeWalkedBackCacheRestorePlan(
                snapshot: snapshot,
                blockTableID: "bt-empty-request",
                blockTable: blockTable,
                cachedMessages: [makeUserMessage("alpha beta gamma delta")],
                requestMessages: [],
                tier: "l2",
                cacheMode: .hybrid
            )
        )

        XCTAssertFalse(plan.partial)
        XCTAssertEqual(plan.blockTableID, "bt-empty-request")
        XCTAssertEqual(plan.restoredTokenCount, blockTable.totalTokenCount)
        XCTAssertEqual(plan.cacheMode, .hybrid)
    }

    func testCacheRestoreMetadataWalkBackReturnsFullPlanForFullySharedMessages() throws {
        let cacheKey = makeCacheKey(
            scopeID: "scope-worker",
            prefixSeed: "prefix-full-shared",
            fingerprintSeed: "fingerprint-full-shared"
        )
        let snapshot = makeSnapshotRef(snapshotID: "snap-full-shared")

        var block = Melix_Worker_V1_BlockRef()
        block.blockID = "blk-full-shared"
        block.tokenStart = 0
        block.tokenEnd = 4
        block.bytes = 256

        var page = Melix_Worker_V1_PageRef()
        page.pageID = "page-full-shared"
        page.blockIds = ["blk-full-shared"]
        page.tokenStart = 0
        page.tokenEnd = 4
        page.bytes = 256

        var blockTable = Melix_Worker_V1_BlockTable()
        blockTable.scopeID = "scope-worker"
        blockTable.cacheKey = cacheKey
        blockTable.blocks = [block]
        blockTable.pages = [page]
        blockTable.totalTokenCount = 4

        let sharedMessage = makeUserMessage("alpha beta gamma delta")
        let plan = try XCTUnwrap(
            makeWalkedBackCacheRestorePlan(
                snapshot: snapshot,
                blockTableID: "bt-full-shared",
                blockTable: blockTable,
                cachedMessages: [sharedMessage],
                requestMessages: [sharedMessage],
                tier: "l2",
                cacheMode: .rotating
            )
        )

        XCTAssertFalse(plan.partial)
        XCTAssertEqual(plan.blockTableID, "bt-full-shared")
        XCTAssertEqual(plan.restoredTokenCount, 4)
        XCTAssertEqual(plan.cacheMode, .rotating)
    }

    func testCacheRestoreMetadataWalkBackAccountsForMediaPrefixesAndIgnoresNilParts() throws {
        let cacheKey = makeCacheKey(
            scopeID: "scope-worker",
            prefixSeed: "prefix-media",
            fingerprintSeed: "fingerprint-media"
        )
        let snapshot = makeSnapshotRef(snapshotID: "snap-media")

        var firstBlock = Melix_Worker_V1_BlockRef()
        firstBlock.blockID = "blk-media-a"
        firstBlock.tokenStart = 0
        firstBlock.tokenEnd = 256
        firstBlock.bytes = 256

        var secondBlock = Melix_Worker_V1_BlockRef()
        secondBlock.blockID = "blk-media-b"
        secondBlock.tokenStart = 256
        secondBlock.tokenEnd = 256
        secondBlock.bytes = 256

        var thirdBlock = Melix_Worker_V1_BlockRef()
        thirdBlock.blockID = "blk-media-c"
        thirdBlock.tokenStart = 256
        thirdBlock.tokenEnd = 1024
        thirdBlock.bytes = 768

        var fullBlock = Melix_Worker_V1_BlockRef()
        fullBlock.blockID = "blk-media-full"
        fullBlock.tokenStart = 1024
        fullBlock.tokenEnd = 2048
        fullBlock.bytes = 1024

        var firstPage = Melix_Worker_V1_PageRef()
        firstPage.pageID = "page-z"
        firstPage.blockIds = ["blk-media-a"]
        firstPage.tokenStart = 0
        firstPage.tokenEnd = 256
        firstPage.bytes = 256

        var secondPage = Melix_Worker_V1_PageRef()
        secondPage.pageID = "page-a"
        secondPage.blockIds = ["blk-media-b"]
        secondPage.tokenStart = 256
        secondPage.tokenEnd = 256
        secondPage.bytes = 256

        var thirdPage = Melix_Worker_V1_PageRef()
        thirdPage.pageID = "page-c"
        thirdPage.blockIds = ["blk-media-c"]
        thirdPage.tokenStart = 256
        thirdPage.tokenEnd = 1024
        thirdPage.bytes = 768

        var fullPage = Melix_Worker_V1_PageRef()
        fullPage.pageID = "page-full"
        fullPage.blockIds = ["blk-media-full"]
        fullPage.tokenStart = 1024
        fullPage.tokenEnd = 2048
        fullPage.bytes = 1024

        var blockTable = Melix_Worker_V1_BlockTable()
        blockTable.scopeID = "scope-worker"
        blockTable.cacheKey = cacheKey
        blockTable.blocks = [firstBlock, secondBlock, thirdBlock, fullBlock]
        blockTable.pages = [firstPage, secondPage, thirdPage, fullPage]
        blockTable.totalTokenCount = 2048

        let cachedMessage = makeMediaRichMessage()
        let requestMessage = makeMediaRichMessage()
        let plan = try XCTUnwrap(
            makeWalkedBackCacheRestorePlan(
                snapshot: snapshot,
                blockTableID: "bt-media",
                blockTable: blockTable,
                cachedMessages: [cachedMessage],
                requestMessages: [requestMessage],
                tier: "l2"
            )
        )

        XCTAssertTrue(plan.partial)
        XCTAssertEqual(plan.restoredTokenCount, 1024)
        XCTAssertEqual(plan.blockTable.totalTokenCount, 1024)
        XCTAssertEqual(plan.boundary.boundaryKind, "partial_prefix_walk_back")
        XCTAssertEqual(plan.pages.count, 3)
    }

    func testCacheRestoreMetadataWalkBackRejectsUnsafeBoundaries() {
        let cacheKey = makeCacheKey(
            scopeID: "scope-worker",
            prefixSeed: "prefix-unsafe",
            fingerprintSeed: "fingerprint-unsafe"
        )
        let snapshot = makeSnapshotRef(snapshotID: "snap-unsafe")

        let unsafeTable = normalizedBlockTable(
            makeBlockTable(
                scopeID: "scope-worker",
                cacheKey: cacheKey,
                blockIDs: ["blk-0", "blk-1"],
                bytes: [256, 256]
            )
        )
        let unsafePlan = makeWalkedBackCacheRestorePlan(
            snapshot: snapshot,
            blockTableID: "bt-unsafe",
            blockTable: unsafeTable,
            cachedMessages: [makeUserMessage("alpha beta gamma delta epsilon zeta eta theta")],
            requestMessages: [makeUserMessage("alpha beta diverged now")],
            tier: "l2"
        )

        XCTAssertNil(unsafePlan)
    }

    func testCacheRestoreMetadataBuildsBoundarySafePrefillChunkBoundaries() {
        let prompt = (1...24).map { "token\($0)" }.joined(separator: " ")
        let messages = [makeUserMessage(prompt)]

        XCTAssertEqual(
            makeBoundarySafePrefillChunkBoundaries(
                messages: messages,
                chunkTokenTarget: 16
            ),
            [16, 24]
        )
        XCTAssertEqual(
            makeBoundarySafePrefillChunkBoundaries(
                messages: messages,
                chunkTokenTarget: 16,
                restoredTokenCount: 16
            ),
            [24]
        )
    }

    func testRestoreBoundarySnapshotRequestResolvesStructuredBoundaryFallback() {
        var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
        request.restoreBoundary.snapshot.snapshotID = "snap-boundary"

        XCTAssertEqual(
            resolvedRestoreSnapshotID(from: request),
            "snap-boundary"
        )
    }

    func testHandshakeReturnsExpectedRuntimeMetadata() async throws {
        let services = makeServices()
        var request = Melix_Worker_V1_HandshakeRequest()
        request.protocolVersion = "melix.worker.v1"

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.handshake(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.Handshake.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(response.protocolVersion, "melix.worker.v1")
        XCTAssertEqual(response.runtimeVersion, "melix-swift-text-worker/dev")
        XCTAssertEqual(response.workerFamily, .text)
        XCTAssertEqual(response.workerInstanceID, "swift-text-worker-001")
        XCTAssertTrue(response.capabilities.cache.supportsPrefixCache)
        XCTAssertEqual(response.capabilities.cache.kvQuantProfiles, ["turboquant-q4", "q4", "q8"])
        XCTAssertEqual(
            response.capabilities.cache.supportedModes,
            [.tiered, .rotating, .hybrid]
        )
        XCTAssertEqual(
            response.capabilities.cache.experimentalModes,
            [.rotating, .hybrid]
        )
        XCTAssertTrue(response.capabilities.execution.supportsContinuousBatching)
        XCTAssertTrue(response.capabilities.execution.supportsSpeculativeDecoding)
        XCTAssertEqual(
            response.capabilities.ext.map { $0.name },
            ["engine_family", "accelerated_prefill", "sparse_prefill", "active_kv_quantized"]
        )
        XCTAssertEqual(response.capabilities.ext.last?.metadata["profiles"], "turboquant-q4,q4,q8")
    }

    func testVisionHandshakeReturnsVisionWorkerFamilyMetadata() async throws {
        let services = makeServices(environment: [
            "MELIX_SWIFT_WORKER_FAMILY": "vision",
            "MELIX_SWIFT_VISION_WORKER_ID": "swift-vision-worker-dev",
        ])
        var request = Melix_Worker_V1_HandshakeRequest()
        request.protocolVersion = "melix.worker.v1"

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.handshake(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.Handshake.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(response.workerFamily, .vision)
        XCTAssertEqual(response.workerInstanceID, "swift-vision-worker-dev")
        XCTAssertEqual(response.runtimeVersion, "melix-swift-vision-worker/dev")
    }

    func testCacheModePolicyResolvesPolicyStringsAndMapsMetrics() {
        var hints = Melix_Worker_V1_CacheHints()
        XCTAssertEqual(CacheModePolicy.resolve(from: hints), .tiered)

        hints.cachePolicy = " rotating-long-context "
        XCTAssertEqual(CacheModePolicy.resolve(from: hints), .rotating)

        hints.cachePolicy = "hybrid-prefill"
        XCTAssertEqual(CacheModePolicy.resolve(from: hints), .hybrid)

        hints.cacheMode = .hybrid
        hints.cachePolicy = "rotating"
        XCTAssertEqual(CacheModePolicy.resolve(from: hints), .hybrid)

        XCTAssertEqual(CacheModePolicy.metricValue(for: .tiered), 1)
        XCTAssertEqual(CacheModePolicy.metricValue(for: .rotating), 2)
        XCTAssertEqual(CacheModePolicy.metricValue(for: .hybrid), 3)
        XCTAssertEqual(CacheModePolicy.metricValue(for: .unspecified), 0)
        XCTAssertEqual(CacheModePolicy.metricValue(for: .UNRECOGNIZED(99)), 0)
    }

    func testRuntimeStatsAndModelListReflectEmptyWorkerState() async throws {
        let services = makeServices()

        let stats = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let models = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.listLoadedModels(
                request: Melix_Worker_V1_ListLoadedModelsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.ListLoadedModels.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(stats.stats.workerState, "idle")
        XCTAssertEqual(stats.stats.activeRequests, 0)
        XCTAssertEqual(stats.stats.residentBytes, 0)
        XCTAssertEqual(stats.stats.modelResidentBytes, 0)
        XCTAssertEqual(stats.stats.cacheResidentBytes, 0)
        XCTAssertEqual(stats.stats.kvCacheBytes, 0)
        XCTAssertEqual(stats.stats.peakAllocationBytes, 0)
        XCTAssertEqual(stats.stats.memoryHeadroomBytes, 0)
        XCTAssertTrue(models.modelHandles.isEmpty)
    }

    func testServicesExposeExpectedRegistrableRpcServices() {
        let services = makeServices()

        XCTAssertEqual(services.registrableServices.count, 4)
    }

    func testDevelopmentModelCatalogResolvesEnvironmentOverride() {
        let catalog = WorkerModelCatalog(environment: [
            "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
        ])

        let model = catalog.get("melix-dev-text")

        XCTAssertEqual(model?.modelID, "melix-dev-text")
        XCTAssertEqual(model?.modelPath, "mlx-community/melix-dev-text-4bit")
        XCTAssertEqual(model?.quantProfileID, "q4")
    }

    func testAutoSwiftMLXBackendUsesInjectedLoader() async throws {
        let backend = AutoSwiftMLXBackend(runtimeName: "fake-mlx-loader") { modelSource in
            ["model_source": modelSource]
        }
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        spec.modelPath = "mlx-community/melix-dev-text-4bit"

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual(backend.runtimeName, "fake-mlx-loader")
        XCTAssertEqual((loaded.storage as? [String: String])?["model_source"], "mlx-community/melix-dev-text-4bit")
    }

    func testAutoSwiftMLXBackendDefaultsToMLXRuntimeNameAndUsesModelIDFallback() async throws {
        let backend = AutoSwiftMLXBackend { modelSource in
            ["model_source": modelSource]
        }
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual(backend.runtimeName, "mlx-swift-lm")
        XCTAssertEqual((loaded.storage as? [String: String])?["model_source"], "melix-dev-text")
    }

    func testAutoSwiftMLXBackendUsesDirectoryLoaderForExistingPath() async throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let backend = AutoSwiftMLXBackend(
            directoryLoader: { directoryURL in
                LoadedTextModel(storage: ["directory": directoryURL.path], residentBytesHint: 1)
            },
            identifierLoader: { _, _ in
                XCTFail("identifier loader should not be used for an existing directory path")
                return LoadedTextModel(storage: [:], residentBytesHint: 0)
            }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        spec.modelPath = tempDirectory.path

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual((loaded.storage as? [String: String])?["directory"], tempDirectory.path)
    }

    func testAutoSwiftMLXBackendLoadsDFlashDraftDirectoryWithNativeRuntime() async throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }
        let configURL = tempDirectory.appendingPathComponent("config.json")
        try """
        {
          "model_type": "qwen3",
          "architectures": ["DFlashDraftModel"],
          "auto_map": {"AutoModel": "dflash.DFlashDraftModel"}
        }
        """.write(to: configURL, atomically: true, encoding: .utf8)

        let backend = AutoSwiftMLXBackend(
            directoryLoader: { _ in
                XCTFail("DFlash draft checkpoints must not enter the normal MLX directory loader")
                return LoadedTextModel(storage: [:], residentBytesHint: 0)
            },
            identifierLoader: { _, _ in
                XCTFail("identifier loader should not be used for an existing DFlash directory")
                return LoadedTextModel(storage: [:], residentBytesHint: 0)
            }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "z-lab/Qwen3.5-27B-DFlash"
        spec.modelPath = tempDirectory.path

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertTrue(loaded.storage is SwiftDFlashDraftRuntime)
    }

    func testAutoSwiftMLXBackendDoesNotRejectLocalNonDFlashDirectoryByNameOnly() async throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("not-dflash-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }
        try #"{"model_type":"qwen3","architectures":["Qwen3ForCausalLM"]}"#
            .write(
                to: tempDirectory.appendingPathComponent("config.json"),
                atomically: true,
                encoding: .utf8
            )

        let backend = AutoSwiftMLXBackend(
            directoryLoader: { directoryURL in
                LoadedTextModel(storage: ["directory": directoryURL.path], residentBytesHint: 1)
            },
            identifierLoader: { _, _ in
                XCTFail("identifier loader should not be used for an existing local directory")
                return LoadedTextModel(storage: [:], residentBytesHint: 0)
            }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "local-qwen"
        spec.modelPath = tempDirectory.path

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual((loaded.storage as? [String: String])?["directory"], tempDirectory.path)
    }

    func testAutoSwiftMLXBackendUsesIdentifierLoaderForRemoteModelSources() async throws {
        let backend = AutoSwiftMLXBackend(
            directoryLoader: { _ in
                XCTFail("directory loader should not be used for remote model identifiers")
                return LoadedTextModel(storage: [:], residentBytesHint: 0)
            },
            identifierLoader: { modelSource, revision in
                LoadedTextModel(
                    storage: ["model_source": modelSource, "revision": revision],
                    residentBytesHint: 2
                )
            }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        spec.modelPath = "mlx-community/melix-dev-text-4bit"
        spec.revision = "dev-branch"

        let loaded = try await backend.loadModel(spec: spec)

        XCTAssertEqual((loaded.storage as? [String: String])?["model_source"], "mlx-community/melix-dev-text-4bit")
        XCTAssertEqual((loaded.storage as? [String: String])?["revision"], "dev-branch")
    }

    func testAutoSwiftMLXBackendGenerateEventsUsesPreparedGenerationFactory() async throws {
        let backend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 4,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.yield(.chunk("Hello"))
                        continuation.yield(.chunk(" world"))
                        continuation.yield(.summary(
                            TextGenerationSummary(
                                promptTokens: 4,
                                completionTokens: 2,
                                tokensPerSecond: 42
                            )
                        ))
                        continuation.finish()
                    }
                )
            }
        )

        let stream = try await backend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("hello")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: stream)

        XCTAssertEqual(events.count, 4)
        XCTAssertEqual(renderedPromptTokens(from: events), 4)
        XCTAssertEqual(renderedTokenChunks(from: events), ["Hello", " world"])
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 2)
    }

    func testAutoSwiftMLXBackendGenerateEventsFallsBackToObservedCompletionCount() async throws {
        let backend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 2,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.yield(.chunk("A"))
                        continuation.yield(.chunk("B"))
                        continuation.finish()
                    }
                )
            }
        )

        let stream = try await backend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("fallback")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: stream)

        XCTAssertEqual(renderedSummary(from: events)?.promptTokens, 2)
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 2)
    }

    func testAutoSwiftMLXBackendGenerateEventsStopsOnAbortSkipsEmptyChunksAndSurfacesThrownErrors() async throws {
        let abortingBackend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 3,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.yield(.chunk(""))
                        continuation.yield(.chunk("ignored"))
                        continuation.finish()
                    }
                )
            }
        )

        let abortedStream = try await abortingBackend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("abort")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { true }
        )
        let abortedEvents = try await collectTextGenerationEvents(from: abortedStream)
        XCTAssertEqual(abortedEvents.count, 2)
        XCTAssertEqual(renderedPromptTokens(from: abortedEvents), 3)
        XCTAssertEqual(renderedSummary(from: abortedEvents)?.completionTokens, 0)

        enum ExpectedFailure: Error {
            case boom
        }

        let throwingBackend = AutoSwiftMLXBackend(
            preparedGenerationFactory: { _, _, _ in
                PreparedTextGeneration(
                    promptTokens: 1,
                    runtimeEvents: AsyncThrowingStream { continuation in
                        continuation.finish(throwing: ExpectedFailure.boom)
                    }
                )
            }
        )

        let failingStream = try await throwingBackend.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("throw")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )

        do {
            _ = try await collectTextGenerationEvents(from: failingStream)
            XCTFail("expected runtime stream failure")
        } catch {
            XCTAssertTrue(error is ExpectedFailure)
        }
    }

    func testAutoSwiftMLXBackendDecodeRejectsUnsupportedSpeculativeModeWithoutFallback() async {
        let backend = AutoSwiftMLXBackend()
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .speculativeDecode
        acceleration.allowBaselineFallback = false

        await XCTAssertThrowsErrorAsync(
            try await backend.decodeEvents(
                model: LoadedTextModel(storage: ["kind": "fake"]),
                context: TextPrefillContext(storage: [:], promptTokens: 1),
                sampling: Melix_Worker_V1_SamplingConfig(),
                maxOutputTokens: 2,
                decodeStepSize: 1,
                prefillToken: "",
                acceleration: acceleration,
                shouldAbort: { false }
            )
        )
    }

    func testAutoSwiftMLXBackendDefaultPreparedGenerationFactoryRejectsNonMLXContainers() async {
        let backend = AutoSwiftMLXBackend()

        await XCTAssertThrowsErrorAsync(
            try await backend.generateEvents(
                model: LoadedTextModel(storage: ["kind": "not-a-container"]),
                messages: [makeUserMessage("default factory")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
    }

    #if canImport(MLX) && canImport(MLXLMCommon) && canImport(MLXLLM) && canImport(Tokenizers)
    func testAutoSwiftMLXBackendReportsHomogeneousBatchDecodeSupport() {
        XCTAssertTrue(AutoSwiftMLXBackend().supportsHomogeneousBatchDecode)
    }

    func testAutoSwiftMLXBackendDefaultPreparedGenerationFactoryUsesLiveModelContainerBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let stream = try await backend.generateEvents(
                    model: LoadedTextModel(
                        storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge live path")],
                    sampling: sampling,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        XCTAssertEqual(renderedPromptTokens(from: events), promptTokens.count)
        XCTAssertFalse(renderedTokenChunks(from: events).joined().isEmpty)

        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.promptTokens, promptTokens.count)
        XCTAssertGreaterThan(summary.completionTokens, 0)
        XCTAssertNotNil(summary.tokensPerSecond)
    }

    func testVendoredChatSessionClearUsesAsyncSerialAccess() async throws {
        try await withTemporaryDefaultMetallib {
            await Device.withDefaultDevice(.cpu) {
                let session = ChatSession(
                    makeLiveSwiftMLXModelContainer(promptTokens: [1, 2, 3]),
                    instructions: "system"
                )

                await session.clear()
            }
        }
    }

    @available(*, deprecated, message: "Exercises the deprecated ModelContainer chat-template compatibility shim.")
    func testVendoredModelContainerConvenienceMethodsUseSerialRead() async throws {
        try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let container = makeLiveSwiftMLXModelContainer(promptTokens: [4, 5, 6])

                let prepared = try await container.prepare(input: UserInput(prompt: "hello"))
                let decoded = await container.decode(tokens: [1, 2])
                let encoded = await container.encode("tok3 tok4")
                let templated = try await container.applyChatTemplate(messages: [
                    ["role": "user", "content": "hello"]
                ])

                XCTAssertEqual(prepared.text.tokens.size, 3)
                XCTAssertEqual(decoded, "tok1 tok2")
                XCTAssertEqual(encoded, [3, 4])
                XCTAssertEqual(templated, [1, 2])
            }
        }
    }

    func testVendoredModelContainerSerialAccessCompactsQueuedWaiters() async throws {
        try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let container = makeLiveSwiftMLXModelContainer(promptTokens: [1, 2, 3])
                let gate = WorkerScaffoldAsyncGate()

                let holder = Task {
                    await container.perform { _ in
                        await gate.enterAndWait()
                        return ()
                    }
                }
                await gate.waitUntilEntered()

                let waiters = (0 ..< 40).map { _ in
                    Task {
                        await container.decode(tokens: [1])
                    }
                }

                try await Task.sleep(nanoseconds: 50_000_000)
                await gate.open()
                await holder.value

                for waiter in waiters {
                    let decoded = await waiter.value
                    XCTAssertEqual(decoded, "tok1")
                }
            }
        }
    }

    func testAutoSwiftMLXBackendPrefillUsesLiveModelContainerBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]

        let result = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                try await backend.prefill(
                    model: LoadedTextModel(
                        storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge prefill live path")],
                    prefillStepSize: 32,
                    resumeHint: "live-prefill",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
            }
        }

        XCTAssertEqual(result.promptTokens, promptTokens.count)
        XCTAssertEqual(result.context.promptTokens, promptTokens.count)
        XCTAssertEqual(result.requestedPrefillStepTokens, 32)
        XCTAssertEqual(result.effectivePrefillWindowTokens, 32)
    }

    func testAutoSwiftMLXBackendPrefillAppliesAcceleratedPrefillPolicyForLiveBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .acceleratedPrefill
        acceleration.prefillHint = "json-schema"

        let result = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                try await backend.prefill(
                    model: LoadedTextModel(
                        storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("{\"kind\":\"object\"}")],
                    prefillStepSize: 4,
                    resumeHint: "live-accelerated-prefill",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
            }
        }

        XCTAssertEqual(result.appliedAcceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(result.appliedAcceleration.prefillHint, "json-schema")
        XCTAssertEqual(result.requestedPrefillStepTokens, 4)
        XCTAssertGreaterThan(result.effectivePrefillWindowTokens, result.requestedPrefillStepTokens)
        XCTAssertGreaterThan(result.acceleratedPrefillGainPct, 0)
        XCTAssertEqual(result.activeKVQuantizationRatio, 0)
    }

    func testAutoSwiftMLXBackendPrefillNormalizesActiveKVProfileForLiveBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized

        let result = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                try await backend.prefill(
                    model: LoadedTextModel(
                        storage: makeQuantizableLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                    ),
                    messages: [makeSystemMessage("system"), makeUserMessage("quantized live prefill")],
                    prefillStepSize: 4,
                    resumeHint: "live-active-kv",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
            }
        }

        XCTAssertEqual(result.appliedAcceleration.mode, .activeKvQuantized)
        XCTAssertEqual(result.appliedAcceleration.activeKvQuantProfile, "turboquant-q4")
        XCTAssertEqual(result.activeKVQuantizationRatio, 25)
    }

    func testAutoSwiftMLXBackendDecodeUsesLiveModelContainerBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge decode live path")],
                    prefillStepSize: 32,
                    resumeHint: "live-decode",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: model,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        XCTAssertFalse(renderedTokenChunks(from: events).joined().isEmpty)
        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.promptTokens, promptTokens.count)
        XCTAssertGreaterThan(summary.completionTokens, 0)
        XCTAssertNotNil(summary.tokensPerSecond)
    }

    func testAutoSwiftMLXBackendBatchesLiveHomogeneousDecodeRequests() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill1 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("batch decode live path")],
                    prefillStepSize: 32,
                    resumeHint: "live-batch-decode-1",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let prefill2 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("batch decode live path")],
                    prefillStepSize: 32,
                    resumeHint: "live-batch-decode-2",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeBatchEvents(
                    requests: [
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill1.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: acceleration,
                            shouldAbort: { false }
                        ),
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill2.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: acceleration,
                            shouldAbort: { false }
                        ),
                    ]
                )
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries.count, 2)
        XCTAssertEqual(summaries[0]?.promptTokens, promptTokens.count)
        XCTAssertEqual(summaries[1]?.promptTokens, promptTokens.count)
        XCTAssertEqual(summaries[0]?.completionTokens, 2)
        XCTAssertEqual(summaries[1]?.completionTokens, 2)
        XCTAssertEqual(summaries[0]?.decodeBatchSize, 2)
        XCTAssertEqual(summaries[1]?.modelEvalBatchSize, 2)
        XCTAssertTrue(events.contains { event in
            guard case .batchSummary(let summary) = event else {
                return false
            }
            return summary.decodeBatchSize == 2
                && summary.modelEvalBatchSize == 2
                && summary.outputTokenCount == 4
        })
    }

    func testAutoSwiftMLXBackendReusesBatchCacheAcrossHomogeneousDecodeSteps() async throws {
        let backend = AutoSwiftMLXBackend()
        let recorder = BatchCacheIdentityRecorder()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 3

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeBatchCacheIdentityModelContainer(recorder: recorder)
                )
                let prefill1 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("batch cache reuse")],
                    prefillStepSize: 32,
                    resumeHint: "batch-cache-reuse-1",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let prefill2 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("batch cache reuse")],
                    prefillStepSize: 32,
                    resumeHint: "batch-cache-reuse-2",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeBatchEvents(
                    requests: [
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill1.context,
                            sampling: sampling,
                            maxOutputTokens: 3,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: acceleration,
                            shouldAbort: { false }
                        ),
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill2.context,
                            sampling: sampling,
                            maxOutputTokens: 3,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: acceleration,
                            shouldAbort: { false }
                        ),
                    ]
                )
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries[0]?.completionTokens, 3)
        XCTAssertEqual(summaries[1]?.completionTokens, 3)
        XCTAssertEqual(summaries[0]?.decodeBatchSize, 2)
        XCTAssertEqual(summaries[1]?.modelEvalBatchSize, 2)
        XCTAssertEqual(recorder.batchSizes, [2, 2, 2])
        XCTAssertEqual(recorder.sequenceLengths, [1, 1, 1])
        XCTAssertEqual(recorder.cacheOffsets, [5, 6, 7])
        XCTAssertEqual(Set(recorder.cacheIdentifiers).count, 1)

        let batchProbe = try XCTUnwrap(summaries[0]?.decodeBatchProbe)
        XCTAssertEqual(batchProbe.decodeTokenEvalCallCount, 4)
        XCTAssertEqual(batchProbe.decodeTokenIDCallCount, 6)
    }

    func testAutoSwiftMLXBackendDecodeBatchFallsBackForSingleRequest() async throws {
        let backend = AutoSwiftMLXBackend()
        let recorder = BatchCacheIdentityRecorder()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeBatchCacheIdentityModelContainer(recorder: recorder)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("single fallback")],
                    prefillStepSize: 32,
                    resumeHint: "single-batch-fallback",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeBatchEvents(
                    requests: [
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                    ]
                )
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries.count, 1)
        XCTAssertEqual(summaries[0]?.completionTokens, 2)
        XCTAssertNil(summaries[0]?.decodeBatchSize)
        XCTAssertFalse(events.contains { event in
            if case .batchSummary = event { return true }
            return false
        })
        XCTAssertEqual(recorder.batchSizes, [1, 1])
    }

    func testAutoSwiftMLXBackendDecodeBatchFallbackPropagatesPerRequestFailure() async throws {
        let backend = AutoSwiftMLXBackend()

        let stream = try await backend.decodeBatchEvents(
            requests: [
                TextRuntimeDecodeRequest(
                    model: LoadedTextModel(storage: ["kind": "not-a-swift-mlx-container"]),
                    draftModel: nil,
                    context: TextPrefillContext(storage: [:], promptTokens: 1),
                    sampling: Melix_Worker_V1_SamplingConfig(),
                    maxOutputTokens: 1,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                ),
            ]
        )

        await XCTAssertThrowsErrorAsync(try await collectTextBatchGenerationEvents(from: stream))
    }

    func testAutoSwiftMLXBackendDecodeBatchFallsBackForUnsupportedCacheSignature() async throws {
        let backend = AutoSwiftMLXBackend()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 1

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(storage: makeConstantTokenModelContainer())
                let request1 = TextRuntimeDecodeRequest(
                    model: model,
                    draftModel: nil,
                    context: makePreparedDecodeContext(
                        prepared: .tokens(LMInput.Text(tokens: MLXArray([2]))),
                        cache: [QuantizedKVCache(groupSize: 64, bits: 4)]
                    ),
                    sampling: sampling,
                    maxOutputTokens: 1,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let request2 = TextRuntimeDecodeRequest(
                    model: model,
                    draftModel: nil,
                    context: makePreparedDecodeContext(
                        prepared: .tokens(LMInput.Text(tokens: MLXArray([2]))),
                        cache: [QuantizedKVCache(groupSize: 64, bits: 4)]
                    ),
                    sampling: sampling,
                    maxOutputTokens: 1,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeBatchEvents(requests: [request1, request2])
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries.count, 2)
        XCTAssertEqual(summaries[0]?.completionTokens, 1)
        XCTAssertEqual(summaries[1]?.completionTokens, 1)
        XCTAssertNil(summaries[0]?.decodeBatchSize)
        XCTAssertFalse(events.contains { event in
            if case .batchSummary = event { return true }
            return false
        })
    }

    func testAutoSwiftMLXBackendBatchDecodeUsesProcessorPathForRepetitionPenalty() async throws {
        let backend = AutoSwiftMLXBackend()
        let recorder = BatchCacheIdentityRecorder()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.frequencyPenalty = 1.1
        sampling.maxOutputTokens = 2

        setenv("MELIX_SWIFT_BATCH_DECODE_FORCE_MODEL_EVAL_PROBE", "1", 1)
        defer { unsetenv("MELIX_SWIFT_BATCH_DECODE_FORCE_MODEL_EVAL_PROBE") }

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeBatchCacheIdentityModelContainer(recorder: recorder)
                )
                let prefill1 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("processor batch")],
                    prefillStepSize: 32,
                    resumeHint: "processor-batch-1",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let prefill2 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("processor batch")],
                    prefillStepSize: 32,
                    resumeHint: "processor-batch-2",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeBatchEvents(
                    requests: [
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill1.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill2.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                    ]
                )
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        let batchProbe = try XCTUnwrap(summaries[0]?.decodeBatchProbe)
        XCTAssertEqual(summaries[0]?.completionTokens, 2)
        XCTAssertEqual(summaries[1]?.completionTokens, 2)
        XCTAssertEqual(batchProbe.decodeTokenEvalCallCount, 4)
        XCTAssertEqual(batchProbe.decodeTokenIDCallCount, 4)
        XCTAssertGreaterThanOrEqual(batchProbe.decodeModelEvalSyncCallCount, 1)
        XCTAssertEqual(recorder.batchSizes, [2, 2])
    }

    func testAutoSwiftMLXBackendBatchDecodeRebuildsCacheWhenOneOfThreePeersAborts() async throws {
        let backend = AutoSwiftMLXBackend()
        let recorder = BatchCacheIdentityRecorder()
        let abortingPeer = AbortAfterPoll(falsePollsBeforeAbort: 1)
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        setenv("MELIX_SWIFT_BATCH_DECODE_FORCE_MODEL_EVAL_PROBE", "1", 1)
        defer { unsetenv("MELIX_SWIFT_BATCH_DECODE_FORCE_MODEL_EVAL_PROBE") }

        let events = try await collectThreePeerBatchDecodeEvents(
            backend: backend,
            recorder: recorder,
            sampling: sampling,
            abortingPeer: abortingPeer
        )

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries[0]?.completionTokens, 0)
        XCTAssertEqual(summaries[1]?.completionTokens, 2)
        XCTAssertEqual(summaries[2]?.completionTokens, 2)
        XCTAssertEqual(recorder.batchSizes, [3, 2])
        XCTAssertEqual(recorder.sequenceLengths, [1, 1])
        XCTAssertGreaterThanOrEqual(summaries[1]?.decodeBatchProbe?.decodeModelEvalSyncCallCount ?? 0, 1)
    }

    func testAutoSwiftMLXBackendBatchDecodeMaterializesCacheForSingleRemainingPeer() async throws {
        let backend = AutoSwiftMLXBackend()
        let recorder = BatchCacheIdentityRecorder()
        let abortingPeer = AbortAfterPoll(falsePollsBeforeAbort: 1)
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeBatchCacheIdentityModelContainer(recorder: recorder)
                )
                let prefill1 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("two-way shrink one")],
                    prefillStepSize: 32,
                    resumeHint: "two-way-shrink-1",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let prefill2 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("two-way shrink two")],
                    prefillStepSize: 32,
                    resumeHint: "two-way-shrink-2",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeBatchEvents(
                    requests: [
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill1.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { abortingPeer.shouldAbort() }
                        ),
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill2.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                    ]
                )
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries[0]?.completionTokens, 0)
        XCTAssertEqual(summaries[1]?.completionTokens, 2)
        XCTAssertEqual(recorder.batchSizes, [2, 1])
        XCTAssertEqual(recorder.sequenceLengths, [1, 1])
    }

    func testAutoSwiftMLXBackendBatchDecodeSupportsRotatingCacheState() async throws {
        let backend = AutoSwiftMLXBackend()
        let recorder = BatchCacheIdentityRecorder()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeBatchCacheIdentityModelContainer(
                        recorder: recorder,
                        cacheKind: .rotating(maxSize: 8)
                    )
                )
                let prefill1 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("rotating batch")],
                    prefillStepSize: 32,
                    resumeHint: "rotating-batch-1",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let prefill2 = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("rotating batch")],
                    prefillStepSize: 32,
                    resumeHint: "rotating-batch-2",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeBatchEvents(
                    requests: [
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill1.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: prefill2.context,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                    ]
                )
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries[0]?.completionTokens, 2)
        XCTAssertEqual(summaries[1]?.completionTokens, 2)
        XCTAssertEqual(summaries[0]?.decodeBatchSize, 2)
        XCTAssertEqual(recorder.cacheMaxSizes, [8, 8])
    }

    func testAutoSwiftMLXBackendBatchArgMaxTokenIDsBridgeThroughUInt32() async throws {
        try await withTemporaryDefaultMetallib {
            Device.withDefaultDevice(.cpu) {
                let logits = MLXArray([
                    Float(-3), Float(1), Float(8), Float(0),
                    Float(2), Float(4), Float(-1), Float(9),
                ], [2, 1, 4])

                XCTAssertEqual(argMax(logits[0..., -1, 0...], axis: -1).dtype, .uint32)
                XCTAssertEqual(melixTestingBatchedArgMaxTokenIDs(from: logits), [2, 3])
            }
        }
    }

    func testAutoSwiftMLXBackendBatchDecodeSplitsRotatingAdapterByUnderlyingCacheType() async throws {
        try await withTemporaryDefaultMetallib {
            try Device.withDefaultDevice(.cpu) {
                let cache1 = RotatingKVCache(maxSize: 8)
                let cache2 = RotatingKVCache(maxSize: 8)
                let keys1 = MLXArray.zeros([1, 1, 3, 4])
                let values1 = MLXArray.zeros([1, 1, 3, 4])
                let keys2 = MLXArray.zeros([1, 1, 3, 4])
                let values2 = MLXArray.zeros([1, 1, 3, 4])
                _ = cache1.update(keys: keys1, values: values1)
                _ = cache2.update(keys: keys2, values: values2)

                let batchedCache = try XCTUnwrap(melixTestingMakeBatchDecodeCache(from: [[cache1], [cache2]]))
                let splitCaches = melixTestingSplitBatchDecodeCache(batchedCache, batchSize: 2)

                XCTAssertEqual(splitCaches.count, 2)
                for splitCache in splitCaches {
                    let splitLayer = try XCTUnwrap(splitCache.first)
                    XCTAssertTrue(splitLayer is RotatingKVCache)
                    XCTAssertEqual(splitLayer.maxSize, 8)
                }
            }
        }
    }

    func testAutoSwiftMLXBackendBatchDecodeStopsOnAdditionalEOSToken() async throws {
        let backend = AutoSwiftMLXBackend()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeConstantTokenModelContainer(extraEOSTokens: ["tok3"])
                )
                let context1 = makePreparedDecodeContext(
                    prepared: .tokens(LMInput.Text(tokens: MLXArray([2]))),
                    cache: makeSimpleKVCache(sequenceLength: 3)
                )
                let context2 = makePreparedDecodeContext(
                    prepared: .tokens(LMInput.Text(tokens: MLXArray([2]))),
                    cache: makeSimpleKVCache(sequenceLength: 3)
                )
                let stream = try await backend.decodeBatchEvents(
                    requests: [
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: context1,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                        TextRuntimeDecodeRequest(
                            model: model,
                            draftModel: nil,
                            context: context2,
                            sampling: sampling,
                            maxOutputTokens: 2,
                            decodeStepSize: 1,
                            prefillToken: "",
                            acceleration: Melix_Worker_V1_AccelerationPolicy(),
                            shouldAbort: { false }
                        ),
                    ]
                )
                return try await collectTextBatchGenerationEvents(from: stream)
            }
        }

        let summaries = renderedBatchRequestSummaries(from: events)
        XCTAssertEqual(summaries[0]?.completionTokens, 0)
        XCTAssertEqual(summaries[1]?.completionTokens, 0)
        XCTAssertTrue(events.contains { event in
            guard case .batchSummary(let summary) = event else {
                return false
            }
            return summary.outputTokenCount == 0
        })
    }

    func testAutoSwiftMLXBackendDecodeUsesLiveSpeculativeDraftBridge() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .speculativeDecode
        acceleration.draftModelID = "melix-tests/draft"
        acceleration.numDraftTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let targetModel = LoadedTextModel(
                    storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let draftModel = LoadedTextModel(
                    storage: makeLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill = try await backend.prefill(
                    model: targetModel,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge speculative decode")],
                    prefillStepSize: 32,
                    resumeHint: "live-speculative-decode",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: targetModel,
                    draftModel: draftModel,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        XCTAssertFalse(renderedTokenChunks(from: events).joined().isEmpty)
        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.promptTokens, promptTokens.count)
        XCTAssertGreaterThan(summary.completionTokens, 0)
        XCTAssertNotNil(summary.tokensPerSecond)
        XCTAssertNotNil(summary.speculativeAcceptedTokens)
        XCTAssertNotNil(summary.speculativeRejectedTokens)
        XCTAssertNotNil(summary.speculativeDraftProposeMillis)
        XCTAssertNotNil(summary.speculativeTargetVerifyMillis)
    }

    func testAutoSwiftMLXBackendDecodeUsesNativeDFlashSpeculativeDraftRuntime() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .speculativeDecode
        acceleration.draftModelID = "melix-tests/dflash-draft"
        acceleration.numDraftTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let targetModel = LoadedTextModel(
                    storage: makeDFlashTestTargetModelContainer(promptTokens: promptTokens)
                )
                let draftModel = LoadedTextModel(
                    storage: try makeTestDFlashDraftRuntime()
                )
                let prefill = try await backend.prefill(
                    model: targetModel,
                    messages: [makeSystemMessage("system"), makeUserMessage("native dflash decode")],
                    prefillStepSize: 32,
                    resumeHint: "live-dflash-decode",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: targetModel,
                    draftModel: draftModel,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        XCTAssertFalse(renderedTokenChunks(from: events).joined().isEmpty)
        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.promptTokens, promptTokens.count)
        XCTAssertEqual(summary.completionTokens, 2)
        XCTAssertEqual(summary.dflashEnabled, true)
        XCTAssertNotNil(summary.speculativeAcceptedTokens)
        XCTAssertNotNil(summary.speculativeRejectedTokens)
        XCTAssertNotNil(summary.speculativeDraftProposeMillis)
        XCTAssertNotNil(summary.speculativeTargetVerifyMillis)
        XCTAssertEqual(summary.dflashBlockSize, 2)
        XCTAssertEqual(summary.dflashTargetHiddenLayers, 1)
    }

    func testAutoSwiftMLXBackendDFlashSkipsAcceptedBonusAdvanceAndFinalRebuild() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3]
        let recorder = DFlashTargetForwardRecorder()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 5

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .speculativeDecode
        acceleration.draftModelID = "melix-tests/dflash-draft"
        acceleration.numDraftTokens = 2

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let targetModel = LoadedTextModel(
                    storage: makeDFlashTestTargetModelContainer(
                        promptTokens: promptTokens,
                        recorder: recorder
                    )
                )
                let draftModel = LoadedTextModel(
                    storage: try makeTestDFlashDraftRuntime()
                )
                let prefill = try await backend.prefill(
                    model: targetModel,
                    messages: [makeSystemMessage("system"), makeUserMessage("native dflash decode")],
                    prefillStepSize: 32,
                    resumeHint: "live-dflash-decode",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: targetModel,
                    draftModel: draftModel,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 5,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.completionTokens, 5)
        XCTAssertEqual(recorder.inputLengths, [promptTokens.count, 2, 2])
    }

    func testAutoSwiftMLXBackendDecodeReportsTurboQuantFusedRuntimeRoute() async throws {
        let backend = AutoSwiftMLXBackend(turboQuantCandidateProbeEnabled: true)
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "turboquant-q4"

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeQuantizableLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge active kv decode")],
                    prefillStepSize: 32,
                    resumeHint: "live-active-kv-decode",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: model,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        let summary = try XCTUnwrap(renderedSummary(from: events))
        let activeKVProbe = try XCTUnwrap(summary.activeKVProbe)
        XCTAssertEqual(activeKVProbe.backendCode, 2)
        XCTAssertEqual(activeKVProbe.kernelPathCode, 20)
        XCTAssertEqual(activeKVProbe.runtimeRouteCode, 2)
        XCTAssertEqual(activeKVProbe.runtimeBlockReasonCode, 0)
        XCTAssertEqual(activeKVProbe.quantizationRatioPercent, 25)
        XCTAssertEqual(activeKVProbe.candidateDispatchCode, 1)
        XCTAssertGreaterThanOrEqual(activeKVProbe.prefillQuantizeMicros, 0)
        XCTAssertGreaterThan(activeKVProbe.decodeTokenCount, 0)
        XCTAssertGreaterThan(activeKVProbe.estimatedQuantizedBytes, 0)
        XCTAssertGreaterThan(activeKVProbe.estimatedFP16Bytes, activeKVProbe.estimatedQuantizedBytes)
        XCTAssertEqual(activeKVProbe.estimatedMemorySavingsPercent, 75)
        XCTAssertEqual(activeKVProbe.fallbackCount, 0)
        XCTAssertEqual(activeKVProbe.candidateEligibilityCheckCount, 1)
    }

    func testAutoSwiftMLXBackendDecodeUsesVendoredTurboQuantRouteWhenProbeIsDisabled() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "turboquant-q4"

        let result = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeQuantizableLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge disabled candidate checks")],
                    prefillStepSize: 32,
                    resumeHint: "live-disabled-candidate-checks",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: model,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return (
                    activeKVQuantizationRatio: prefill.activeKVQuantizationRatio,
                    events: try await collectTextGenerationEvents(from: stream)
                )
            }
        }

        XCTAssertEqual(result.activeKVQuantizationRatio, 0)
        let summary = try XCTUnwrap(renderedSummary(from: result.events))
        let activeKVProbe = try XCTUnwrap(summary.activeKVProbe)
        XCTAssertEqual(activeKVProbe.backendCode, 2)
        XCTAssertEqual(activeKVProbe.kernelPathCode, 20)
        XCTAssertEqual(activeKVProbe.runtimeRouteCode, 2)
        XCTAssertEqual(activeKVProbe.runtimeBlockReasonCode, 0)
        XCTAssertEqual(activeKVProbe.quantizationRatioPercent, 25)
        XCTAssertGreaterThan(activeKVProbe.estimatedQuantizedBytes, 0)
        XCTAssertEqual(activeKVProbe.estimatedMemorySavingsPercent, 75)
        XCTAssertEqual(activeKVProbe.fallbackCount, 0)
        XCTAssertEqual(activeKVProbe.candidateDispatchCode, 0)
        XCTAssertEqual(activeKVProbe.candidateEligibilityCheckCount, 0)
        XCTAssertEqual(activeKVProbe.decodeQuantizeTotalMicros, 0)
    }

    func testAutoSwiftMLXBackendDecodeSkipsTerminalModelCallAtMaxOutputTokens() async throws {
        let backend = AutoSwiftMLXBackend()
        let counter = CountingLanguageModelCallCounter()
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 1

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "q4"

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeCountingPreparedLogitsModelContainer(counter: counter)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge counted decode")],
                    prefillStepSize: 32,
                    resumeHint: "live-counted-decode",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: model,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 1,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        let summary = try XCTUnwrap(renderedSummary(from: events))
        XCTAssertEqual(summary.completionTokens, 1)
        let activeKVProbe = try XCTUnwrap(summary.activeKVProbe)
        XCTAssertEqual(activeKVProbe.decodeModelCallCount, 0)
        XCTAssertEqual(counter.stepCallCount, 0)
    }

    func testAutoSwiftMLXBackendDecodeCanLazilyQuantizeBaselinePrefillCache() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "q4"

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeQuantizableLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge lazy active kv decode")],
                    prefillStepSize: 32,
                    resumeHint: "live-baseline-prefill-active-kv-decode",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: model,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        let summary = try XCTUnwrap(renderedSummary(from: events))
        let activeKVProbe = try XCTUnwrap(summary.activeKVProbe)
        XCTAssertEqual(activeKVProbe.backendCode, 1)
        XCTAssertEqual(activeKVProbe.kernelPathCode, 10)
        XCTAssertEqual(activeKVProbe.quantizationRatioPercent, 25)
        XCTAssertGreaterThan(activeKVProbe.decodeTokenCount, 0)
        XCTAssertGreaterThan(activeKVProbe.estimatedQuantizedBytes, 0)
        XCTAssertEqual(activeKVProbe.estimatedMemorySavingsPercent, 75)
    }

    func testAutoSwiftMLXBackendDecodeRecordsOptInModelEvalSyncProbe() async throws {
        let backend = AutoSwiftMLXBackend()
        let promptTokens = [1, 2, 3, 4, 5]
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0
        sampling.topP = 1
        sampling.maxOutputTokens = 2

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "q4"

        setenv("MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE", "1", 1)
        defer { unsetenv("MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE") }

        let events = try await withTemporaryDefaultMetallib {
            try await Device.withDefaultDevice(.cpu) {
                let model = LoadedTextModel(
                    storage: makeQuantizableLiveSwiftMLXModelContainer(promptTokens: promptTokens)
                )
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("bridge active kv eval probe")],
                    prefillStepSize: 32,
                    resumeHint: "live-active-kv-eval-probe",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                let stream = try await backend.decodeEvents(
                    model: model,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: acceleration,
                    shouldAbort: { false }
                )
                return try await collectTextGenerationEvents(from: stream)
            }
        }

        let summary = try XCTUnwrap(renderedSummary(from: events))
        let activeKVProbe = try XCTUnwrap(summary.activeKVProbe)
        XCTAssertEqual(activeKVProbe.decodeModelEvalSyncCallCount, 1)
        XCTAssertGreaterThanOrEqual(activeKVProbe.decodeModelEvalSyncTotalMicros, 0)
    }
    #endif

    func testChatMessageConversionFlattensTextAndRejectsUnsupportedParts() throws {
        let converted = try convertChatMessages([
            makeUserMessage("line one", extraText: "line two"),
            makeSystemMessage("system prompt"),
        ])

        XCTAssertEqual(converted.count, 2)
        XCTAssertEqual(converted[0].content, "line one\nline two")
        XCTAssertEqual(converted[1].content, "system prompt")

        var invalid = Melix_Worker_V1_ChatMessage()
        invalid.role = "user"
        var imagePart = Melix_Worker_V1_MessagePart()
        imagePart.imageUri = "file:///tmp/test.png"
        invalid.parts = [imagePart]

        XCTAssertThrowsError(try convertChatMessages([invalid]))
    }

    func testChatMessageConversionCoversAssistantToolEmptyAndUnsupportedRoles() throws {
        let assistant = try convertChatMessages([makeRoleMessage("assistant", text: "draft")])
        XCTAssertEqual(assistant.first?.content, "draft")

        let tool = try convertChatMessages([makeRoleMessage("tool", text: "tool output")])
        XCTAssertEqual(tool.first?.content, "tool output")

        let emptyRole = try convertChatMessages([makeRoleMessage("", text: "fallback user")])
        XCTAssertEqual(emptyRole.first?.content, "fallback user")

        XCTAssertThrowsError(try convertChatMessages([]))
        XCTAssertThrowsError(try convertChatMessages([makeRoleMessage("critic", text: "unsupported")]))
    }

    func testFlattenTextContentSkipsUnsetParts() throws {
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var textPart = Melix_Worker_V1_MessagePart()
        textPart.text = "hello"
        let emptyPart = Melix_Worker_V1_MessagePart()
        message.parts = [textPart, emptyPart]

        XCTAssertEqual(try flattenTextContent(from: message), "hello")
    }

    func testGenerateParameterMappingUsesPhaseOneDefaults() {
        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.temperature = 0.7
        sampling.topP = 0.95
        sampling.maxOutputTokens = 64
        sampling.frequencyPenalty = 0.5
        sampling.presencePenalty = 0.2

        let parameters = makeGenerateParameters(from: sampling)

        XCTAssertEqual(parameters.temperature, 0.7)
        XCTAssertEqual(parameters.topP, 0.95)
        XCTAssertEqual(parameters.maxTokens, 64)
        XCTAssertEqual(parameters.repetitionPenalty, 0.5)
    }

    func testRuntimeUnavailableErrorReturnsMessageAsDescription() {
        let error = RuntimeUnavailableError(message: "mlx unavailable")

        XCTAssertEqual(error.errorDescription, "mlx unavailable")
    }

    func testTextRuntimeUsesResidentDeltaAndForwardsUnload() async throws {
        let backend = FakeRuntimeBackend(residentBytesHint: 2_048)
        let probe = ResidentMemoryProbe(samples: [100, 3_600])
        let runtime = TextRuntime(
            backend: backend,
            residentMemoryReader: { probe.next() }
        )
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"

        let loaded = try await runtime.loadModel(spec: spec)
        await runtime.unloadModel(loaded.model)
        let unloadedCount = await backend.unloadedModelCount()

        XCTAssertEqual(runtime.runtimeName, "fake-mlx-swift")
        XCTAssertEqual(loaded.estimatedResidentBytes, 3_500)
        XCTAssertEqual(unloadedCount, 1)
    }

    func testTextRuntimeDefaultResidentReaderAndDefaultUnloadPathAreSafe() async throws {
        let runtime = TextRuntime(backend: DefaultUnloadBackend())
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"

        let loaded = try await runtime.loadModel(spec: spec)
        await runtime.unloadModel(loaded.model)

        XCTAssertEqual(runtime.runtimeName, "default-unload-backend")
        XCTAssertGreaterThanOrEqual(loaded.estimatedResidentBytes, 0)
    }

    func testTextRuntimeForwardsGenerateEventsAndDefaultGenerateThrowsUnavailable() async throws {
        let runtime = TextRuntime(backend: FakeRuntimeBackend(generatedChunks: ["swift"]))
        let generated = try await runtime.generateEvents(
            model: LoadedTextModel(storage: ["kind": "fake"]),
            messages: [makeUserMessage("go")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: generated)
        XCTAssertEqual(renderedTokenChunks(from: events), ["swift"])

        let unavailableRuntime = TextRuntime(backend: DefaultUnloadBackend())
        let unavailableModel = try await unavailableRuntime.loadModel(spec: Melix_Worker_V1_ModelSpec())
        await XCTAssertThrowsErrorAsync(
            try await unavailableRuntime.generateEvents(
                model: unavailableModel.model,
                messages: [makeUserMessage("go")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
    }

    func testTextRuntimeForwardsPrefillAndDefaultPrefillThrowsUnavailable() async throws {
        let runtime = TextRuntime(backend: FakeRuntimeBackend())
        let loaded = try await runtime.loadModel(spec: Melix_Worker_V1_ModelSpec())
        let result = try await runtime.prefill(
            model: loaded.model,
            messages: [makeUserMessage("prefill runtime")],
            prefillStepSize: 8,
            resumeHint: "runtime-resume",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )

        XCTAssertEqual(result.promptTokens, 1)
        XCTAssertEqual(result.context.promptTokens, 1)
        XCTAssertEqual(result.requestedPrefillStepTokens, 8)
        XCTAssertEqual(result.effectivePrefillWindowTokens, 8)
        XCTAssertEqual((result.context.storage as? [String: String])?["resume_hint"], "runtime-resume")
        XCTAssertEqual((result.context.storage as? [String: String])?["prefill_step_size"], "8")

        let unavailableRuntime = TextRuntime(backend: DefaultUnloadBackend())
        let unavailableModel = try await unavailableRuntime.loadModel(spec: Melix_Worker_V1_ModelSpec())

        await XCTAssertThrowsErrorAsync(
            try await unavailableRuntime.prefill(
                model: unavailableModel.model,
                messages: [makeUserMessage("go")],
                prefillStepSize: 4,
                resumeHint: "unavailable",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                shouldAbort: { false }
            )
        )
    }

    func testTextRuntimeForwardsDecodeAndDefaultDecodeThrowsUnavailable() async throws {
        let runtime = TextRuntime(backend: FakeRuntimeBackend(decodedChunks: ["decode", " path"]))
        let loaded = try await runtime.loadModel(spec: Melix_Worker_V1_ModelSpec())
        let prefill = try await runtime.prefill(
            model: loaded.model,
            messages: [makeUserMessage("decode runtime")],
            prefillStepSize: 8,
            resumeHint: "decode-resume",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let decoded = try await runtime.decodeEvents(
            model: loaded.model,
            context: prefill.context,
            sampling: Melix_Worker_V1_SamplingConfig(),
            maxOutputTokens: 8,
            decodeStepSize: 1,
            prefillToken: "",
            acceleration: acceleration,
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: decoded)
        XCTAssertEqual(renderedTokenChunks(from: events), ["decode", " path"])
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 2)

        let unavailableRuntime = TextRuntime(backend: DefaultUnloadBackend())
        let unavailableModel = try await unavailableRuntime.loadModel(spec: Melix_Worker_V1_ModelSpec())

        await XCTAssertThrowsErrorAsync(
            try await unavailableRuntime.decodeEvents(
                model: unavailableModel.model,
                context: TextPrefillContext(storage: [:], promptTokens: 1),
                sampling: Melix_Worker_V1_SamplingConfig(),
                maxOutputTokens: 4,
                decodeStepSize: 1,
                prefillToken: "",
                acceleration: acceleration,
                shouldAbort: { false }
            )
        )
    }

    func testDrainTransitionsRuntimeStateToDraining() async throws {
        let services = makeServices()

        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var response = Melix_Worker_V1_DrainResponse()
            var request = Melix_Worker_V1_DrainRequest()
            request.stopAcceptingNew = true
            response = try await services.runtime.drain(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.Drain.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
            return response
        }

        let stats = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(stats.stats.workerState, "draining")
    }

    func testRuntimeRegistrySupportsLoadedModelLookupAndReadableErrors() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var request = Melix_Worker_V1_ModelSpec()
        request.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(request)
        let found = await registry.getLoadedModel(loaded.handle)
        let missing = await registry.getLoadedModel("missing")

        XCTAssertEqual(found?.handle, loaded.handle)
        XCTAssertNil(missing)
        XCTAssertEqual(WorkerRuntimeRegistryError.unknownModelHandle.errorDescription, "Unknown model handle.")
    }

    func testRuntimeRegistryVisionWorkerAcceptsVLMRouteAndRejectsTextOnlyRoutes() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(workerID: "vision-test", workerFamily: .vision),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_VLM_MODEL_PATH": "mlx-community/melix-dev-vlm-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var vlmRequest = Melix_Worker_V1_ModelSpec()
        vlmRequest.modelID = "melix-dev-vlm"
        let loaded = try await registry.loadModel(vlmRequest)
        XCTAssertEqual(loaded.spec.modelID, "melix-dev-vlm")
        XCTAssertEqual(loaded.spec.requestRoutes.first?.workerFamily, .vision)

        var textRequest = Melix_Worker_V1_ModelSpec()
        textRequest.modelID = "melix-dev-text"
        do {
            _ = try await registry.loadModel(textRequest)
            XCTFail("expected requestRouteUnsupported")
        } catch {
            guard case let WorkerRuntimeRegistryError.requestRouteUnsupported(modelID, workerFamily, reason) = error else {
                return XCTFail("expected requestRouteUnsupported, got \(error)")
            }
            XCTAssertEqual(modelID, "melix-dev-text")
            XCTAssertEqual(workerFamily, .vision)
            XCTAssertEqual(reason, "worker_family_mismatch")
        }
    }

    func testWorkerServiceDefensiveRouteValidationReturnsStructuredRouteError() async throws {
        let services = makeServices(environment: [
            "MELIX_SWIFT_WORKER_FAMILY": "vision",
        ])

        var request = Melix_Worker_V1_LoadModelRequest()
        request.model.modelID = "melix-dev-text"

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "route_not_supported")
        XCTAssertFalse(response.error.retriable)
        XCTAssertTrue(response.error.message.contains("Worker defensive validation"))
        XCTAssertEqual(response.error.details["model_id"], "melix-dev-text")
        XCTAssertEqual(response.error.details["worker_family_candidates"], "vision")
        XCTAssertEqual(response.error.details["reason"], "worker_family_mismatch")
    }

    func testRuntimeRegistryVisionWorkerAcceptsVideoOnlyNativeRoute() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(workerID: "vision-video-test", workerFamily: .vision),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "video-only-dev"
        model.modelPath = "video-only-dev"
        var route = Melix_Worker_V1_RequestRouteDeclaration()
        route.task = .generateMultimodal
        route.supportedModalities = [.video]
        route.requiresAnyModality = [.video]
        route.workerFamily = .vision
        route.modelFamilyTarget = "video-only.test"
        route.supportsNativeVideo = true
        model.requestRoutes = [route]

        let loaded = try await registry.loadModel(model)

        XCTAssertEqual(loaded.spec.modelID, "video-only-dev")
        XCTAssertEqual(loaded.spec.requestRoutes.first?.requiresAnyModality, [.video])
    }

    func testVisionPayloadReceiptIsWrittenAsynchronously() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-vision-payload-receipt-\(UUID().uuidString)", isDirectory: true)
        let receiptPath = directory.appendingPathComponent("vision-payload.jsonl").path
        defer {
            try? FileManager.default.removeItem(at: directory)
        }
        let services = makeServices(
            environment: [
                "MELIX_SWIFT_WORKER_FAMILY": "vision",
                "MELIX_SWIFT_VISION_PAYLOAD_RECEIPT_PATH": receiptPath,
            ],
            backend: FakeRuntimeBackend(generatedChunks: ["vision"])
        )
        var loadRequest = Melix_Worker_V1_LoadModelRequest()
        loadRequest.model.modelID = "melix-dev-vlm"
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.loadModel(
                request: loadRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        XCTAssertTrue(loadResponse.ok, loadResponse.error.message)

        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-vision-payload-receipt"
        request.execution.modelHandle = loadResponse.modelHandle
        request.messages = [
            makeVisionMessage(
                prompt: "receipt",
                imageBytes: Data("image".utf8),
                videoBytes: Data("video".utf8),
                videoFilename: "clip.mp4"
            )
        ]
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.generate(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Generate.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let maybeContents = await waitForFileContents(atPath: receiptPath)
        let contents = try XCTUnwrap(maybeContents)
        let firstLine = try XCTUnwrap(contents.split(separator: "\n").first)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(firstLine.utf8)) as? [String: Any])
        let mediaParts = try XCTUnwrap(payload["media_parts"] as? [[String: Any]])

        XCTAssertEqual(payload["request_id"] as? String, "req-vision-payload-receipt")
        XCTAssertEqual(payload["worker_family"] as? String, "vision")
        XCTAssertEqual(mediaParts.map { $0["kind"] as? String }, ["image", "video"])
    }

    func testRuntimeRegistryTracksBusyStateAndGenerateEventsForLoadedModel() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend(generatedChunks: ["one", " two"]))
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        await registry.startRequest()
        let busyStats = await registry.runtimeStats()
        await registry.finishRequest()
        let idleStats = await registry.runtimeStats()

        let stream = try await registry.generateEvents(
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry")],
            sampling: Melix_Worker_V1_SamplingConfig(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(from: stream)

        XCTAssertEqual(busyStats.workerState, "busy")
        XCTAssertEqual(idleStats.workerState, "idle")
        XCTAssertEqual(renderedTokenChunks(from: events), ["one", " two"])
        await XCTAssertThrowsErrorAsync(
            try await registry.generateEvents(
                modelHandle: "missing",
                messages: [makeUserMessage("registry")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
    }

    func testRuntimeRegistryStoresPrefillContextsForLoadedModel() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let result = try await registry.prefill(
            requestID: "req-prefill-registry",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry prefill")],
            prefillStepSize: 16,
            returnDecodeHandle: true,
            resumeHint: "registry-resume",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let stored = await registry.prefillContext(for: result.decodeHandle)
        let contextCount = await registry.prefillContextCount()
        let cacheResponse = await registry.cacheStatsResponse()
        let runtimeStats = await registry.runtimeStats()

        XCTAssertFalse(result.decodeHandle.isEmpty)
        XCTAssertFalse(result.blockTableID.isEmpty)
        XCTAssertEqual(result.blockTable.scopeID, cacheResponse.snapshot.scopes.first?.scopeID)
        XCTAssertEqual(result.blockTable.blocks.count, 1)
        XCTAssertEqual(result.promptTokens, 1)
        XCTAssertEqual(contextCount, 1)
        XCTAssertEqual(stored?.modelHandle, loaded.handle)
        XCTAssertEqual(stored?.promptTokens, 1)
        XCTAssertEqual(stored?.requestID, "req-prefill-registry")
        XCTAssertEqual(stored?.blockTableID, result.blockTableID)
        XCTAssertEqual(cacheResponse.stats.blockCount, 1)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.first?.tokenLength, 1)
        XCTAssertEqual(runtimeStats.modelResidentBytes, 0)
        XCTAssertEqual(runtimeStats.cacheResidentBytes, cacheResponse.stats.l1Bytes)
        XCTAssertEqual(runtimeStats.residentBytes, cacheResponse.stats.l1Bytes)
    }

    func testRuntimeRegistryPrefillReusesMatchingHotPrefixMetadata() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let first = try await registry.prefill(
            requestID: "req-prefill-reuse-1",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry cache reuse")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "reuse-1",
            acceleration: acceleration,
            shouldAbort: { false }
        )
        let second = try await registry.prefill(
            requestID: "req-prefill-reuse-2",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry cache reuse")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "reuse-2",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertEqual(first.blockTableID, second.blockTableID)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
        XCTAssertGreaterThan(cacheResponse.stats.l1HitRate, 0)
        XCTAssertGreaterThan(cacheResponse.stats.dedupRatio, 1)
    }

    func testRuntimeRegistryIsolatesDispatchHandlesAndCacheScopesByAdapterSet() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var adapterAlpha = Melix_Worker_V1_ModelSpec()
        adapterAlpha.modelID = "melix-dev-text"
        adapterAlpha.ext["melix.adapter_set_hash"] = "adapter-alpha"
        let loadedAlpha = try await registry.loadModel(adapterAlpha)

        var adapterBeta = Melix_Worker_V1_ModelSpec()
        adapterBeta.modelID = "melix-dev-text"
        adapterBeta.ext["melix.adapter_set_hash"] = "adapter-beta"
        let loadedBeta = try await registry.loadModel(adapterBeta)

        let messages = [makeUserMessage("adapter isolated cache")]
        let alphaPrefill = try await registry.prefill(
            requestID: "req-adapter-alpha",
            modelHandle: loadedAlpha.handle,
            messages: messages,
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "adapter-alpha",
            acceleration: makeAccelerationPolicy(mode: .baseline),
            shouldAbort: { false }
        )
        let betaPrefill = try await registry.prefill(
            requestID: "req-adapter-beta",
            modelHandle: loadedBeta.handle,
            messages: messages,
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "adapter-beta",
            acceleration: makeAccelerationPolicy(mode: .baseline),
            shouldAbort: { false }
        )

        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertTrue(loadedAlpha.handle.contains("::adapter::adapter_alpha::"))
        XCTAssertTrue(loadedBeta.handle.contains("::adapter::adapter_beta::"))
        XCTAssertNotEqual(alphaPrefill.blockTable.scopeID, betaPrefill.blockTable.scopeID)
        XCTAssertNotEqual(alphaPrefill.blockTable.cacheKey.scopeID, betaPrefill.blockTable.cacheKey.scopeID)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 2)
    }

    func testRuntimeRegistryPrefillWithoutDecodeHandleDoesNotStoreContextAndUnloadClearsStoredContexts() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let withoutHandle = try await registry.prefill(
            requestID: "req-prefill-no-handle",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry prefill no handle")],
            prefillStepSize: 8,
            returnDecodeHandle: false,
            resumeHint: "no-handle",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        XCTAssertTrue(withoutHandle.decodeHandle.isEmpty)
        let countWithoutHandle = await registry.prefillContextCount()
        XCTAssertEqual(countWithoutHandle, 0)

        let withHandle = try await registry.prefill(
            requestID: "req-prefill-clear",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry prefill clear")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "clear",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        XCTAssertFalse(withHandle.decodeHandle.isEmpty)
        let countWithHandle = await registry.prefillContextCount()
        XCTAssertEqual(countWithHandle, 1)

        let unloaded = await registry.unloadModel(loaded.handle)
        let countAfterUnload = await registry.prefillContextCount()
        let storedAfterUnload = await registry.prefillContext(for: withHandle.decodeHandle)
        XCTAssertTrue(unloaded)
        XCTAssertEqual(countAfterUnload, 0)
        XCTAssertNil(storedAfterUnload)
    }

    func testRuntimeRegistryRejectsPrefillRequestsThatExceedModelContextLimit() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        do {
            _ = try await registry.prefill(
                requestID: "req-prefill-context-limit",
                modelHandle: loaded.handle,
                messages: [makeUserMessage(repeatingTokenPrompt(count: 8_193))],
                prefillStepSize: 8,
                returnDecodeHandle: true,
                resumeHint: "context-limit",
                acceleration: acceleration,
                shouldAbort: { false }
            )
            XCTFail("expected context-limit guard to reject oversized prefill")
        } catch let error as WorkerRuntimeRegistryError {
            guard case let WorkerRuntimeRegistryError.contextLimitExceeded(maxContext, promptTokens) = error else {
                return XCTFail("expected contextLimitExceeded, got \(error)")
            }
            XCTAssertEqual(maxContext, 8_192)
            XCTAssertEqual(promptTokens, 8_193)
        }
    }

    func testRuntimeRegistryRejectsPrefillRequestsThatExceedProcessBudget() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(
                processMemoryBudgetBytes: 4_500,
                prefillMemoryHeadroomBytes: 1_024
            ),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        do {
            _ = try await registry.prefill(
                requestID: "req-prefill-memory-guard",
                modelHandle: loaded.handle,
                messages: [makeUserMessage(repeatingTokenPrompt(count: 2))],
                prefillStepSize: 8,
                returnDecodeHandle: true,
                resumeHint: "memory-guard",
                acceleration: acceleration,
                shouldAbort: { false }
            )
            XCTFail("expected prefill memory guard to reject oversized request")
        } catch let error as WorkerRuntimeRegistryError {
            guard case let WorkerRuntimeRegistryError.prefillMemoryGuardExceeded(
                budgetBytes,
                headroomBytes,
                projectedResidentBytes,
                promptTokens,
                estimatedPrefillBytes,
                requiredBytes
            ) = error else {
                return XCTFail("expected prefillMemoryGuardExceeded, got \(error)")
            }
            XCTAssertEqual(budgetBytes, 4_500)
            XCTAssertEqual(headroomBytes, 1_024)
            XCTAssertEqual(projectedResidentBytes, 4_096)
            XCTAssertEqual(promptTokens, 2)
            XCTAssertEqual(estimatedPrefillBytes, 4_096)
            XCTAssertEqual(requiredBytes, 5_120)
        }
    }

    func testRuntimeRegistryRejectsQuadraticPrefillFallbacksAboveConfiguredThreshold() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(
                prefillQuadraticGuardTokenThreshold: 4
            ),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        do {
            _ = try await registry.prefill(
                requestID: "req-prefill-quadratic-guard",
                modelHandle: loaded.handle,
                messages: [makeUserMessage(repeatingTokenPrompt(count: 5))],
                prefillStepSize: 8,
                returnDecodeHandle: true,
                resumeHint: "quadratic-guard",
                acceleration: acceleration,
                shouldAbort: { false }
            )
            XCTFail("expected quadratic prefill guard to reject baseline fallback")
        } catch let error as WorkerRuntimeRegistryError {
            guard case let WorkerRuntimeRegistryError.quadraticPrefillGuardExceeded(
                promptTokens,
                tokenLimit,
                accelerationMode
            ) = error else {
                return XCTFail("expected quadraticPrefillGuardExceeded, got \(error)")
            }
            XCTAssertEqual(promptTokens, 5)
            XCTAssertEqual(tokenLimit, 4)
            XCTAssertEqual(accelerationMode, "baseline")
        }
    }

    func testRuntimeRegistryAllowsPrefillWhenMemoryEnforcementIsDisabled() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(
                memoryEnforcementDisabled: true,
                processMemoryBudgetBytes: 4_500,
                prefillMemoryHeadroomBytes: 1_024
            ),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let result = try await registry.prefill(
            requestID: "req-prefill-memory-enforcement-disabled",
            modelHandle: loaded.handle,
            messages: [makeUserMessage(repeatingTokenPrompt(count: 2))],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "memory-enforcement-disabled",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        XCTAssertFalse(result.decodeHandle.isEmpty)
    }

    func testRuntimeRegistryUsesConfiguredInitialCacheBlockTarget() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(initialCacheBlocks: 4),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let messages = (0..<80).map { _ in makeUserMessage("token") }
        let result = try await registry.prefill(
            requestID: "req-prefill-initial-cache-blocks",
            modelHandle: loaded.handle,
            messages: messages,
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "initial-cache-blocks",
            acceleration: acceleration,
            shouldAbort: { false }
        )
        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertEqual(result.promptTokens, 80)
        XCTAssertEqual(result.blockTable.blocks.count, 4)
        XCTAssertEqual(cacheResponse.stats.blockCount, 4)
    }

    func testRuntimeRegistryDefaultsCacheHintsFromModelSettings() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        loadRequest.settings.cacheMode = .hybrid
        loadRequest.settings.cacheBlockSizeTokens = 16
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        let messages = (0..<32).map { _ in makeUserMessage("token") }
        let result = try await registry.prefill(
            requestID: "req-prefill-model-cache-defaults",
            modelHandle: loaded.handle,
            messages: messages,
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "model-cache-defaults",
            acceleration: acceleration,
            shouldAbort: { false }
        )
        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertEqual(result.promptTokens, 32)
        XCTAssertEqual(result.blockTable.blocks.count, 2)
        XCTAssertEqual(cacheResponse.stats.activeMode, .hybrid)
    }

    func testRuntimeRegistryCountsNameOnlyPromptTokensForContextGuard() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        loadRequest.maxContext = 2
        let loaded = try await registry.loadModel(loadRequest)

        var namedMessage = Melix_Worker_V1_ChatMessage()
        namedMessage.role = "user"
        namedMessage.name = "alpha beta gamma"

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        do {
            _ = try await registry.prefill(
                requestID: "req-prefill-name-only",
                modelHandle: loaded.handle,
                messages: [namedMessage],
                prefillStepSize: 8,
                returnDecodeHandle: true,
                resumeHint: "name-only",
                acceleration: acceleration,
                shouldAbort: { false }
            )
            XCTFail("expected context-limit guard to use name-only prompt tokens")
        } catch let error as WorkerRuntimeRegistryError {
            guard case let .contextLimitExceeded(maxContext, promptTokens) = error else {
                return XCTFail("expected contextLimitExceeded, got \(error)")
            }
            XCTAssertEqual(maxContext, 2)
            XCTAssertEqual(promptTokens, 3)
        }
    }

    func testRuntimeRegistryCountsMediaBlankAndNilPartsForContextGuard() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        loadRequest.maxContext = 200
        let loaded = try await registry.loadModel(loadRequest)

        var blankPart = Melix_Worker_V1_MessagePart()
        blankPart.text = "   "

        let nilPart = Melix_Worker_V1_MessagePart()

        var imagePart = Melix_Worker_V1_MessagePart()
        imagePart.imageUri = "file:///tmp/test.png"

        var videoPart = Melix_Worker_V1_MessagePart()
        videoPart.videoUri = "file:///tmp/test.mp4"

        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        message.parts = [blankPart, nilPart, imagePart, videoPart]

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline

        do {
            _ = try await registry.prefill(
                requestID: "req-prefill-media-part",
                modelHandle: loaded.handle,
                messages: [message],
                prefillStepSize: 8,
                returnDecodeHandle: true,
                resumeHint: "media-part",
                acceleration: acceleration,
                shouldAbort: { false }
            )
            XCTFail("expected context-limit guard to count media parts")
        } catch let error as WorkerRuntimeRegistryError {
            guard case let .contextLimitExceeded(maxContext, promptTokens) = error else {
                return XCTFail("expected contextLimitExceeded, got \(error)")
            }
            XCTAssertEqual(maxContext, 200)
            XCTAssertEqual(promptTokens, 512)
        }
    }

    func testRuntimeRegistryBeginDecodeConsumesStoredContextAndTracksActiveDecodeState() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var loadRequest = Melix_Worker_V1_ModelSpec()
        loadRequest.modelID = "melix-dev-text"
        let loaded = try await registry.loadModel(loadRequest)

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .baseline
        let prefill = try await registry.prefill(
            requestID: "req-prefill-begin-decode",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("registry decode")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "begin-decode",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let session = try await registry.beginDecode(decodeHandle: prefill.decodeHandle)
        let statsDuringDecode = await registry.runtimeStats()
        let storedAfterBegin = await registry.prefillContext(for: prefill.decodeHandle)
        await registry.finishDecode()
        let statsAfterDecode = await registry.runtimeStats()

        XCTAssertEqual(session.prefill.requestID, "req-prefill-begin-decode")
        XCTAssertEqual(session.loadedModel.handle, loaded.handle)
        XCTAssertEqual(statsDuringDecode.activeDecodes, 1)
        XCTAssertEqual(statsDuringDecode.activeRequests, 1)
        XCTAssertNil(storedAfterBegin)
        XCTAssertEqual(statsAfterDecode.activeDecodes, 0)
        XCTAssertEqual(statsAfterDecode.activeRequests, 0)

        await XCTAssertThrowsErrorAsync(
            try await registry.beginDecode(decodeHandle: "missing-decode")
        )
    }

    func testRuntimeLifecycleLoadAndUnloadTrackModelState() async throws {
        let backend = FakeRuntimeBackend()
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: backend,
            residentMemorySamples: [1_000, 5_096]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.memoryBudgetBytes = 4_096
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let listedResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.listLoadedModels(
                request: Melix_Worker_V1_ListLoadedModelsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.ListLoadedModels.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let loadedStats = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let unloadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_UnloadModelRequest()
            request.modelHandle = loadResponse.modelHandle
            return try await services.runtime.unloadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.UnloadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let postUnloadStats = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertTrue(loadResponse.ok)
        XCTAssertEqual(loadResponse.modelHandle, "melix-dev-text::1")
        XCTAssertEqual(loadResponse.estimatedResidentBytes, 4_096)
        XCTAssertEqual(listedResponse.modelHandles, ["melix-dev-text::1"])
        XCTAssertEqual(loadedStats.stats.residentBytes, 4_096)
        XCTAssertEqual(loadedStats.stats.modelResidentBytes, 4_096)
        XCTAssertEqual(loadedStats.stats.cacheResidentBytes, 0)
        XCTAssertEqual(loadedStats.stats.kvCacheBytes, 0)
        XCTAssertTrue(unloadResponse.ok)
        XCTAssertEqual(postUnloadStats.stats.residentBytes, 0)
        XCTAssertEqual(postUnloadStats.stats.modelResidentBytes, 0)
        XCTAssertEqual(services.metrics.counters["swift_text.loaded_model_count"], 0)

        let loadedSpecs = await backend.loadedSpecs()
        XCTAssertEqual(loadedSpecs.map(\.modelPath), ["mlx-community/melix-dev-text-4bit"])
    }

    func testRuntimeLifecycleRejectsModelLoadsThatExceedProcessBudgetAndReportsHeadroom() async throws {
        let services = makeServices(
            environment: [
                "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "4500",
                "MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES": "1024",
            ],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [1_000, 5_096]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let runtimeStats = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(loadResponse.ok)
        XCTAssertEqual(loadResponse.error.code, "memory_budget_exceeded")
        XCTAssertEqual(loadResponse.error.message, "Projected resident memory would exceed the process budget.")
        XCTAssertEqual(loadResponse.error.details["budget_bytes"], "4500")
        XCTAssertEqual(loadResponse.error.details["headroom_bytes"], "1024")
        XCTAssertEqual(loadResponse.error.details["projected_resident_bytes"], "4096")
        XCTAssertEqual(loadResponse.error.details["required_bytes"], "5120")
        XCTAssertEqual(runtimeStats.stats.memoryHeadroomBytes, 1_024)
        XCTAssertEqual(runtimeStats.stats.residentBytes, 0)
        let loadedModelCount = await services.registry.loadedModelCount()
        XCTAssertEqual(loadedModelCount, 0)
    }

    func testRuntimeLifecycleRejectsUnsupportedDiskStreamingMode() async throws {
        let services = makeServices(
            environment: [:],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [1_000, 5_096]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.diskStreamingMode = .diskStreamingRequireDisk
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(loadResponse.ok)
        XCTAssertEqual(loadResponse.error.code, "disk_streaming_unsupported")
        XCTAssertEqual(loadResponse.error.details["model_id"], "melix-dev-text")
        XCTAssertEqual(loadResponse.error.details["requested_mode"], "3")
        let loadedModelCount = await services.registry.loadedModelCount()
        XCTAssertEqual(loadedModelCount, 0)
    }

    func testRuntimeLifecycleRejectsModelLoadsThatExceedExplicitRequestBudget() async throws {
        let services = makeServices(
            environment: [
                "MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES": "1024",
            ],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [1_000, 5_096]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.memoryBudgetBytes = 4_500
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(loadResponse.ok)
        XCTAssertEqual(loadResponse.error.code, "memory_budget_exceeded")
        XCTAssertEqual(loadResponse.error.details["budget_bytes"], "4500")
        XCTAssertEqual(loadResponse.error.details["headroom_bytes"], "1024")
        XCTAssertEqual(loadResponse.error.details["projected_resident_bytes"], "4096")
        XCTAssertEqual(loadResponse.error.details["required_bytes"], "5120")
        let loadedModelCount = await services.registry.loadedModelCount()
        XCTAssertEqual(loadedModelCount, 0)
    }

    func testRuntimeLifecycleAllowsModelLoadsWhenMemoryEnforcementIsExplicitlyDisabled() async throws {
        let services = makeServices(
            environment: [
                "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT": "yes",
                "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "4500",
                "MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES": "1024",
            ],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [1_000, 5_096]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.memoryBudgetBytes = 4_500
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let runtimeStats = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertTrue(loadResponse.ok)
        XCTAssertEqual(loadResponse.modelHandle, "melix-dev-text::1")
        XCTAssertEqual(runtimeStats.stats.memoryHeadroomBytes, 0)
        XCTAssertEqual(runtimeStats.stats.modelResidentBytes, 4_096)
        XCTAssertEqual(services.metrics.counters["swift_text.memory_enforcement_disabled"], 1)
        let loadedModelCount = await services.registry.loadedModelCount()
        XCTAssertEqual(loadedModelCount, 1)
    }

    func testRuntimeRegistryDerivesResidencyPoliciesAndExplicitDiskStreamingDefaults() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [:]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var pinnedSpec = makeModelSpec(modelID: "pinned-model")
        pinnedSpec.settings.pinOnLoad = true
        let pinnedLoaded = try await registry.loadModel(pinnedSpec)

        var policySpec = makeModelSpec(modelID: "policy-model")
        policySpec.settings.memoryPolicy = .memoryResidencyPinned
        let policyLoaded = try await registry.loadModel(policySpec)

        var ttlAndDiskSpec = makeModelSpec(modelID: "ttl-disk-model")
        ttlAndDiskSpec.settings.ttlSeconds = 60
        ttlAndDiskSpec.settings.diskStreamingMode = .diskStreamingDisabled
        let ttlAndDiskLoaded = try await registry.loadModel(ttlAndDiskSpec)

        XCTAssertEqual(pinnedLoaded.residency.policy, .memoryResidencyPinned)
        XCTAssertEqual(policyLoaded.residency.policy, .memoryResidencyPinned)
        XCTAssertEqual(ttlAndDiskLoaded.residency.policy, .memoryResidencyTtl)
        XCTAssertEqual(ttlAndDiskLoaded.residency.effectiveDiskStreamingMode, .diskStreamingDisabled)
    }

    func testWorkerRuntimeRegistryErrorSupportsMemoryBudgetDescriptionsAndEquality() {
        let budgetError = WorkerRuntimeRegistryError.memoryBudgetExceeded(
            budgetBytes: 4_500,
            headroomBytes: 1_024,
            projectedResidentBytes: 4_096,
            requiredBytes: 5_120
        )
        let sameBudgetError = WorkerRuntimeRegistryError.memoryBudgetExceeded(
            budgetBytes: 4_500,
            headroomBytes: 1_024,
            projectedResidentBytes: 4_096,
            requiredBytes: 5_120
        )
        let differentBudgetError = WorkerRuntimeRegistryError.memoryBudgetExceeded(
            budgetBytes: 4_096,
            headroomBytes: 0,
            projectedResidentBytes: 4_096,
            requiredBytes: 4_096
        )

        XCTAssertEqual(
            budgetError.errorDescription,
            "Projected resident memory would exceed the process budget."
        )
        XCTAssertEqual(budgetError, sameBudgetError)
        XCTAssertNotEqual(budgetError, differentBudgetError)
        XCTAssertNotEqual(budgetError, .unknownModelHandle)
    }

    func testWorkerRuntimeRegistryErrorSupportsDiskStreamingMappingsAndEquality() {
        let diskStreamingError = WorkerRuntimeRegistryError.diskStreamingUnsupported(
            requestedMode: .diskStreamingRequireDisk,
            modelID: "melix-dev-text"
        )
        let sameDiskStreamingError = WorkerRuntimeRegistryError.diskStreamingUnsupported(
            requestedMode: .diskStreamingRequireDisk,
            modelID: "melix-dev-text"
        )
        let differentDiskStreamingError = WorkerRuntimeRegistryError.diskStreamingUnsupported(
            requestedMode: .diskStreamingPreferDisk,
            modelID: "melix-dev-text"
        )

        XCTAssertEqual(
            diskStreamingError.errorDescription,
            "The selected runtime does not support disk-streaming mode."
        )
        XCTAssertEqual(diskStreamingError.explicitPrefillErrorDetails["requested_mode"], "3")
        XCTAssertEqual(diskStreamingError.explicitPrefillErrorDetails["model_id"], "melix-dev-text")
        XCTAssertEqual(diskStreamingError.saveRestoreErrorCode, "failed_precondition")
        XCTAssertEqual(diskStreamingError, sameDiskStreamingError)
        XCTAssertNotEqual(diskStreamingError, differentDiskStreamingError)
    }

    func testWorkerRuntimeRegistryErrorExposesPrefillGuardMetadataAndMappings() {
        let contextError = WorkerRuntimeRegistryError.contextLimitExceeded(maxContext: 32, promptTokens: 64)
        let sameContextError = WorkerRuntimeRegistryError.contextLimitExceeded(maxContext: 32, promptTokens: 64)
        let differentContextError = WorkerRuntimeRegistryError.contextLimitExceeded(maxContext: 16, promptTokens: 64)

        XCTAssertEqual(contextError.errorDescription, "Prefill prompt exceeds the model context limit.")
        XCTAssertEqual(contextError.explicitPrefillErrorCode, "context_limit_exceeded")
        XCTAssertEqual(contextError.explicitPrefillErrorDetails["max_context"], "32")
        XCTAssertEqual(contextError.explicitPrefillErrorDetails["prompt_tokens"], "64")
        XCTAssertEqual(contextError.saveRestoreErrorCode, "out_of_range")
        XCTAssertEqual(contextError, sameContextError)
        XCTAssertNotEqual(contextError, differentContextError)

        let prefillGuardError = WorkerRuntimeRegistryError.prefillMemoryGuardExceeded(
            budgetBytes: 4_500,
            headroomBytes: 1_024,
            projectedResidentBytes: 4_096,
            promptTokens: 2,
            estimatedPrefillBytes: 4_096,
            requiredBytes: 5_120
        )
        let samePrefillGuardError = WorkerRuntimeRegistryError.prefillMemoryGuardExceeded(
            budgetBytes: 4_500,
            headroomBytes: 1_024,
            projectedResidentBytes: 4_096,
            promptTokens: 2,
            estimatedPrefillBytes: 4_096,
            requiredBytes: 5_120
        )
        let differentPrefillGuardError = WorkerRuntimeRegistryError.prefillMemoryGuardExceeded(
            budgetBytes: 4_500,
            headroomBytes: 1_024,
            projectedResidentBytes: 4_096,
            promptTokens: 3,
            estimatedPrefillBytes: 6_144,
            requiredBytes: 6_168
        )

        XCTAssertEqual(
            prefillGuardError.errorDescription,
            "Projected prefill memory would exceed the process budget."
        )
        XCTAssertEqual(prefillGuardError.explicitPrefillErrorCode, "prefill_memory_guard_exceeded")
        XCTAssertEqual(prefillGuardError.explicitPrefillErrorDetails["budget_bytes"], "4500")
        XCTAssertEqual(prefillGuardError.explicitPrefillErrorDetails["headroom_bytes"], "1024")
        XCTAssertEqual(prefillGuardError.explicitPrefillErrorDetails["projected_resident_bytes"], "4096")
        XCTAssertEqual(prefillGuardError.explicitPrefillErrorDetails["prompt_tokens"], "2")
        XCTAssertEqual(prefillGuardError.explicitPrefillErrorDetails["estimated_prefill_bytes"], "4096")
        XCTAssertEqual(prefillGuardError.explicitPrefillErrorDetails["required_bytes"], "5120")
        XCTAssertEqual(prefillGuardError.saveRestoreErrorCode, "resource_exhausted")
        XCTAssertEqual(prefillGuardError, samePrefillGuardError)
        XCTAssertNotEqual(prefillGuardError, differentPrefillGuardError)

        let quadraticError = WorkerRuntimeRegistryError.quadraticPrefillGuardExceeded(
            promptTokens: 5,
            tokenLimit: 4,
            accelerationMode: "speculative_decode"
        )
        let sameQuadraticError = WorkerRuntimeRegistryError.quadraticPrefillGuardExceeded(
            promptTokens: 5,
            tokenLimit: 4,
            accelerationMode: "speculative_decode"
        )
        let differentQuadraticError = WorkerRuntimeRegistryError.quadraticPrefillGuardExceeded(
            promptTokens: 6,
            tokenLimit: 4,
            accelerationMode: "active_kv_quantized"
        )

        XCTAssertEqual(
            quadraticError.errorDescription,
            "Prefill request exceeds the configured quadratic fallback threshold."
        )
        XCTAssertEqual(quadraticError.explicitPrefillErrorCode, "quadratic_prefill_guard_exceeded")
        XCTAssertEqual(quadraticError.explicitPrefillErrorDetails["prompt_tokens"], "5")
        XCTAssertEqual(quadraticError.explicitPrefillErrorDetails["token_limit"], "4")
        XCTAssertEqual(quadraticError.explicitPrefillErrorDetails["acceleration_mode"], "speculative_decode")
        XCTAssertEqual(quadraticError.saveRestoreErrorCode, "resource_exhausted")
        XCTAssertEqual(quadraticError, sameQuadraticError)
        XCTAssertNotEqual(quadraticError, differentQuadraticError)

        XCTAssertNil(WorkerRuntimeRegistryError.unknownModelHandle.explicitPrefillErrorCode)
        XCTAssertEqual(WorkerRuntimeRegistryError.unknownModelHandle.explicitPrefillErrorDetails, [:])
        XCTAssertEqual(WorkerRuntimeRegistryError.unknownModelHandle.saveRestoreErrorCode, "not_found")
        XCTAssertEqual(WorkerRuntimeRegistryError.snapshotModelNotLoaded.saveRestoreErrorCode, "failed_precondition")
        XCTAssertEqual(accelerationModeName(.baseline), "baseline")
        XCTAssertEqual(accelerationModeName(.acceleratedPrefill), "accelerated_prefill")
        XCTAssertEqual(accelerationModeName(.sparsePrefill), "sparse_prefill")
        XCTAssertEqual(accelerationModeName(.speculativeDecode), "speculative_decode")
        XCTAssertEqual(accelerationModeName(.activeKvQuantized), "active_kv_quantized")
        XCTAssertEqual(accelerationModeName(.UNRECOGNIZED(999)), "unspecified")
    }

    func testRuntimeLifecycleReportsLoadFailuresAndMissingHandles() async throws {
        let services = makeServices(
            backend: FakeRuntimeBackend(loadError: FakeRuntimeBackendError.loadFailed),
            residentMemorySamples: [1_000, 1_000]
        )

        let failedLoad = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let missingUnload = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_UnloadModelRequest()
            request.modelHandle = "missing-handle"
            return try await services.runtime.unloadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.UnloadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(failedLoad.ok)
        XCTAssertEqual(failedLoad.error.code, "load_failed")
        XCTAssertFalse(missingUnload.ok)
        XCTAssertEqual(missingUnload.error.code, "not_found")
    }

    func testInferenceUnaryFallbackRpcsReturnStructuredUnimplemented() async throws {
        let services = makeServices()

        let embedResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.embed(
                request: Melix_Worker_V1_EmbedRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Embed.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let rerankResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.rerank(
                request: Melix_Worker_V1_RerankRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Rerank.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let transcribeResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.transcribe(
                request: Melix_Worker_V1_TranscribeRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Transcribe.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let speakResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.speak(
                request: Melix_Worker_V1_SpeakRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Speak.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let speakStreamWriter = RecordingRPCWriter<Melix_Worker_V1_SpeakStreamEvent>()
        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.speakStream(
                request: Melix_Worker_V1_SpeakRequest(),
                response: RPCWriter(wrapping: speakStreamWriter),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.SpeakStream.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let imageGenerateResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.imageGenerate(
                request: Melix_Worker_V1_ImageGenerateRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.ImageGenerate.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let imageEditResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.imageEdit(
                request: Melix_Worker_V1_ImageEditRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.ImageEdit.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let speakStreamEvents = await speakStreamWriter.snapshot()

        XCTAssertEqual(embedResponse.error.code, "unimplemented")
        XCTAssertEqual(rerankResponse.error.code, "unimplemented")
        XCTAssertEqual(transcribeResponse.error.code, "unimplemented")
        XCTAssertEqual(speakResponse.error.code, "unimplemented")
        XCTAssertEqual(speakStreamEvents.map(\.kind), [.error])
        XCTAssertEqual(speakStreamEvents.first?.error.code, "unimplemented")
        XCTAssertEqual(imageGenerateResponse.error.code, "unimplemented")
        XCTAssertEqual(imageEditResponse.error.code, "unimplemented")
        XCTAssertEqual(imageGenerateResponse.job.state, .imageJobFailed)
        XCTAssertEqual(imageGenerateResponse.job.operation, "image_generate")
        XCTAssertEqual(imageEditResponse.job.state, .imageJobFailed)
        XCTAssertEqual(imageEditResponse.job.operation, "image_edit")
    }

    func testPrefillReturnsDecodeHandleAndMetricsForLoadedModel() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [100, 2_148]
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-success"
            request.execution.modelHandle = loadResponse.modelHandle
            request.returnDecodeHandle = true
            request.prefillStepSize = 32
            request.resumeHint = "tool-follow-up"
            request.execution.acceleration.mode = .baseline
            request.messages = [makeUserMessage("prefill me")]

            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let stored = await services.registry.prefillContext(for: response.decodeHandle)
        let contextCount = await services.registry.prefillContextCount()
        let metrics = services.metrics.counters

        XCTAssertTrue(response.ok)
        XCTAssertFalse(response.decodeHandle.isEmpty)
        XCTAssertFalse(response.blockTableID.isEmpty)
        XCTAssertEqual(response.blockTable.blocks.count, 1)
        XCTAssertEqual(response.promptTokens, 1)
        XCTAssertEqual(response.lifecyclePhase, .executionPrefilling)
        XCTAssertEqual(response.admissionState, .admissionAdmitted)
        XCTAssertEqual(response.appliedAcceleration.mode, .baseline)
        XCTAssertEqual(contextCount, 1)
        XCTAssertEqual(stored?.modelHandle, loadResponse.modelHandle)
        XCTAssertEqual(stored?.promptTokens, 1)
        XCTAssertEqual(metrics["swift_text.prefill_context_count"], 1)
        XCTAssertEqual(metrics["swift_text.prefill_prompt_tokens"], 1)
        XCTAssertEqual(metrics["swift_text.accelerated_prefill_gain_pct"], 0)
        XCTAssertEqual(metrics["swift_text.active_kv_quantization_ratio"], 0)
        XCTAssertEqual(metrics["swift_text.cache_block_count"], 1)
        XCTAssertEqual(metrics["swift_text.cache_prefix_count"], 1)
        XCTAssertNotNil(metrics["swift_text.prefill_ms"])
    }

    func testPrefillHonorsPreferredBlockSizeAheadOfInitialBlockTarget() async throws {
        let services = makeServices(
            environment: [
                "MELIX_SWIFT_TEXT_WORKER_INITIAL_CACHE_BLOCKS": "4",
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
            ],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let messages = (0..<80).map { _ in makeUserMessage("token") }
        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-preferred-block-size"
            request.execution.modelHandle = loadResponse.modelHandle
            request.execution.cacheHints.preferredBlockSize = 32
            request.returnDecodeHandle = true
            request.prefillStepSize = 32
            request.execution.acceleration.mode = .baseline
            request.messages = messages

            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.promptTokens, 80)
        XCTAssertEqual(response.blockTable.blocks.count, 3)
    }

    func testPrefillReturnsAcceleratedPrefillMetricsAndStoredAppliedPolicy() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-accelerated"
            request.execution.modelHandle = loadResponse.modelHandle
            request.execution.acceleration.mode = .acceleratedPrefill
            request.execution.acceleration.prefillHint = "json-schema"
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("{\"kind\":\"structured\"}")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let stored = await services.registry.prefillContext(for: response.decodeHandle)
        let metrics = services.metrics.counters

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.appliedAcceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(response.appliedAcceleration.prefillHint, "json-schema")
        XCTAssertEqual(metrics["swift_text.accelerated_prefill_gain_pct"], 50)
        XCTAssertEqual(stored?.acceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(stored?.acceleration.prefillHint, "json-schema")
    }

    func testPrefillReturnsActiveKVQuantizationRatioAndNormalizedProfile() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-active-kv"
            request.execution.modelHandle = loadResponse.modelHandle
            request.execution.acceleration.mode = .activeKvQuantized
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("cache quantized")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let stored = await services.registry.prefillContext(for: response.decodeHandle)
        let metrics = services.metrics.counters

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.appliedAcceleration.mode, .activeKvQuantized)
        XCTAssertEqual(response.appliedAcceleration.activeKvQuantProfile, "turboquant-q4")
        XCTAssertEqual(metrics["swift_text.active_kv_quantization_ratio"], 25)
        XCTAssertEqual(stored?.acceleration.mode, .activeKvQuantized)
        XCTAssertEqual(stored?.acceleration.activeKvQuantProfile, "turboquant-q4")
    }

    func testPrefillTracksSparsePrefillProtectionAndSkipMetrics() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-sparse"
            request.execution.modelHandle = loadResponse.modelHandle
            request.execution.acceleration.mode = .sparsePrefill
            request.returnDecodeHandle = true
            request.messages = [
                makeSystemMessage("{\"guard\":\"always\"}\n{\"rules\":[1,2,3]}"),
                makeUserMessage("{\"kind\":\"structured\"}", extraText: "{\"kind\":\"structured\"}")
            ]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let metrics = services.metrics.counters

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.appliedAcceleration.mode, .sparsePrefill)
        XCTAssertEqual(metrics["swift_text.sparse_prefill_accepted_skip_count"], 1)
        XCTAssertEqual(metrics["swift_text.sparse_prefill_rejected_opportunity_count"], 1)
        XCTAssertEqual(metrics["swift_text.sparse_prefill_protected_region_count"], 1)
    }

    func testPrefillSurfacesActivePrefillInRuntimeStatsWhileRunning() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(prefillDelayNanos: 150_000_000)
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let task = Task {
            try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-prefill-busy"
                request.execution.modelHandle = loadResponse.modelHandle
                request.returnDecodeHandle = true
                request.messages = [makeUserMessage("slow prefill")]
                return try await services.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
        }

        try? await Task.sleep(nanoseconds: 30_000_000)

        let statsWhileBusy = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        _ = try await task.value

        let statsAfter = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertEqual(statsWhileBusy.stats.workerState, "busy")
        XCTAssertEqual(statsWhileBusy.stats.activeRequests, 1)
        XCTAssertEqual(statsWhileBusy.stats.activePrefills, 1)
        XCTAssertEqual(statsWhileBusy.stats.activeDecodes, 0)
        XCTAssertEqual(statsAfter.stats.activePrefills, 0)
    }

    func testPrefillAbortStopsBeforeRegisteringDecodeContext() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(prefillDelayNanos: 120_000_000)
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let prefillTask = Task {
            try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-prefill-abort"
                request.execution.modelHandle = loadResponse.modelHandle
                request.returnDecodeHandle = true
                request.messages = [makeUserMessage("abort slow prefill before context registration")]
                return try await services.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
        }

        try await Task.sleep(nanoseconds: 30_000_000)

        let abortResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_AbortRequest()
            request.requestID = "req-prefill-abort"
            return try await services.inference.abort(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Abort.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await prefillTask.value
        let contextCount = await services.registry.prefillContextCount()
        let statsAfter = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.getRuntimeStats(
                request: Melix_Worker_V1_GetRuntimeStatsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.GetRuntimeStats.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertTrue(abortResponse.ok)
        XCTAssertTrue(abortResponse.found)
        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "cancelled")
        XCTAssertTrue(response.decodeHandle.isEmpty)
        XCTAssertEqual(contextCount, 0)
        XCTAssertEqual(statsAfter.stats.activePrefills, 0)
        XCTAssertEqual(statsAfter.stats.activeRequests, 0)
    }

    func testPrefillReturnsNotFoundForUnknownModelHandle() async throws {
        let services = makeServices()

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-missing"
            request.execution.modelHandle = "missing-handle"
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("missing")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "not_found")
    }

    func testPrefillReturnsRuntimeErrorForBackendFailureWithoutRequestID() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(prefillError: FakeRuntimeBackendError.prefillFailed)
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.modelHandle = loadResponse.modelHandle
            request.returnDecodeHandle = true
            request.messages = [makeUserMessage("prefill error")]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "runtime_error")
        XCTAssertEqual(services.metrics.counters["swift_text.rpc_error_count"], 1)
        XCTAssertNotNil(services.metrics.counters["swift_text.prefill_ms"])
    }

    func testPrefillReturnsContextLimitExceededForOversizedRequests() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-context-limit-rpc"
            request.execution.modelHandle = loadResponse.modelHandle
            request.returnDecodeHandle = true
            request.execution.acceleration.mode = .baseline
            request.messages = [makeUserMessage(repeatingTokenPrompt(count: 8_193))]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "context_limit_exceeded")
        XCTAssertEqual(response.error.details["max_context"], "8192")
        XCTAssertEqual(response.error.details["prompt_tokens"], "8193")
        XCTAssertEqual(services.metrics.counters["swift_text.prefill_guard_rejection_count"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.prefill_context_limit_rejection_count"], 1)
    }

    func testPrefillReturnsExplicitMemoryGuardFailures() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "4500",
                "MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES": "1024",
            ],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-memory-guard-rpc"
            request.execution.modelHandle = loadResponse.modelHandle
            request.returnDecodeHandle = true
            request.execution.acceleration.mode = .baseline
            request.messages = [makeUserMessage(repeatingTokenPrompt(count: 2))]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "prefill_memory_guard_exceeded")
        XCTAssertEqual(response.error.details["budget_bytes"], "4500")
        XCTAssertEqual(response.error.details["headroom_bytes"], "1024")
        XCTAssertEqual(response.error.details["prompt_tokens"], "2")
        XCTAssertEqual(response.error.details["required_bytes"], "5120")
        XCTAssertEqual(services.metrics.counters["swift_text.prefill_guard_rejection_count"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.prefill_memory_guard_rejection_count"], 1)
    }

    func testPrefillReturnsQuadraticGuardFailuresForLargeBaselineRequests() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_PREFILL_QUADRATIC_GUARD_TOKEN_THRESHOLD": "4",
            ],
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_PrefillRequest()
            request.execution.id.requestID = "req-prefill-quadratic-guard-rpc"
            request.execution.modelHandle = loadResponse.modelHandle
            request.returnDecodeHandle = true
            request.execution.acceleration.mode = .baseline
            request.messages = [makeUserMessage(repeatingTokenPrompt(count: 5))]
            return try await services.inference.prefill(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.error.code, "quadratic_prefill_guard_exceeded")
        XCTAssertEqual(response.error.details["prompt_tokens"], "5")
        XCTAssertEqual(response.error.details["token_limit"], "4")
        XCTAssertEqual(response.error.details["acceleration_mode"], "baseline")
        XCTAssertEqual(services.metrics.counters["swift_text.prefill_guard_rejection_count"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.prefill_quadratic_guard_rejection_count"], 1)
    }

    func testGenerateStreamsPrefillTokenUsageAndCompletedForLoadedModel() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(),
            residentMemorySamples: [100, 2_148]
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-generate-success"
        request.execution.modelHandle = loadResponse.modelHandle
        request.returnUsage = true
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Say hello from Swift."
        message.parts = [part]
        request.messages = [message]

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.generate(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Generate.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertGreaterThanOrEqual(recorded.count, 3)
        XCTAssertEqual(recorded.first?.requestID, "req-generate-success")
        XCTAssertEqual(recorded.first?.executionKind, "generate")
        XCTAssertTrue(matches(recorded.first?.payload, .prefillStarted))
        XCTAssertTrue(recorded.contains(where: { matches($0.payload, .tokenDelta) }))
        XCTAssertTrue(recorded.contains(where: { matches($0.payload, .usageDelta) }))
        XCTAssertTrue(matches(recorded.last?.payload, .completed))
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
        XCTAssertFalse(recorded.last?.completed.assistantText.isEmpty ?? true)
        XCTAssertEqual(services.metrics.counters["swift_text.stream_event_count"], recorded.count)
    }

    func testGenerateSuppressesHarmonyThoughtChannelForLoadedModel() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(generatedChunks: [
                "<|channel>thought\n<channel|>\n{\"output\":\"pwd\",\"exit_code\":0}",
                "<|channel>final\n<channel|>\nRepository reviewed.",
            ])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-harmony-generate"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.ext["melix.harmony"] = "true"
        request.returnUsage = true
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Review the repo."
        message.parts = [part]
        request.messages = [message]

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.generate(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Generate.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        let tokenText = recorded.compactMap { event -> String? in
            guard case .tokenDelta(let token) = event.payload else {
                return nil
            }
            return token.text
        }
        let reasoningText = recorded.compactMap { event -> String? in
            guard case .reasoningDelta(let reasoning) = event.payload else {
                return nil
            }
            return reasoning.text
        }
        let usage = try XCTUnwrap(recorded.first { event in
            matches(event.payload, .usageDelta)
        }?.usageDelta)

        XCTAssertEqual(tokenText, ["\nRepository reviewed."])
        XCTAssertEqual(reasoningText, ["\n{\"output\":\"pwd\",\"exit_code\":0}"])
        XCTAssertEqual(usage.completionTokens, 2)
        XCTAssertEqual(recorded.last?.completed.assistantText, "\nRepository reviewed.")
        XCTAssertFalse(recorded.last?.completed.assistantText.contains("<|channel>") ?? true)
        XCTAssertFalse(recorded.last?.completed.assistantText.contains("pwd") ?? true)
        let metrics = services.metrics.counters
        XCTAssertGreaterThan(metrics["swift_text.generate_harmony_filter_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.generate_harmony_filter_call_count"], 3)
        XCTAssertGreaterThan(metrics["swift_text.generate_harmony_filter_avg_us"] ?? 0, 0)
        XCTAssertGreaterThan(metrics["swift_text.generate_grpc_write_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.generate_grpc_write_call_count"], recorded.count)
        XCTAssertGreaterThan(metrics["swift_text.generate_grpc_write_avg_us"] ?? 0, 0)
    }

    func testDecodeCoalescesGemmaVisibleTokenDeltasAfterFirstToken() async throws {
        let services = makeServices(
            backend: FakeRuntimeBackend(
                generatedChunks: ["unused"],
                decodedChunks: ["A", "B", "C", "D", "E", "F"]
            )
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "unsloth/gemma-4-E4B-it-MLX-8bit"
            request.model.modelPath = "unsloth/gemma-4-E4B-it-MLX-8bit"
            request.model.requestRoutes = [makeTextRequestRoute()]
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-gemma-cadence-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Continue."
        message.parts = [part]
        prefillRequest.messages = [message]

        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-gemma-cadence"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.maxOutputTokens = 6
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        let tokenText = recorded.compactMap { event -> String? in
            guard case .tokenDelta(let token) = event.payload else {
                return nil
            }
            return token.text
        }
        let usage = try XCTUnwrap(recorded.first { event in
            matches(event.payload, .usageDelta)
        }?.usageDelta)

        XCTAssertEqual(tokenText, ["A", "BCDE", "F"])
        XCTAssertEqual(usage.completionTokens, 6)
        XCTAssertEqual(recorded.last?.completed.assistantText, "ABCDEF")
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.decode_stream_event_count"], recorded.count)
        XCTAssertEqual(metrics["swift_text.decode_grpc_write_call_count"], recorded.count)
        XCTAssertEqual(recorded.count, 6)
    }

    func testDecodeDoesNotCoalesceNonGemmaVisibleTokenDeltas() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(
                generatedChunks: ["unused"],
                decodedChunks: ["A", "B", "C", "D", "E", "F"]
            )
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-non-gemma-cadence-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Continue."
        message.parts = [part]
        prefillRequest.messages = [message]

        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-non-gemma-cadence"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.maxOutputTokens = 6
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        let tokenText = recorded.compactMap { event -> String? in
            guard case .tokenDelta(let token) = event.payload else {
                return nil
            }
            return token.text
        }
        let usage = try XCTUnwrap(recorded.first { event in
            matches(event.payload, .usageDelta)
        }?.usageDelta)

        XCTAssertEqual(tokenText, ["A", "B", "C", "D", "E", "F"])
        XCTAssertEqual(usage.completionTokens, 6)
        XCTAssertEqual(recorded.last?.completed.assistantText, "ABCDEF")
        XCTAssertEqual(recorded.count, 9)
    }

    func testDecodeFlushesPendingVisibleDeltasBeforeReasoningDeltas() async throws {
        let services = makeServices(
            backend: FakeRuntimeBackend(
                generatedChunks: ["unused"],
                decodedChunks: [
                    "A",
                    "B",
                    "<|channel>thought\n<channel|>R",
                    "<|channel>final\n<channel|>C",
                ]
            )
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "unsloth/gemma-4-E4B-it-MLX-8bit"
            request.model.modelPath = "unsloth/gemma-4-E4B-it-MLX-8bit"
            request.model.requestRoutes = [makeTextRequestRoute()]
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-gemma-reasoning-cadence-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Think and answer."
        message.parts = [part]
        prefillRequest.messages = [message]

        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-gemma-reasoning-cadence"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.maxOutputTokens = 4
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let payloadText = (await writer.snapshot()).compactMap { event -> String? in
            switch event.payload {
            case .tokenDelta(let token):
                return "token:\(token.text)"
            case .reasoningDelta(let reasoning):
                return "reasoning:\(reasoning.text)"
            default:
                return nil
            }
        }

        XCTAssertEqual(payloadText, ["token:A", "token:B", "reasoning:R", "token:C"])
    }

    func testGenerateReturnsNotFoundErrorEventForUnknownModelHandle() async throws {
        let services = makeServices()
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-generate-missing"
        request.execution.modelHandle = "missing-model-handle"

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.generate(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Generate.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].requestID, "req-generate-missing")
        XCTAssertEqual(recorded[0].executionKind, "generate")
        XCTAssertTrue(matches(recorded[0].payload, .error))
        XCTAssertEqual(recorded[0].error.error.code, "not_found")
    }

    func testAbortCancelsActiveGenerationAndReportsCancelledCompletion() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(
                generatedChunks: ["one", " two", " three", " four"],
                tokenDelayNanos: 40_000_000
            ),
            residentMemorySamples: [100, 2_148]
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var generateRequest = Melix_Worker_V1_GenerateRequest()
        generateRequest.execution.id.requestID = "req-generate-abort"
        generateRequest.execution.modelHandle = loadResponse.modelHandle
        var message = Melix_Worker_V1_ChatMessage()
        message.role = "user"
        var part = Melix_Worker_V1_MessagePart()
        part.text = "Generate enough tokens to be cancellable."
        message.parts = [part]
        generateRequest.messages = [message]

        let generateTask = Task {
            try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.generate(
                    request: generateRequest,
                    response: RPCWriter(wrapping: writer),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Generate.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
        }

        try await Task.sleep(nanoseconds: 20_000_000)

        let abortResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_AbortRequest()
            request.requestID = "req-generate-abort"
            return try await services.inference.abort(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Abort.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        _ = try await generateTask.value

        let recorded = await writer.snapshot()
        XCTAssertTrue(abortResponse.ok)
        XCTAssertTrue(abortResponse.found)
        XCTAssertGreaterThanOrEqual(recorded.count, 2)
        XCTAssertTrue(matches(recorded.last?.payload, .completed))
        XCTAssertEqual(recorded.last?.completed.finishReason, "cancelled")
        XCTAssertNotNil(services.metrics.counters["swift_text.abort_ms"])
    }

    func testDecodeStreamingRpcStreamsTokensAndCleansUpStoredContext() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(decodedChunks: ["decode", " result"])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-decode-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("decode rpc")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.scheduling.lane = "text.decode.batch"
        request.decodeHandle = prefillResponse.decodeHandle
        request.maxOutputTokens = 1
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertGreaterThanOrEqual(recorded.count, 4)
        XCTAssertEqual(recorded[0].decodeStarted.decodeHandle, prefillResponse.decodeHandle)
        XCTAssertEqual(recorded[0].executionKind, "decode")
        XCTAssertEqual(recorded[0].lane, "text.decode.batch")
        XCTAssertEqual(recorded[1].tokenDelta.text, "decode")
        XCTAssertEqual(recorded[2].usageDelta.completionTokens, 1)
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
        let storedAfterDecode = await services.registry.prefillContext(for: prefillResponse.decodeHandle)
        XCTAssertNil(storedAfterDecode)
        XCTAssertEqual(services.metrics.counters["swift_text.decode_batch_size"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.model_eval_batch_size"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.decode_batch_observation_count"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.decode_loop_iterations"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.per_batch_output_token_count"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.per_batch_output_tokens_per_second"], 8)
        XCTAssertEqual(services.metrics.counters["swift_text.decode_tokens_per_second"], 8)
    }

    func testDecodeStreamingRpcBatchesHomogeneousDeterministicDecodeRequests() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "deterministic",
            ],
            backend: DeterministicTextBackend(tokenDelayNanos: 0)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest1 = Melix_Worker_V1_PrefillRequest()
        prefillRequest1.execution.id.requestID = "req-batch-decode-1"
        prefillRequest1.execution.modelHandle = loadResponse.modelHandle
        prefillRequest1.returnDecodeHandle = true
        prefillRequest1.messages = [makeUserMessage("batch decode alpha")]

        var prefillRequest2 = Melix_Worker_V1_PrefillRequest()
        prefillRequest2.execution.id.requestID = "req-batch-decode-2"
        prefillRequest2.execution.modelHandle = loadResponse.modelHandle
        prefillRequest2.returnDecodeHandle = true
        prefillRequest2.messages = [makeUserMessage("batch decode beta")]

        let prefillResponse1 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest1,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        let prefillResponse2 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest2,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.maxOutputTokens = 2

        let writer1 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request1 = Melix_Worker_V1_DecodeRequest()
        request1.execution.id.requestID = "req-batch-decode-1"
        request1.execution.modelHandle = loadResponse.modelHandle
        request1.execution.scheduling.lane = "text.decode.batch"
        request1.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request1.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request1.execution.ext["melix.scheduler.admission_batch_capacity"] = "2"
        request1.execution.ext["melix.scheduler.admission_cohort_size"] = "2"
        request1.decodeHandle = prefillResponse1.decodeHandle
        request1.sampling = sampling
        request1.maxOutputTokens = 2
        request1.returnUsage = true

        let writer2 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request2 = Melix_Worker_V1_DecodeRequest()
        request2.execution.id.requestID = "req-batch-decode-2"
        request2.execution.modelHandle = loadResponse.modelHandle
        request2.execution.scheduling.lane = "text.decode.batch"
        request2.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request2.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request2.execution.ext["melix.scheduler.admission_batch_capacity"] = "2"
        request2.execution.ext["melix.scheduler.admission_cohort_size"] = "2"
        request2.decodeHandle = prefillResponse2.decodeHandle
        request2.sampling = sampling
        request2.maxOutputTokens = 2
        request2.returnUsage = true

        async let decode1: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request1,
                response: RPCWriter(wrapping: writer1),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        async let decode2: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request2,
                response: RPCWriter(wrapping: writer2),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        _ = try await (decode1, decode2)

        let recorded1 = await writer1.snapshot()
        let recorded2 = await writer2.snapshot()
        XCTAssertEqual(recorded1.first?.decodeStarted.decodeHandle, prefillResponse1.decodeHandle)
        XCTAssertEqual(recorded2.first?.decodeStarted.decodeHandle, prefillResponse2.decodeHandle)
        XCTAssertTrue(recorded1.contains(where: { matches($0.payload, .tokenDelta) }))
        XCTAssertTrue(recorded2.contains(where: { matches($0.payload, .tokenDelta) }))
        XCTAssertEqual(recorded1.first { matches($0.payload, .usageDelta) }?.usageDelta.completionTokens, 2)
        XCTAssertEqual(recorded2.first { matches($0.payload, .usageDelta) }?.usageDelta.completionTokens, 2)
        XCTAssertEqual(recorded1.last?.completed.finishReason, "stop")
        XCTAssertEqual(recorded2.last?.completed.finishReason, "stop")

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.decode_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.decode_batch_size_max"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size_max"], 2)
        XCTAssertEqual(metrics["swift_text.decode_batch_observation_count"], 2)
        XCTAssertEqual(metrics["swift_text.decode_loop_iterations"], 2)
        XCTAssertEqual(metrics["swift_text.per_batch_output_token_count"], 4)
        XCTAssertGreaterThan(metrics["swift_text.per_batch_output_tokens_per_second"] ?? 0, 0)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_loop_total_us"] ?? 0, 0)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_model_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_batch_model_call_count"], 2)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_model_avg_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_batch_model_eval_sync_call_count"], 0)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_sample_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_batch_sample_call_count"], 4)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_token_eval_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_batch_token_eval_call_count"], 4)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_token_eval_avg_us"] ?? 0, 0)
        XCTAssertGreaterThan(metrics["swift_text.decode_harmony_filter_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_harmony_filter_call_count"], 6)
        XCTAssertGreaterThan(metrics["swift_text.decode_harmony_filter_avg_us"] ?? 0, 0)
        XCTAssertGreaterThan(metrics["swift_text.decode_grpc_write_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_grpc_write_call_count"], 10)
        XCTAssertGreaterThan(metrics["swift_text.decode_grpc_write_avg_us"] ?? 0, 0)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_token_id_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_batch_token_id_call_count"], 4)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_detokenize_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_batch_detokenize_call_count"], 4)
        XCTAssertGreaterThan(metrics["swift_text.decode_batch_stream_yield_total_us"] ?? 0, 0)
        XCTAssertEqual(metrics["swift_text.decode_batch_stream_yield_call_count"], 4)
    }

    func testDecodeStreamingRpcBatchesHomogeneousRequestsAcrossConfiguredPendingWindow() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "deterministic",
                // Keep the window above CI scheduling jitter; this test asserts batching, not a timing SLA.
                "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_PENDING_WINDOW_MS": "1000",
            ],
            backend: DeterministicTextBackend(tokenDelayNanos: 0)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest1 = Melix_Worker_V1_PrefillRequest()
        prefillRequest1.execution.id.requestID = "req-batch-window-1"
        prefillRequest1.execution.modelHandle = loadResponse.modelHandle
        prefillRequest1.returnDecodeHandle = true
        prefillRequest1.messages = [makeUserMessage("batch window alpha")]

        var prefillRequest2 = Melix_Worker_V1_PrefillRequest()
        prefillRequest2.execution.id.requestID = "req-batch-window-2"
        prefillRequest2.execution.modelHandle = loadResponse.modelHandle
        prefillRequest2.returnDecodeHandle = true
        prefillRequest2.messages = [makeUserMessage("batch window beta")]

        let prefillResponse1 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest1,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        let prefillResponse2 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest2,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.maxOutputTokens = 2

        let writer1 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request1 = Melix_Worker_V1_DecodeRequest()
        request1.execution.id.requestID = "req-batch-window-1"
        request1.execution.modelHandle = loadResponse.modelHandle
        request1.execution.scheduling.lane = "text.decode.batch"
        request1.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request1.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request1.decodeHandle = prefillResponse1.decodeHandle
        request1.sampling = sampling
        request1.maxOutputTokens = 2
        request1.returnUsage = true

        let writer2 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request2 = Melix_Worker_V1_DecodeRequest()
        request2.execution.id.requestID = "req-batch-window-2"
        request2.execution.modelHandle = loadResponse.modelHandle
        request2.execution.scheduling.lane = "text.decode.batch"
        request2.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request2.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request2.decodeHandle = prefillResponse2.decodeHandle
        request2.sampling = sampling
        request2.maxOutputTokens = 2
        request2.returnUsage = true

        async let decode1: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request1,
                response: RPCWriter(wrapping: writer1),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        try await Task.sleep(nanoseconds: 10_000_000)
        async let decode2: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request2,
                response: RPCWriter(wrapping: writer2),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        _ = try await (decode1, decode2)

        let recorded1 = await writer1.snapshot()
        let recorded2 = await writer2.snapshot()
        XCTAssertEqual(recorded1.first?.decodeStarted.decodeHandle, prefillResponse1.decodeHandle)
        XCTAssertEqual(recorded2.first?.decodeStarted.decodeHandle, prefillResponse2.decodeHandle)
        XCTAssertTrue(recorded1.contains(where: { matches($0.payload, .tokenDelta) }))
        XCTAssertTrue(recorded2.contains(where: { matches($0.payload, .tokenDelta) }))

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.decode_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.decode_batch_size_max"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size_max"], 2)
    }

    func testDecodeStreamingRpcCancelsOneBatchedRequestWhilePeerCompletes() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "deterministic",
                "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_PENDING_WINDOW_MS": "50",
            ],
            backend: DeterministicTextBackend(tokenDelayNanos: 40_000_000)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest1 = Melix_Worker_V1_PrefillRequest()
        prefillRequest1.execution.id.requestID = "req-batch-cancel-1"
        prefillRequest1.execution.modelHandle = loadResponse.modelHandle
        prefillRequest1.returnDecodeHandle = true
        prefillRequest1.messages = [makeUserMessage("batch cancel alpha")]

        var prefillRequest2 = Melix_Worker_V1_PrefillRequest()
        prefillRequest2.execution.id.requestID = "req-batch-cancel-2"
        prefillRequest2.execution.modelHandle = loadResponse.modelHandle
        prefillRequest2.returnDecodeHandle = true
        prefillRequest2.messages = [makeUserMessage("batch cancel beta")]

        let prefillResponse1 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest1,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        let prefillResponse2 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest2,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.maxOutputTokens = 3

        let writer1 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request1 = Melix_Worker_V1_DecodeRequest()
        request1.execution.id.requestID = "req-batch-cancel-1"
        request1.execution.modelHandle = loadResponse.modelHandle
        request1.execution.scheduling.lane = "text.decode.batch"
        request1.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request1.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request1.execution.ext["melix.scheduler.admission_cohort_id"] = "cohort-batch-cancel"
        request1.execution.ext["melix.scheduler.admission_cohort_size"] = "2"
        request1.execution.ext["melix.scheduler.admission_batch_capacity"] = "2"
        request1.decodeHandle = prefillResponse1.decodeHandle
        request1.sampling = sampling
        request1.maxOutputTokens = 3
        request1.returnUsage = true

        let writer2 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request2 = Melix_Worker_V1_DecodeRequest()
        request2.execution.id.requestID = "req-batch-cancel-2"
        request2.execution.modelHandle = loadResponse.modelHandle
        request2.execution.scheduling.lane = "text.decode.batch"
        request2.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request2.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request2.execution.ext["melix.scheduler.admission_cohort_id"] = "cohort-batch-cancel"
        request2.execution.ext["melix.scheduler.admission_cohort_size"] = "2"
        request2.execution.ext["melix.scheduler.admission_batch_capacity"] = "2"
        request2.decodeHandle = prefillResponse2.decodeHandle
        request2.sampling = sampling
        request2.maxOutputTokens = 3
        request2.returnUsage = true

        async let decode1: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request1,
                response: RPCWriter(wrapping: writer1),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        async let decode2: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request2,
                response: RPCWriter(wrapping: writer2),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        try await Task.sleep(nanoseconds: 75_000_000)
        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var abortRequest = Melix_Worker_V1_AbortRequest()
            abortRequest.requestID = "req-batch-cancel-1"
            return try await services.inference.abort(
                request: abortRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Abort.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        _ = try await (decode1, decode2)

        let recorded1 = await writer1.snapshot()
        let recorded2 = await writer2.snapshot()
        let cancelledKinds = payloadKinds(recorded1)
        XCTAssertEqual(cancelledKinds.first, .decodeStarted)
        XCTAssertEqual(cancelledKinds.last, .completed)
        XCTAssertFalse(cancelledKinds.contains(.usageDelta))
        XCTAssertEqual(payloadKinds(recorded2), [.decodeStarted, .tokenDelta, .tokenDelta, .tokenDelta, .usageDelta, .completed])
        XCTAssertEqual(recorded1.last?.completed.finishReason, "cancelled")
        XCTAssertFalse(recorded1.contains(where: { matches($0.payload, .usageDelta) }))
        XCTAssertEqual(recorded2.first { matches($0.payload, .usageDelta) }?.usageDelta.completionTokens, 3)
        XCTAssertEqual(recorded2.last?.completed.finishReason, "stop")

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.decode_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.decode_batch_size_max"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size_max"], 2)
    }

    func testDecodeStreamingRpcWaitsForSchedulerCohortBeyondOrdinaryPendingWindow() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "deterministic",
                "MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_PENDING_WINDOW_MS": "10",
            ],
            backend: DeterministicTextBackend(tokenDelayNanos: 0)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest1 = Melix_Worker_V1_PrefillRequest()
        prefillRequest1.execution.id.requestID = "req-scheduler-cohort-1"
        prefillRequest1.execution.modelHandle = loadResponse.modelHandle
        prefillRequest1.returnDecodeHandle = true
        prefillRequest1.messages = [makeUserMessage("scheduler cohort alpha")]

        var prefillRequest2 = Melix_Worker_V1_PrefillRequest()
        prefillRequest2.execution.id.requestID = "req-scheduler-cohort-2"
        prefillRequest2.execution.modelHandle = loadResponse.modelHandle
        prefillRequest2.returnDecodeHandle = true
        prefillRequest2.messages = [makeUserMessage("scheduler cohort beta")]

        let prefillResponse1 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest1,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        let prefillResponse2 = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest2,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var sampling = Melix_Worker_V1_SamplingConfig()
        sampling.maxOutputTokens = 2

        let writer1 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request1 = Melix_Worker_V1_DecodeRequest()
        request1.execution.id.requestID = "req-scheduler-cohort-1"
        request1.execution.modelHandle = loadResponse.modelHandle
        request1.execution.scheduling.lane = "text.decode.batch"
        request1.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request1.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request1.execution.ext["melix.scheduler.admission_cohort_id"] = "cohort-delayed-decode"
        request1.execution.ext["melix.scheduler.admission_cohort_size"] = "2"
        request1.execution.ext["melix.scheduler.admission_batch_capacity"] = "2"
        request1.decodeHandle = prefillResponse1.decodeHandle
        request1.sampling = sampling
        request1.maxOutputTokens = 2
        request1.returnUsage = true

        let writer2 = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request2 = Melix_Worker_V1_DecodeRequest()
        request2.execution.id.requestID = "req-scheduler-cohort-2"
        request2.execution.modelHandle = loadResponse.modelHandle
        request2.execution.scheduling.lane = "text.decode.batch"
        request2.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request2.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request2.execution.ext["melix.scheduler.admission_cohort_id"] = "cohort-delayed-decode"
        request2.execution.ext["melix.scheduler.admission_cohort_size"] = "2"
        request2.execution.ext["melix.scheduler.admission_batch_capacity"] = "2"
        request2.decodeHandle = prefillResponse2.decodeHandle
        request2.sampling = sampling
        request2.maxOutputTokens = 2
        request2.returnUsage = true

        async let decode1: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request1,
                response: RPCWriter(wrapping: writer1),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        try await Task.sleep(nanoseconds: 100_000_000)
        async let decode2: Void = withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request2,
                response: RPCWriter(wrapping: writer2),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        _ = try await (decode1, decode2)

        let recorded1 = await writer1.snapshot()
        let recorded2 = await writer2.snapshot()
        XCTAssertTrue(recorded1.contains(where: { matches($0.payload, .tokenDelta) }))
        XCTAssertTrue(recorded2.contains(where: { matches($0.payload, .tokenDelta) }))

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.decode_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.decode_batch_size_max"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size"], 2)
        XCTAssertEqual(metrics["swift_text.model_eval_batch_size_max"], 2)
    }

    func testDecodeStreamingRpcFallsBackWhenHomogeneousBatchDecodeUnsupported() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["one"])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-unsupported-batch"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("unsupported batch")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-unsupported-batch"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.ext["melix.gateway.concurrent_processing"] = "true"
        request.execution.ext["melix.gateway.max_concurrent_sequences"] = "2"
        request.execution.ext["melix.gateway.completion_batch_size"] = "2"
        request.decodeHandle = prefillResponse.decodeHandle
        request.maxOutputTokens = 1
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.first?.decodeStarted.decodeHandle, prefillResponse.decodeHandle)
        XCTAssertTrue(recorded.contains(where: { matches($0.payload, .tokenDelta) }))
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
        XCTAssertEqual(services.metrics.counters["swift_text.decode_batch_size"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.model_eval_batch_size"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.decode_batch_observation_count"], 1)
    }

    func testDecodeStreamingRpcReturnsStructuredNotFoundForMissingDecodeHandle() async throws {
        let services = makeServices()
        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-missing-decode"
        request.decodeHandle = "missing-decode"

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].error.error.code, "not_found")
    }

    func testDecodeStreamingRpcFallsBackToStoredRequestIDAndHandlesSummaryOnlyDecode() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(decodedChunks: [])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-stored-decode"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("summary only decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.returnUsage = true

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 3)
        XCTAssertEqual(recorded[0].requestID, "req-stored-decode")
        XCTAssertGreaterThan(recorded[1].usageDelta.promptTokens, 0)
        XCTAssertEqual(recorded[1].usageDelta.completionTokens, 0)
        XCTAssertEqual(recorded[2].completed.assistantText, "")
        XCTAssertEqual(recorded[2].completed.finishReason, "stop")
        XCTAssertNotNil(services.metrics.counters["swift_text.decode_ttft_ms"])
    }

    func testDecodeStreamingRpcReturnsStructuredRuntimeErrorForBackendDecodeFailure() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(decodeError: FakeRuntimeBackendError.decodeFailed)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-runtime-error-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("runtime error decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-runtime-error"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].error.error.code, "runtime_error")
    }

    func testDecodeStreamingRpcFallsBackToBaselineWhenSpeculativeDecodeAllowsFallback() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["fallback"])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-fallback-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.execution.acceleration.mode = .speculativeDecode
        prefillRequest.execution.acceleration.allowBaselineFallback = true
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("fallback decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-fallback-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = true
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.first?.decodeStarted.decodeHandle, prefillResponse.decodeHandle)
        XCTAssertEqual(recorded.first?.accelerationMode, .baseline)
        XCTAssertFalse(matches(recorded.first?.payload, .accelerationApplied))
        XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_fallback_count"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_draft_model_configured"], 0)
    }

    func testDecodeStreamingRpcReturnsStructuredUnimplementedWhenSpeculativeDecodeCannotFallback() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["unused"])
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-no-fallback-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("no fallback decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-no-fallback-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].error.error.code, "unimplemented")
    }

    func testDecodeStreamingRpcUsesLoadedDraftModelForLiveSpeculativeDecode() async throws {
        let backend = FakeRuntimeBackend(decodedChunks: ["spec", " decode"])
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: backend
        )
        let targetLoadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text-draft"
            request.model.tokenizerHash = "tok-dev"
            request.model.requestRoutes = [makeTextRequestRoute()]
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-live-spec-prefill"
        prefillRequest.execution.modelHandle = targetLoadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("live speculative decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-live-spec-decode"
        request.execution.modelHandle = targetLoadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.execution.acceleration.draftModelID = "melix-dev-text-draft"
        request.execution.acceleration.numDraftTokens = 4
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        let decodedDraftModelID = await backend.lastDecodedDraftModelID()
        XCTAssertEqual(recorded.first?.accelerationApplied.policy.mode, .speculativeDecode)
        XCTAssertEqual(decodedDraftModelID, "melix-dev-text-draft")
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_fallback_count"], 0)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_draft_model_configured"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_num_draft_tokens"], 4)
    }

    func testDecodeStreamingRpcRejectsSpeculativeDecodeWhenDraftTokenizerHashDiffers() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["unused"])
        )
        let targetLoadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.model.tokenizerHash = "tok-target"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text-draft"
            request.model.tokenizerHash = "tok-draft"
            request.model.requestRoutes = [makeTextRequestRoute()]
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-tokenizer-prefill"
        prefillRequest.execution.modelHandle = targetLoadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("tokenizer mismatch")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-tokenizer-decode"
        request.execution.modelHandle = targetLoadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.execution.acceleration.draftModelID = "melix-dev-text-draft"
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].error.error.code, "unimplemented")
        XCTAssertTrue(recorded[0].error.error.message.contains("tokenizer"))
    }

    func testDecodeStreamingRpcUsesLoadedDFlashDraftForLiveSpeculativeDecode() async throws {
        let backend = FakeRuntimeBackend(decodedChunks: ["unused"])
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: backend
        )
        let targetLoadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.model.tokenizerHash = "tok-shared"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "z-lab/Qwen3.5-27B-DFlash"
            request.model.ext["melix.draft.runtime_kind"] = "dflash"
            request.model.requestRoutes = [makeTextRequestRoute()]
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-dflash-prefill"
        prefillRequest.execution.modelHandle = targetLoadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("dflash draft")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-dflash-decode"
        request.execution.modelHandle = targetLoadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.execution.acceleration.draftModelID = "z-lab/Qwen3.5-27B-DFlash"
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        let decodedDraftModelID = await backend.lastDecodedDraftModelID()
        XCTAssertFalse(recorded.contains(where: { !$0.error.error.code.isEmpty }))
        XCTAssertEqual(decodedDraftModelID, "z-lab/Qwen3.5-27B-DFlash")
    }

    func testDecodeStreamingRpcRejectsSpeculativeDecodeForNonGreedySampling() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "auto",
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["unused"])
        )
        let targetLoadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.model.tokenizerHash = "tok-shared"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text-draft"
            request.model.tokenizerHash = "tok-shared"
            request.model.requestRoutes = [makeTextRequestRoute()]
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-sampling-prefill"
        prefillRequest.execution.modelHandle = targetLoadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("non greedy speculative decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-sampling-decode"
        request.execution.modelHandle = targetLoadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.execution.acceleration.draftModelID = "melix-dev-text-draft"
        request.sampling.temperature = 0.7
        request.sampling.topP = 1
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.count, 1)
        XCTAssertEqual(recorded[0].error.error.code, "unimplemented")
        XCTAssertTrue(recorded[0].error.error.message.contains("greedy"))
    }

    func testDecodeStreamingRpcCanBeAbortedWithoutUsageTrailer() async throws {
        let services = makeServices(
            environment: ["MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"],
            backend: FakeRuntimeBackend(
                decodedChunks: ["decode", " cancel", " tail"],
                decodeDelayNanos: 40_000_000
            )
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-decode-cancel-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("cancel decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-decode-cancel"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle
        request.returnUsage = true

        let decodeTask = Task {
            try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.decode(
                    request: request,
                    response: RPCWriter(wrapping: writer),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
        }

        try await Task.sleep(nanoseconds: 60_000_000)
        _ = try await withTestServerContextRPCCancellationHandle { handle in
            var abortRequest = Melix_Worker_V1_AbortRequest()
            abortRequest.requestID = "req-decode-cancel"
            return try await services.inference.abort(
                request: abortRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Abort.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        _ = try await decodeTask.value

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.last?.completed.finishReason, "cancelled")
        XCTAssertFalse(recorded.contains(where: { matches($0.payload, .usageDelta) }))
    }

    func testDecodeStreamingRpcSupportsDeterministicSpeculativeMetrics() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": "deterministic",
            ],
            backend: DeterministicTextBackend(tokenDelayNanos: 1_000_000)
        )
        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-spec-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.execution.acceleration.mode = .speculativeDecode
        prefillRequest.execution.acceleration.allowBaselineFallback = false
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("speculative decode")]
        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-spec-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.execution.acceleration.mode = .speculativeDecode
        request.execution.acceleration.allowBaselineFallback = false
        request.execution.acceleration.draftModelID = "melix-dev-text-draft"
        request.execution.acceleration.numDraftTokens = 4
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertEqual(recorded.first?.accelerationApplied.policy.mode, .speculativeDecode)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_accepted_tokens"], 2)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_rejected_tokens"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_acceptance_rate"], 66)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_rollback_rate"], 33)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_draft_model_configured"], 1)
        XCTAssertEqual(services.metrics.counters["swift_text.speculative_num_draft_tokens"], 4)
    }

    func testDecodeStreamingRpcRecordsActiveKVQuantizationRatio() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ],
            backend: FakeRuntimeBackend(decodedChunks: ["active", " kv"])
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-active-kv-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.execution.acceleration.mode = .activeKvQuantized
        prefillRequest.execution.acceleration.activeKvQuantProfile = "q8"
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("active kv decode")]

        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-active-kv-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let recorded = await writer.snapshot()
        XCTAssertTrue(matches(recorded.first?.payload, .accelerationApplied))
        XCTAssertEqual(recorded.first?.accelerationApplied.policy.mode, .activeKvQuantized)
        XCTAssertEqual(recorded.first?.accelerationApplied.policy.activeKvQuantProfile, "q8")
        XCTAssertEqual(services.metrics.counters["swift_text.active_kv_quantization_ratio"], 50)
    }

    func testDecodeStreamingRpcRecordsActiveKVProbeSummary() async throws {
        let services = makeServices(
            environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ],
            backend: FakeRuntimeBackend(
                decodedChunks: ["probe"],
                activeKVProbeSummary: ActiveKVProbeSummary(
                    backendCode: 1,
                    kernelPathCode: 10,
                    runtimeRouteCode: 1,
                    runtimeBlockReasonCode: 2,
                    quantizationRatioPercent: 25,
                    prefillQuantizeMicros: 150,
                    decodeModelTotalMicros: 900,
                    decodeModelCallCount: 3,
                    decodeTokenEvalTotalMicros: 1_800,
                    decodeTokenEvalCallCount: 3,
                    decodeModelEvalSyncTotalMicros: 1_500,
                    decodeModelEvalSyncCallCount: 3,
                    decodeSampleTotalMicros: 210,
                    decodeSampleCallCount: 3,
                    decodeTokenIDTotalMicros: 90,
                    decodeTokenIDCallCount: 3,
                    decodeDetokenizeTotalMicros: 150,
                    decodeDetokenizeCallCount: 3,
                    decodeStreamYieldTotalMicros: 60,
                    decodeStreamYieldCallCount: 3,
                    decodeSummaryTotalMicros: 45,
                    decodeSummaryCallCount: 1,
                    turboQuantCandidateTotalMicros: 30,
                    turboQuantCandidateCallCount: 1,
                    decodeQuantizeTotalMicros: 120,
                    decodeLoopTotalMicros: 2_100,
                    decodeTokenCount: 3,
                    estimatedFP16Bytes: 4_000,
                    estimatedQuantizedBytes: 1_000,
                    estimatedMemorySavingsPercent: 75,
                    fallbackCount: 0,
                    cacheUpdateTotalMicros: 1_200,
                    cacheUpdateCallCount: 3,
                    cacheExpandTotalMicros: 90,
                    cacheQuantizeTotalMicros: 540,
                    cacheAppendTotalMicros: 360,
                    cacheMaterializeTotalMicros: 210,
                    cacheMaterializeCallCount: 3,
                    fusedAttentionTotalMicros: 750,
                    fusedAttentionCallCount: 3,
                    fusedAttentionRouteTotalMicros: 900,
                    fusedAttentionActiveLaneTotal: 48,
                    fusedAttentionLaunchedLaneTotal: 96,
                    fusedAttentionSoftmaxLaneTotal: 96,
                    fusedAttentionSoftmaxTokenLaneTotal: 6_144
                )
            )
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefillRequest = Melix_Worker_V1_PrefillRequest()
        prefillRequest.execution.id.requestID = "req-active-kv-probe-prefill"
        prefillRequest.execution.modelHandle = loadResponse.modelHandle
        prefillRequest.execution.acceleration.mode = .activeKvQuantized
        prefillRequest.returnDecodeHandle = true
        prefillRequest.messages = [makeUserMessage("active kv probe")]

        let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefillRequest,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
        var request = Melix_Worker_V1_DecodeRequest()
        request.execution.id.requestID = "req-active-kv-probe-decode"
        request.execution.modelHandle = loadResponse.modelHandle
        request.decodeHandle = prefillResponse.decodeHandle

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.decode(
                request: request,
                response: RPCWriter(wrapping: writer),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.active_kv_quantization_ratio"], 25)
        XCTAssertEqual(metrics["swift_text.active_kv_backend_code"], 1)
        XCTAssertEqual(metrics["swift_text.active_kv_kernel_path_code"], 10)
        XCTAssertEqual(metrics["swift_text.active_kv_runtime_route_code"], 1)
        XCTAssertEqual(metrics["swift_text.active_kv_runtime_block_reason_code"], 2)
        XCTAssertEqual(metrics["swift_text.active_kv_prefill_quantize_us"], 150)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_model_total_us"], 900)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_model_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_model_avg_us"], 300)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_token_eval_total_us"], 1_800)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_token_eval_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_token_eval_avg_us"], 600)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_model_eval_sync_total_us"], 1_500)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_model_eval_sync_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_model_eval_sync_avg_us"], 500)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_sample_total_us"], 210)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_sample_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_sample_avg_us"], 70)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_token_id_total_us"], 90)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_token_id_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_token_id_avg_us"], 30)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_detokenize_total_us"], 150)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_detokenize_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_detokenize_avg_us"], 50)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_stream_yield_total_us"], 60)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_stream_yield_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_stream_yield_avg_us"], 20)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_summary_total_us"], 45)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_summary_call_count"], 1)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_summary_avg_us"], 45)
        XCTAssertEqual(metrics["swift_text.active_kv_turboquant_candidate_total_us"], 30)
        XCTAssertEqual(metrics["swift_text.active_kv_turboquant_candidate_call_count"], 1)
        XCTAssertEqual(metrics["swift_text.active_kv_turboquant_candidate_avg_us"], 30)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_quantize_total_us"], 120)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_quantize_avg_us"], 40)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_loop_total_us"], 2_100)
        XCTAssertEqual(metrics["swift_text.active_kv_decode_token_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_estimated_fp16_bytes"], 4_000)
        XCTAssertEqual(metrics["swift_text.active_kv_estimated_quantized_bytes"], 1_000)
        XCTAssertEqual(metrics["swift_text.active_kv_estimated_memory_savings_pct"], 75)
        XCTAssertEqual(metrics["swift_text.active_kv_fallback_count"], 0)
        XCTAssertEqual(metrics["swift_text.active_kv_candidate_dispatch_code"], 0)
        XCTAssertEqual(metrics["swift_text.active_kv_candidate_eligibility_check_count"], 0)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_update_total_us"], 1_200)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_update_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_update_avg_us"], 400)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_expand_total_us"], 90)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_quantize_total_us"], 540)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_append_total_us"], 360)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_materialize_total_us"], 210)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_materialize_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_cache_materialize_avg_us"], 70)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_total_us"], 750)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_call_count"], 3)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_avg_us"], 250)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_route_total_us"], 900)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_route_avg_us"], 300)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_active_lane_total"], 48)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_launched_lane_total"], 96)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_inactive_lane_total"], 48)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_softmax_lane_total"], 96)
        XCTAssertEqual(metrics["swift_text.active_kv_fused_attention_softmax_token_lane_total"], 6_144)
    }

    func testActiveKVProbeSummaryAveragesReturnZeroWithoutDecodeTokens() {
        let summary = ActiveKVProbeSummary(
            backendCode: 1,
            kernelPathCode: 10,
            prefillQuantizeMicros: 0,
            decodeModelTotalMicros: 120,
            decodeTokenEvalTotalMicros: 90,
            decodeTokenEvalCallCount: 0,
            decodeModelEvalSyncTotalMicros: 70,
            decodeModelEvalSyncCallCount: 0,
            decodeSampleTotalMicros: 60,
            decodeSampleCallCount: 0,
            decodeTokenIDTotalMicros: 50,
            decodeTokenIDCallCount: 0,
            decodeDetokenizeTotalMicros: 40,
            decodeDetokenizeCallCount: 0,
            decodeStreamYieldTotalMicros: 30,
            decodeStreamYieldCallCount: 0,
            decodeSummaryTotalMicros: 20,
            decodeSummaryCallCount: 0,
            turboQuantCandidateTotalMicros: 10,
            turboQuantCandidateCallCount: 0,
            decodeQuantizeTotalMicros: 80,
            decodeLoopTotalMicros: 400,
            decodeTokenCount: 0,
            estimatedFP16Bytes: 0,
            estimatedQuantizedBytes: 0,
            estimatedMemorySavingsPercent: 0,
            fallbackCount: 0
        )

        XCTAssertEqual(summary.decodeModelAverageMicros, 0)
        XCTAssertEqual(summary.decodeTokenEvalAverageMicros, 0)
        XCTAssertEqual(summary.decodeModelEvalSyncAverageMicros, 0)
        XCTAssertEqual(summary.decodeSampleAverageMicros, 0)
        XCTAssertEqual(summary.decodeTokenIDAverageMicros, 0)
        XCTAssertEqual(summary.decodeDetokenizeAverageMicros, 0)
        XCTAssertEqual(summary.decodeStreamYieldAverageMicros, 0)
        XCTAssertEqual(summary.decodeSummaryAverageMicros, 0)
        XCTAssertEqual(summary.turboQuantCandidateAverageMicros, 0)
        XCTAssertEqual(summary.decodeQuantizeAverageMicros, 0)
        XCTAssertEqual(summary.cacheUpdateAverageMicros, 0)
        XCTAssertEqual(summary.cacheMaterializeAverageMicros, 0)
    }

    func testCacheManagementRpcsExposeHotAndDiskTierMetadata() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let services = makeServices(
                environment: [
                    "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                    "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path,
                ],
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await services.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-cache-prefill"
                request.execution.modelHandle = loadResponse.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.prefillStepSize = 8
                request.messages = [makeUserMessage("cache me")]

                return try await services.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let cacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var pinRequest = Melix_Worker_V1_PinPrefixRequest()
            pinRequest.prefix = try XCTUnwrap(cacheResponse.snapshot.hotPrefixes.first)
            let pinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.pinPrefix(
                    request: pinRequest,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.PinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var unpinRequest = Melix_Worker_V1_UnpinPrefixRequest()
            unpinRequest.prefix = pinRequest.prefix
            let unpinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.unpinPrefix(
                    request: unpinRequest,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.UnpinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let saveResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-cache-prefill"
                request.decodeHandle = prefillResponse.decodeHandle
                request.tokenBoundary = prefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let postSaveCacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = saveResponse.snapshotID
                return try await services.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var purgeRequest = Melix_Worker_V1_PurgeCacheRequest()
            purgeRequest.scope = pinRequest.prefix.scope
            purgeRequest.includePinned = true
            let purgeResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.purgeCache(
                    request: purgeRequest,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.PurgeCache.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let postPurgeCacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(prefillResponse.ok)
            XCTAssertEqual(cacheResponse.stats.blockCount, 1)
            XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
            XCTAssertGreaterThan(cacheResponse.stats.l2Bytes, 0)
            XCTAssertTrue(pinResponse.ok)
            XCTAssertTrue(unpinResponse.ok)
            XCTAssertTrue(saveResponse.ok)
            XCTAssertFalse(saveResponse.snapshotID.isEmpty)
            XCTAssertEqual(postSaveCacheResponse.stats.snapshotCount, 1)
            XCTAssertGreaterThan(postSaveCacheResponse.stats.quantizedBytes, 0)
            XCTAssertGreaterThan(postSaveCacheResponse.stats.compressionRatio, 1.0)
            XCTAssertTrue(restoreResponse.ok)
            XCTAssertEqual(restoreResponse.snapshot.snapshotID, saveResponse.snapshotID)
            XCTAssertEqual(restoreResponse.blockTableID, prefillResponse.blockTableID)
            XCTAssertTrue(purgeResponse.ok)
            XCTAssertEqual(purgeResponse.purgedBlocks, 2)
            XCTAssertEqual(postPurgeCacheResponse.stats.blockCount, 0)
            XCTAssertEqual(postPurgeCacheResponse.snapshot.hotPrefixes.count, 0)
            XCTAssertEqual(postPurgeCacheResponse.stats.snapshotCount, 0)
        }
    }

    func testCacheManagementRpcsPublishColdTierHitRateAndQueueMetricsAfterRestart() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path,
            ]

            let initialServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let initialLoad = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await initialServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let initialPrefill = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-cold-tier-seed"
                request.execution.modelHandle = initialLoad.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.prefillStepSize = 8
                request.messages = [makeUserMessage("seed a cold-tier prefix")]
                return try await initialServices.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            _ = try await withTestServerContextRPCCancellationHandle { handle in
                try await initialServices.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restartedServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let restartedLoad = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await restartedServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restartedPrefill = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-cold-tier-reuse"
                request.execution.modelHandle = restartedLoad.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.prefillStepSize = 8
                request.messages = [makeUserMessage("seed a cold-tier prefix")]
                return try await restartedServices.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let cacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await restartedServices.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertEqual(restartedPrefill.blockTableID, initialPrefill.blockTableID)
            XCTAssertEqual(cacheResponse.stats.l1HitRate, 0, accuracy: 0.0001)
            XCTAssertEqual(cacheResponse.stats.l2HitRate, 1, accuracy: 0.0001)
            XCTAssertEqual(initialServices.metrics.counters["swift_text.cache_l2_writeback_count"], 1)
            XCTAssertEqual(restartedServices.metrics.counters["swift_text.cache_l2_hit_rate"], 100)
            XCTAssertEqual(restartedServices.metrics.counters["swift_text.cache_l2_writeback_queue_depth"], 0)
            XCTAssertEqual(restartedServices.metrics.counters["swift_text.cache_l2_restore_queue_depth"], 0)
            XCTAssertEqual(restartedServices.metrics.counters["swift_text.cache_l2_writeback_count"], 0)
        }
    }

    func testCacheManagementRpcsPublishActiveExperimentalCacheModeMetrics() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit",
                "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path,
            ]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await services.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            _ = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-hybrid-cache-mode"
                request.execution.modelHandle = loadResponse.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.execution.cacheHints.cacheMode = .hybrid
                request.returnDecodeHandle = true
                request.prefillStepSize = 8
                request.messages = [makeUserMessage("activate hybrid cache mode")]
                return try await services.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let cacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertEqual(cacheResponse.stats.activeMode, .hybrid)
            XCTAssertEqual(services.metrics.counters["swift_text.cache_active_mode"], 3)
            XCTAssertEqual(services.metrics.counters["swift_text.cache_rotating_mode_active"], 0)
            XCTAssertEqual(services.metrics.counters["swift_text.cache_hybrid_mode_active"], 1)
        }
    }

    func testBoundarySnapshotRestoreSurvivesRegistryRestartOnDeterministicBackend() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]

            let initialServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await initialServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-restart-prefill"
                request.execution.modelHandle = loadResponse.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.prefillStepSize = 8
                request.messages = [makeUserMessage("persist this prompt")]
                return try await initialServices.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let saveResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-restart-prefill"
                request.decodeHandle = prefillResponse.decodeHandle
                request.tokenBoundary = prefillResponse.promptTokens
                return try await initialServices.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(saveResponse.ok)

            let restartedServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let restartedLoadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await restartedServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
            XCTAssertTrue(restartedLoadResponse.ok)

            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = saveResponse.snapshotID
                return try await restartedServices.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
            try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_DecodeRequest()
                request.execution.id.requestID = "req-restart-decode"
                request.execution.modelHandle = restartedLoadResponse.modelHandle
                request.decodeHandle = restoreResponse.decodeHandle
                request.returnUsage = true
                try await restartedServices.inference.decode(
                    request: request,
                    response: RPCWriter(wrapping: writer),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restoredCacheResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await restartedServices.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let recorded = await writer.snapshot()
            XCTAssertTrue(restoreResponse.ok)
            XCTAssertFalse(restoreResponse.decodeHandle.isEmpty)
            XCTAssertTrue(recorded.contains(where: { matches($0.payload, .tokenDelta) }))
            XCTAssertEqual(restoredCacheResponse.stats.snapshotCount, 1)
            XCTAssertGreaterThan(restoredCacheResponse.stats.l2Bytes, 0)
            XCTAssertEqual(restoredCacheResponse.stats.l2RestoreHitRate, 1.0, accuracy: 0.0001)
        }
    }

    func testPrefillCanRestoreBoundarySnapshotsFromCacheHints() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await services.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var initialPrefill = Melix_Worker_V1_PrefillRequest()
            initialPrefill.execution.id.requestID = "req-restore-source"
            initialPrefill.execution.modelHandle = loadResponse.modelHandle
            initialPrefill.execution.cacheHints.allowL2 = true
            initialPrefill.execution.cacheHints.persistL2 = true
            initialPrefill.returnDecodeHandle = true
            initialPrefill.messages = [makeUserMessage("persist this boundary")]
            let initialPrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: initialPrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-restore-source"
                request.decodeHandle = initialPrefillResponse.decodeHandle
                request.tokenBoundary = initialPrefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var restorePrefill = Melix_Worker_V1_PrefillRequest()
            restorePrefill.execution.id.requestID = "req-restore-target"
            restorePrefill.execution.modelHandle = loadResponse.modelHandle
            restorePrefill.execution.cacheHints.restoreSnapshotID = savedSnapshot.snapshotID
            restorePrefill.execution.cacheHints.cacheMode = .rotating
            restorePrefill.returnDecodeHandle = true
            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: restorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(restoreResponse.ok)
            XCTAssertEqual(restoreResponse.restoredSnapshotID, savedSnapshot.snapshotID)
            XCTAssertEqual(restoreResponse.blockTableID, initialPrefillResponse.blockTableID)
            XCTAssertFalse(restoreResponse.decodeHandle.isEmpty)
            XCTAssertTrue(restoreResponse.hasRestorePlan)
            XCTAssertFalse(restoreResponse.restorePlan.partial)
            XCTAssertEqual(restoreResponse.restorePlan.cacheMode, .rotating)
            let restoredContext = await services.registry.prefillContext(for: restoreResponse.decodeHandle)
            XCTAssertEqual(restoredContext?.restoredSnapshotID, savedSnapshot.snapshotID)
        }
    }

    func testPrefillRestoreWalksBackPartialPrefixesToSafeBoundary() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await services.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let sourcePrompt = (1...24).map { "token\($0)" }.joined(separator: " ")
            let divergedPrompt = (1...20).map { "token\($0)" }.joined(separator: " ") + " tail-x tail-y"

            var sourcePrefill = Melix_Worker_V1_PrefillRequest()
            sourcePrefill.execution.id.requestID = "req-partial-source"
            sourcePrefill.execution.modelHandle = loadResponse.modelHandle
            sourcePrefill.execution.cacheHints.allowL2 = true
            sourcePrefill.execution.cacheHints.persistL2 = true
            sourcePrefill.returnDecodeHandle = true
            sourcePrefill.messages = [makeUserMessage(sourcePrompt)]
            let sourcePrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: sourcePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-partial-source"
                request.decodeHandle = sourcePrefillResponse.decodeHandle
                request.tokenBoundary = sourcePrefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var restorePrefill = Melix_Worker_V1_PrefillRequest()
            restorePrefill.execution.id.requestID = "req-partial-target"
            restorePrefill.execution.modelHandle = loadResponse.modelHandle
            restorePrefill.execution.cacheHints.restoreSnapshotID = savedSnapshot.snapshotID
            restorePrefill.execution.cacheHints.cachePolicy = "hybrid"
            restorePrefill.prefillStepSize = 16
            restorePrefill.returnDecodeHandle = true
            restorePrefill.messages = [makeUserMessage(divergedPrompt)]
            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: restorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(restoreResponse.ok)
            XCTAssertEqual(restoreResponse.restoredSnapshotID, savedSnapshot.snapshotID)
            XCTAssertTrue(restoreResponse.hasRestorePlan)
            XCTAssertTrue(restoreResponse.restorePlan.partial)
            XCTAssertEqual(restoreResponse.restorePlan.restoredTokenCount, 16)
            XCTAssertEqual(restoreResponse.restorePlan.blockTable.totalTokenCount, 16)
            XCTAssertTrue(restoreResponse.blockTableID.contains("walkback-16"))
            XCTAssertEqual(restoreResponse.restorePlan.cacheMode, .hybrid)
            XCTAssertEqual(restoreResponse.promptTokens, 22)

            let restoredContext = await services.registry.prefillContext(for: restoreResponse.decodeHandle)
            XCTAssertEqual(restoredContext?.restoredSnapshotID, savedSnapshot.snapshotID)
            XCTAssertEqual(restoredContext?.blockTable.totalTokenCount, 16)
            let restoredStorage = restoredContext?.context.storage as? [String: String]
            XCTAssertEqual(restoredStorage?["prefill_step_size"], "16")
        }
    }

    func testPrefillRestoreFallsBackToColdPathWhenNoSafeBoundaryExists() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await services.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var sourcePrefill = Melix_Worker_V1_PrefillRequest()
            sourcePrefill.execution.id.requestID = "req-cold-fallback-source"
            sourcePrefill.execution.modelHandle = loadResponse.modelHandle
            sourcePrefill.execution.cacheHints.allowL2 = true
            sourcePrefill.execution.cacheHints.persistL2 = true
            sourcePrefill.returnDecodeHandle = true
            sourcePrefill.messages = [makeUserMessage("alpha beta gamma delta epsilon zeta eta theta")]
            let sourcePrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: sourcePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-cold-fallback-source"
                request.decodeHandle = sourcePrefillResponse.decodeHandle
                request.tokenBoundary = sourcePrefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var restorePrefill = Melix_Worker_V1_PrefillRequest()
            restorePrefill.execution.id.requestID = "req-cold-fallback-target"
            restorePrefill.execution.modelHandle = loadResponse.modelHandle
            restorePrefill.execution.cacheHints.restoreSnapshotID = savedSnapshot.snapshotID
            restorePrefill.returnDecodeHandle = true
            restorePrefill.messages = [makeUserMessage("totally different prompt with no shared prefix")]
            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: restorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(restoreResponse.ok)
            XCTAssertEqual(restoreResponse.restoredSnapshotID, "")
            XCTAssertFalse(restoreResponse.hasRestorePlan)
            XCTAssertNotEqual(restoreResponse.blockTableID, sourcePrefillResponse.blockTableID)
        }
    }

    func testRestoreResumeHintFallsBackWhenSnapshotIdentifierIsEmpty() {
        var restorePlan = Melix_Worker_V1_CacheRestorePlan()
        restorePlan.partial = true
        restorePlan.restoredTokenCount = 8

        XCTAssertEqual(
            restoreResumeHint(
                snapshotID: "",
                restorePlan: restorePlan,
                fallback: "runtime-resume"
            ),
            "runtime-resume"
        )
    }

    func testDecodeStreamingRpcEmitsRecoveryEventsForRestoredSnapshots() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: FakeRuntimeBackend(decodedChunks: ["resume", " ok"])
            )

            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await services.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var sourcePrefill = Melix_Worker_V1_PrefillRequest()
            sourcePrefill.execution.id.requestID = "req-recovery-source"
            sourcePrefill.execution.modelHandle = loadResponse.modelHandle
            sourcePrefill.execution.cacheHints.allowL2 = true
            sourcePrefill.execution.cacheHints.persistL2 = true
            sourcePrefill.returnDecodeHandle = true
            sourcePrefill.messages = [makeUserMessage("persist for recovery decode")]
            let sourcePrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: sourcePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-recovery-source"
                request.decodeHandle = sourcePrefillResponse.decodeHandle
                request.tokenBoundary = sourcePrefillResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var restorePrefill = Melix_Worker_V1_PrefillRequest()
            restorePrefill.execution.id.requestID = "req-recovery-decode"
            restorePrefill.execution.modelHandle = loadResponse.modelHandle
            restorePrefill.execution.cacheHints.restoreSnapshotID = savedSnapshot.snapshotID
            restorePrefill.returnDecodeHandle = true
            let restorePrefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: restorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let writer = RecordingRPCWriter<Melix_Worker_V1_ExecuteEvent>()
            var decodeRequest = Melix_Worker_V1_DecodeRequest()
            decodeRequest.execution.id.requestID = "req-recovery-decode"
            decodeRequest.execution.modelHandle = loadResponse.modelHandle
            decodeRequest.execution.cacheHints.saveBoundarySnapshot = true
            decodeRequest.decodeHandle = restorePrefillResponse.decodeHandle
            decodeRequest.returnUsage = true

            try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.decode(
                    request: decodeRequest,
                    response: RPCWriter(wrapping: writer),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Decode.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let recorded = await writer.snapshot()
            let startedEvent = try XCTUnwrap(recorded.first(where: { !$0.decodeStarted.decodeHandle.isEmpty }))
            XCTAssertEqual(startedEvent.decodeStarted.decodeHandle, restorePrefillResponse.decodeHandle)
            let cacheDecisionEvent = try XCTUnwrap(recorded.first(where: { !$0.cacheDecision.restoredSnapshotID.isEmpty }))
            XCTAssertEqual(cacheDecisionEvent.cacheDecision.restoredSnapshotID, savedSnapshot.snapshotID)
            let snapshotEvent = try XCTUnwrap(recorded.first(where: { !$0.snapshotCreated.snapshotID.isEmpty }))
            XCTAssertFalse(snapshotEvent.snapshotCreated.snapshotID.isEmpty)
            XCTAssertGreaterThan(snapshotEvent.snapshotCreated.tokenBoundary, 0)
            XCTAssertEqual(recorded.last?.completed.finishReason, "stop")
            XCTAssertNotNil(services.metrics.counters["swift_text.cache_snapshot_save_ms"])
        }
    }

    func testCacheManagementRpcsReturnStructuredErrorsForUnknownRefsAndUnloadedSnapshotModels() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            var unknownPrefix = Melix_Worker_V1_PrefixRef()
            unknownPrefix.prefixID = "missing-prefix"

            let pinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PinPrefixRequest()
                request.prefix = unknownPrefix
                return try await services.cache.pinPrefix(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.PinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let unpinResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_UnpinPrefixRequest()
                request.prefix = unknownPrefix
                return try await services.cache.unpinPrefix(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.UnpinPrefix.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let saveMissingResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "missing-request"
                request.decodeHandle = "missing-decode"
                request.tokenBoundary = 2
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restoreMissingResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = "missing-snapshot"
                return try await services.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let initialServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )
            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await initialServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-precondition-prefill"
                request.execution.modelHandle = loadResponse.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.messages = [makeUserMessage("persist before failed precondition")]
                return try await initialServices.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let savedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-precondition-prefill"
                request.decodeHandle = prefillResponse.decodeHandle
                request.tokenBoundary = prefillResponse.promptTokens
                return try await initialServices.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let unloadedServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )
            let failedPreconditionRestore = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = savedSnapshot.snapshotID
                return try await unloadedServices.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertFalse(pinResponse.ok)
            XCTAssertEqual(pinResponse.error.code, "not_found")
            XCTAssertFalse(unpinResponse.ok)
            XCTAssertEqual(unpinResponse.error.code, "not_found")
            XCTAssertFalse(saveMissingResponse.ok)
            XCTAssertEqual(saveMissingResponse.error.code, "not_found")
            XCTAssertFalse(restoreMissingResponse.ok)
            XCTAssertEqual(restoreMissingResponse.error.code, "not_found")
            XCTAssertFalse(failedPreconditionRestore.ok)
            XCTAssertEqual(failedPreconditionRestore.error.code, "failed_precondition")
            XCTAssertGreaterThanOrEqual(services.metrics.counters["swift_text.rpc_error_count"] ?? 0, 2)
        }
    }

    func testBoundarySnapshotRestoreRejectsMismatchedAdapterScope() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let initialServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            let initialLoad = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                request.model.ext["melix.adapter_set_hash"] = "adapter-alpha"
                return try await initialServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let prefillResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_PrefillRequest()
                request.execution.id.requestID = "req-adapter-snapshot"
                request.execution.modelHandle = initialLoad.modelHandle
                request.execution.cacheHints.allowL2 = true
                request.execution.cacheHints.persistL2 = true
                request.returnDecodeHandle = true
                request.messages = [makeUserMessage("persist adapter alpha")]
                return try await initialServices.inference.prefill(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let saveResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-adapter-snapshot"
                request.decodeHandle = prefillResponse.decodeHandle
                request.tokenBoundary = prefillResponse.promptTokens
                return try await initialServices.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restartedServices = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            _ = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                request.model.ext["melix.adapter_set_hash"] = "adapter-beta"
                return try await restartedServices.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let restoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_RestoreBoundarySnapshotRequest()
                request.snapshotID = saveResponse.snapshotID
                return try await restartedServices.cache.restoreBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.RestoreBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertFalse(restoreResponse.ok)
            XCTAssertEqual(restoreResponse.error.code, "failed_precondition")
            XCTAssertEqual(
                restoreResponse.error.message,
                "The loaded model configuration is incompatible with this snapshot."
            )
        }
    }

    func testUnloadModelPurgesOnlyMatchingAdapterScope() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var adapterAlpha = Melix_Worker_V1_ModelSpec()
        adapterAlpha.modelID = "melix-dev-text"
        adapterAlpha.ext["melix.adapter_set_hash"] = "adapter-alpha"
        let loadedAlpha = try await registry.loadModel(adapterAlpha)

        var adapterBeta = Melix_Worker_V1_ModelSpec()
        adapterBeta.modelID = "melix-dev-text"
        adapterBeta.ext["melix.adapter_set_hash"] = "adapter-beta"
        let loadedBeta = try await registry.loadModel(adapterBeta)

        let messages = [makeUserMessage("adapter scoped purge")]
        let alphaPrefill = try await registry.prefill(
            requestID: "req-purge-alpha",
            modelHandle: loadedAlpha.handle,
            messages: messages,
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "purge-alpha",
            acceleration: makeAccelerationPolicy(mode: .baseline),
            shouldAbort: { false }
        )
        let betaPrefill = try await registry.prefill(
            requestID: "req-purge-beta",
            modelHandle: loadedBeta.handle,
            messages: messages,
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "purge-beta",
            acceleration: makeAccelerationPolicy(mode: .baseline),
            shouldAbort: { false }
        )

        XCTAssertNotEqual(alphaPrefill.blockTable.scopeID, betaPrefill.blockTable.scopeID)

        let unloaded = await registry.unloadModel(loadedAlpha.handle)
        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertTrue(unloaded)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.first?.scope.scopeID, betaPrefill.blockTable.scopeID)
    }

    func testRuntimeRegistryUsesLegacyAdapterHashForHandlesAndCacheScopes() async throws {
        let registry = WorkerRuntimeRegistry(
            configuration: WorkerConfiguration(),
            modelCatalog: WorkerModelCatalog(environment: [
                "MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/melix-dev-text-4bit"
            ]),
            runtime: TextRuntime(backend: FakeRuntimeBackend())
        )

        var legacyAdapter = Melix_Worker_V1_ModelSpec()
        legacyAdapter.modelID = "melix-dev-text"
        legacyAdapter.ext["adapter_set_hash"] = "adapter-legacy"

        let loaded = try await registry.loadModel(legacyAdapter)
        let prefill = try await registry.prefill(
            requestID: "req-legacy-adapter",
            modelHandle: loaded.handle,
            messages: [makeUserMessage("legacy adapter scope")],
            prefillStepSize: 8,
            returnDecodeHandle: true,
            resumeHint: "legacy-adapter",
            acceleration: makeAccelerationPolicy(mode: .baseline),
            shouldAbort: { false }
        )
        let cacheResponse = await registry.cacheStatsResponse()

        XCTAssertTrue(loaded.handle.contains("::adapter::adapter_legacy::"))
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.count, 1)
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.first?.scope.multimodalAdapterHash, "adapter-legacy")
        XCTAssertEqual(cacheResponse.snapshot.hotPrefixes.first?.scope.scopeID, prefill.blockTable.scopeID)
    }

    func testDiskCacheStorePurgeScopeSupportsEmptyAndModelOnlyScopes() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let fileManager = FileManager.default
            try fileManager.createDirectory(
                at: cacheRoot.appendingPathComponent("prefixes", isDirectory: true),
                withIntermediateDirectories: true
            )
            try fileManager.createDirectory(
                at: cacheRoot.appendingPathComponent("snapshots", isDirectory: true),
                withIntermediateDirectories: true
            )

            let store = DiskCacheStore(rootPath: cacheRoot.path)

            func persistSnapshot(
                scopeID: String,
                modelID: String,
                prefixID: String,
                snapshotID: String
            ) async {
                let scope = makeCacheScope(scopeID: scopeID, modelID: modelID)
                let key = makeCacheKey(
                    scopeID: scopeID,
                    prefixSeed: "\(prefixID)-prefix",
                    fingerprintSeed: "\(prefixID)-fingerprint"
                )
                let prefix = makePrefixRef(prefixID: prefixID, scope: scope, cacheKey: key)
                let table = makeBlockTable(scopeID: scopeID, cacheKey: key, blockIDs: ["\(prefixID)-block"], bytes: [64])

                await store.persistPrefix(
                    prefix: prefix,
                    blockTableID: "table-\(prefixID)",
                    blockTable: table,
                    quantizedBytes: 32
                )
                await store.saveSnapshot(
                    snapshot: makeSnapshotRef(snapshotID: snapshotID),
                    model: makeModelSpec(modelID: modelID),
                    messages: [makeUserMessage(snapshotID)],
                    resumeHint: "resume-\(snapshotID)",
                    acceleration: makeAccelerationPolicy(mode: .baseline),
                    promptTokens: 4,
                    blockTableID: "table-\(prefixID)",
                    blockTable: table,
                    prefix: nil
                )
            }

            await persistSnapshot(
                scopeID: "scope-alpha",
                modelID: "model-alpha",
                prefixID: "prefix-alpha",
                snapshotID: "snapshot-alpha"
            )
            await persistSnapshot(
                scopeID: "scope-beta",
                modelID: "model-beta",
                prefixID: "prefix-beta",
                snapshotID: "snapshot-beta"
            )

            await store.purgeScope(Melix_Worker_V1_CacheScope())

            let fullyPurged = await store.summary()
            XCTAssertEqual(fullyPurged.snapshotCount, 0)
            XCTAssertEqual(fullyPurged.l2Bytes, 0)

            await persistSnapshot(
                scopeID: "scope-alpha",
                modelID: "model-alpha",
                prefixID: "prefix-alpha-2",
                snapshotID: "snapshot-alpha-2"
            )
            await persistSnapshot(
                scopeID: "scope-beta",
                modelID: "model-beta",
                prefixID: "prefix-beta-2",
                snapshotID: "snapshot-beta-2"
            )

            var modelOnlyScope = Melix_Worker_V1_CacheScope()
            modelOnlyScope.modelID = "model-beta"
            await store.purgeScope(modelOnlyScope)

            let remaining = await store.summary()
            let betaRestore = await store.restoreSnapshot(snapshotID: "snapshot-beta-2")
            let alphaRestore = await store.restoreSnapshot(snapshotID: "snapshot-alpha-2")
            XCTAssertEqual(remaining.snapshotCount, 1)
            XCTAssertEqual(remaining.l2Bytes, 32)
            XCTAssertEqual(remaining.scopes.first?.scope.modelID, "model-alpha")
            XCTAssertNil(betaRestore)
            XCTAssertNotNil(alphaRestore)
        }
    }

    func testDiskCacheStoreSupportsPurgesRestoreMissesAndModelEviction() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let fileManager = FileManager.default
            try fileManager.createDirectory(
                at: cacheRoot.appendingPathComponent("prefixes", isDirectory: true),
                withIntermediateDirectories: true
            )
            try fileManager.createDirectory(
                at: cacheRoot.appendingPathComponent("snapshots", isDirectory: true),
                withIntermediateDirectories: true
            )
            try Data("not-json".utf8).write(
                to: cacheRoot.appendingPathComponent("prefixes/bad.json"),
                options: [.atomic]
            )
            try Data("still-not-json".utf8).write(
                to: cacheRoot.appendingPathComponent("snapshots/bad.json"),
                options: [.atomic]
            )

            let store = DiskCacheStore(rootPath: cacheRoot.path)
            let missingRestore = await store.restoreSnapshot(snapshotID: "missing-snapshot")
            let initialSummary = await store.summary()
            XCTAssertNil(missingRestore)
            XCTAssertEqual(initialSummary.l2RestoreHitRate, 0, accuracy: 0.0001)

            let scope = makeCacheScope(scopeID: "scope-alpha", modelID: "model-alpha")
            let cacheKey = makeCacheKey(scopeID: scope.scopeID, prefixSeed: "alpha-prefix", fingerprintSeed: "alpha-fingerprint")
            let pinnedPrefix = makePrefixRef(
                prefixID: "prefix-alpha",
                scope: scope,
                cacheKey: cacheKey,
                pinned: true
            )
            let blockTable = makeBlockTable(scopeID: scope.scopeID, cacheKey: cacheKey, blockIDs: ["a0", "a1"], bytes: [120, 80])
            await store.persistPrefix(
                prefix: pinnedPrefix,
                blockTableID: "table-alpha",
                blockTable: blockTable,
                quantizedBytes: 100
            )

            let model = makeModelSpec(modelID: "model-alpha")
            let snapshotRef = makeSnapshotRef(snapshotID: "snapshot-alpha")
            let messages = [makeUserMessage("alpha snapshot")]
            await store.saveSnapshot(
                snapshot: snapshotRef,
                model: model,
                messages: messages,
                resumeHint: "resume-alpha",
                acceleration: makeAccelerationPolicy(mode: .baseline),
                promptTokens: 4,
                blockTableID: "table-alpha",
                blockTable: blockTable,
                prefix: nil
            )

            let summaryAfterSave = await store.summary()
            XCTAssertEqual(summaryAfterSave.snapshotCount, 1)
            XCTAssertEqual(summaryAfterSave.scopes.first?.snapshotCount, 1)
            XCTAssertEqual(summaryAfterSave.quantizedBytes, 100)
            XCTAssertEqual(summaryAfterSave.unquantizedBytes, 200)

            let skippedPinned = await store.purge(scope: scope, cacheKey: cacheKey, includePinned: false)
            let afterSkippedPinned = await store.summary()
            XCTAssertEqual(skippedPinned, 0)
            XCTAssertEqual(afterSkippedPinned.l2Bytes, 100)

            let purgedPinned = await store.purge(scope: scope, cacheKey: cacheKey, includePinned: true)
            let afterPurgedPinned = await store.summary()
            XCTAssertEqual(purgedPinned, 2)
            XCTAssertEqual(afterPurgedPinned.snapshotCount, 0)
            XCTAssertEqual(afterPurgedPinned.l2Bytes, 0)

            let otherScope = makeCacheScope(scopeID: "scope-beta", modelID: "model-beta")
            let otherKey = makeCacheKey(scopeID: otherScope.scopeID, prefixSeed: "beta-prefix", fingerprintSeed: "beta-fingerprint")
            let otherPrefix = makePrefixRef(prefixID: "prefix-beta", scope: otherScope, cacheKey: otherKey)
            let otherTable = makeBlockTable(scopeID: otherScope.scopeID, cacheKey: otherKey, blockIDs: ["b0"], bytes: [64])
            let otherSnapshot = makeSnapshotRef(snapshotID: "snapshot-beta")
            await store.saveSnapshot(
                snapshot: otherSnapshot,
                model: makeModelSpec(modelID: "model-beta"),
                messages: [makeUserMessage("beta snapshot")],
                resumeHint: "resume-beta",
                acceleration: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "q4"),
                promptTokens: 3,
                blockTableID: "table-beta",
                blockTable: otherTable,
                prefix: otherPrefix
            )

            let restoredSnapshot = await store.restoreSnapshot(snapshotID: otherSnapshot.snapshotID)
            let restored = try XCTUnwrap(restoredSnapshot)
            XCTAssertEqual(restored.snapshot.snapshotID, otherSnapshot.snapshotID)
            XCTAssertEqual(restored.blockTableID, "table-beta")

            await store.purgeModel(modelID: "model-beta")
            let finalSummary = await store.summary()
            XCTAssertEqual(finalSummary.snapshotCount, 0)
            XCTAssertEqual(finalSummary.l2Bytes, 0)
            XCTAssertEqual(finalSummary.l2RestoreHitRate, 0.5, accuracy: 0.0001)
        }
    }

    func testDiskCacheStoreRejectsPersistedEntriesFromStaleRuntimeFingerprint() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let sourceStore = DiskCacheStore(
                rootPath: cacheRoot.path,
                runtimeCacheFingerprint: "runtime-cache-a"
            )
            let scope = makeCacheScope(scopeID: "scope-stale-runtime", modelID: "model-stale-runtime")
            let cacheKey = makeCacheKey(
                scopeID: scope.scopeID,
                prefixSeed: "stale-prefix",
                fingerprintSeed: "stale-fingerprint"
            )
            let prefix = makePrefixRef(prefixID: "prefix-stale-runtime", scope: scope, cacheKey: cacheKey)
            let blockTable = makeBlockTable(
                scopeID: scope.scopeID,
                cacheKey: cacheKey,
                blockIDs: ["stale-block"],
                bytes: [128]
            )

            await sourceStore.persistPrefix(
                prefix: prefix,
                blockTableID: "table-stale-runtime",
                blockTable: blockTable,
                quantizedBytes: 64
            )
            await sourceStore.saveSnapshot(
                snapshot: makeSnapshotRef(snapshotID: "snapshot-stale-runtime"),
                model: makeModelSpec(modelID: "model-stale-runtime"),
                messages: [makeUserMessage("stale runtime cache entry")],
                resumeHint: "resume-stale-runtime",
                acceleration: makeAccelerationPolicy(mode: .baseline),
                promptTokens: 4,
                blockTableID: "table-stale-runtime",
                blockTable: blockTable,
                prefix: nil
            )

            let staleRuntimeStore = DiskCacheStore(
                rootPath: cacheRoot.path,
                runtimeCacheFingerprint: "runtime-cache-b"
            )
            let summary = await staleRuntimeStore.summary()
            let restore = await staleRuntimeStore.restorePrefix(cacheKey: cacheKey)
            let snapshot = await staleRuntimeStore.restoreSnapshot(snapshotID: "snapshot-stale-runtime")

            XCTAssertNil(restore)
            XCTAssertNil(snapshot)
            XCTAssertEqual(summary.l2Bytes, 0)
            XCTAssertEqual(summary.snapshotCount, 0)
            XCTAssertEqual(summary.namespaceMismatchCount, 2)
        }
    }

    func testHotCacheStoreTracksPagedOwnershipAndPurgesItWithPrefixEntries() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = HotCacheStore(
                diskStore: DiskCacheStore(rootPath: cacheRoot.path),
                initialCacheBlocks: 0
            )

            let scope = makeCacheScope(scopeID: "scope-hot", modelID: "model-hot")
            let cacheKey = makeCacheKey(
                scopeID: scope.scopeID,
                prefixSeed: "hot-prefix",
                fingerprintSeed: "hot-fingerprint"
            )
            var execution = Melix_Worker_V1_ExecutionMetadata()
            execution.scope = scope
            execution.cacheKey = cacheKey
            execution.cacheHints.preferredBlockSize = 16

            let registration = try await store.registerPrefill(
                execution: execution,
                model: makeModelSpec(modelID: "model-hot"),
                messages: [makeUserMessage("paged cache ownership")],
                promptTokens: 40,
                decodeHandle: "decode-hot-1",
                activeKVQuantizationRatio: 50
            )

            let ownership = await store.ownershipSnapshot()
            let stats = await store.stats()

            XCTAssertEqual(registration.blockTable.blocks.count, 3)
            XCTAssertEqual(registration.blockTable.pages.count, 3)
            XCTAssertEqual(ownership.prefixCount, 1)
            XCTAssertEqual(ownership.pageCount, 3)
            XCTAssertEqual(ownership.blockCount, 3)
            XCTAssertEqual(ownership.pageIDsByPrefixID[registration.prefix.prefixID]?.count, 3)
            XCTAssertEqual(
                Set(ownership.blockIDsByPageID.values.flatMap { $0 }),
                Set(registration.blockTable.blocks.map(\.blockID))
            )
            XCTAssertEqual(stats.blockCount, 3)

            let purged = await store.purgeCache(scope: scope, cacheKey: cacheKey, includePinned: true)
            let postPurgeOwnership = await store.ownershipSnapshot()

            XCTAssertEqual(purged, 3)
            XCTAssertEqual(postPurgeOwnership.prefixCount, 0)
            XCTAssertEqual(postPurgeOwnership.pageCount, 0)
            XCTAssertEqual(postPurgeOwnership.blockCount, 0)
        }
    }

    func testHotCacheStoreRetainsSharedPagedOwnershipUntilLastPrefixIsPurged() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = HotCacheStore(
                diskStore: DiskCacheStore(rootPath: cacheRoot.path),
                initialCacheBlocks: 0
            )

            let scope = makeCacheScope(scopeID: "scope-shared", modelID: "model-shared")

            func register(prefixSeed: String, fingerprintSeed: String) async throws -> HotCacheRegistration {
                var execution = Melix_Worker_V1_ExecutionMetadata()
                execution.scope = scope
                execution.cacheKey = makeCacheKey(
                    scopeID: scope.scopeID,
                    prefixSeed: prefixSeed,
                    fingerprintSeed: fingerprintSeed
                )
                execution.cacheHints.preferredBlockSize = 16
                return try await store.registerPrefill(
                    execution: execution,
                    model: makeModelSpec(modelID: "model-shared"),
                    messages: [makeUserMessage(prefixSeed)],
                    promptTokens: 32,
                    decodeHandle: "decode-shared",
                    activeKVQuantizationRatio: 50
                )
            }

            let first = try await register(prefixSeed: "shared-1", fingerprintSeed: "shared-fp-1")
            let second = try await register(prefixSeed: "shared-2", fingerprintSeed: "shared-fp-2")

            XCTAssertNotEqual(first.prefix.prefixID, second.prefix.prefixID)

            let initialOwnership = await store.ownershipSnapshot()
            XCTAssertEqual(initialOwnership.prefixCount, 2)
            XCTAssertEqual(initialOwnership.pageCount, 2)
            XCTAssertEqual(initialOwnership.blockCount, 2)
            XCTAssertEqual(initialOwnership.sharedPageCount, 2)
            XCTAssertEqual(initialOwnership.sharedBlockCount, 2)
            XCTAssertTrue(initialOwnership.pageRefCountByPageID.values.allSatisfy { $0 == 2 })
            XCTAssertTrue(initialOwnership.blockRefCountByBlockID.values.allSatisfy { $0 == 2 })
            XCTAssertEqual(initialOwnership.copyOnWriteForkCount, 0)

            let firstPurged = await store.purgeCache(
                scope: scope,
                cacheKey: first.prefix.cacheKey,
                includePinned: true
            )
            let midOwnership = await store.ownershipSnapshot()

            XCTAssertEqual(firstPurged, 0)
            XCTAssertEqual(midOwnership.prefixCount, 1)
            XCTAssertEqual(midOwnership.pageCount, 2)
            XCTAssertEqual(midOwnership.blockCount, 2)
            XCTAssertEqual(midOwnership.sharedPageCount, 0)
            XCTAssertEqual(midOwnership.sharedBlockCount, 0)
            XCTAssertTrue(midOwnership.pageRefCountByPageID.values.allSatisfy { $0 == 1 })
            XCTAssertTrue(midOwnership.blockRefCountByBlockID.values.allSatisfy { $0 == 1 })

            let secondPurged = await store.purgeCache(
                scope: scope,
                cacheKey: second.prefix.cacheKey,
                includePinned: true
            )
            let finalOwnership = await store.ownershipSnapshot()

            XCTAssertEqual(secondPurged, 2)
            XCTAssertEqual(finalOwnership.prefixCount, 0)
            XCTAssertEqual(finalOwnership.pageCount, 0)
            XCTAssertEqual(finalOwnership.blockCount, 0)
        }
    }

    func testBoundarySnapshotSaveForksSharedBlockTablesUsingCopyOnWrite() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let diskStore = DiskCacheStore(rootPath: cacheRoot.path)
            let store = HotCacheStore(
                diskStore: diskStore,
                initialCacheBlocks: 0
            )

            let scope = makeCacheScope(scopeID: "scope-cow", modelID: "model-cow")

            func register(prefixSeed: String, fingerprintSeed: String) async throws -> HotCacheRegistration {
                var execution = Melix_Worker_V1_ExecutionMetadata()
                execution.scope = scope
                execution.cacheKey = makeCacheKey(
                    scopeID: scope.scopeID,
                    prefixSeed: prefixSeed,
                    fingerprintSeed: fingerprintSeed
                )
                execution.cacheHints.preferredBlockSize = 16
                return try await store.registerPrefill(
                    execution: execution,
                    model: makeModelSpec(modelID: "model-cow"),
                    messages: [makeUserMessage(prefixSeed)],
                    promptTokens: 32,
                    decodeHandle: "decode-shared-cow",
                    activeKVQuantizationRatio: 50
                )
            }

            let first = try await register(prefixSeed: "cow-1", fingerprintSeed: "cow-fp-1")
            _ = try await register(prefixSeed: "cow-2", fingerprintSeed: "cow-fp-2")

            let prefill = StoredPrefillContext(
                decodeHandle: "decode-shared-cow",
                modelHandle: "model-handle-cow",
                requestID: "req-cow",
                promptTokens: 32,
                messages: [makeUserMessage("save a shared boundary snapshot")],
                resumeHint: "",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                activeKVQuantizationRatio: 50,
                blockTableID: first.blockTableID,
                blockTable: first.blockTable,
                restoredSnapshotID: "",
                prefix: first.prefix,
                context: TextPrefillContext(storage: [:], promptTokens: 32)
            )

            let saved = await store.saveBoundarySnapshot(
                requestID: "req-cow",
                tokenBoundary: 32,
                model: makeModelSpec(modelID: "model-cow"),
                prefill: prefill
            )
            let ownership = await store.ownershipSnapshot()
            let restoredSnapshot = await store.restoreBoundarySnapshot(snapshotID: saved.snapshot.snapshotID)
            let restored = try XCTUnwrap(restoredSnapshot)

            XCTAssertTrue(saved.copyOnWriteForked)
            XCTAssertEqual(ownership.copyOnWriteForkCount, 1)
            XCTAssertNotEqual(saved.blockTableID, first.blockTableID)
            XCTAssertTrue(saved.blockTableID.contains("::cow-"))
            XCTAssertTrue(saved.blockTable.blocks.allSatisfy { $0.blockID.contains("::cow-") })
            XCTAssertTrue(saved.blockTable.pages.allSatisfy { $0.pageID.contains("::cow-") })
            XCTAssertEqual(restored.blockTableID, saved.blockTableID)
            XCTAssertEqual(restored.blockTable.blocks.map(\.blockID), saved.blockTable.blocks.map(\.blockID))
            XCTAssertEqual(restored.blockTable.pages.map(\.pageID), saved.blockTable.pages.map(\.pageID))
        }
    }

    func testHotCacheStorePurgesPagedOwnershipByModelAndScope() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = HotCacheStore(
                diskStore: DiskCacheStore(rootPath: cacheRoot.path),
                initialCacheBlocks: 0
            )

            func register(
                scopeID: String,
                modelID: String,
                prefixSeed: String
            ) async throws {
                var execution = Melix_Worker_V1_ExecutionMetadata()
                execution.scope = makeCacheScope(scopeID: scopeID, modelID: modelID)
                execution.cacheKey = makeCacheKey(
                    scopeID: scopeID,
                    prefixSeed: prefixSeed,
                    fingerprintSeed: "\(prefixSeed)-fp"
                )
                execution.cacheHints.preferredBlockSize = 16
                _ = try await store.registerPrefill(
                    execution: execution,
                    model: makeModelSpec(modelID: modelID),
                    messages: [makeUserMessage(prefixSeed)],
                    promptTokens: 16,
                    decodeHandle: "decode-\(prefixSeed)",
                    activeKVQuantizationRatio: 25
                )
            }

            try await register(scopeID: "scope-one", modelID: "model-one", prefixSeed: "prefix-one")
            try await register(scopeID: "scope-two", modelID: "model-two", prefixSeed: "prefix-two")

            await store.purgeModel(modelID: "model-one")
            let afterModelPurge = await store.ownershipSnapshot()
            XCTAssertEqual(afterModelPurge.prefixCount, 1)
            XCTAssertEqual(afterModelPurge.pageCount, 1)
            XCTAssertEqual(afterModelPurge.blockCount, 1)

            await store.purgeScope(makeCacheScope(scopeID: "scope-two", modelID: "model-two"))
            let afterScopePurge = await store.ownershipSnapshot()
            XCTAssertEqual(afterScopePurge.prefixCount, 0)
            XCTAssertEqual(afterScopePurge.pageCount, 0)
            XCTAssertEqual(afterScopePurge.blockCount, 0)
        }
    }

    // MARK: - Hit taxonomy (milestone #40 phase 1)

    func testHotCacheHitTaxonomyBaselineIsZero() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = HotCacheStore(
                diskStore: DiskCacheStore(rootPath: cacheRoot.path),
                initialCacheBlocks: 0
            )
            let taxonomy = await store.hitTaxonomy()
            XCTAssertEqual(taxonomy.exactHitCount, 0)
            XCTAssertEqual(taxonomy.partialHitCount, 0)
            XCTAssertEqual(taxonomy.fallbackCount, 0)
            XCTAssertEqual(taxonomy.reconstructionFailureCount, 0)
        }
    }

    func testHotCacheHitTaxonomyIncrementsFallbackForColdRegistration() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = HotCacheStore(
                diskStore: DiskCacheStore(rootPath: cacheRoot.path),
                initialCacheBlocks: 0
            )
            let scope = makeCacheScope(scopeID: "scope-cold", modelID: "model-cold")

            for index in 0..<2 {
                var execution = Melix_Worker_V1_ExecutionMetadata()
                execution.scope = scope
                execution.cacheKey = makeCacheKey(
                    scopeID: scope.scopeID,
                    prefixSeed: "cold-\(index)",
                    fingerprintSeed: "cold-fp-\(index)"
                )
                execution.cacheHints.preferredBlockSize = 16
                _ = try await store.registerPrefill(
                    execution: execution,
                    model: makeModelSpec(modelID: "model-cold"),
                    messages: [makeUserMessage("cold-\(index)")],
                    promptTokens: 16,
                    decodeHandle: "decode-cold-\(index)",
                    activeKVQuantizationRatio: 25
                )
            }

            let taxonomy = await store.hitTaxonomy()
            XCTAssertEqual(taxonomy.fallbackCount, 2)
            XCTAssertEqual(taxonomy.exactHitCount, 0)
            XCTAssertEqual(taxonomy.partialHitCount, 0)
            XCTAssertEqual(taxonomy.reconstructionFailureCount, 0)
        }
    }

    func testHotCacheHitTaxonomyIncrementsExactHitOnKeyReuse() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = HotCacheStore(
                diskStore: DiskCacheStore(rootPath: cacheRoot.path),
                initialCacheBlocks: 0
            )
            let scope = makeCacheScope(scopeID: "scope-reuse", modelID: "model-reuse")
            let cacheKey = makeCacheKey(
                scopeID: scope.scopeID,
                prefixSeed: "reuse-prefix",
                fingerprintSeed: "reuse-fp"
            )

            func register() async throws {
                var execution = Melix_Worker_V1_ExecutionMetadata()
                execution.scope = scope
                execution.cacheKey = cacheKey
                execution.cacheHints.preferredBlockSize = 16
                _ = try await store.registerPrefill(
                    execution: execution,
                    model: makeModelSpec(modelID: "model-reuse"),
                    messages: [makeUserMessage("reuse-prefix")],
                    promptTokens: 24,
                    decodeHandle: "decode-reuse",
                    activeKVQuantizationRatio: 50
                )
            }

            try await register()
            try await register()
            try await register()

            let taxonomy = await store.hitTaxonomy()
            XCTAssertEqual(taxonomy.fallbackCount, 1)
            XCTAssertEqual(taxonomy.exactHitCount, 2)
            XCTAssertEqual(taxonomy.partialHitCount, 0)
            XCTAssertEqual(taxonomy.reconstructionFailureCount, 0)
        }
    }

    func testHotCacheHitTaxonomyDirectRecordHooksAdvanceCounters() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = HotCacheStore(
                diskStore: DiskCacheStore(rootPath: cacheRoot.path),
                initialCacheBlocks: 0
            )
            // Accessor coverage for the registry-level hooks; end-to-end wiring is
            // verified by `testPrefillRecordsHitTaxonomyAcrossBoundarySnapshotPaths`.
            await store.recordExactHit()
            await store.recordExactHit()
            await store.recordPartialHit()
            await store.recordReconstructionFailure()
            let taxonomy = await store.hitTaxonomy()
            XCTAssertEqual(taxonomy.exactHitCount, 2)
            XCTAssertEqual(taxonomy.partialHitCount, 1)
            XCTAssertEqual(taxonomy.reconstructionFailureCount, 1)
            XCTAssertEqual(taxonomy.fallbackCount, 0)
        }
    }

    func testPrefillRecordsHitTaxonomyAcrossBoundarySnapshotPaths() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let environment = ["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path]
            let services = makeServices(
                environment: environment,
                backend: DeterministicTextBackend(tokenDelayNanos: 0)
            )

            // Load the test model.
            let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_LoadModelRequest()
                request.model.modelID = "melix-dev-text"
                return try await services.runtime.loadModel(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            // Initial cold prefill — drives the fallback path.
            var initialPrefill = Melix_Worker_V1_PrefillRequest()
            initialPrefill.execution.id.requestID = "req-taxonomy-source"
            initialPrefill.execution.modelHandle = loadResponse.modelHandle
            initialPrefill.execution.cacheHints.allowL2 = true
            initialPrefill.execution.cacheHints.persistL2 = true
            initialPrefill.returnDecodeHandle = true
            initialPrefill.messages = [makeUserMessage("alpha beta gamma delta epsilon")]
            let initialResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: initialPrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let afterFallback = await services.registry.cacheHitTaxonomy()
            XCTAssertEqual(afterFallback.fallbackCount, 1)
            XCTAssertEqual(afterFallback.exactHitCount, 0)
            XCTAssertEqual(afterFallback.partialHitCount, 0)
            XCTAssertEqual(afterFallback.reconstructionFailureCount, 0)

            // Save a boundary snapshot so we can exercise the restore paths.
            let saved = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-taxonomy-source"
                request.decodeHandle = initialResponse.decodeHandle
                request.tokenBoundary = initialResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            // Invalid snapshot ID — restoreBoundarySnapshotRecord throws → reconstruction failure
            // must be recorded AND the cache ownership must be unchanged across the throw.
            let beforeBadRestore = await services.registry.cacheOwnershipSnapshot()
            var badRestorePrefill = Melix_Worker_V1_PrefillRequest()
            badRestorePrefill.execution.id.requestID = "req-taxonomy-bad"
            badRestorePrefill.execution.modelHandle = loadResponse.modelHandle
            badRestorePrefill.execution.cacheHints.restoreSnapshotID = "snapshot-does-not-exist"
            badRestorePrefill.returnDecodeHandle = true
            do {
                _ = try await withTestServerContextRPCCancellationHandle { handle in
                    try await services.inference.prefill(
                        request: badRestorePrefill,
                        context: ServerContext(
                            descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                            remotePeer: "in-process:test",
                            localPeer: "in-process:test",
                            cancellation: handle
                        )
                    )
                }
            } catch {
                // Expected: unknown snapshot id
            }
            let afterBadRestore = await services.registry.cacheOwnershipSnapshot()
            let afterBadTaxonomy = await services.registry.cacheHitTaxonomy()
            XCTAssertEqual(afterBadTaxonomy.reconstructionFailureCount, 1,
                           "reconstruction failure must fire when restoreBoundarySnapshotRecord throws")
            // Reference invariant: nothing should mutate the ownership snapshot on a
            // failed reconstruction (issue #40 Phase 1 safety gate).
            XCTAssertEqual(afterBadRestore.prefixCount, beforeBadRestore.prefixCount)
            XCTAssertEqual(afterBadRestore.pageRefCountByPageID, beforeBadRestore.pageRefCountByPageID)
            XCTAssertEqual(afterBadRestore.blockRefCountByBlockID, beforeBadRestore.blockRefCountByBlockID)

            // Successful restore with identical messages → exact hit branch of the
            // walked-back restore plan (`restorePlan.partial == false`).
            var exactRestorePrefill = Melix_Worker_V1_PrefillRequest()
            exactRestorePrefill.execution.id.requestID = "req-taxonomy-exact"
            exactRestorePrefill.execution.modelHandle = loadResponse.modelHandle
            exactRestorePrefill.execution.cacheHints.restoreSnapshotID = saved.snapshotID
            exactRestorePrefill.returnDecodeHandle = true
            // Same messages as the initial prefill → restorePlan.partial must be false.
            exactRestorePrefill.messages = [makeUserMessage("alpha beta gamma delta epsilon")]
            _ = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: exactRestorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let afterExactRestore = await services.registry.cacheHitTaxonomy()
            XCTAssertEqual(afterExactRestore.exactHitCount, 1,
                           "non-partial walked-back restore must record an exact hit, not a partial hit")
            XCTAssertEqual(afterExactRestore.partialHitCount, 0)
            XCTAssertEqual(afterExactRestore.fallbackCount, 1)
            XCTAssertEqual(afterExactRestore.reconstructionFailureCount, 1)

            // Diverging-messages restore — walked-back plan is `partial: true`.
            // Recipe mirrors `testPrefillCanRestoreBoundarySnapshotsFromHints` partial case:
            // a second scope with a long prompt followed by a shortened, diverging
            // restore prompt so `safeReusableTokenBoundary` < cached total tokens.
            let longSourcePrompt = (1...24).map { "tok\($0)" }.joined(separator: " ")
            let divergedPrompt = (1...20).map { "tok\($0)" }.joined(separator: " ") + " tail-x tail-y"

            var partialSourcePrefill = Melix_Worker_V1_PrefillRequest()
            partialSourcePrefill.execution.id.requestID = "req-partial-source"
            partialSourcePrefill.execution.modelHandle = loadResponse.modelHandle
            partialSourcePrefill.execution.cacheHints.allowL2 = true
            partialSourcePrefill.execution.cacheHints.persistL2 = true
            partialSourcePrefill.returnDecodeHandle = true
            partialSourcePrefill.messages = [makeUserMessage(longSourcePrompt)]
            let partialSourceResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: partialSourcePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            let partialSavedSnapshot = try await withTestServerContextRPCCancellationHandle { handle in
                var request = Melix_Worker_V1_SaveBoundarySnapshotRequest()
                request.requestID = "req-partial-source"
                request.decodeHandle = partialSourceResponse.decodeHandle
                request.tokenBoundary = partialSourceResponse.promptTokens
                return try await services.cache.saveBoundarySnapshot(
                    request: request,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.SaveBoundarySnapshot.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            var partialRestorePrefill = Melix_Worker_V1_PrefillRequest()
            partialRestorePrefill.execution.id.requestID = "req-partial-target"
            partialRestorePrefill.execution.modelHandle = loadResponse.modelHandle
            partialRestorePrefill.execution.cacheHints.restoreSnapshotID = partialSavedSnapshot.snapshotID
            partialRestorePrefill.execution.cacheHints.cachePolicy = "hybrid"
            partialRestorePrefill.prefillStepSize = 16
            partialRestorePrefill.returnDecodeHandle = true
            partialRestorePrefill.messages = [makeUserMessage(divergedPrompt)]
            let partialRestoreResponse = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.inference.prefill(
                    request: partialRestorePrefill,
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }

            XCTAssertTrue(partialRestoreResponse.restorePlan.partial,
                          "precondition: diverged messages must yield a partial restore plan")

            let afterPartialRestore = await services.registry.cacheHitTaxonomy()
            XCTAssertEqual(afterPartialRestore.partialHitCount, 1,
                           "partial walked-back restore must record a partial hit")
            XCTAssertEqual(afterPartialRestore.exactHitCount, 1,
                           "partial restore must NOT double-advance exactHit")
            XCTAssertEqual(afterPartialRestore.fallbackCount, 2,
                           "the partial source prefill itself is a cold registration (fallback++)")
            XCTAssertEqual(afterPartialRestore.reconstructionFailureCount, 1)
        }
    }

    func testHotCacheSnapshotIncludesDiskOnlyScopeSummary() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let diskStore = DiskCacheStore(rootPath: cacheRoot.path)
            let store = HotCacheStore(diskStore: diskStore, initialCacheBlocks: 0)
            let scope = makeCacheScope(scopeID: "scope-disk-only", modelID: "model-disk-only")
            let cacheKey = makeCacheKey(
                scopeID: scope.scopeID,
                prefixSeed: "disk-only-prefix",
                fingerprintSeed: "disk-only-fingerprint"
            )
            let prefix = makePrefixRef(prefixID: "prefix-disk-only", scope: scope, cacheKey: cacheKey)
            let blockTable = makeBlockTable(
                scopeID: scope.scopeID,
                cacheKey: cacheKey,
                blockIDs: ["disk-block"],
                bytes: [128]
            )

            await diskStore.persistPrefix(
                prefix: prefix,
                blockTableID: "table-disk-only",
                blockTable: blockTable,
                quantizedBytes: 64
            )

            let snapshot = await store.snapshot()
            let scopeSummary = try XCTUnwrap(snapshot.scopes.first)

            XCTAssertTrue(snapshot.hotPrefixes.isEmpty)
            XCTAssertEqual(scopeSummary.scope.scopeID, "scope-disk-only")
            XCTAssertEqual(scopeSummary.l1Bytes, 0)
            XCTAssertEqual(scopeSummary.l2Bytes, 64)
            XCTAssertEqual(scopeSummary.prefixCount, 0)
        }
    }

    func testHotCacheStorePromotesColdTierPrefixesBackIntoL1() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let diskStore = DiskCacheStore(rootPath: cacheRoot.path)
            let store = HotCacheStore(diskStore: diskStore, initialCacheBlocks: 0)
            let scope = makeCacheScope(scopeID: "scope-cold-promote", modelID: "model-cold-promote")
            let cacheKey = makeCacheKey(
                scopeID: scope.scopeID,
                prefixSeed: "cold-promote-prefix",
                fingerprintSeed: "cold-promote-fingerprint"
            )
            let prefix = makePrefixRef(prefixID: "prefix-cold-promote", scope: scope, cacheKey: cacheKey)
            let blockTable = makeBlockTable(
                scopeID: scope.scopeID,
                cacheKey: cacheKey,
                blockIDs: ["cold-b0", "cold-b1"],
                bytes: [128, 128]
            )

            await diskStore.persistPrefix(
                prefix: prefix,
                blockTableID: "table-cold-promote",
                blockTable: blockTable,
                quantizedBytes: 96
            )

            var execution = Melix_Worker_V1_ExecutionMetadata()
            execution.scope = scope
            execution.cacheKey = cacheKey
            execution.cacheHints.allowL2 = true
            execution.cacheHints.persistL2 = true
            execution.cacheHints.preferredBlockSize = 16

            let registration = try await store.registerPrefill(
                execution: execution,
                model: makeModelSpec(modelID: "model-cold-promote"),
                messages: [makeUserMessage("cold tier promotion")],
                promptTokens: 32,
                decodeHandle: "decode-cold-promote",
                activeKVQuantizationRatio: 50
            )
            let stats = await store.stats()
            let snapshot = await store.snapshot()

            XCTAssertTrue(registration.cacheHit)
            XCTAssertEqual(registration.blockTableID, "table-cold-promote")
            XCTAssertEqual(registration.prefix.prefixID, "prefix-cold-promote")
            XCTAssertEqual(registration.prefix.tier, "l1")
            XCTAssertEqual(stats.l1HitRate, 0, accuracy: 0.0001)
            XCTAssertEqual(stats.l2HitRate, 1, accuracy: 0.0001)
            XCTAssertEqual(snapshot.hotPrefixes.count, 1)
            XCTAssertEqual(snapshot.hotPrefixes.first?.prefixID, "prefix-cold-promote")
            XCTAssertEqual(snapshot.hotPrefixes.first?.tier, "l1")
        }
    }

    func testWorkerCacheStatsExposeRuntimeFingerprintAndMemoryBudgetDiagnostics() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let services = makeServices(
                environment: [
                    "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path,
                    "MELIX_SWIFT_TEXT_WORKER_RUNTIME_CACHE_FINGERPRINT": "runtime-cache-test",
                    "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "20000",
                    "MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES": "1000",
                ],
                backend: FakeRuntimeBackend(residentBytesHint: 4_096)
            )

            let loaded = try await services.registry.loadModel(makeModelSpec(modelID: "model-cache-budget"))
            _ = try await services.registry.prefill(
                requestID: "req-cache-budget",
                modelHandle: loaded.handle,
                messages: [makeUserMessage("cache budget diagnostics")],
                prefillStepSize: 16,
                returnDecodeHandle: true,
                resumeHint: "",
                acceleration: makeAccelerationPolicy(mode: .baseline),
                shouldAbort: { false }
            )

            let response = await services.registry.cacheStatsResponse()

            XCTAssertEqual(response.stats.runtimeCacheFingerprint, "runtime-cache-test")
            XCTAssertEqual(response.snapshot.stats.runtimeCacheFingerprint, "runtime-cache-test")
            XCTAssertEqual(response.stats.activeMemoryBytes, 4_096 + response.stats.l1Bytes)
            XCTAssertEqual(response.stats.maxWorkingSetBytes, 20_000)
            XCTAssertEqual(response.stats.effectiveCacheBudgetBytes, 14_904)
        }
    }

    func testCacheStatsRPCEmitsRuntimeFingerprintAndNamespaceMismatchMetrics() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let staleStore = DiskCacheStore(
                rootPath: cacheRoot.path,
                runtimeCacheFingerprint: "runtime-cache-old"
            )
            let scope = makeCacheScope(scopeID: "scope-rpc-stale", modelID: "model-rpc-stale")
            let cacheKey = makeCacheKey(
                scopeID: scope.scopeID,
                prefixSeed: "rpc-stale-prefix",
                fingerprintSeed: "rpc-stale-fingerprint"
            )
            let prefix = makePrefixRef(prefixID: "prefix-rpc-stale", scope: scope, cacheKey: cacheKey)
            let blockTable = makeBlockTable(
                scopeID: scope.scopeID,
                cacheKey: cacheKey,
                blockIDs: ["rpc-stale-block"],
                bytes: [128]
            )
            await staleStore.persistPrefix(
                prefix: prefix,
                blockTableID: "table-rpc-stale",
                blockTable: blockTable,
                quantizedBytes: 64
            )

            let services = makeServices(
                environment: [
                    "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": cacheRoot.path,
                    "MELIX_SWIFT_TEXT_WORKER_RUNTIME_CACHE_FINGERPRINT": "runtime-cache-new",
                    "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "4096",
                ]
            )
            let response = try await withTestServerContextRPCCancellationHandle { handle in
                try await services.cache.getCacheStats(
                    request: Melix_Worker_V1_GetCacheStatsRequest(),
                    context: ServerContext(
                        descriptor: Melix_Worker_V1_CacheService.Method.GetCacheStats.descriptor,
                        remotePeer: "in-process:test",
                        localPeer: "in-process:test",
                        cancellation: handle
                    )
                )
            }
            let counters = services.metrics.counters

            XCTAssertEqual(response.stats.runtimeCacheFingerprint, "runtime-cache-new")
            XCTAssertEqual(response.stats.cacheNamespaceMismatchCount, 1)
            XCTAssertEqual(counters["swift_text.cache_namespace_mismatch_count"], 1)
            XCTAssertEqual(counters["swift_text.max_working_set_bytes"], 4_096)
            XCTAssertEqual(counters["swift_text.runtime_cache_fingerprint_code"], 0)
        }
    }

    func testDiskCacheStoreNormalizesLegacyBlockTablesIntoPagedOwnership() async throws {
        try await withTemporaryCacheRoot { cacheRoot in
            let store = DiskCacheStore(rootPath: cacheRoot.path)
            let scope = makeCacheScope(scopeID: "scope-disk", modelID: "model-disk")
            let cacheKey = makeCacheKey(
                scopeID: scope.scopeID,
                prefixSeed: "disk-prefix",
                fingerprintSeed: "disk-fingerprint"
            )
            let prefix = makePrefixRef(prefixID: "prefix-disk", scope: scope, cacheKey: cacheKey)
            let legacyTable = makeBlockTable(
                scopeID: scope.scopeID,
                cacheKey: cacheKey,
                blockIDs: ["d0", "d1"],
                bytes: [96, 96]
            )

            XCTAssertTrue(legacyTable.pages.isEmpty)

            await store.persistPrefix(
                prefix: prefix,
                blockTableID: "table-disk",
                blockTable: legacyTable,
                quantizedBytes: 64
            )

            let ownership = await store.ownershipSnapshot()
            let summary = await store.summary()

            XCTAssertEqual(ownership.prefixCount, 1)
            XCTAssertEqual(ownership.pageCount, 2)
            XCTAssertEqual(ownership.blockCount, 2)
            XCTAssertEqual(summary.scopes.first?.snapshotCount, 0)
            XCTAssertEqual(summary.l2Bytes, 64)
        }
    }

    func testDiskCacheQuantizationHelpersClampAndNormalizeProfiles() {
        let table = makeBlockTable(
            scopeID: "scope-quant",
            cacheKey: makeCacheKey(scopeID: "scope-quant", prefixSeed: "quant-prefix", fingerprintSeed: "quant-fingerprint"),
            blockIDs: ["q0", "q1"],
            bytes: [120, 80]
        )

        XCTAssertEqual(storageBoundaryQuantizedBytes(for: table, activeKVQuantizationRatio: 0), 100)
        XCTAssertEqual(storageBoundaryQuantizedBytes(for: table, activeKVQuantizationRatio: 150), 200)
        XCTAssertEqual(storageBoundaryQuantizedBytes(for: table, activeKVQuantizationRatio: 1), 2)

        XCTAssertEqual(activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .baseline)), 0)
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "q4")),
            25
        )
        XCTAssertEqual(
            activeKVQuantizationRatio(
                from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "turboquant-q4")
            ),
            25
        )
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized)),
            25
        )
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "  ")),
            25
        )
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "q8")),
            50
        )
        XCTAssertEqual(
            activeKVQuantizationRatio(from: makeAccelerationPolicy(mode: .activeKvQuantized, activeKvQuantProfile: "custom")),
            50
        )
    }

    #if canImport(MLXLMCommon)
    func testActiveKVDefaultProfileNormalizesToTurboQuantQ4() {
        var activeAcceleration = Melix_Worker_V1_AccelerationPolicy()
        activeAcceleration.mode = .activeKvQuantized

        let normalized = normalizedAccelerationPolicy(activeAcceleration)

        XCTAssertEqual(normalized.activeKvQuantProfile, "turboquant-q4")
        XCTAssertEqual(
            activeKVKernelPathCode(
                for: normalized,
                turboQuantRuntimeRoute: .blocked(.attentionHookUnavailable)
            ),
            90
        )
    }

    func testActiveKVDecodeQuantizationGuardSkipsWhenCacheIsAlreadyQuantized() {
        var activeAcceleration = Melix_Worker_V1_AccelerationPolicy()
        activeAcceleration.mode = .activeKvQuantized
        activeAcceleration.activeKvQuantProfile = "q4"

        let standardCache = KVCacheSimple()
        standardCache.offset = 2
        XCTAssertTrue(
            shouldAttemptActiveKVDecodeQuantization(
                cache: [standardCache],
                kvBits: 4,
                quantizedKVStart: 0,
                acceleration: activeAcceleration
            )
        )

        let quantizedCache = QuantizedKVCache(groupSize: 64, bits: 4)
        quantizedCache.offset = 2
        XCTAssertFalse(
            shouldAttemptActiveKVDecodeQuantization(
                cache: [quantizedCache],
                kvBits: 4,
                quantizedKVStart: 0,
                acceleration: activeAcceleration
            )
        )

        standardCache.offset = 0
        XCTAssertFalse(
            shouldAttemptActiveKVDecodeQuantization(
                cache: [standardCache],
                kvBits: 4,
                quantizedKVStart: 0,
                acceleration: activeAcceleration
            )
        )

        standardCache.offset = 2
        XCTAssertFalse(
            shouldAttemptActiveKVDecodeQuantization(
                cache: [standardCache],
                kvBits: nil,
                quantizedKVStart: 0,
                acceleration: activeAcceleration
            )
        )

        var baselineAcceleration = Melix_Worker_V1_AccelerationPolicy()
        baselineAcceleration.mode = .baseline
        XCTAssertFalse(
            shouldAttemptActiveKVDecodeQuantization(
                cache: [standardCache],
                kvBits: 4,
                quantizedKVStart: 0,
                acceleration: baselineAcceleration
            )
        )
    }

    func testActiveKVDecodeQuantizationGuardDetectsEligibleSimpleLayerAfterMambaCache() {
        var activeAcceleration = Melix_Worker_V1_AccelerationPolicy()
        activeAcceleration.mode = .activeKvQuantized
        activeAcceleration.activeKvQuantProfile = "turboquant-q4"

        let mambaCache = MambaCache()
        let simpleCache = KVCacheSimple()
        simpleCache.offset = 2

        XCTAssertTrue(
            shouldAttemptActiveKVDecodeQuantization(
                cache: [mambaCache, simpleCache],
                kvBits: 4,
                quantizedKVStart: 0,
                acceleration: activeAcceleration
            )
        )

        let quantizedCache = QuantizedKVCache(groupSize: 64, bits: 4)
        quantizedCache.offset = 2
        XCTAssertFalse(
            shouldAttemptActiveKVDecodeQuantization(
                cache: [mambaCache, quantizedCache],
                kvBits: 4,
                quantizedKVStart: 0,
                acceleration: activeAcceleration
            )
        )
    }
    #endif

    #if canImport(MLX) && canImport(MLXLMCommon)
    func testMaybeQuantizeKVCacheQuantizesSimpleLayerAfterMambaCache() async throws {
        try await withTemporaryDefaultMetallib {
            var emptyCache: [KVCache] = []
            maybeQuantizeKVCache(cache: &emptyCache, kvBits: 4)
            XCTAssertTrue(emptyCache.isEmpty)

            let mambaCache = MambaCache()
            let simpleCache = KVCacheSimple()
            let sequenceLength = 2
            let headDimension = 32
            let keyValues = (0 ..< sequenceLength * headDimension).map { Float($0 % 11) / 11.0 }
            let valueValues = (0 ..< sequenceLength * headDimension).map { Float($0 % 13) / 13.0 }
            let keys = MLXArray(keyValues, [1, 1, sequenceLength, headDimension])
            let values = MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            _ = simpleCache.update(keys: keys, values: values)

            var cache: [KVCache] = [mambaCache, simpleCache]
            maybeQuantizeKVCache(cache: &cache, kvBits: nil, kvGroupSize: 32)
            XCTAssertTrue(cache[0] is MambaCache)
            XCTAssertTrue(cache[1] is KVCacheSimple)

            maybeQuantizeKVCache(
                cache: &cache,
                kvBits: 4,
                kvGroupSize: 32,
                quantizedKVStart: 0
            )

            XCTAssertTrue(cache[0] is MambaCache)
            let quantizedCache = try XCTUnwrap(cache[1] as? QuantizedKVCacheProtocol)
            XCTAssertEqual(quantizedCache.bits, 4)
            XCTAssertEqual(quantizedCache.groupSize, 32)
            XCTAssertEqual(quantizedCache.offset, sequenceLength)
            XCTAssertNotNil(quantizedCache.getQuantizedState())
        }
    }

    #if canImport(MLXLLM)
    func testSwiftTextRuntimeRegistryCreatesGemma4TextBackboneFromNestedVLMConfig() async throws {
        try await withTemporaryDefaultMetallib {
            let configURL = URL(
                fileURLWithPath: FileManager.default.currentDirectoryPath,
                isDirectory: true
            ).appendingPathComponent("config.json")
            let configJSON =
                """
                {
                  "model_type": "gemma4",
                  "text_config": {
                    "model_type": "gemma4_text",
                    "hidden_size": 32,
                    "num_hidden_layers": 2,
                    "intermediate_size": 64,
                    "num_attention_heads": 2,
                    "head_dim": 8,
                    "global_head_dim": 16,
                    "global_partial_rotary_factor": 0.25,
                    "rms_norm_eps": 0.000001,
                    "vocab_size": 64,
                    "vocab_size_per_layer_input": 64,
                    "num_key_value_heads": 1,
                    "num_global_key_value_heads": 1,
                    "num_kv_shared_layers": 0,
                    "hidden_size_per_layer_input": 0,
                    "sliding_window": 8,
                    "sliding_window_pattern": 2,
                    "max_position_embeddings": 128,
                    "attention_k_eq_v": false,
                    "final_logit_softcapping": 30.0,
                    "use_double_wide_mlp": false,
                    "enable_moe_block": false,
                    "layer_types": ["sliding_attention", "full_attention"],
                    "tie_word_embeddings": true
                  }
                }
                """
            try configJSON.data(using: .utf8)!.write(to: configURL)

            let supportsGemma4 = await LLMTypeRegistry.shared.supportsModelType("gemma4")
            let supportsGemma4Text = await LLMTypeRegistry.shared.supportsModelType("gemma4_text")
            XCTAssertTrue(supportsGemma4)
            XCTAssertTrue(supportsGemma4Text)

            let model = try await LLMTypeRegistry.shared.createModel(
                configuration: configURL,
                modelType: "gemma4"
            )

            XCTAssertEqual(String(describing: type(of: model)), "Gemma4Model")
        }
    }

    func testGemma4ProportionalRoPEKeepsDerivedFrequenciesOutOfLoadParameters() async throws {
        try await withTemporaryDefaultMetallib {
            let rope = initializeRopeLayer(
                dims: 16,
                base: 10_000,
                traditional: false,
                scalingConfig: [
                    "rope_type": .string("proportional"),
                    "factor": .int(8),
                    "partial_rotary_factor": .float(0.5),
                ],
                maxPositionEmbeddings: 131_072
            )

            let parameterNames = rope.parameters().flattened().map(\.0)

            XCTAssertFalse(parameterNames.contains("freqs"))
            XCTAssertTrue(rope.items().keys.contains("_freqs"))
        }
    }

    func testGemma4TextFullAttentionCacheUsesLongContextGrowthStep() async throws {
        try await withTemporaryDefaultMetallib {
            let configJSON =
                """
                {
                  "model_type": "gemma4_text",
                  "hidden_size": 32,
                  "num_hidden_layers": 4,
                  "intermediate_size": 64,
                  "num_attention_heads": 2,
                  "head_dim": 8,
                  "global_head_dim": 16,
                  "global_partial_rotary_factor": 0.25,
                  "rms_norm_eps": 0.000001,
                  "vocab_size": 64,
                  "vocab_size_per_layer_input": 64,
                  "num_key_value_heads": 1,
                  "num_global_key_value_heads": 1,
                  "num_kv_shared_layers": 1,
                  "hidden_size_per_layer_input": 0,
                  "sliding_window": 512,
                  "sliding_window_pattern": 2,
                  "max_position_embeddings": 131072,
                  "attention_k_eq_v": false,
                  "final_logit_softcapping": 30.0,
                  "use_double_wide_mlp": false,
                  "enable_moe_block": false,
                  "layer_types": [
                    "sliding_attention",
                    "full_attention",
                    "full_attention",
                    "sliding_attention"
                  ],
                  "tie_word_embeddings": true
                }
                """
            let config = try JSONDecoder().decode(
                Gemma4TextConfiguration.self,
                from: Data(configJSON.utf8)
            )
            let model = Gemma4TextModel(config)

            let cache = model.newCache(parameters: nil)

            XCTAssertEqual(cache.count, 3)
            XCTAssertEqual(cache[0].maxSize, 512)
            let firstFullCache = try XCTUnwrap(cache[1] as? KVCacheSimple)
            let secondFullCache = try XCTUnwrap(cache[2] as? KVCacheSimple)
            XCTAssertEqual(firstFullCache.step, 1024)
            XCTAssertEqual(secondFullCache.step, 1024)
        }
    }

    func testGemma4TextActiveKVDecodeUsesFusedAttentionWithoutMaterializingWhenKVSharingIsDisabled()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            let configJSON =
                """
                {
                  "model_type": "gemma4_text",
                  "hidden_size": 32,
                  "num_hidden_layers": 1,
                  "intermediate_size": 64,
                  "num_attention_heads": 2,
                  "head_dim": 32,
                  "global_head_dim": 32,
                  "global_partial_rotary_factor": 1.0,
                  "rms_norm_eps": 0.000001,
                  "vocab_size": 64,
                  "vocab_size_per_layer_input": 64,
                  "num_key_value_heads": 1,
                  "num_global_key_value_heads": 1,
                  "num_kv_shared_layers": 0,
                  "hidden_size_per_layer_input": 0,
                  "sliding_window": 8,
                  "sliding_window_pattern": 2,
                  "max_position_embeddings": 128,
                  "attention_k_eq_v": false,
                  "final_logit_softcapping": 30.0,
                  "use_double_wide_mlp": false,
                  "enable_moe_block": false,
                  "layer_types": ["full_attention"],
                  "tie_word_embeddings": true
                }
                """
            let config = try JSONDecoder().decode(
                Gemma4TextConfiguration.self,
                from: Data(configJSON.utf8)
            )
            let model = Gemma4TextModel(config)
            var cache = model.newCache(parameters: nil)
            let prompt = MLXArray([1, 2, 3], [1, 3])
            _ = model(prompt, cache: cache)

            maybeQuantizeKVCache(cache: &cache, kvBits: 4, kvGroupSize: 32)
            let quantizedCache = try XCTUnwrap(cache.first as? QuantizedKVCacheProtocol)

            _ = model(MLXArray([4], [1, 1]), cache: cache)

            XCTAssertEqual(quantizedCache.fusedAttentionDispatchCount, 1)
            XCTAssertEqual(quantizedCache.fusedAttentionCallCount, 1)
            XCTAssertEqual(quantizedCache.quantizedCacheMaterializeCallCount, 0)
        }
    }
    #endif

    func testQuantizedKVCacheRecordsUpdateAndMaterializeProbeTimings() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 2
            let headDimension = 32
            let groupSize = 32
            let keyValues = (0 ..< sequenceLength * headDimension).map { Float(($0 % 13) - 6) / 8.0 }
            let valueValues = (0 ..< sequenceLength * headDimension).map { Float(($0 % 17) - 8) / 10.0 }
            let keys = MLXArray(keyValues, [1, 1, sequenceLength, headDimension])
            let values = MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)

            XCTAssertEqual(cache.quantizedCacheUpdateCallCount, 0)
            XCTAssertEqual(cache.quantizedCacheMaterializeCallCount, 0)

            _ = cache.updateQuantized(keys: keys, values: values)
            let updateTotalAfterFirstAppend = cache.quantizedCacheUpdateTotalMicros

            XCTAssertEqual(cache.quantizedCacheUpdateCallCount, 1)
            XCTAssertEqual(cache.quantizedCacheMaterializeCallCount, 1)
            XCTAssertGreaterThanOrEqual(cache.quantizedCacheUpdateTotalMicros, 0)
            XCTAssertGreaterThanOrEqual(cache.quantizedCacheExpandTotalMicros, 0)
            XCTAssertGreaterThanOrEqual(cache.quantizedCacheQuantizeTotalMicros, 0)
            XCTAssertGreaterThanOrEqual(cache.quantizedCacheAppendTotalMicros, 0)
            XCTAssertGreaterThanOrEqual(cache.quantizedCacheMaterializeTotalMicros, 0)

            let state = try XCTUnwrap(cache.getQuantizedState())
            XCTAssertEqual(state.0.0.dtype, DType.uint32)
            XCTAssertEqual(cache.quantizedCacheMaterializeCallCount, 2)

            _ = cache.updateQuantized(
                keys: MLXArray(Array(repeating: Float(0.25), count: headDimension), [1, 1, 1, headDimension]),
                values: MLXArray(Array(repeating: Float(-0.25), count: headDimension), [1, 1, 1, headDimension])
            )

            XCTAssertEqual(cache.quantizedCacheUpdateCallCount, 2)
            XCTAssertGreaterThanOrEqual(cache.quantizedCacheUpdateTotalMicros, updateTotalAfterFirstAppend)
            XCTAssertEqual(cache.quantizedCacheMaterializeCallCount, 3)
        }
    }
    #endif

    #if canImport(MLX)
    func testActiveKVModelEvalSyncProbeIsOptIn() async throws {
        try await withTemporaryDefaultMetallib {
            let logits = MLXArray([Float(1.0), Float(2.0)], [1, 2])

            XCTAssertNil(activeKVModelEvalSyncMicrosIfNeeded(enabled: false, logits: logits))

            let elapsed = activeKVModelEvalSyncMicrosIfNeeded(enabled: true, logits: logits)

            XCTAssertNotNil(elapsed)
            XCTAssertGreaterThanOrEqual(elapsed ?? -1, 0)
        }
    }

    func testTurboQuantMetalCapabilityRunsCustomIdentityKernel() async throws {
        try await withTemporaryDefaultMetallib {
            let input = MLXArray([Float(1.0), Float(-2.0), Float(3.5), Float(4.25)])

            let output = TurboQuantMetalKernelCapability.runIdentitySmokeKernel(input)

            XCTAssertEqual(output.shape, input.shape)
            XCTAssertEqual(output.dtype, input.dtype)
            XCTAssertTrue(allClose(output, input).all().item())
        }
    }

    func testTurboQuantMetalCapabilityRunsMSEQ4ValueDecodeKernel() async throws {
        try await withTemporaryDefaultMetallib {
            let packedValues = MLXArray(
                [
                    Int32(0x31), Int32(0x75),
                    Int32(0x42), Int32(0x86),
                    Int32(0x0f), Int32(0xa9),
                ],
                [3, 2]
            )
            let weights = MLXArray([Float(0.2), Float(0.3), Float(0.5)])
            let scales = MLXArray(
                [Float(0.5), Float(0.25), Float(1.0), Float(0.125), Float(0.2), Float(0.75)],
                [3, 2]
            )
            let biases = MLXArray(
                [Float(-1.0), Float(0.5), Float(-2.0), Float(-0.25), Float(0.0), Float(-3.0)],
                [3, 2]
            )

            let output = TurboQuantMetalKernelCapability.runMSEQ4ValueDecodeSmokeKernel(
                packedValues: packedValues,
                weights: weights,
                scales: scales,
                biases: biases,
                sequenceLength: 3,
                headDimension: 4,
                groupSize: 2
            )

            let expected = MLXArray([Float(1.4), Float(0.7), Float(2.375), Float(2.925)])
            XCTAssertEqual(output.shape, [4])
            XCTAssertEqual(output.dtype, DType.float32)
            XCTAssertTrue(allClose(output, expected).all().item())
        }
    }

    func testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionKernel() async throws {
        try await withTemporaryDefaultMetallib {
            let query = MLXArray([Float(0.25), Float(-0.5), Float(0.75), Float(1.0)])
            let packedKeys = MLXArray(
                [
                    Int32(0x31), Int32(0x75),
                    Int32(0x42), Int32(0x86),
                    Int32(0x0f), Int32(0xa9),
                ],
                [3, 2]
            )
            let keyScales = MLXArray(
                [Float(0.5), Float(0.25), Float(1.0), Float(0.125), Float(0.2), Float(0.75)],
                [3, 2]
            )
            let keyBiases = MLXArray(
                [Float(-1.0), Float(0.5), Float(-2.0), Float(-0.25), Float(0.0), Float(-3.0)],
                [3, 2]
            )
            let packedValues = MLXArray(
                [
                    Int32(0x10), Int32(0x32),
                    Int32(0x23), Int32(0x01),
                    Int32(0x11), Int32(0x11),
                ],
                [3, 2]
            )
            let valueScales = MLXArray(
                [Float(1.0), Float(0.5), Float(0.25), Float(1.0), Float(0.5), Float(0.25)],
                [3, 2]
            )
            let valueBiases = MLXArray(
                [Float(0.0), Float(-1.0), Float(0.5), Float(0.0), Float(-0.5), Float(0.25)],
                [3, 2]
            )

            let output = TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionSmokeKernel(
                query: query,
                packedKeys: packedKeys,
                keyScales: keyScales,
                keyBiases: keyBiases,
                packedValues: packedValues,
                valueScales: valueScales,
                valueBiases: valueBiases,
                sequenceLength: 3,
                headDimension: 4,
                groupSize: 2
            )

            let expected = MLXArray([
                Float(0.021352084),
                Float(0.096066497),
                Float(0.469048419),
                Float(0.491459166),
            ])
            XCTAssertEqual(output.shape, [4])
            XCTAssertEqual(output.dtype, DType.float32)
            XCTAssertTrue(allClose(output, expected).all().item())
        }
    }

    #if canImport(MLXLMCommon)
    func testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 3
            let headDimension = 32
            let groupSize = 32
            let queryValues = (0 ..< headDimension).map { Float($0 - 12) / 16.0 }
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 19) - 9) / 8.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 23) - 11) / 10.0
            }
            let queries = MLXArray(queryValues, [1, 1, 1, headDimension])
            let keys = MLXArray(keyValues, [1, 1, sequenceLength, headDimension])
            let values = MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            let (quantizedKeys, quantizedValues) = cache.updateQuantized(keys: keys, values: values)

            let output = try XCTUnwrap(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: queries[0, 0, 0, 0...],
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            let expected = quantizedScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: Float(1.0 / Double(headDimension).squareRoot()),
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            )[0, 0, 0, 0...]

            XCTAssertEqual(quantizedKeys.0.dtype, DType.uint32)
            XCTAssertEqual(output.shape, [headDimension])
            XCTAssertEqual(output.dtype, DType.float32)
            XCTAssertTrue(allClose(output, expected, rtol: 1e-4, atol: 1e-4).all().item())
        }
    }

    func testVendoredFusedQ4AttentionMatchesQuantizedReferenceForDecodeGQA() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 4
            let headDimension = 32
            let groupSize = 32
            let queryHeadCount = 2
            let kvHeadCount = 1
            let queryValues = (0 ..< queryHeadCount * headDimension).map { index in
                Float((index % 31) - 15) / 17.0
            }
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 19) - 9) / 8.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 23) - 11) / 10.0
            }
            let queries = MLXArray(queryValues, [1, queryHeadCount, 1, headDimension])
            let keys = MLXArray(keyValues, [1, kvHeadCount, sequenceLength, headDimension])
            let values = MLXArray(valueValues, [1, kvHeadCount, sequenceLength, headDimension])
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            let (quantizedKeys, quantizedValues) = cache.updateQuantized(keys: keys, values: values)

            let fused = try XCTUnwrap(fusedQ4ScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: Float(1.0 / Double(headDimension).squareRoot()),
                mask: .causal,
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            ))
            let expected = quantizedScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: Float(1.0 / Double(headDimension).squareRoot()),
                mask: .causal,
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            )

            XCTAssertEqual(fused.shape, expected.shape)
            XCTAssertTrue(allClose(fused, expected, rtol: 1e-4, atol: 1e-4).all().item())
        }
    }

    func testVendoredFusedQ4AttentionPreservesQueryDTypeForDecodeGQA() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 4
            let headDimension = 32
            let groupSize = 32
            let queryHeadCount = 2
            let kvHeadCount = 1
            let queryValues = (0 ..< queryHeadCount * headDimension).map { index in
                Float((index % 31) - 15) / 17.0
            }
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 19) - 9) / 8.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 23) - 11) / 10.0
            }
            let queries = MLXArray(queryValues, [1, queryHeadCount, 1, headDimension]).asType(.bfloat16)
            let keys = MLXArray(keyValues, [1, kvHeadCount, sequenceLength, headDimension]).asType(.bfloat16)
            let values = MLXArray(valueValues, [1, kvHeadCount, sequenceLength, headDimension]).asType(.bfloat16)
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            let (quantizedKeys, quantizedValues) = cache.updateQuantized(keys: keys, values: values)

            let fused = try XCTUnwrap(fusedQ4ScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: Float(1.0 / Double(headDimension).squareRoot()),
                mask: .causal,
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            ))
            let expected = quantizedScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: Float(1.0 / Double(headDimension).squareRoot()),
                mask: .causal,
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            )

            XCTAssertEqual(fused.dtype, queries.dtype)
            XCTAssertTrue(allClose(fused, expected, rtol: 1e-2, atol: 1e-2).all().item())
        }
    }

    func testVendoredFusedQ4AttentionMatchesQuantizedReferenceForDecodeHeadDimension128()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 4
            let headDimension = 128
            let groupSize = 64
            let queryHeadCount = 2
            let kvHeadCount = 1
            let queryValues = (0 ..< queryHeadCount * headDimension).map { index in
                Float((index % 37) - 18) / 19.0
            }
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 29) - 14) / 13.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 31) - 15) / 14.0
            }
            let queries = MLXArray(queryValues, [1, queryHeadCount, 1, headDimension]).asType(.bfloat16)
            let keys = MLXArray(keyValues, [1, kvHeadCount, sequenceLength, headDimension]).asType(.bfloat16)
            let values = MLXArray(valueValues, [1, kvHeadCount, sequenceLength, headDimension]).asType(.bfloat16)
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            let (quantizedKeys, quantizedValues) = cache.updateQuantized(keys: keys, values: values)

            let fused = try XCTUnwrap(fusedQ4ScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: Float(1.0 / Double(headDimension).squareRoot()),
                mask: .causal,
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            ))
            let expected = quantizedScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: Float(1.0 / Double(headDimension).squareRoot()),
                mask: .causal,
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            )

            XCTAssertEqual(fused.shape, expected.shape)
            XCTAssertTrue(allClose(fused, expected, rtol: 1e-2, atol: 1e-2).all().item())
        }
    }

    func testAttentionWithCacheUpdateUsesFusedQuantizedStorageWithoutMaterializingForDecode()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 4
            let headDimension = 32
            let groupSize = 32
            let queryHeadCount = 4
            let kvHeadCount = 2
            let scale = Float(1.0 / Double(headDimension).squareRoot())
            let queryValues = (0 ..< queryHeadCount * headDimension).map { index in
                Float((index % 31) - 15) / 17.0
            }
            let keyValues = (0 ..< kvHeadCount * sequenceLength * headDimension).map { index in
                Float((index % 19) - 9) / 8.0
            }
            let valueValues = (0 ..< kvHeadCount * sequenceLength * headDimension).map { index in
                Float((index % 23) - 11) / 10.0
            }
            let queries = MLXArray(queryValues, [1, queryHeadCount, 1, headDimension])
            let keys = MLXArray(keyValues, [1, kvHeadCount, sequenceLength, headDimension])
            let values = MLXArray(valueValues, [1, kvHeadCount, sequenceLength, headDimension])
            let fusedCache = QuantizedKVCache(groupSize: groupSize, bits: 4)

            let fused = attentionWithCacheUpdate(
                queries: queries,
                keys: keys,
                values: values,
                cache: fusedCache,
                scale: scale,
                mask: .causal
            )
            let referenceKeys = quantized(keys, groupSize: groupSize, bits: 4)
            let referenceValues = quantized(values, groupSize: groupSize, bits: 4)
            let quantizedKeys: QuantizedKVCacheTuple = (
                referenceKeys.wq,
                referenceKeys.scales,
                referenceKeys.biases
            )
            let quantizedValues: QuantizedKVCacheTuple = (
                referenceValues.wq,
                referenceValues.scales,
                referenceValues.biases
            )
            let expected = quantizedScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: scale,
                mask: .causal,
                groupSize: groupSize,
                bits: 4,
                mode: .affine
            )

            XCTAssertEqual(fusedCache.offset, sequenceLength)
            XCTAssertEqual(fusedCache.quantizedCacheUpdateCallCount, 1)
            XCTAssertEqual(fusedCache.fusedAttentionDispatchCount, 1)
            XCTAssertEqual(fusedCache.fusedAttentionCallCount, 1)
            XCTAssertEqual(fusedCache.fusedAttentionActiveLaneTotal, 4)
            XCTAssertEqual(fusedCache.fusedAttentionLaunchedLaneTotal, 32)
            XCTAssertEqual(fusedCache.fusedAttentionSoftmaxLaneTotal, 1)
            XCTAssertEqual(fusedCache.fusedAttentionSoftmaxTokenLaneTotal, 4)
            XCTAssertGreaterThanOrEqual(fusedCache.fusedAttentionTotalMicros, 0)
            XCTAssertGreaterThanOrEqual(fusedCache.fusedAttentionRouteTotalMicros, fusedCache.fusedAttentionTotalMicros)
            XCTAssertEqual(fusedCache.quantizedCacheMaterializeCallCount, 0)
            XCTAssertTrue(allClose(fused, expected, rtol: 1e-4, atol: 1e-4).all().item())
        }
    }

    func testAttentionWithCacheUpdateMaterializesQuantizedStorageWhenFusedRouteIsUnsupported()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 3
            let headDimension = 32
            let groupSize = 32
            let scale = Float(1.0 / Double(headDimension).squareRoot())
            let queryValues = (0 ..< headDimension).map { index in
                Float((index % 29) - 14) / 15.0
            }
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 17) - 8) / 9.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 13) - 6) / 7.0
            }
            let queries = MLXArray(queryValues, [1, 1, 1, headDimension])
            let keys = MLXArray(keyValues, [1, 1, sequenceLength, headDimension])
            let values = MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            let fallbackCache = QuantizedKVCache(groupSize: groupSize, bits: 8)
            let referenceCache = QuantizedKVCache(groupSize: groupSize, bits: 8)

            let fallback = attentionWithCacheUpdate(
                queries: queries,
                keys: keys,
                values: values,
                cache: fallbackCache,
                scale: scale,
                mask: .causal
            )
            let (quantizedKeys, quantizedValues) = referenceCache.updateQuantized(
                keys: keys,
                values: values
            )
            let expected = quantizedScaledDotProductAttention(
                queries: queries,
                quantizedKeys: quantizedKeys,
                quantizedValues: quantizedValues,
                scale: scale,
                mask: .causal,
                groupSize: groupSize,
                bits: 8,
                mode: .affine
            )

            XCTAssertEqual(fallbackCache.fusedAttentionDispatchCount, 0)
            XCTAssertEqual(fallbackCache.quantizedCacheUpdateCallCount, 1)
            XCTAssertEqual(fallbackCache.quantizedCacheMaterializeCallCount, 1)
            XCTAssertTrue(allClose(fallback, expected, rtol: 1e-4, atol: 1e-4).all().item())
        }
    }

    func testFusedDecodeQuantizerMatchesReferenceForSingleTokenAffineQ4()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            try assertFusedDecodeQuantizerMatchesReference(
                dtype: .float32,
                headDimension: 32,
                groupSize: 32,
                rtol: 1e-6,
                atol: 1e-6
            )
        }
    }

    func testFusedDecodeQuantizerMatchesReferenceForSingleTokenBFloat16AffineQ4()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            try assertFusedDecodeQuantizerMatchesReference(
                dtype: .bfloat16,
                headDimension: 128,
                groupSize: 64,
                rtol: 1e-2,
                atol: 1e-2
            )
        }
    }

    func testFusedDecodeQuantizerRejectsUnsupportedInputs() async throws {
        try await withTemporaryDefaultMetallib {
            let (keys, values) = makeDecodeKeyValueTensors(dtype: .float32, headDimension: 32)

            XCTAssertNil(fusedQ4AffineKeyValueQuantizedForDecode(
                keys: keys,
                values: values,
                groupSize: 32,
                bits: 8,
                mode: .affine
            ))
            XCTAssertNil(fusedQ4AffineKeyValueQuantizedForDecode(
                keys: keys,
                values: values,
                groupSize: 24,
                bits: 4,
                mode: .affine
            ))
        }
    }

    func testQuantizedKVCacheUsesNativeDecodeQuantizerByDefaultForSingleTokenAffineQ4()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            assertQuantizedKVCacheStorageMatchesReference(
                dtype: .bfloat16,
                headDimension: 128,
                groupSize: 64,
                expectedFusedDecodeQuantizeCallCount: 0,
                rtol: 1e-2,
                atol: 1e-2
            )
        }
    }

    func testFusedDecodeQuantizerDefaultReadsInjectedEnvironment() {
        XCTAssertFalse(melixDefaultFusedDecodeQuantizeEnabled(environment: [:]))
        XCTAssertFalse(melixDefaultFusedDecodeQuantizeEnabled(
            environment: ["MELIX_SWIFT_TURBOQUANT_FUSED_QUANTIZE": "true"]
        ))
        XCTAssertTrue(melixDefaultFusedDecodeQuantizeEnabled(
            environment: ["MELIX_SWIFT_TURBOQUANT_FUSED_QUANTIZE": "1"]
        ))
    }

    func testQuantizedKVCacheUsesFusedDecodeQuantizerWhenExplicitlyEnabledForSingleTokenAffineQ4()
        async throws
    {
        try await withTemporaryDefaultMetallib {
            assertQuantizedKVCacheStorageMatchesReference(
                dtype: .bfloat16,
                headDimension: 128,
                groupSize: 64,
                fusedDecodeQuantizeEnabled: true,
                expectedFusedDecodeQuantizeCallCount: 1,
                rtol: 1e-2,
                atol: 1e-2
            )
        }
    }

    private func assertFusedDecodeQuantizerMatchesReference(
        dtype: DType,
        headDimension: Int,
        groupSize: Int,
        rtol: Double,
        atol: Double
    ) throws {
        let (keys, values) = makeDecodeKeyValueTensors(dtype: dtype, headDimension: headDimension)
        let fused = try XCTUnwrap(fusedQ4AffineKeyValueQuantizedForDecode(
            keys: keys,
            values: values,
            groupSize: groupSize,
            bits: 4,
            mode: .affine
        ))
        let referenceKeys = quantized(keys, groupSize: groupSize, bits: 4)
        let referenceValues = quantized(values, groupSize: groupSize, bits: 4)

        assertQuantizedTuplesMatchReference(
            keys: fused.0,
            values: fused.1,
            referenceKeys: referenceKeys,
            referenceValues: referenceValues,
            rtol: rtol,
            atol: atol
        )
    }

    private func assertQuantizedKVCacheStorageMatchesReference(
        dtype: DType,
        headDimension: Int,
        groupSize: Int,
        fusedDecodeQuantizeEnabled: Bool? = nil,
        expectedFusedDecodeQuantizeCallCount: Int,
        rtol: Double,
        atol: Double
    ) {
        let (keys, values) = makeDecodeKeyValueTensors(dtype: dtype, headDimension: headDimension)
        let cache = QuantizedKVCache(
            groupSize: groupSize,
            bits: 4,
            fusedDecodeQuantizeEnabled: fusedDecodeQuantizeEnabled
        )

        let storageState = cache.updateQuantizedStorage(keys: keys, values: values)
        let referenceKeys = quantized(keys, groupSize: groupSize, bits: 4)
        let referenceValues = quantized(values, groupSize: groupSize, bits: 4)

        XCTAssertEqual(
            cache.quantizedCacheFusedDecodeQuantizeCallCount,
            expectedFusedDecodeQuantizeCallCount
        )
        XCTAssertEqual(storageState.sequenceLength, 1)
        assertQuantizedTuplesMatchReference(
            keys: (
                storageState.keys.0[.ellipsis, ..<1, 0...],
                storageState.keys.1[.ellipsis, ..<1, 0...],
                storageState.keys.2![.ellipsis, ..<1, 0...]
            ),
            values: (
                storageState.values.0[.ellipsis, ..<1, 0...],
                storageState.values.1[.ellipsis, ..<1, 0...],
                storageState.values.2![.ellipsis, ..<1, 0...]
            ),
            referenceKeys: referenceKeys,
            referenceValues: referenceValues,
            rtol: rtol,
            atol: atol
        )
    }

    private func makeDecodeKeyValueTensors(
        dtype: DType,
        headDimension: Int
    ) -> (MLXArray, MLXArray) {
        let kvHeadCount = 2
        let keyValues = (0 ..< kvHeadCount * headDimension).map { index in
            Float((index % 23) - 11) / 13.0
        }
        let valueValues = (0 ..< kvHeadCount * headDimension).map { index in
            Float((index % 29) - 14) / 15.0
        }
        let keys = MLXArray(keyValues, [1, kvHeadCount, 1, headDimension]).asType(dtype)
        let values = MLXArray(valueValues, [1, kvHeadCount, 1, headDimension]).asType(dtype)
        return (keys, values)
    }

    private func assertQuantizedTuplesMatchReference(
        keys: QuantizedKVCacheTuple,
        values: QuantizedKVCacheTuple,
        referenceKeys: (wq: MLXArray, scales: MLXArray, biases: MLXArray?),
        referenceValues: (wq: MLXArray, scales: MLXArray, biases: MLXArray?),
        rtol: Double,
        atol: Double
    ) {
        XCTAssertEqual(keys.0.asArray(UInt32.self), referenceKeys.wq.asArray(UInt32.self))
        XCTAssertTrue(allClose(keys.1, referenceKeys.scales, rtol: rtol, atol: atol).all().item())
        XCTAssertTrue(allClose(keys.2!, referenceKeys.biases!, rtol: rtol, atol: atol).all().item())
        XCTAssertEqual(values.0.asArray(UInt32.self), referenceValues.wq.asArray(UInt32.self))
        XCTAssertTrue(allClose(values.1, referenceValues.scales, rtol: rtol, atol: atol).all().item())
        XCTAssertTrue(allClose(values.2!, referenceValues.biases!, rtol: rtol, atol: atol).all().item())
    }

    func testVendoredFusedQ4AttentionLaunchPlanUsesOnlineSoftmaxAcrossValueLanes() throws {
        let plan = try XCTUnwrap(turboQuantFusedAttentionLaunchPlan(
            batchCount: 2,
            queryHeadCount: 4,
            kvHeadCount: 2,
            sequenceLength: 64,
            headDimension: 128,
            groupSize: 64
        ))

        XCTAssertEqual(plan.gridX, 32)
        XCTAssertEqual(plan.gridY, 4)
        XCTAssertEqual(plan.gridZ, 2)
        XCTAssertEqual(plan.threadGroupX, 32)
        XCTAssertEqual(plan.sharedScoreCount, 0)
        XCTAssertEqual(plan.scoreDotProductsPerQueryHead, 64)
        XCTAssertEqual(plan.scoreReductionLaneCount, 16)
        XCTAssertEqual(plan.scoreReductionSimdgroupCount, 1)
        XCTAssertEqual(plan.softmaxLaneCount, 1)
        XCTAssertFalse(plan.usesThreadgroupSharedScores)
        XCTAssertTrue(plan.usesThreadgroupParallelScoreReduction)
        XCTAssertTrue(plan.usesOnlineSoftmax)
    }

    func testVendoredFusedQ4AttentionLaunchPlanTracksScaleBiasLoadReduction() throws {
        let cases: [(groupSize: Int, expectedLoadLaneCount: Int, expectedReduction: Bool)] = [
            (128, 1, true),
            (64, 2, true),
            (32, 4, true),
            (8, 16, false),
        ]

        for testCase in cases {
            let plan = try XCTUnwrap(turboQuantFusedAttentionLaunchPlan(
                batchCount: 2,
                queryHeadCount: 4,
                kvHeadCount: 2,
                sequenceLength: 64,
                headDimension: 128,
                groupSize: testCase.groupSize
            ))

            XCTAssertEqual(plan.scoreReductionLaneCount, 16)
            XCTAssertEqual(plan.scaleBiasLoadLaneCount, testCase.expectedLoadLaneCount)
            XCTAssertEqual(plan.usesReducedScaleBiasLoads, testCase.expectedReduction)
        }
    }

    func testVendoredFusedQ4AttentionLaunchPlanRejectsInvalidPackedScaleBiasGroups() throws {
        XCTAssertNil(turboQuantFusedAttentionLaunchPlan(
            batchCount: 1,
            queryHeadCount: 1,
            kvHeadCount: 1,
            sequenceLength: 1,
            headDimension: 128,
            groupSize: 4
        ))
        XCTAssertNil(turboQuantFusedAttentionLaunchPlan(
            batchCount: 1,
            queryHeadCount: 1,
            kvHeadCount: 1,
            sequenceLength: 1,
            headDimension: 128,
            groupSize: 24
        ))
    }

    func testTurboQuantMetalCapabilityRejectsUnsupportedQuantizedKVCacheStateInputs() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 3
            let headDimension = 32
            let groupSize = 32
            let query = MLXArray((0 ..< headDimension).map { Float($0 - 12) / 16.0 })
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 19) - 9) / 8.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 23) - 11) / 10.0
            }
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            let (quantizedKeys, quantizedValues) = cache.updateQuantized(
                keys: MLXArray(keyValues, [1, 1, sequenceLength, headDimension]),
                values: MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            )
            let int32PackedKeys = MLXArray([Int32](repeating: 0, count: sequenceLength * headDimension / 8), [
                1, 1, sequenceLength, headDimension / 8,
            ])
            let rankOnePackedKeys = quantizedKeys.0[0, 0, 0, 0...]

            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 2
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: (quantizedKeys.0, quantizedKeys.1, nil),
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    sequenceLength: 0,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength,
                    headDimension: 31,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: (int32PackedKeys, quantizedKeys.1, quantizedKeys.2),
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: (rankOnePackedKeys, quantizedKeys.1, quantizedKeys.2),
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    batchIndex: 1,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    headIndex: 1,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength + 1,
                    headDimension: headDimension,
                    groupSize: groupSize,
                    bits: 4
                )
            )
            XCTAssertNil(
                TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionKernelFromQuantizedState(
                    query: query,
                    quantizedKeys: quantizedKeys,
                    quantizedValues: quantizedValues,
                    sequenceLength: sequenceLength,
                    headDimension: headDimension,
                    groupSize: 16,
                    bits: 4
                )
            )
        }
    }

    func testTurboQuantCandidateDispatchReadsQuantizedKVCacheState() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 3
            let headDimension = 32
            let groupSize = 32
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 17) - 8) / 8.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 29) - 14) / 12.0
            }
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            _ = cache.updateQuantized(
                keys: MLXArray(keyValues, [1, 1, sequenceLength, headDimension]),
                values: MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            )

            XCTAssertTrue(dispatchTurboQuantFusedAttentionCandidateFromQuantizedCacheState(cache: [cache]))
        }
    }

    func testTurboQuantCandidateDispatchRequiresExplicitProbeMode() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 3
            let headDimension = 32
            let groupSize = 32
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 17) - 8) / 8.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 29) - 14) / 12.0
            }
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            _ = cache.updateQuantized(
                keys: MLXArray(keyValues, [1, 1, sequenceLength, headDimension]),
                values: MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            )
            var acceleration = Melix_Worker_V1_AccelerationPolicy()
            acceleration.mode = .activeKvQuantized
            acceleration.activeKvQuantProfile = "turboquant-q4"

            XCTAssertFalse(shouldDispatchTurboQuantFusedAttentionCandidate(
                cache: [cache],
                acceleration: acceleration,
                candidateProbeEnabled: false
            ))
            XCTAssertTrue(shouldDispatchTurboQuantFusedAttentionCandidate(
                cache: [cache],
                acceleration: acceleration,
                candidateProbeEnabled: true
            ))
        }
    }

    func testTurboQuantActiveKVUsesVendoredRuntimeWithoutProbe() {
        var q4Acceleration = Melix_Worker_V1_AccelerationPolicy()
        q4Acceleration.mode = .activeKvQuantized
        q4Acceleration.activeKvQuantProfile = "q4"
        XCTAssertTrue(shouldUseActiveKVQuantization(for: q4Acceleration))

        var turboQuantAcceleration = Melix_Worker_V1_AccelerationPolicy()
        turboQuantAcceleration.mode = .activeKvQuantized
        turboQuantAcceleration.activeKvQuantProfile = "turboquant-q4"
        XCTAssertTrue(shouldUseActiveKVQuantization(for: turboQuantAcceleration))
    }

    func testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch() async throws {
        try await withTemporaryDefaultMetallib {
            let sequenceLength = 3
            let headDimension = 32
            let groupSize = 32
            let keyValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 17) - 8) / 8.0
            }
            let valueValues = (0 ..< sequenceLength * headDimension).map { index in
                Float((index % 29) - 14) / 12.0
            }
            let cache = QuantizedKVCache(groupSize: groupSize, bits: 4)
            _ = cache.updateQuantized(
                keys: MLXArray(keyValues, [1, 1, sequenceLength, headDimension]),
                values: MLXArray(valueValues, [1, 1, sequenceLength, headDimension])
            )
            cache.recordFusedAttentionDispatch()
            var acceleration = Melix_Worker_V1_AccelerationPolicy()
            acceleration.mode = .activeKvQuantized
            acceleration.activeKvQuantProfile = "turboquant-q4"

            let route = turboQuantRuntimeFusedAttentionRoute(
                cache: [cache],
                acceleration: acceleration
            )

            XCTAssertEqual(route, .routed)
            XCTAssertEqual(activeKVKernelPathCode(for: acceleration, turboQuantRuntimeRoute: route), 20)
            XCTAssertEqual(activeKVFallbackCount(for: acceleration, turboQuantRuntimeRoute: route), 0)
            XCTAssertEqual(activeKVRuntimeRouteCode(for: route), 2)
            XCTAssertEqual(activeKVRuntimeBlockReasonCode(for: route), 0)
        }
    }

    func testTurboQuantRuntimeRouteReportsRoutedFromDispatchEvidenceBeforeStateRecheck() {
        let cache = QuantizedKVCache(groupSize: 32, bits: 4)
        cache.recordFusedAttentionDispatch()

        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "turboquant-q4"

        let route = turboQuantRuntimeFusedAttentionRoute(
            cache: [KVCacheSimple(), cache],
            acceleration: acceleration
        )

        XCTAssertEqual(route, .routed)
        XCTAssertEqual(activeKVKernelPathCode(for: acceleration, turboQuantRuntimeRoute: route), 20)
        XCTAssertEqual(activeKVFallbackCount(for: acceleration, turboQuantRuntimeRoute: route), 0)
        XCTAssertEqual(activeKVRuntimeRouteCode(for: route), 2)
        XCTAssertEqual(activeKVRuntimeBlockReasonCode(for: route), 0)
    }

    func testTurboQuantRuntimeRouteCodeMappingsCoverInactiveUnsupportedAndRoutedStates() {
        XCTAssertEqual(activeKVRuntimeRouteCode(for: .disabled), 0)
        XCTAssertEqual(activeKVRuntimeBlockReasonCode(for: .disabled), 0)
        XCTAssertEqual(activeKVRuntimeRouteCode(for: .blocked(.unsupportedCacheState)), 1)
        XCTAssertEqual(activeKVRuntimeBlockReasonCode(for: .blocked(.unsupportedCacheState)), 1)
        XCTAssertEqual(activeKVRuntimeRouteCode(for: .routed), 2)
        XCTAssertEqual(activeKVRuntimeBlockReasonCode(for: .routed), 0)
    }
    #endif
    #endif

    func testMaintenanceRpcsReturnStructuredUnimplemented() async throws {
        let services = makeServices()
        let convertWriter = RecordingRPCWriter<Melix_Worker_V1_ConvertModelEvent>()
        let benchWriter = RecordingRPCWriter<Melix_Worker_V1_RunBenchEvent>()

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.convertModel(
                request: Melix_Worker_V1_ConvertModelRequest(),
                response: RPCWriter(wrapping: convertWriter),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.ConvertModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let infoResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.getModelInfo(
                request: Melix_Worker_V1_GetModelInfoRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.GetModelInfo.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let doctorResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.runDoctor(
                request: Melix_Worker_V1_RunDoctorRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.RunDoctor.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let benchMatrixResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.runBenchMatrix(
                request: Melix_Worker_V1_RunBenchMatrixRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.RunBenchMatrix.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let evaluationResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.runEvaluation(
                request: Melix_Worker_V1_RunEvaluationRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.RunEvaluation.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let exportResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.exportResults(
                request: Melix_Worker_V1_ExportResultsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.ExportResults.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let submitResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.submitResults(
                request: Melix_Worker_V1_SubmitResultsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.SubmitResults.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let searchResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.searchHubModels(
                request: Melix_Worker_V1_SearchHubModelsRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.SearchHubModels.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let modelCardResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.getHubModelCard(
                request: Melix_Worker_V1_GetHubModelCardRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.GetHubModelCard.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        try await withTestServerContextRPCCancellationHandle { handle in
            try await services.maintenance.runBench(
                request: Melix_Worker_V1_RunBenchRequest(),
                response: RPCWriter(wrapping: benchWriter),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_MaintenanceService.Method.RunBench.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let convertEvents = await convertWriter.snapshot()
        let benchEvents = await benchWriter.snapshot()

        XCTAssertEqual(convertEvents.count, 1)
        XCTAssertEqual(convertEvents[0].failed.error.code, "unimplemented")
        XCTAssertFalse(infoResponse.ok)
        XCTAssertEqual(infoResponse.error.code, "unimplemented")
        XCTAssertFalse(doctorResponse.ok)
        XCTAssertEqual(doctorResponse.error.code, "unimplemented")
        XCTAssertTrue(benchMatrixResponse.hasJob)
        XCTAssertEqual(benchMatrixResponse.job.schemaVersion, "melix.benchmark_matrix_job.v1")
        XCTAssertEqual(benchMatrixResponse.job.jobID, "swift-text-unimplemented")
        XCTAssertEqual(benchMatrixResponse.job.benchmarkMode, "matrix")
        XCTAssertEqual(benchMatrixResponse.job.status, "failed")
        XCTAssertTrue(benchMatrixResponse.summaryRows.isEmpty)
        XCTAssertFalse(evaluationResponse.ok)
        XCTAssertEqual(evaluationResponse.error.code, "unimplemented")
        XCTAssertFalse(exportResponse.ok)
        XCTAssertEqual(exportResponse.error.code, "unimplemented")
        XCTAssertFalse(submitResponse.ok)
        XCTAssertEqual(submitResponse.error.code, "unimplemented")
        XCTAssertFalse(searchResponse.ok)
        XCTAssertEqual(searchResponse.error.code, "unimplemented")
        XCTAssertFalse(modelCardResponse.ok)
        XCTAssertEqual(modelCardResponse.error.code, "unimplemented")
        XCTAssertEqual(benchEvents.count, 1)
        XCTAssertEqual(benchEvents[0].failed.error.code, "unimplemented")
    }

    func testBootstrapBuildsServerWithDeterministicConfiguration() throws {
        let configuration = WorkerConfiguration()
        let bootstrap = try WorkerBootstrap.build(configuration: configuration)

        XCTAssertEqual(bootstrap.configuration.workerID, configuration.workerID)
        XCTAssertEqual(bootstrap.services.runtime.configuration.workerID, configuration.workerID)
        XCTAssertEqual(bootstrap.services.metrics.counters["swift_text.unimplemented_rpc_count"], 0)
        XCTAssertNotNil(bootstrap.services.metrics.counters["swift_text.registry_init_ms"])
        XCTAssertNotNil(bootstrap.services.metrics.counters["swift_text.services_init_ms"])
        XCTAssertNotNil(bootstrap.services.metrics.counters["swift_text.server_construct_ms"])
        XCTAssertNotNil(bootstrap.services.metrics.counters["swift_text.bootstrap_ms"])
    }

    func testBootstrapRecordsSpawnToBootstrapMetricWhenStartupOriginIsProvided() throws {
        let bootstrap = try WorkerBootstrap.build(
            configuration: WorkerConfiguration(),
            environment: ["MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS": "0"]
        )

        XCTAssertGreaterThanOrEqual(bootstrap.services.metrics.counters["swift_text.spawn_to_bootstrap_ms"] ?? -1, 0)
    }

    func testSwiftBackendReceivesTurboQuantCandidateProbeConfiguration() throws {
        let runtime = makeTextRuntime(for: WorkerConfiguration(turboQuantCandidateProbeEnabled: true))
        let backend = try XCTUnwrap(runtime.backend as? AutoSwiftMLXBackend)

        XCTAssertTrue(backend.turboQuantCandidateProbeEnabled)
    }

    func testDeterministicBackendModeBuildsARepeatableTextRuntime() async throws {
        let runtime = makeTextRuntime(for: WorkerConfiguration(backendMode: "deterministic"))

        XCTAssertEqual(runtime.runtimeName, "deterministic-text")

        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await runtime.loadModel(spec: spec)
        let events = try await collectTextGenerationEvents(
            from: try await runtime.generateEvents(
                model: loaded.model,
                messages: [makeUserMessage("hello deterministic swift")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )

        XCTAssertEqual(renderedPromptTokens(from: events), 3)
        XCTAssertEqual(renderedTokenChunks(from: events), ["Echo: ", "hello ", "deterministic ", "swift"])
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 4)
    }

    func testDeterministicBackendRendersEmptyPromptAndStopsWhenAborted() async throws {
        let runtime = makeTextRuntime(for: WorkerConfiguration(backendMode: "deterministic"))
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await runtime.loadModel(spec: spec)

        let emptyPromptEvents = try await collectTextGenerationEvents(
            from: try await runtime.generateEvents(
                model: loaded.model,
                messages: [makeUserMessage("   ")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )
        XCTAssertEqual(renderedTokenChunks(from: emptyPromptEvents), ["Echo: ", "empty"])
        XCTAssertEqual(renderedSummary(from: emptyPromptEvents)?.completionTokens, 2)

        let abortedEvents = try await collectTextGenerationEvents(
            from: try await runtime.generateEvents(
                model: loaded.model,
                messages: [makeUserMessage("abort after one token")],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { true }
            )
        )
        XCTAssertEqual(renderedTokenChunks(from: abortedEvents), [])
        XCTAssertEqual(renderedSummary(from: abortedEvents)?.completionTokens, 0)
    }

    func testDeterministicBackendPrefillCapturesPromptMetadataAndThrowsWhenAborted() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 0)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("hello deterministic swift", extraText: "again")],
            prefillStepSize: 16,
            resumeHint: "deterministic-resume",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )

        let stored = try XCTUnwrap(result.context.storage as? [String: String])
        XCTAssertEqual(result.promptTokens, 4)
        XCTAssertEqual(result.context.promptTokens, 4)
        XCTAssertEqual(stored["prompt"], "hello deterministic swift\nagain")
        XCTAssertEqual(stored["resume_hint"], "deterministic-resume")
        XCTAssertEqual(stored["prefill_step_size"], "16")

        await XCTAssertThrowsErrorAsync(
            try await backend.prefill(
                model: loaded,
                messages: [makeUserMessage("hello deterministic swift", extraText: "again")],
                prefillStepSize: 16,
                resumeHint: "deterministic-resume",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                shouldAbort: { true }
            )
        )
    }

    func testDeterministicBackendAcceleratedPrefillReportsGainAndHint() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 20_000_000)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .acceleratedPrefill
        acceleration.prefillHint = "json-schema"

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("{\"type\":\"object\",\"name\":\"alpha\"}", extraText: "{\"type\":\"object\",\"name\":\"beta\"}")],
            prefillStepSize: 16,
            resumeHint: "structured",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let stored = try XCTUnwrap(result.context.storage as? [String: String])
        XCTAssertEqual(result.appliedAcceleration.mode, .acceleratedPrefill)
        XCTAssertEqual(result.appliedAcceleration.prefillHint, "json-schema")
        XCTAssertGreaterThan(result.acceleratedPrefillGainPct, 0)
        XCTAssertEqual(result.activeKVQuantizationRatio, 0)
        XCTAssertEqual(stored["prefill_hint"], "json-schema")
        XCTAssertEqual(stored["prefill_gain_pct"], String(result.acceleratedPrefillGainPct))
    }

    func testDeterministicBackendActiveKVPrefillReportsQuantizationRatio() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 0)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .activeKvQuantized
        acceleration.activeKvQuantProfile = "q8"

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("quantized cache")],
            prefillStepSize: 8,
            resumeHint: "quantized",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        let stored = try XCTUnwrap(result.context.storage as? [String: String])
        XCTAssertEqual(result.appliedAcceleration.mode, .activeKvQuantized)
        XCTAssertEqual(result.appliedAcceleration.activeKvQuantProfile, "q8")
        XCTAssertEqual(result.activeKVQuantizationRatio, 50)
        XCTAssertEqual(stored["active_kv_quant_profile"], "q8")
        XCTAssertEqual(stored["active_kv_quant_ratio"], "50")
    }

    func testDeterministicBackendSparsePrefillStructuredPromptReportsGainAndHint() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 24_000_000)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .sparsePrefill

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("{\"kind\":\"structured\"}", extraText: "{\"kind\":\"structured\"}")],
            prefillStepSize: 8,
            resumeHint: "",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        XCTAssertEqual(result.appliedAcceleration.mode, .sparsePrefill)
        XCTAssertEqual(result.appliedAcceleration.prefillHint, "sparse-prefill:structured")
        XCTAssertGreaterThan(result.acceleratedPrefillGainPct, 0)
    }

    func testDeterministicBackendSparsePrefillFallsBackForPlainPrompt() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 24_000_000)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)
        var acceleration = Melix_Worker_V1_AccelerationPolicy()
        acceleration.mode = .sparsePrefill

        let result = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("plain prompt")],
            prefillStepSize: 8,
            resumeHint: "",
            acceleration: acceleration,
            shouldAbort: { false }
        )

        XCTAssertEqual(result.appliedAcceleration.mode, .sparsePrefill)
        XCTAssertEqual(result.appliedAcceleration.prefillHint, "sparse-prefill")
        XCTAssertEqual(result.acceleratedPrefillGainPct, 0)
    }

    func testSparsePrefillPlanCountsAcceptedRejectedProtectedAndRepeatedLines() {
        var developer = Melix_Worker_V1_ChatMessage()
        developer.role = "developer"
        var developerPart = Melix_Worker_V1_MessagePart()
        developerPart.text = "repeat\nrepeat\nrepeat"
        developer.parts = [developerPart]

        let plan = sparsePrefillPlan(
            for: [
                makeSystemMessage("{\"guard\":\"always\"}\n{\"schema\":true}"),
                developer,
                makeUserMessage("repeat\nrepeat\nrepeat"),
                makeUserMessage("   ")
            ],
            policy: makeAccelerationPolicy(mode: .sparsePrefill)
        )

        XCTAssertEqual(plan.acceptedSkipCount, 1)
        XCTAssertEqual(plan.rejectedOpportunityCount, 2)
        XCTAssertEqual(plan.protectedRegionCount, 2)
        XCTAssertTrue(promptLooksStructuredForPrefill("{\"kind\":\"json\"}\n{\"kind\":\"json\"}"))
        XCTAssertFalse(promptLooksStructuredForPrefill("plain text"))
        XCTAssertFalse(sparsePrefillEligibleText("   "))
        XCTAssertTrue(promptContainsSparseRepeats("echo\necho\necho"))
        XCTAssertFalse(promptContainsSparseRepeats("alpha\nbeta"))
    }

    func testDeterministicBackendPartialRestoreResumeHintFlowsThroughDecodeEvents() async throws {
        let backend = DeterministicTextBackend(tokenDelayNanos: 40_000_000)
        var spec = Melix_Worker_V1_ModelSpec()
        spec.modelID = "melix-dev-text"
        let loaded = try await backend.loadModel(spec: spec)

        let prefill = try await backend.prefill(
            model: loaded,
            messages: [makeUserMessage("alpha beta gamma delta")],
            prefillStepSize: 4,
            resumeHint: "snapshot-restore:snap-1:partial:16",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )

        let events = try await collectTextGenerationEvents(
            from: try await backend.decodeEvents(
                model: loaded,
                context: prefill.context,
                sampling: Melix_Worker_V1_SamplingConfig(),
                maxOutputTokens: 8,
                decodeStepSize: 1,
                prefillToken: "",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                shouldAbort: { false }
            )
        )

        XCTAssertEqual(renderedTokenChunks(from: events), ["Decoded: ", "alpha ", "beta ", "gamma ", "delta"])
        XCTAssertEqual(renderedSummary(from: events)?.completionTokens, 5)
    }

    func testDeterministicVisionBackendGeneratesImageAndVideoResponses() async throws {
        let backend = DeterministicVisionBackend(tokenDelayNanos: 0)
        var spec = WorkerModelCatalog.devVisionModel()
        spec.modelID = "melix-dev-vlm"
        let loaded = try await backend.loadModel(spec: spec)

        let imageEvents = try await collectTextGenerationEvents(
            from: try await backend.generateEvents(
                model: loaded,
                messages: [
                    makeVisionMessage(
                        prompt: "Summarize the image.",
                        imageBytes: Data("swift vision image".utf8),
                        imageFilename: "fixture.png"
                    )
                ],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )

        XCTAssertEqual(
            renderedTokenChunks(from: imageEvents).joined(),
            "Image content: swift vision image\nPrompt: Summarize the image."
        )

        var videoSampling = Melix_Worker_V1_SamplingConfig()
        videoSampling.maxOutputTokens = 64
        let videoEvents = try await collectTextGenerationEvents(
            from: try await backend.generateEvents(
                model: loaded,
                messages: [
                    makeVisionMessage(
                        prompt: "Summarize the clip.",
                        videoBytes: Data("swift video".utf8),
                        videoFilename: "clip.mp4",
                        frameBudget: 5,
                        startMs: 400,
                        endMs: 2_400
                    )
                ],
                sampling: videoSampling,
                shouldAbort: { false }
            )
        )

        XCTAssertEqual(
            renderedTokenChunks(from: videoEvents).joined(),
            """
            Video content: clip.mp4
            Frame policy: uniform_sample 5 frame(s) from 400ms to 2400ms
            Prompt: Summarize the clip.
            """
        )
        let optionalStats = await backend.runtimeStatsOverlay()
        let stats = try XCTUnwrap(optionalStats)
        XCTAssertEqual(stats.lastProbeKind, "vlm")
        XCTAssertEqual(stats.lastVideoEffectiveFrameCount, 5)
        XCTAssertEqual(stats.lastVideoRequestedFrameBudget, 5)
        XCTAssertEqual(stats.lastVideoWindowMs, 2_000)
    }

    func testDeterministicVisionBackendNormalizesLocalVideoURI() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-vision-video-uri-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let videoURL = directory.appendingPathComponent("local-clip.mp4")
        try Data("swift video uri".utf8).write(to: videoURL)
        defer {
            try? FileManager.default.removeItem(at: directory)
        }
        let backend = DeterministicVisionBackend(tokenDelayNanos: 0)
        let loaded = try await backend.loadModel(spec: WorkerModelCatalog.devVisionModel())

        let events = try await collectTextGenerationEvents(
            from: try await backend.generateEvents(
                model: loaded,
                messages: [
                    makeVisionMessage(
                        prompt: "Summarize the local clip.",
                        videoURI: videoURL.path,
                        videoFilename: "",
                        frameBudget: 6,
                        startMs: 250,
                        endMs: 1_250
                    )
                ],
                sampling: Melix_Worker_V1_SamplingConfig(),
                shouldAbort: { false }
            )
        )

        XCTAssertEqual(
            renderedTokenChunks(from: events).joined(),
            """
            Video content: local-clip.mp4
            Frame policy: uniform_sample 6 frame(s) from 250ms to 1250ms
            Prompt: Summarize the local clip.
            """
        )
        let maybeStats = await backend.runtimeStatsOverlay()
        let stats = try XCTUnwrap(maybeStats)
        XCTAssertEqual(stats.lastVideoEffectiveFrameCount, 6)
        XCTAssertEqual(stats.lastVideoWindowMs, 1_000)
    }

    func testDeterministicVisionBackendAppliesOCRStopSequences() async throws {
        let backend = DeterministicVisionBackend(tokenDelayNanos: 0)
        let loaded = try await backend.loadModel(spec: WorkerModelCatalog.devOCRModel())
        var sampling = Melix_Worker_V1_SamplingConfig()

        let defaultEvents = try await collectTextGenerationEvents(
            from: try await backend.generateEvents(
                model: loaded,
                messages: [
                    makeVisionMessage(
                        imageBytes: Data("title<ocr:end>body".utf8),
                        imageFilename: "ocr.png"
                    )
                ],
                sampling: sampling,
                shouldAbort: { false }
            )
        )
        XCTAssertEqual(renderedTokenChunks(from: defaultEvents).joined(), "title")

        sampling.stop = ["body"]
        let overrideEvents = try await collectTextGenerationEvents(
            from: try await backend.generateEvents(
                model: loaded,
                messages: [
                    makeVisionMessage(
                        imageBytes: Data("title<ocr:end>body".utf8),
                        imageFilename: "ocr.png"
                    )
                ],
                sampling: sampling,
                shouldAbort: { false }
            )
        )
        XCTAssertEqual(renderedTokenChunks(from: overrideEvents).joined(), "title<ocr:end>")
    }

    func testDeterministicVisionBackendPrefillDecodePreservesVisionPayload() async throws {
        let backend = DeterministicVisionBackend(tokenDelayNanos: 0)
        let loaded = try await backend.loadModel(spec: WorkerModelCatalog.devVisionModel())
        let prefill = try await backend.prefill(
            model: loaded,
            messages: [
                makeVisionMessage(
                    prompt: "Caption the image.",
                    imageBytes: Data("phase aware image".utf8),
                    imageFilename: "phase.png"
                )
            ],
            prefillStepSize: 16,
            resumeHint: "",
            acceleration: Melix_Worker_V1_AccelerationPolicy(),
            shouldAbort: { false }
        )
        let events = try await collectTextGenerationEvents(
            from: try await backend.decodeEvents(
                model: loaded,
                context: prefill.context,
                sampling: Melix_Worker_V1_SamplingConfig(),
                maxOutputTokens: 64,
                decodeStepSize: 1,
                prefillToken: "",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                shouldAbort: { false }
            )
        )

        XCTAssertEqual(
            renderedTokenChunks(from: events).joined(),
            "Image content: phase aware image\nPrompt: Caption the image."
        )
    }

    func testAutoSwiftMLXBackendDefaultPrefillRejectsNonMLXContainers() async {
        let backend = AutoSwiftMLXBackend()

        do {
            _ = try await backend.prefill(
                model: LoadedTextModel(storage: ["kind": "not-a-container"]),
                messages: [makeUserMessage("default prefill factory")],
                prefillStepSize: 4,
                resumeHint: "prefill",
                acceleration: Melix_Worker_V1_AccelerationPolicy(),
                shouldAbort: { false }
            )
            XCTFail("expected prefill to fail for non-MLX containers")
        } catch {
            XCTAssertTrue(error.localizedDescription.contains("Loaded model is not a Swift MLX model container"))
        }
    }

    func testWarmupAndShutdownReturnExpectedStructuredResponses() async throws {
        let services = makeServices()

        let warmupResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.warmupModel(
                request: Melix_Worker_V1_WarmupModelRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.WarmupModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let shutdownResponse = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.runtime.shutdown(
                request: Melix_Worker_V1_ShutdownRequest(),
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.Shutdown.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        XCTAssertFalse(warmupResponse.ok)
        XCTAssertEqual(warmupResponse.error.code, "unimplemented")
        XCTAssertTrue(shutdownResponse.ok)
    }

    func testPrefillRecordsBoundarySafeChunkMetricsForLongPrompts() async throws {
        let services = makeServices(
            backend: DeterministicTextBackend(tokenDelayNanos: 0)
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let prompt = (1...24).map { "token\($0)" }.joined(separator: " ")
        var prefill = Melix_Worker_V1_PrefillRequest()
        prefill.execution.id.requestID = "req-chunked-prefill"
        prefill.execution.modelHandle = loadResponse.modelHandle
        prefill.prefillStepSize = 16
        prefill.returnDecodeHandle = true
        prefill.messages = [makeUserMessage(prompt)]

        _ = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefill,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.prefill_chunk_count"], 2)
        XCTAssertEqual(metrics["swift_text.prefill_chunk_target_tokens"], 16)
        XCTAssertEqual(metrics["swift_text.prefill_last_chunk_tokens"], 24)
    }

    func testPrefillMetricsSeparateTextWorkerWindowFromChunkCompatibility() async throws {
        let services = makeServices(
            backend: DeterministicTextBackend(tokenDelayNanos: 0)
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        let prompt = (1...24).map { "token\($0)" }.joined(separator: " ")
        var prefill = Melix_Worker_V1_PrefillRequest()
        prefill.execution.id.requestID = "req-text-window-prefill"
        prefill.execution.modelHandle = loadResponse.modelHandle
        prefill.prefillStepSize = 512
        prefill.returnDecodeHandle = true
        prefill.messages = [makeUserMessage(prompt)]

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefill,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        XCTAssertTrue(response.ok, response.error.message)

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.prefill_chunk_target_tokens"], 512)
        XCTAssertEqual(metrics["swift_text.worker_prefill_requested_step_tokens"], 512)
        XCTAssertEqual(metrics["swift_text.worker_prefill_effective_window_tokens"], 512)
    }

    func testPrefillMetricsRecordVisionWorkerWindow() async throws {
        let services = makeServices(
            backend: FakeRuntimeBackend()
        )

        let loadResponse = try await withTestServerContextRPCCancellationHandle { handle in
            var request = Melix_Worker_V1_LoadModelRequest()
            request.model.modelID = "melix-dev-text"
            request.model.maxContext = 1024
            return try await services.runtime.loadModel(
                request: request,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_RuntimeService.Method.LoadModel.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }

        var prefill = Melix_Worker_V1_PrefillRequest()
        prefill.execution.id.requestID = "req-vision-window-prefill"
        prefill.execution.modelHandle = loadResponse.modelHandle
        prefill.prefillStepSize = 16
        prefill.returnDecodeHandle = false
        prefill.messages = [makeVisionBearingMessage("describe this image")]

        let response = try await withTestServerContextRPCCancellationHandle { handle in
            try await services.inference.prefill(
                request: prefill,
                context: ServerContext(
                    descriptor: Melix_Worker_V1_InferenceService.Method.Prefill.descriptor,
                    remotePeer: "in-process:test",
                    localPeer: "in-process:test",
                    cancellation: handle
                )
            )
        }
        XCTAssertTrue(response.ok, response.error.message)

        let metrics = services.metrics.counters
        XCTAssertEqual(metrics["swift_text.prefill_chunk_target_tokens"], 16)
        XCTAssertEqual(metrics["swift_text.worker_prefill_requested_step_tokens"], 16)
        XCTAssertEqual(metrics["swift_text.worker_prefill_effective_window_tokens"], 16)
    }
}

@available(macOS 15.0, *)
private func withTestServerContextRPCCancellationHandle<Success>(
    _ operation: (ServerContext.RPCCancellationHandle) async throws -> Success
) async rethrows -> Success {
    // grpc-swift's generic task-local helper currently crashes under this XCTest package on the
    // active Xcode toolchain. The worker tests only need a concrete cancellation handle.
    try await operation(ServerContext.RPCCancellationHandle())
}

@available(macOS 15.0, *)
private func makeServices(
    environment: [String: String] = [:],
    backend: some TextRuntimeBackend = FakeRuntimeBackend(),
    residentMemorySamples: [UInt64] = [0, 0]
) -> WorkerServices {
    let configuration = WorkerConfiguration.fromEnvironment(environment)
    let metrics = MetricsStore()
    let abortRegistry = AbortRegistry()
    let catalog = WorkerModelCatalog(environment: environment)
    let probe = ResidentMemoryProbe(samples: residentMemorySamples)
    let runtime = TextRuntime(
        backend: backend,
        residentMemoryReader: { probe.next() }
    )
    let registry = WorkerRuntimeRegistry(
        configuration: configuration,
        modelCatalog: catalog,
        runtime: runtime
    )
    return WorkerServices(
        configuration: configuration,
        registry: registry,
        abortRegistry: abortRegistry,
        metrics: metrics
    )
}

@available(macOS 15.0, *)
private func waitForFileContents(
    atPath path: String,
    attempts: Int = 100
) async -> String? {
    for _ in 0..<attempts {
        if let contents = try? String(contentsOfFile: path, encoding: .utf8),
           !contents.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return contents
        }
        try? await Task.sleep(nanoseconds: 10_000_000)
    }
    return try? String(contentsOfFile: path, encoding: .utf8)
}

@available(macOS 15.0, *)
private actor RecordingRPCWriterStorage<Element: Sendable> {
    private var elements: [Element] = []

    func append(_ element: Element) {
        elements.append(element)
    }

    func append(contentsOf elements: some Sequence<Element>) {
        self.elements.append(contentsOf: elements)
    }

    func snapshot() -> [Element] {
        elements
    }
}

@available(macOS 15.0, *)
private enum FakeRuntimeBackendError: Error {
    case loadFailed
    case prefillFailed
    case decodeFailed
}

@available(macOS 15.0, *)
private actor FakeRuntimeBackendStorage {
    private var specs: [Melix_Worker_V1_ModelSpec] = []

    func append(_ spec: Melix_Worker_V1_ModelSpec) {
        specs.append(spec)
    }

    func snapshot() -> [Melix_Worker_V1_ModelSpec] {
        specs
    }
}

@available(macOS 15.0, *)
private actor FakeRuntimeBackendDecodeStorage {
    private var lastDraftModelID: String?

    func record(draftModel: LoadedTextModel?) {
        if let modelID = (draftModel?.storage as? [String: String])?["model_id"] {
            lastDraftModelID = modelID
            return
        }
        #if canImport(MLXLMCommon) && canImport(MLXLLM)
        lastDraftModelID = (draftModel?.storage as? SwiftDFlashDraftRuntime)?.modelID
        #else
        lastDraftModelID = nil
        #endif
    }

    func snapshotLastDraftModelID() -> String? {
        lastDraftModelID
    }
}

@available(macOS 15.0, *)
private final class FakeRuntimeBackend: TextRuntimeBackend, @unchecked Sendable {
    let runtimeName: String = "fake-mlx-swift"

    private let loadError: Error?
    private let prefillError: Error?
    private let decodeError: Error?
    private let residentBytesHint: UInt64
    private let generatedChunks: [String]
    private let decodedChunks: [String]
    private let tokenDelayNanos: UInt64
    private let prefillDelayNanos: UInt64
    private let decodeDelayNanos: UInt64
    private let activeKVProbeSummary: ActiveKVProbeSummary?
    private let storage = FakeRuntimeBackendStorage()
    private let decodeStorage = FakeRuntimeBackendDecodeStorage()
    private let unloadedStorage = FakeRuntimeBackendUnloadStorage()

    init(
        loadError: Error? = nil,
        prefillError: Error? = nil,
        decodeError: Error? = nil,
        residentBytesHint: UInt64 = 0,
        generatedChunks: [String] = ["Hello", " from Swift"],
        decodedChunks: [String]? = nil,
        tokenDelayNanos: UInt64 = 0,
        prefillDelayNanos: UInt64 = 0,
        decodeDelayNanos: UInt64 = 0,
        activeKVProbeSummary: ActiveKVProbeSummary? = nil
    ) {
        self.loadError = loadError
        self.prefillError = prefillError
        self.decodeError = decodeError
        self.residentBytesHint = residentBytesHint
        self.generatedChunks = generatedChunks
        self.decodedChunks = decodedChunks ?? generatedChunks
        self.tokenDelayNanos = tokenDelayNanos
        self.prefillDelayNanos = prefillDelayNanos
        self.decodeDelayNanos = decodeDelayNanos
        self.activeKVProbeSummary = activeKVProbeSummary
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        await storage.append(spec)
        if let loadError {
            throw loadError
        }
        #if canImport(MLXLMCommon) && canImport(MLXLLM)
        if DFlashDraftSupport.isDFlashDraftModelSpec(spec) {
            return LoadedTextModel(
                storage: SwiftDFlashDraftRuntime(modelID: spec.modelID),
                residentBytesHint: residentBytesHint
            )
        }
        #endif
        return LoadedTextModel(
            storage: ["model_id": spec.modelID, "model_path": spec.modelPath],
            residentBytesHint: residentBytesHint
        )
    }

    func unloadModel(_ model: LoadedTextModel) async {
        await unloadedStorage.increment()
    }

    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        if let prefillError {
            throw prefillError
        }
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        if prefillDelayNanos > 0 {
            try? await Task.sleep(nanoseconds: prefillDelayNanos)
        }
        try throwIfTextRuntimeCancellationRequested(shouldAbort)

        let promptTokens = max(1, messages.count)
        return RuntimePrefillResult(
            context: TextPrefillContext(
                storage: [
                    "resume_hint": resumeHint,
                    "prefill_step_size": String(prefillStepSize),
                ],
                promptTokens: promptTokens
            ),
            promptTokens: promptTokens,
            requestedPrefillStepTokens: Int(clamping: prefillStepSize),
            effectivePrefillWindowTokens: Int(clamping: max(prefillStepSize, 1)),
            appliedAcceleration: normalizedAccelerationPolicy(acceleration),
            acceleratedPrefillGainPct: acceleration.mode == .acceleratedPrefill ? 50 : 0,
            activeKVQuantizationRatio: activeKVQuantizationRatioPercent(for: acceleration)
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.yield(.prefillStarted(promptTokens: max(1, messages.count)))

            Task {
                var emitted = 0
                for chunk in generatedChunks {
                    if shouldAbort() {
                        break
                    }
                    if tokenDelayNanos > 0 {
                        try? await Task.sleep(nanoseconds: tokenDelayNanos)
                    }
                    if shouldAbort() {
                        break
                    }
                    emitted += 1
                    continuation.yield(.token(chunk))
                }

                continuation.yield(.summary(
                    TextGenerationSummary(
                        promptTokens: max(1, messages.count),
                        completionTokens: emitted,
                        tokensPerSecond: emitted > 0 ? Double(emitted) * 10.0 : nil
                    )
                ))
                continuation.finish()
            }
        }
    }

    func decodeEvents(
        model: LoadedTextModel,
        draftModel: LoadedTextModel? = nil,
        context: TextPrefillContext,
        sampling: Melix_Worker_V1_SamplingConfig,
        maxOutputTokens: UInt32,
        decodeStepSize: UInt32,
        prefillToken: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        await decodeStorage.record(draftModel: draftModel)
        if let decodeError {
            throw decodeError
        }

        let chunks = maxOutputTokens > 0
            ? Array(decodedChunks.prefix(Int(maxOutputTokens)))
            : decodedChunks

        return AsyncThrowingStream { continuation in
            Task {
                var emitted = 0

                for chunk in chunks {
                    if shouldAbort() {
                        break
                    }
                    if decodeDelayNanos > 0 {
                        try? await Task.sleep(nanoseconds: decodeDelayNanos)
                    }
                    if shouldAbort() {
                        break
                    }
                    emitted += 1
                    continuation.yield(.token(chunk))
                }

                let speculativeAccepted = acceleration.mode == .speculativeDecode ? max(emitted - 1, 0) : nil
                let speculativeRejected = acceleration.mode == .speculativeDecode && emitted > 0 ? 1 : nil
                continuation.yield(.summary(
                    TextGenerationSummary(
                        promptTokens: max(1, context.promptTokens),
                        completionTokens: emitted,
                        tokensPerSecond: emitted > 0 ? Double(emitted) * 8.0 : nil,
                        speculativeAcceptedTokens: speculativeAccepted,
                        speculativeRejectedTokens: speculativeRejected,
                        activeKVProbe: activeKVProbeSummary
                    )
                ))
                continuation.finish()
            }
        }
    }

    func loadedSpecs() async -> [Melix_Worker_V1_ModelSpec] {
        await storage.snapshot()
    }

    func unloadedModelCount() async -> Int {
        await unloadedStorage.count()
    }

    func lastDecodedDraftModelID() async -> String? {
        await decodeStorage.snapshotLastDraftModelID()
    }
}

@available(macOS 15.0, *)
private struct DefaultUnloadBackend: TextRuntimeBackend {
    let runtimeName: String = "default-unload-backend"

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        LoadedTextModel(storage: ["model_id": spec.modelID], residentBytesHint: 1)
    }
}

@available(macOS 15.0, *)
private actor FakeRuntimeBackendUnloadStorage {
    private var value: Int = 0

    func increment() {
        value += 1
    }

    func count() -> Int {
        value
    }
}

@available(macOS 15.0, *)
private final class ResidentMemoryProbe: @unchecked Sendable {
    private let lock = NSLock()
    private var samples: [UInt64]

    init(samples: [UInt64]) {
        self.samples = samples
    }

    func next() -> UInt64 {
        lock.lock()
        defer { lock.unlock() }
        if samples.isEmpty {
            return 0
        }
        return samples.removeFirst()
    }
}

@available(macOS 15.0, *)
private final class RecordingRPCWriter<Element: Sendable>: RPCWriterProtocol, @unchecked Sendable {
    private let storage = RecordingRPCWriterStorage<Element>()

    func write(_ element: Element) async throws {
        await storage.append(element)
    }

    func write(contentsOf elements: some Sequence<Element>) async throws {
        let snapshot = Array(elements)
        await storage.append(contentsOf: snapshot)
    }

    func snapshot() async -> [Element] {
        await storage.snapshot()
    }
}

@available(macOS 15.0, *)
private func matches(
    _ payload: Melix_Worker_V1_ExecuteEvent.OneOf_Payload?,
    _ matcher: ExecuteEventPayloadMatcher
) -> Bool {
    guard let payload else {
        return false
    }

    switch (payload, matcher) {
    case (.prefillStarted, .prefillStarted),
         (.decodeStarted, .decodeStarted),
         (.accelerationApplied, .accelerationApplied),
         (.tokenDelta, .tokenDelta),
         (.usageDelta, .usageDelta),
         (.completed, .completed),
         (.error, .error):
        return true
    default:
        return false
    }
}

@available(macOS 15.0, *)
private func payloadKinds(
    _ events: [Melix_Worker_V1_ExecuteEvent]
) -> [ExecuteEventPayloadMatcher] {
    events.compactMap { event in
        guard let payload = event.payload else {
            return nil
        }
        switch payload {
        case .prefillStarted:
            return .prefillStarted
        case .decodeStarted:
            return .decodeStarted
        case .accelerationApplied:
            return .accelerationApplied
        case .tokenDelta:
            return .tokenDelta
        case .usageDelta:
            return .usageDelta
        case .completed:
            return .completed
        case .error:
            return .error
        default:
            return nil
        }
    }
}

@available(macOS 15.0, *)
private enum ExecuteEventPayloadMatcher {
    case prefillStarted
    case decodeStarted
    case accelerationApplied
    case tokenDelta
    case usageDelta
    case completed
    case error
}

@available(macOS 15.0, *)
private func makeUserMessage(
    _ text: String,
    extraText: String? = nil
) -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = "user"

    var parts: [Melix_Worker_V1_MessagePart] = []
    var firstPart = Melix_Worker_V1_MessagePart()
    firstPart.text = text
    parts.append(firstPart)

    if let extraText {
        var extraPart = Melix_Worker_V1_MessagePart()
        extraPart.text = extraText
        parts.append(extraPart)
    }

    message.parts = parts
    return message
}

@available(macOS 15.0, *)
private func makeMediaRichMessage() -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = "user"

    var imageURI = Melix_Worker_V1_MessagePart()
    imageURI.imageUri = "file:///tmp/image.png"

    var imageBytes = Melix_Worker_V1_MessagePart()
    imageBytes.imageBytes = Data([0x01, 0x02, 0x03])

    var audioURI = Melix_Worker_V1_MessagePart()
    audioURI.audioUri = "file:///tmp/audio.wav"

    var audioBytes = Melix_Worker_V1_MessagePart()
    audioBytes.audioBytes = Data([0x04, 0x05, 0x06])

    var videoURI = Melix_Worker_V1_MessagePart()
    videoURI.videoUri = "file:///tmp/video.mp4"

    var videoBytes = Melix_Worker_V1_MessagePart()
    videoBytes.videoBytes = Data([0x07, 0x08, 0x09])

    let empty = Melix_Worker_V1_MessagePart()
    message.parts = [imageURI, imageBytes, audioURI, audioBytes, videoURI, videoBytes, empty]
    return message
}

@available(macOS 15.0, *)
private func makeVisionBearingMessage(_ text: String) -> Melix_Worker_V1_ChatMessage {
    var message = makeUserMessage(text)
    var imageURI = Melix_Worker_V1_MessagePart()
    imageURI.imageUri = "file:///tmp/image.png"
    message.parts.append(imageURI)
    return message
}

@available(macOS 15.0, *)
private func makeVisionMessage(
    prompt: String = "",
    imageBytes: Data? = nil,
    imageFilename: String = "image.png",
    videoBytes: Data? = nil,
    videoURI: String? = nil,
    videoFilename: String = "video.mp4",
    frameBudget: UInt32 = 0,
    startMs: UInt32 = 0,
    endMs: UInt32 = 0
) -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = "user"
    var parts: [Melix_Worker_V1_MessagePart] = []

    if !prompt.isEmpty {
        var promptPart = Melix_Worker_V1_MessagePart()
        promptPart.text = prompt
        parts.append(promptPart)
    }

    if let imageBytes {
        var imagePart = Melix_Worker_V1_MessagePart()
        imagePart.imageBytes = imageBytes
        imagePart.media.mediaType = .image
        imagePart.media.sourceKind = .mediaSourceInlineBytes
        imagePart.media.mimeType = "image/png"
        imagePart.media.filename = imageFilename
        imagePart.media.byteLength = UInt64(imageBytes.count)
        parts.append(imagePart)
    }

    if let videoBytes {
        var videoPart = Melix_Worker_V1_MessagePart()
        videoPart.videoBytes = videoBytes
        videoPart.media.mediaType = .video
        videoPart.media.sourceKind = .mediaSourceInlineBytes
        videoPart.media.mimeType = "video/mp4"
        videoPart.media.format = "mp4"
        videoPart.media.filename = videoFilename
        videoPart.media.frameBudget = frameBudget
        videoPart.media.startMs = startMs
        videoPart.media.endMs = endMs
        videoPart.media.byteLength = UInt64(videoBytes.count)
        parts.append(videoPart)
    }

    if let videoURI {
        var videoPart = Melix_Worker_V1_MessagePart()
        videoPart.videoUri = videoURI
        videoPart.media.mediaType = .video
        videoPart.media.sourceKind = .mediaSourceUri
        videoPart.media.mimeType = "video/mp4"
        videoPart.media.format = "mp4"
        videoPart.media.filename = videoFilename
        videoPart.media.frameBudget = frameBudget
        videoPart.media.startMs = startMs
        videoPart.media.endMs = endMs
        parts.append(videoPart)
    }

    message.parts = parts
    return message
}

@available(macOS 15.0, *)
private func makeSystemMessage(_ text: String) -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = "system"

    var part = Melix_Worker_V1_MessagePart()
    part.text = text
    message.parts = [part]
    return message
}

@available(macOS 15.0, *)
private func makeRoleMessage(_ role: String, text: String) -> Melix_Worker_V1_ChatMessage {
    var message = Melix_Worker_V1_ChatMessage()
    message.role = role

    var part = Melix_Worker_V1_MessagePart()
    part.text = text
    message.parts = [part]
    return message
}

@available(macOS 15.0, *)
private func makeCacheScope(scopeID: String, modelID: String) -> Melix_Worker_V1_CacheScope {
    var scope = Melix_Worker_V1_CacheScope()
    scope.scopeID = scopeID
    scope.modelID = modelID
    return scope
}

@available(macOS 15.0, *)
private func makeCacheKey(
    scopeID: String,
    prefixSeed: String,
    fingerprintSeed: String
) -> Melix_Worker_V1_CacheKey {
    var key = Melix_Worker_V1_CacheKey()
    key.scopeID = scopeID
    key.prefixHash = Data(prefixSeed.utf8)
    key.fingerprintHash = Data(fingerprintSeed.utf8)
    return key
}

@available(macOS 15.0, *)
private func makePrefixRef(
    prefixID: String,
    scope: Melix_Worker_V1_CacheScope,
    cacheKey: Melix_Worker_V1_CacheKey,
    pinned: Bool = false
) -> Melix_Worker_V1_PrefixRef {
    var prefix = Melix_Worker_V1_PrefixRef()
    prefix.prefixID = prefixID
    prefix.scope = scope
    prefix.cacheKey = cacheKey
    prefix.pinned = pinned
    prefix.tokenLength = 4
    return prefix
}

@available(macOS 15.0, *)
private func makeBlockTable(
    scopeID: String,
    cacheKey: Melix_Worker_V1_CacheKey,
    blockIDs: [String],
    bytes: [UInt64]
) -> Melix_Worker_V1_BlockTable {
    var table = Melix_Worker_V1_BlockTable()
    table.scopeID = scopeID
    table.cacheKey = cacheKey
    table.blocks = zip(blockIDs, bytes).enumerated().map { index, pair in
        var block = Melix_Worker_V1_BlockRef()
        block.blockID = pair.0
        block.tokenStart = Int32(index * 16)
        block.tokenEnd = Int32((index + 1) * 16)
        block.bytes = pair.1
        return block
    }
    return table
}

@available(macOS 15.0, *)
private func makeSnapshotRef(snapshotID: String) -> Melix_Worker_V1_SnapshotRef {
    var snapshot = Melix_Worker_V1_SnapshotRef()
    snapshot.snapshotID = snapshotID
    snapshot.requestID = "request-\(snapshotID)"
    snapshot.sessionID = "session-\(snapshotID)"
    snapshot.branchID = "branch-\(snapshotID)"
    snapshot.tokenBoundary = 4
    return snapshot
}

@available(macOS 15.0, *)
private func makeModelSpec(modelID: String) -> Melix_Worker_V1_ModelSpec {
    var model = Melix_Worker_V1_ModelSpec()
    model.modelID = modelID
    model.modelPath = modelID
    model.requestRoutes = [makeTextRequestRoute()]
    return model
}

@available(macOS 15.0, *)
private func makeTextRequestRoute() -> Melix_Worker_V1_RequestRouteDeclaration {
    var route = Melix_Worker_V1_RequestRouteDeclaration()
    route.task = .generateText
    route.supportedModalities = [.text]
    route.workerFamily = .text
    route.modelFamilyTarget = "text.test"
    route.residencyPolicy = .singleResidency
    return route
}

@available(macOS 15.0, *)
private func makeAccelerationPolicy(
    mode: Melix_Worker_V1_AccelerationMode,
    activeKvQuantProfile: String = ""
) -> Melix_Worker_V1_AccelerationPolicy {
    var policy = Melix_Worker_V1_AccelerationPolicy()
    policy.mode = mode
    policy.activeKvQuantProfile = activeKvQuantProfile
    return policy
}

@available(macOS 15.0, *)
private func collectTextGenerationEvents(
    from stream: AsyncThrowingStream<TextGenerationEvent, Error>
) async throws -> [TextGenerationEvent] {
    var events: [TextGenerationEvent] = []
    for try await event in stream {
        events.append(event)
    }
    return events
}

@available(macOS 15.0, *)
private func collectTextBatchGenerationEvents(
    from stream: AsyncThrowingStream<TextBatchGenerationEvent, Error>
) async throws -> [TextBatchGenerationEvent] {
    var events: [TextBatchGenerationEvent] = []
    for try await event in stream {
        events.append(event)
    }
    return events
}

@available(macOS 15.0, *)
private func collectThreePeerBatchDecodeEvents(
    backend: AutoSwiftMLXBackend,
    recorder: BatchCacheIdentityRecorder,
    sampling: Melix_Worker_V1_SamplingConfig,
    abortingPeer: AbortAfterPoll
) async throws -> [TextBatchGenerationEvent] {
    try await withTemporaryDefaultMetallib {
        try await Device.withDefaultDevice(.cpu) {
            let model = LoadedTextModel(
                storage: makeBatchCacheIdentityModelContainer(recorder: recorder)
            )
            var prefills: [RuntimePrefillResult] = []
            for index in 0 ..< 3 {
                let prefill = try await backend.prefill(
                    model: model,
                    messages: [makeSystemMessage("system"), makeUserMessage("three-way shrink \(index)")],
                    prefillStepSize: 32,
                    resumeHint: "three-way-shrink-\(index)",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: { false }
                )
                prefills.append(prefill)
            }

            var requests: [TextRuntimeDecodeRequest] = []
            for (index, prefill) in prefills.enumerated() {
                let shouldAbort: @Sendable () -> Bool
                if index == 0 {
                    shouldAbort = { abortingPeer.shouldAbort() }
                } else {
                    shouldAbort = { false }
                }
                requests.append(TextRuntimeDecodeRequest(
                    model: model,
                    draftModel: nil,
                    context: prefill.context,
                    sampling: sampling,
                    maxOutputTokens: 2,
                    decodeStepSize: 1,
                    prefillToken: "",
                    acceleration: Melix_Worker_V1_AccelerationPolicy(),
                    shouldAbort: shouldAbort
                ))
            }

            let stream = try await backend.decodeBatchEvents(requests: requests)
            return try await collectTextBatchGenerationEvents(from: stream)
        }
    }
}

@available(macOS 15.0, *)
private func renderedPromptTokens(from events: [TextGenerationEvent]) -> Int? {
    for event in events {
        if case .prefillStarted(let promptTokens) = event {
            return promptTokens
        }
    }
    return nil
}

@available(macOS 15.0, *)
private func renderedBatchRequestSummaries(
    from events: [TextBatchGenerationEvent]
) -> [Int: TextGenerationSummary] {
    var summaries: [Int: TextGenerationSummary] = [:]
    for event in events {
        if case .summary(let requestIndex, let summary) = event {
            summaries[requestIndex] = summary
        }
    }
    return summaries
}

@available(macOS 15.0, *)
private func renderedTokenChunks(from events: [TextGenerationEvent]) -> [String] {
    events.compactMap { event in
        guard case .token(let text) = event else {
            return nil
        }
        return text
    }
}

@available(macOS 15.0, *)
private func renderedSummary(from events: [TextGenerationEvent]) -> TextGenerationSummary? {
    for event in events {
        if case .summary(let summary) = event {
            return summary
        }
    }
    return nil
}

@available(macOS 15.0, *)
private func repeatingTokenPrompt(count: Int) -> String {
    Array(repeating: "token", count: count).joined(separator: " ")
}

@available(macOS 15.0, *)
private func XCTAssertThrowsErrorAsync<T>(
    _ expression: @autoclosure () async throws -> T,
    _ message: @autoclosure () -> String = "",
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    do {
        _ = try await expression()
        XCTFail(message().isEmpty ? "Expected async expression to throw an error." : message(), file: file, line: line)
    } catch {
    }
}

#if canImport(MLX) && canImport(MLXLMCommon) && canImport(MLXLLM) && canImport(Tokenizers)
@available(macOS 15.0, *)
private func makeLiveSwiftMLXModelContainer(promptTokens: [Int]) -> ModelContainer {
    let vocabularySize = 32
    let configuration = LlamaConfiguration(
        hiddenSize: 64,
        hiddenLayers: 4,
        intermediateSize: 128,
        attentionHeads: 8,
        rmsNormEps: 0.00001,
        vocabularySize: vocabularySize,
        kvHeads: 4
    )
    let model = LlamaModel(configuration)
    eval(model)

    let context = ModelContext(
        configuration: ModelConfiguration(id: "melix-tests/live-swift-mlx"),
        model: model,
        processor: DeterministicUserInputProcessor(promptTokens: promptTokens),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private func makeQuantizableLiveSwiftMLXModelContainer(promptTokens: [Int]) -> ModelContainer {
    let vocabularySize = 32
    let configuration = LlamaConfiguration(
        hiddenSize: 512,
        hiddenLayers: 1,
        intermediateSize: 1024,
        attentionHeads: 8,
        rmsNormEps: 0.00001,
        vocabularySize: vocabularySize,
        kvHeads: 4
    )
    let model = LlamaModel(configuration)
    eval(model)

    let context = ModelContext(
        configuration: ModelConfiguration(id: "melix-tests/live-swift-mlx-quant"),
        model: model,
        processor: DeterministicUserInputProcessor(promptTokens: promptTokens),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private final class CountingLanguageModelCallCounter: @unchecked Sendable {
    var stepCallCount = 0
}

@available(macOS 15.0, *)
private final class CountingPreparedLogitsLanguageModel: Module, LanguageModel {
    let counter: CountingLanguageModelCallCounter
    let vocabularySize = 32

    init(counter: CountingLanguageModelCallCounter) {
        self.counter = counter
        super.init()
    }

    func prepare(_ input: LMInput, cache: [KVCache], windowSize: Int?) throws -> PrepareResult {
        .logits(LMOutput(logits: logitsForToken(2)))
    }

    func callAsFunction(_ input: LMInput.Text, cache: [KVCache]?, state: LMOutput.State?) -> LMOutput {
        counter.stepCallCount += 1
        return LMOutput(logits: logitsForToken(3))
    }

    func newCache(parameters: GenerateParameters?) -> [KVCache] {
        [KVCacheSimple()]
    }

    private func logitsForToken(_ tokenID: Int) -> MLXArray {
        let values = (0 ..< vocabularySize).map { index in
            index == tokenID ? Float(10) : Float(-10)
        }
        return MLXArray(values, [1, 1, vocabularySize])
    }
}

@available(macOS 15.0, *)
private func makeCountingPreparedLogitsModelContainer(counter: CountingLanguageModelCallCounter) -> ModelContainer {
    let vocabularySize = 32
    let context = ModelContext(
        configuration: ModelConfiguration(id: "melix-tests/counting-prepared-logits"),
        model: CountingPreparedLogitsLanguageModel(counter: counter),
        processor: DeterministicUserInputProcessor(promptTokens: [1, 2, 3]),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private final class BatchCacheIdentityRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var retainedCaches: [AnyObject] = []
    private var recordedCacheIdentifiers: [ObjectIdentifier] = []
    private var recordedBatchSizes: [Int] = []
    private var recordedSequenceLengths: [Int] = []
    private var recordedCacheOffsets: [Int] = []
    private var recordedCacheMaxSizes: [Int] = []

    var cacheIdentifiers: [ObjectIdentifier] {
        lock.lock()
        defer { lock.unlock() }
        return recordedCacheIdentifiers
    }

    var batchSizes: [Int] {
        lock.lock()
        defer { lock.unlock() }
        return recordedBatchSizes
    }

    var sequenceLengths: [Int] {
        lock.lock()
        defer { lock.unlock() }
        return recordedSequenceLengths
    }

    var cacheOffsets: [Int] {
        lock.lock()
        defer { lock.unlock() }
        return recordedCacheOffsets
    }

    var cacheMaxSizes: [Int] {
        lock.lock()
        defer { lock.unlock() }
        return recordedCacheMaxSizes
    }

    func record(cache: (any KVCache)?, batchSize: Int, sequenceLength: Int) {
        guard let cacheObject = cache as AnyObject? else {
            return
        }
        lock.lock()
        retainedCaches.append(cacheObject)
        recordedCacheIdentifiers.append(ObjectIdentifier(cacheObject))
        recordedBatchSizes.append(batchSize)
        recordedSequenceLengths.append(sequenceLength)
        recordedCacheOffsets.append(cache?.offset ?? -1)
        if let maxSize = cache?.maxSize {
            recordedCacheMaxSizes.append(maxSize)
        }
        lock.unlock()
    }
}

@available(macOS 15.0, *)
private enum TestBatchCacheKind {
    case simple
    case rotating(maxSize: Int)
}

@available(macOS 15.0, *)
private final class BatchCacheIdentityLanguageModel: Module, LanguageModel {
    let recorder: BatchCacheIdentityRecorder
    let cacheKind: TestBatchCacheKind
    let vocabularySize = 32

    init(recorder: BatchCacheIdentityRecorder, cacheKind: TestBatchCacheKind = .simple) {
        self.recorder = recorder
        self.cacheKind = cacheKind
        super.init()
    }

    func prepare(_ input: LMInput, cache: [KVCache], windowSize: Int?) throws -> PrepareResult {
        if let simpleCache = cache.first {
            let sequenceLength = max(1, input.text.tokens.size)
            let keys = MLXArray.zeros([1, 1, sequenceLength, 4])
            let values = MLXArray.zeros([1, 1, sequenceLength, 4])
            _ = simpleCache.update(keys: keys, values: values)
        }
        return .tokens(LMInput.Text(tokens: MLXArray([2])))
    }

    func callAsFunction(_ inputs: MLXArray, cache: [KVCache]?) -> MLXArray {
        let batchSize = inputs.dim(0)
        let sequenceLength = inputs.dim(1)
        recorder.record(cache: cache?.first, batchSize: batchSize, sequenceLength: sequenceLength)
        if let cache = cache?.first {
            let keys = MLXArray.zeros([batchSize, 1, sequenceLength, 4])
            let values = MLXArray.zeros([batchSize, 1, sequenceLength, 4])
            _ = cache.update(keys: keys, values: values)
        }
        return logitsForToken(3, batchSize: batchSize)
    }

    func callAsFunction(_ input: LMInput.Text, cache: [KVCache]?, state: LMOutput.State?) -> LMOutput {
        let batchSize = input.tokens.dim(0)
        let sequenceLength = input.tokens.dim(1)
        recorder.record(cache: cache?.first, batchSize: batchSize, sequenceLength: sequenceLength)
        if let cache = cache?.first {
            let keys = MLXArray.zeros([batchSize, 1, sequenceLength, 4])
            let values = MLXArray.zeros([batchSize, 1, sequenceLength, 4])
            _ = cache.update(keys: keys, values: values)
        }
        return LMOutput(logits: logitsForToken(3, batchSize: batchSize))
    }

    func newCache(parameters: GenerateParameters?) -> [KVCache] {
        switch cacheKind {
        case .simple:
            [KVCacheSimple()]
        case .rotating(let maxSize):
            [RotatingKVCache(maxSize: maxSize)]
        }
    }

    private func logitsForToken(_ tokenID: Int, batchSize: Int) -> MLXArray {
        let row = (0 ..< vocabularySize).map { index in
            index == tokenID ? Float(10) : Float(-10)
        }
        return MLXArray(Array(repeating: row, count: batchSize).flatMap { $0 }, [batchSize, 1, vocabularySize])
    }
}

@available(macOS 15.0, *)
private func makeBatchCacheIdentityModelContainer(
    recorder: BatchCacheIdentityRecorder,
    cacheKind: TestBatchCacheKind = .simple
) -> ModelContainer {
    let vocabularySize = 32
    let context = ModelContext(
        configuration: ModelConfiguration(id: "melix-tests/batch-cache-identity"),
        model: BatchCacheIdentityLanguageModel(recorder: recorder, cacheKind: cacheKind),
        processor: DeterministicUserInputProcessor(promptTokens: [1, 2, 3, 4, 5]),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private final class ConstantTokenLanguageModel: Module, LanguageModel {
    let vocabularySize = 32
    let tokenID: Int

    init(tokenID: Int = 3) {
        self.tokenID = tokenID
        super.init()
    }

    func prepare(_ input: LMInput, cache: [KVCache], windowSize: Int?) throws -> PrepareResult {
        .tokens(LMInput.Text(tokens: MLXArray([2])))
    }

    func callAsFunction(_ inputs: MLXArray, cache: [KVCache]?) -> MLXArray {
        logits(batchSize: inputs.dim(0), length: inputs.dim(1))
    }

    func callAsFunction(_ input: LMInput.Text, cache: [KVCache]?, state: LMOutput.State?) -> LMOutput {
        LMOutput(logits: logits(batchSize: input.tokens.dim(0), length: input.tokens.dim(1)))
    }

    func newCache(parameters: GenerateParameters?) -> [KVCache] {
        [KVCacheSimple()]
    }

    private func logits(batchSize: Int, length: Int) -> MLXArray {
        let row = (0 ..< vocabularySize).map { index in
            index == tokenID ? Float(10) : Float(-10)
        }
        return MLXArray(Array(repeating: row, count: batchSize * length).flatMap { $0 }, [batchSize, length, vocabularySize])
    }
}

@available(macOS 15.0, *)
private func makeConstantTokenModelContainer(
    tokenID: Int = 3,
    extraEOSTokens: Set<String> = []
) -> ModelContainer {
    let vocabularySize = 32
    let context = ModelContext(
        configuration: ModelConfiguration(
            id: "melix-tests/constant-token",
            extraEOSTokens: extraEOSTokens
        ),
        model: ConstantTokenLanguageModel(tokenID: tokenID),
        processor: DeterministicUserInputProcessor(promptTokens: [1, 2, 3]),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private func makeSimpleKVCache(sequenceLength: Int) -> [KVCache] {
    let cache = KVCacheSimple()
    let keys = MLXArray.zeros([1, 1, sequenceLength, 4])
    let values = MLXArray.zeros([1, 1, sequenceLength, 4])
    _ = cache.update(keys: keys, values: values)
    return [cache]
}

@available(macOS 15.0, *)
private func makePreparedDecodeContext(
    prepared: PrepareResult,
    cache: [KVCache],
    activeKVQuantizationRatio: Int = 0
) -> TextPrefillContext {
    let input: LMInput
    switch prepared {
    case .tokens(let tokens):
        input = LMInput(tokens: tokens.tokens)
    case .logits:
        input = LMInput(tokens: MLXArray([1]))
    }

    let state = PreparedDecodeState(
        input: input,
        prepared: prepared,
        cache: cache,
        promptPrefillTime: 0,
        prefillQuantizeMicros: 0,
        activeKVQuantizationRatio: activeKVQuantizationRatio
    )
    return TextPrefillContext(storage: state, promptTokens: input.text.tokens.size)
}

@available(macOS 15.0, *)
private final class AbortAfterPoll: @unchecked Sendable {
    private let lock = NSLock()
    private let falsePollsBeforeAbort: Int
    private var pollCount = 0

    init(falsePollsBeforeAbort: Int) {
        self.falsePollsBeforeAbort = falsePollsBeforeAbort
    }

    func shouldAbort() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        pollCount += 1
        return pollCount > falsePollsBeforeAbort
    }
}

@available(macOS 15.0, *)
private final class DFlashTargetForwardRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var recordedInputLengths: [Int] = []

    var inputLengths: [Int] {
        lock.lock()
        defer { lock.unlock() }
        return recordedInputLengths
    }

    func record(inputLength: Int) {
        lock.lock()
        recordedInputLengths.append(inputLength)
        lock.unlock()
    }
}

@available(macOS 15.0, *)
private final class DFlashTestTargetLanguageModel: Module, LanguageModel, DFlashTargetModel {
    let vocabularySize = 32
    let hiddenSize = 4
    let nextTokenID = 7
    let promptTokens: [Int]
    let recorder: DFlashTargetForwardRecorder?

    init(promptTokens: [Int], recorder: DFlashTargetForwardRecorder? = nil) {
        self.promptTokens = promptTokens
        self.recorder = recorder
        super.init()
    }

    var dflashHiddenSize: Int {
        hiddenSize
    }

    var dflashLayerCount: Int {
        1
    }

    func prepare(_ input: LMInput, cache: [KVCache], windowSize: Int?) throws -> PrepareResult {
        .logits(LMOutput(logits: logits(batchSize: 1, length: 1)))
    }

    func callAsFunction(_ input: LMInput.Text, cache: [KVCache]?, state: LMOutput.State?) -> LMOutput {
        LMOutput(logits: logits(batchSize: input.tokens.dim(0), length: input.tokens.dim(1)))
    }

    func newCache(parameters: GenerateParameters?) -> [KVCache] {
        [KVCacheSimple()]
    }

    func dflashTokenEmbeddings(_ tokenIDs: MLXArray) throws -> MLXArray {
        MLXArray.zeros([tokenIDs.dim(0), tokenIDs.dim(1), hiddenSize])
    }

    func dflashLogits(fromHiddenStates hiddenStates: MLXArray) throws -> MLXArray {
        logits(batchSize: hiddenStates.dim(0), length: hiddenStates.dim(1))
    }

    func dflashForward(
        input: LMInput.Text,
        cache: [KVCache]?,
        targetLayerIDs: [Int]
    ) throws -> DFlashTargetForwardResult {
        recorder?.record(inputLength: input.tokens.dim(1))
        let hidden = MLXArray.zeros([input.tokens.dim(0), input.tokens.dim(1), hiddenSize])
        return DFlashTargetForwardResult(
            logits: logits(batchSize: input.tokens.dim(0), length: input.tokens.dim(1)),
            hidden: hidden
        )
    }

    private func logits(batchSize: Int, length: Int) -> MLXArray {
        let values = (0 ..< batchSize * length * vocabularySize).map { index in
            index % vocabularySize == nextTokenID ? Float(10) : Float(-10)
        }
        return MLXArray(values, [batchSize, length, vocabularySize])
    }
}

@available(macOS 15.0, *)
private func makeDFlashTestTargetModelContainer(
    promptTokens: [Int],
    recorder: DFlashTargetForwardRecorder? = nil
) -> ModelContainer {
    let vocabularySize = 32
    let context = ModelContext(
        configuration: ModelConfiguration(id: "melix-tests/dflash-target"),
        model: DFlashTestTargetLanguageModel(promptTokens: promptTokens, recorder: recorder),
        processor: DeterministicUserInputProcessor(promptTokens: promptTokens),
        tokenizer: DeterministicTokenizer(vocabularySize: vocabularySize)
    )
    return ModelContainer(context: context)
}

@available(macOS 15.0, *)
private func makeTestDFlashDraftRuntime() throws -> SwiftDFlashDraftRuntime {
    let configuration = DFlashDraftConfiguration(
        hiddenSize: 4,
        hiddenLayers: 1,
        intermediateSize: 8,
        attentionHeads: 1,
        kvHeads: 1,
        headDim: 4,
        vocabularySize: 32,
        blockSize: 2,
        numTargetLayers: 1,
        targetLayerIDs: [0],
        maskTokenID: 0
    )
    let model = try DFlashDraftModel(configuration)
    eval(model)
    return SwiftDFlashDraftRuntime(
        modelID: "melix-tests/dflash-draft",
        configuration: configuration,
        model: model
    )
}

@available(macOS 15.0, *)
private struct DeterministicUserInputProcessor: UserInputProcessor {
    let promptTokens: [Int]

    func prepare(input: UserInput) async throws -> LMInput {
        LMInput(tokens: MLXArray(promptTokens))
    }
}

@available(macOS 15.0, *)
private struct DeterministicTokenizer: Tokenizer {
    let vocabularySize: Int

    private var tokenLookup: [Int: String] {
        Dictionary(uniqueKeysWithValues: (0 ..< vocabularySize).map { ($0, "tok\($0)") })
    }

    func tokenize(text: String) -> [String] {
        text.split(separator: " ").map(String.init)
    }

    func encode(text: String) -> [Int] {
        encode(text: text, addSpecialTokens: true)
    }

    func encode(text: String, addSpecialTokens: Bool) -> [Int] {
        let tokens = tokenize(text: text)
        if tokens.isEmpty {
            return [1]
        }
        return tokens.enumerated().map { index, token in
            convertTokenToId(token) ?? max(1, (index % max(1, vocabularySize - 1)) + 1)
        }
    }

    func decode(tokens: [Int], skipSpecialTokens: Bool) -> String {
        tokens.compactMap { convertIdToToken($0) }.joined(separator: " ")
    }

    func convertTokenToId(_ token: String) -> Int? {
        if let explicit = Int(token.replacingOccurrences(of: "tok", with: "")) {
            return explicit % vocabularySize
        }
        return nil
    }

    func convertIdToToken(_ id: Int) -> String? {
        tokenLookup[id] ?? "tok\(id)"
    }

    var bosToken: String? { nil }
    var bosTokenId: Int? { nil }
    var eosToken: String? { nil }
    var eosTokenId: Int? { nil }
    var unknownToken: String? { nil }
    var unknownTokenId: Int? { nil }
    var hasChatTemplate: Bool { true }

    func applyChatTemplate(messages: [Tokenizers.Message]) throws -> [Int] {
        Array(1 ... max(1, messages.count + 1))
    }

    func applyChatTemplate(messages: [Tokenizers.Message], tools: [Tokenizers.ToolSpec]?) throws
        -> [Int]
    {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        tools: [Tokenizers.ToolSpec]?,
        additionalContext: [String: any Sendable]?
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        chatTemplate: Tokenizers.ChatTemplateArgument
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(messages: [Tokenizers.Message], chatTemplate: String) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        chatTemplate: Tokenizers.ChatTemplateArgument?,
        addGenerationPrompt: Bool,
        truncation: Bool,
        maxLength: Int?,
        tools: [Tokenizers.ToolSpec]?
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }

    func applyChatTemplate(
        messages: [Tokenizers.Message],
        chatTemplate: Tokenizers.ChatTemplateArgument?,
        addGenerationPrompt: Bool,
        truncation: Bool,
        maxLength: Int?,
        tools: [Tokenizers.ToolSpec]?,
        additionalContext: [String: any Sendable]?
    ) throws -> [Int] {
        try applyChatTemplate(messages: messages)
    }
}

private actor WorkerScaffoldAsyncGate {
    private var isEntered = false
    private var isOpen = false
    private var enteredContinuation: CheckedContinuation<Void, Never>?
    private var waitingContinuation: CheckedContinuation<Void, Never>?

    func waitUntilEntered() async {
        if isEntered {
            return
        }
        await withCheckedContinuation { continuation in
            enteredContinuation = continuation
        }
    }

    func enterAndWait() async {
        isEntered = true
        enteredContinuation?.resume()
        enteredContinuation = nil

        if isOpen {
            return
        }
        await withCheckedContinuation { continuation in
            waitingContinuation = continuation
        }
    }

    func open() {
        isOpen = true
        waitingContinuation?.resume()
        waitingContinuation = nil
    }
}

@available(macOS 15.0, *)
private func withTemporaryDefaultMetallib<T>(
    _ operation: () async throws -> T
) async throws -> T {
    let fileManager = FileManager.default
    guard let metallibURL = findLocalMLXMetallib() else {
        throw XCTSkip("No local mlx.metallib was found for the Swift MLX live-bridge test.")
    }

    let temporaryDirectory = fileManager.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fileManager.createDirectory(at: temporaryDirectory, withIntermediateDirectories: true)

    let defaultMetallibURL = temporaryDirectory.appendingPathComponent("default.metallib")
    try fileManager.createSymbolicLink(at: defaultMetallibURL, withDestinationURL: metallibURL)

    let originalDirectory = fileManager.currentDirectoryPath
    guard fileManager.changeCurrentDirectoryPath(temporaryDirectory.path) else {
        try? fileManager.removeItem(at: temporaryDirectory)
        throw RuntimeUnavailableError(message: "Failed to switch into the temporary MLX metallib directory.")
    }

    defer {
        _ = fileManager.changeCurrentDirectoryPath(originalDirectory)
        try? fileManager.removeItem(at: temporaryDirectory)
    }

    return try await operation()
}

@available(macOS 15.0, *)
private func withTemporaryCacheRoot<T>(
    _ operation: (URL) async throws -> T
) async throws -> T {
    let fileManager = FileManager.default
    let cacheRoot = fileManager.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fileManager.createDirectory(at: cacheRoot, withIntermediateDirectories: true)
    defer { try? fileManager.removeItem(at: cacheRoot) }
    return try await operation(cacheRoot)
}

@available(macOS 15.0, *)
private func findLocalMLXMetallib() -> URL? {
    let fileManager = FileManager.default
    let currentDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
    let candidateRoots = [
        currentDirectory,
        currentDirectory.deletingLastPathComponent(),
        currentDirectory.deletingLastPathComponent().deletingLastPathComponent(),
    ]

    let candidatePrefixes = [
        ".venv",
        ".uv-cache",
    ]

    for root in candidateRoots {
        for prefix in candidatePrefixes {
            let searchRoot = root.appendingPathComponent(prefix, isDirectory: true)
            guard fileManager.fileExists(atPath: searchRoot.path) else {
                continue
            }
            guard let enumerator = fileManager.enumerator(
                at: searchRoot,
                includingPropertiesForKeys: [.isRegularFileKey],
                options: [.skipsHiddenFiles]
            ) else {
                continue
            }

            for case let fileURL as URL in enumerator {
                guard fileURL.lastPathComponent == "mlx.metallib" else {
                    continue
                }
                return fileURL
            }
        }
    }

    return nil
}
#endif
