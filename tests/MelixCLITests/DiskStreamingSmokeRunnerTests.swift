import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Disk Streaming Smoke")
struct DiskStreamingSmokeRunnerTests {
    @Test("command parser accepts explicit smoke arguments")
    func commandParserAcceptsExplicitArguments() throws {
        let options = try DiskStreamingSmokeCommand.parseArguments([
            "--model-id", "melix-dev-text-alt",
            "--json",
        ])

        #expect(options == .init(modelID: "melix-dev-text-alt"))
    }

    @Test("command renderer prints machine-readable payload")
    func commandRendererPrintsMachineReadablePayload() async throws {
        let output = try await DiskStreamingSmokeCommand.renderReport(
            arguments: ["--json"],
            environment: [:],
            reportBuilder: { modelID, _ in
                DiskStreamingSmokeReport(
                    ok: true,
                    modelID: modelID,
                    baseline: .init(
                        reportPath: "/tmp/melix-baseline.md",
                        metrics: [
                            "bench.smoke.ttft_ms": 12.5,
                            "bench.smoke.tokens_per_second": 48.0,
                        ]
                    ),
                    streamingPreferDisk: .init(
                        requestedMode: "prefer_disk",
                        effectiveMode: "disabled",
                        errorCode: "disk_streaming_unsupported",
                        transitionReason: "operator_load_disk_streaming_unsupported",
                        cacheCompatibility: "limited",
                        cacheCompatibilityReason: "disk_streaming_unsupported"
                    ),
                    streamingRequireDisk: .init(
                        requestedMode: "require_disk",
                        effectiveMode: "disabled",
                        errorCode: "disk_streaming_unsupported",
                        transitionReason: "operator_load_disk_streaming_unsupported",
                        cacheCompatibility: "disabled",
                        cacheCompatibilityReason: "disk_streaming_unsupported"
                    ),
                    capability: .init(
                        runtimeSupportsDiskStreaming: false,
                        cacheCompatibility: "limited",
                        cacheCompatibilityReason: "disk_streaming_unsupported"
                    ),
                    futureMetrics: [
                        "ssd_restore_latency_ms": "unavailable_until_runtime_support",
                        "disk_streaming_throughput_delta": "unavailable_until_runtime_support",
                    ]
                )
            }
        )

        #expect(output.contains("\"ok\" : true"))
        #expect(output.contains("\"bench.smoke.ttft_ms\" : 12.5"))
        #expect(output.contains("\"errorCode\" : \"disk_streaming_unsupported\""))
        #expect(output.contains("\"runtimeSupportsDiskStreaming\" : false"))
    }

    @Test("command renderer uses clientBuilder when no report builder is provided")
    func commandRendererUsesClientBuilderPathWhenNoReportBuilderIsProvided() async throws {
        let client = DiskStreamingSmokeStubClient()

        let output = try await DiskStreamingSmokeCommand.renderReport(
            arguments: ["--json"],
            environment: [:],
            clientBuilder: { _ in client }
        )

        #expect(output.contains("\"modelID\" : \"melix-dev-text\""))
        #expect(output.contains("\"bench.smoke.ttft_ms\" : 14.2"))
    }

    @Test("runner records baseline and unsupported-path evidence and restores settings")
    func runnerRecordsBaselineUnsupportedEvidenceAndRestoresSettings() async throws {
        let client = DiskStreamingSmokeStubClient()
        let runner = DiskStreamingSmokeRunner(client: client)

        let report = try await runner.run(modelID: "melix-dev-text")

        #expect(report.ok)
        #expect(report.modelID == "melix-dev-text")
        #expect(report.baseline.metrics["bench.smoke.ttft_ms"] == 14.2)
        #expect(report.streamingPreferDisk.errorCode == "disk_streaming_unsupported")
        #expect(report.streamingPreferDisk.effectiveMode == "disabled")
        #expect(report.streamingPreferDisk.cacheCompatibility == "limited")
        #expect(report.streamingRequireDisk.errorCode == "disk_streaming_unsupported")
        #expect(report.capability.runtimeSupportsDiskStreaming == false)
        #expect(report.futureMetrics["ssd_restore_latency_ms"] == "unavailable_until_runtime_support")
        #expect(await client.updatedDiskStreamingModes == ["disabled", "prefer_disk", "require_disk", "disabled"])
    }

    @Test("runner restores the original mode when the baseline benchmark fails")
    func runnerRestoresTheOriginalModeWhenTheBaselineBenchmarkFails() async throws {
        let client = DiskStreamingSmokeStubClient(
            initialDiskStreamingMode: "prefer_disk",
            benchFailureCode: "bench_failed"
        )
        let runner = DiskStreamingSmokeRunner(client: client)

        await #expect(throws: ControlPlaneXPCClientError.requestFailed(code: "bench_failed", message: "baseline failed")) {
            _ = try await runner.run(modelID: "melix-dev-text")
        }

        #expect(await client.updatedDiskStreamingModes == ["disabled", "prefer_disk"])
    }

    @Test("runner throws when the requested model is absent from the snapshot")
    func runnerThrowsWhenTheRequestedModelIsAbsentFromTheSnapshot() async throws {
        let client = DiskStreamingSmokeStubClient(snapshotModelID: "other-model")
        let runner = DiskStreamingSmokeRunner(client: client)

        await #expect(throws: DiskStreamingSmokeRunnerError.missingModel("melix-dev-text")) {
            _ = try await runner.run(modelID: "melix-dev-text")
        }
    }

    @Test("runner falls back to derived cache compatibility when snapshot evidence is unavailable")
    func runnerFallsBackToDerivedCacheCompatibilityWhenSnapshotEvidenceIsUnavailable() async throws {
        let client = DiskStreamingSmokeStubClient(
            unsupportedModes: ["prefer_disk", "require_disk"],
            compatibilityByMode: [
                "prefer_disk": .cacheCompatibilityUnknown,
                "require_disk": .cacheCompatibilityUnknown,
            ],
            compatibilityReasonByMode: [
                "prefer_disk": "worker cache compatibility evidence is unavailable",
                "require_disk": "",
            ]
        )
        let runner = DiskStreamingSmokeRunner(client: client)

        let report = try await runner.run(modelID: "melix-dev-text")

        #expect(report.streamingPreferDisk.cacheCompatibility == "limited")
        #expect(report.streamingPreferDisk.cacheCompatibilityReason == "disk_streaming_unsupported")
        #expect(report.streamingRequireDisk.cacheCompatibility == "disabled")
        #expect(report.streamingRequireDisk.cacheCompatibilityReason == "disk_streaming_unsupported")
    }

    @Test("runner preserves observed compatibility when the runtime accepts the requested mode")
    func runnerPreservesObservedCompatibilityWhenTheRuntimeAcceptsTheRequestedMode() async throws {
        let client = DiskStreamingSmokeStubClient(
            unsupportedModes: [],
            compatibilityByMode: [
                "prefer_disk": .cacheCompatibilityCompatible,
                "require_disk": .cacheCompatibilityDisabled,
            ],
            compatibilityReasonByMode: [
                "prefer_disk": "resident_only",
                "require_disk": "operator_disabled",
            ],
            effectiveModeByMode: [
                "prefer_disk": .diskStreamingPreferDisk,
                "require_disk": .diskStreamingRequireDisk,
            ]
        )
        let runner = DiskStreamingSmokeRunner(client: client)

        let report = try await runner.run(modelID: "melix-dev-text")

        #expect(report.capability.runtimeSupportsDiskStreaming)
        #expect(report.streamingPreferDisk.effectiveMode == "prefer_disk")
        #expect(report.streamingPreferDisk.cacheCompatibility == "compatible")
        #expect(report.streamingPreferDisk.cacheCompatibilityReason == "resident_only")
        #expect(report.streamingRequireDisk.effectiveMode == "require_disk")
        #expect(report.streamingRequireDisk.cacheCompatibility == "disabled")
        #expect(report.streamingRequireDisk.cacheCompatibilityReason == "operator_disabled")
    }

    @Test("helper mappings cover compatibility and disk-streaming label branches")
    func helperMappingsCoverCompatibilityAndDiskStreamingLabelBranches() {
        #expect(resolvedUnsupportedCacheCompatibility(
            requestedMode: "prefer_disk",
            observedCompatibility: "unknown",
            errorCode: "disk_streaming_unsupported"
        ) == "limited")
        #expect(resolvedUnsupportedCacheCompatibility(
            requestedMode: "require_disk",
            observedCompatibility: "unknown",
            errorCode: "disk_streaming_unsupported"
        ) == "disabled")
        #expect(resolvedUnsupportedCacheCompatibility(
            requestedMode: "prefer_disk",
            observedCompatibility: "compatible",
            errorCode: ""
        ) == "compatible")
        #expect(resolvedUnsupportedCacheCompatibilityReason(
            observedReason: "",
            errorCode: "disk_streaming_unsupported"
        ) == "disk_streaming_unsupported")
        #expect(resolvedUnsupportedCacheCompatibilityReason(
            observedReason: "resident_only",
            errorCode: ""
        ) == "resident_only")
        #expect(diskStreamingModeLabel(.diskStreamingPreferDisk) == "prefer_disk")
        #expect(diskStreamingModeLabel(.diskStreamingRequireDisk) == "require_disk")
        #expect(diskStreamingModeLabel(.diskStreamingDisabled) == "disabled")
        #expect(cacheCompatibilityLabel(.cacheCompatibilityCompatible) == "compatible")
        #expect(cacheCompatibilityLabel(.cacheCompatibilityLimited) == "limited")
        #expect(cacheCompatibilityLabel(.cacheCompatibilityDisabled) == "disabled")
        #expect(cacheCompatibilityLabel(.cacheCompatibilityUnknown) == "unknown")
    }

    @Test("command parser rejects missing values and unexpected arguments")
    func commandParserRejectsInvalidArguments() throws {
        #expect(throws: MelixCLIError.missingValue("--model-id")) {
            _ = try DiskStreamingSmokeCommand.parseArguments(["--model-id"])
        }
        #expect(throws: MelixCLIError.usage("""
            Usage:
              melix-disk-streaming-smoke [--model-id MODEL] [--json]
            """)) {
            _ = try DiskStreamingSmokeCommand.parseArguments(["--unexpected"])
        }
    }
}

private actor DiskStreamingSmokeStubClient: ControlPlaneXPCClient {
    private var diskStreamingMode = "disabled"
    private var updatedDiskStreamingModesStorage: [String] = []
    private let snapshotModelID: String
    private let benchFailureCode: String?
    private let unsupportedModes: Set<String>
    private let compatibilityByMode: [String: Melix_Controlplane_V1_CacheCompatibilityState]
    private let compatibilityReasonByMode: [String: String]
    private let effectiveModeByMode: [String: Melix_Controlplane_V1_DiskStreamingMode]

    init(
        initialDiskStreamingMode: String = "disabled",
        snapshotModelID: String = "melix-dev-text",
        benchFailureCode: String? = nil,
        unsupportedModes: Set<String> = ["prefer_disk", "require_disk"],
        compatibilityByMode: [String: Melix_Controlplane_V1_CacheCompatibilityState] = [:],
        compatibilityReasonByMode: [String: String] = [:],
        effectiveModeByMode: [String: Melix_Controlplane_V1_DiskStreamingMode] = [:]
    ) {
        diskStreamingMode = initialDiskStreamingMode
        self.snapshotModelID = snapshotModelID
        self.benchFailureCode = benchFailureCode
        self.unsupportedModes = unsupportedModes
        self.compatibilityByMode = compatibilityByMode
        self.compatibilityReasonByMode = compatibilityReasonByMode
        self.effectiveModeByMode = effectiveModeByMode
    }

    var updatedDiskStreamingModes: [String] {
        updatedDiskStreamingModesStorage
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse { .init() }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return AsyncStream { continuation in
            continuation.finish()
        }
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        var cachePolicy = Melix_Controlplane_V1_CachePolicySummary()
        cachePolicy.requestedMode = diskStreamingMode == "disabled" ? .tiered : .hybrid
        cachePolicy.effectiveMode = .tiered
        cachePolicy.compatibility = compatibilityByMode[diskStreamingMode]
            ?? (diskStreamingMode == "disabled" ? .cacheCompatibilityCompatible : .cacheCompatibilityLimited)
        cachePolicy.compatibilityReason = compatibilityReasonByMode[diskStreamingMode]
            ?? (diskStreamingMode == "disabled" ? "resident_only" : "disk_streaming_unsupported")

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = snapshotModelID
        model.kind = "text"
        model.settings.diskStreamingMode = diskStreamingMode == "require_disk" ? .diskStreamingRequireDisk : diskStreamingMode == "prefer_disk" ? .diskStreamingPreferDisk : .diskStreamingDisabled
        model.residency.effectiveDiskStreamingMode = effectiveModeByMode[diskStreamingMode] ?? .diskStreamingDisabled
        model.cachePolicy = cachePolicy

        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.models = [model]
        return snapshot
    }

    func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        return try await serverSnapshot()
    }

    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        return try await serverSnapshot()
    }

    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        return try await serverSnapshot()
    }

    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        return try await serverSnapshot()
    }

    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        return try await serverSnapshot()
    }

    func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        _ = autoSleepEnabled
        _ = lightSleepAfterSeconds
        _ = deepSleepAfterSeconds
        return try await serverSnapshot()
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        if unsupportedModes.contains(diskStreamingMode) {
            throw ControlPlaneXPCClientError.requestFailed(
                code: "disk_streaming_unsupported",
                message: "The runtime does not support disk-backed execution."
            )
        }
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID
        return model
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID
        return model
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        if let mode = values["disk_streaming_mode"] {
            diskStreamingMode = mode
            updatedDiskStreamingModesStorage.append(mode)
        }
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        return model
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        return Melix_Controlplane_V1_ModelInfo()
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = quantProfileID
        _ = weightQuant
        _ = kvQuant
        _ = ext
        return Melix_Controlplane_V1_ModelOperationResult()
    }

    func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult {
        #expect(request.modelID == "melix-dev-text")
        if let benchFailureCode {
            throw ControlPlaneXPCClientError.requestFailed(code: benchFailureCode, message: "baseline failed")
        }
        return ControlPlaneBenchResult(
            reportPath: "/tmp/melix-baseline.md",
            reportMarkdown: "# Baseline",
            metrics: [
                "bench.smoke.ttft_ms": 14.2,
                "bench.smoke.tokens_per_second": 42.4,
            ]
        )
    }

    func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(code: "unimplemented", message: "matrix unsupported")
    }

    func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(code: "unimplemented", message: "eval unsupported")
    }

    func exportResults(outputDir: String) async throws -> ControlPlaneExportResult {
        _ = outputDir
        throw ControlPlaneXPCClientError.requestFailed(code: "unimplemented", message: "export unsupported")
    }

    func cancelRequest(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func applyServerSessionGatewayAccess(
        serverSessionID: String,
        primaryKey: String,
        keyID: String,
        label: String,
        tokenHint: String
    ) async throws {
        _ = serverSessionID
        _ = primaryKey
        _ = keyID
        _ = label
        _ = tokenHint
    }

    func clearServerSessionGatewayAccess(serverSessionID: String) async throws {
        _ = serverSessionID
    }
}
